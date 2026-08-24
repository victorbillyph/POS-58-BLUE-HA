"""ESC/POS communication with MPT-II style thermal printers (BLE and serial)."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass

from bleak import BleakClient, BleakError

try:  # running inside Home Assistant
    from homeassistant.exceptions import HomeAssistantError
except ImportError:  # standalone CLI usage without Home Assistant
    HomeAssistantError = Exception  # type: ignore[assignment,misc]

try:
    from homeassistant.components import bluetooth as _ha_bluetooth
except ImportError:  # pragma: no cover - standalone usage
    _ha_bluetooth = None

from .const import (
    BLE_CHUNK_SIZE,
    BLE_CONNECT_TIMEOUT,
    BLE_INTER_CHUNK_DELAY,
    BLE_SCAN_TIMEOUT,
    KNOWN_SERVICE_UUIDS,
    KNOWN_WRITE_CHARS,
)

_LOGGER = logging.getLogger(__name__)


class PrinterError(HomeAssistantError):
    """Base error for printer communication failures."""


class PrinterTimeout(PrinterError):
    """Raised when the printer cannot be reached in time."""


ALIGN_CODES = {
    "left": b"\x1b\x61\x00",
    "center": b"\x1b\x61\x01",
    "right": b"\x1b\x61\x02",
}

SIZE_CODES = {
    "normal": b"\x1d\x21\x00",
    "tall": b"\x1d\x21\x01",
    "wide": b"\x1d\x21\x10",
    "double": b"\x1d\x21\x11",
}

ESC_INIT = b"\x1b@"
BOLD_ON = b"\x1b\x45\x01"
BOLD_OFF = b"\x1b\x45\x00"
UNDERLINE_ON = b"\x1b\x2d\x01"
UNDERLINE_OFF = b"\x1b\x2d\x00"
CUT_FULL = b"\x1dV\x00"
CUT_PARTIAL = b"\x1dV\x42\x00"


@dataclass
class DiscoveredPrinter:
    """A printer found through Bluetooth discovery."""

    address: str
    name: str
    rssi: int


def _wrap_line(line: str, width: int) -> list[str]:
    """Greedy word wrap keeping empty lines intact."""
    line = line.rstrip()
    if not line:
        return [""]
    words = line.split(" ")
    wrapped: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width or not current:
            current = candidate
        else:
            wrapped.append(current)
            current = word
    if current:
        wrapped.append(current)
    return wrapped


def build_text_payload(
    message: str,
    *,
    align: str = "left",
    bold: bool = False,
    underline: bool = False,
    size: str = "normal",
    feed: int = 3,
    cut: bool = False,
    width: int = 32,
) -> bytes:
    """Build an ESC/POS byte stream from user text."""
    if align not in ALIGN_CODES:
        align = "left"
    if size not in SIZE_CODES:
        size = "normal"

    out = bytearray(ESC_INIT)
    effective_width = max(8, width // (2 if size in ("wide", "double") else 1))

    out += ALIGN_CODES[align]
    out += BOLD_ON if bold else BOLD_OFF
    out += UNDERLINE_ON if underline else UNDERLINE_OFF
    out += SIZE_CODES[size]

    lines: list[str] = []
    for raw in message.splitlines() or [""]:
        lines.extend(_wrap_line(raw, effective_width))
    text = "\n".join(lines) + "\n"
    out += text.encode("cp437", errors="replace")

    feed = max(0, min(int(feed), 20))
    if feed:
        out += bytes([0x1B, 0x64, feed])
    else:
        out += b"\n\n"

    if cut:
        out += CUT_PARTIAL
    return bytes(out)


class BaseEscposPrinter:
    """Common interface for printer transports."""

    def __init__(self, name: str | None = None) -> None:
        self.name = name or "MPT Printer"

    async def async_send(self, payload: bytes) -> None:
        raise NotImplementedError

    async def async_test(self) -> None:
        await self.async_send(ESC_INIT)


class BleEscposPrinter(BaseEscposPrinter):
    """Printer connected over Bluetooth Low Energy using bleak."""

    def __init__(
        self, hass: Any, address: str, name: str | None = None
    ) -> None:
        super().__init__(name)
        self.hass = hass
        self.address = address.lower()
        self._char_uuid: str | None = None

    @staticmethod
    def _pick_character(client: BleakClient) -> str:
        writable: list[str] = []
        preferred: list[str] = []
        for service in client.services:
            service_match = any(
                service.uuid.lower().startswith(u[:8]) for u in KNOWN_SERVICE_UUIDS
            )
            for char in service.characteristics:
                props = set(char.properties)
                if not ({"write", "write-without-response"} & props):
                    continue
                uuid = char.uuid.lower()
                writable.append(uuid)
                if uuid in KNOWN_WRITE_CHARS:
                    preferred.append(uuid)
                elif service_match and char.uuid.lower().startswith("0000ff"):
                    preferred.append(uuid)
        for candidate in KNOWN_WRITE_CHARS + preferred:
            if candidate in writable:
                return candidate
        if writable:
            return writable[0]
        raise PrinterError(
            "Nenhuma característica de escrita encontrada no dispositivo BLE"
        )

    def _write_chunk_flags(self, client: BleakClient, char_uuid: str) -> bool:
        for service in client.services:
            for char in service.characteristics:
                if char.uuid.lower() == char_uuid:
                    return "write" in char.properties and (
                        "write-without-response" not in char.properties
                    )
        return True

    async def _resolve_device(self):
        """Resolve the BLE device, preferring Home Assistant's own scanner."""
        if _ha_bluetooth is not None and self.hass is not None:
            device = _ha_bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            if device is not None:
                return device
        from bleak import BleakScanner

        device = await BleakScanner.find_device_by_address(
            self.address, timeout=BLE_SCAN_TIMEOUT
        )
        if device is None:
            raise PrinterTimeout(
                f"Impressora {self.address} não encontrada no scan BLE "
                f"({int(BLE_SCAN_TIMEOUT)}s). Ela alterna entre modos LE e "
                "clássico — tente novamente ou aperte o botão dela."
            )
        return device

    async def _send_once(self, payload: bytes) -> None:
        device = await self._resolve_device()
        client = BleakClient(device)
        try:
            await asyncio.wait_for(client.connect(), timeout=BLE_CONNECT_TIMEOUT)
            if self._char_uuid is None:
                self._char_uuid = self._pick_character(client)
            response = self._write_chunk_flags(client, self._char_uuid)
            for offset in range(0, len(payload), BLE_CHUNK_SIZE):
                chunk = payload[offset : offset + BLE_CHUNK_SIZE]
                await client.write_gatt_char(
                    self._char_uuid, chunk, response=response
                )
                if offset + BLE_CHUNK_SIZE < len(payload):
                    await asyncio.sleep(BLE_INTER_CHUNK_DELAY)
        except asyncio.TimeoutError as err:
            raise PrinterTimeout(f"Tempo esgotado conectando em {self.address}") from err
        except (BleakError, OSError) as err:
            raise PrinterError(f"Falha BLE: {err}") from err
        finally:
            try:
                await client.disconnect()
            except BleakError:  # pragma: no cover - best effort cleanup
                pass

    async def async_send(self, payload: bytes) -> None:
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                await self._send_once(payload)
                return
            except PrinterTimeout:
                raise
            except PrinterError as err:
                last_err = err
                self._char_uuid = None
                if attempt == 0:
                    await asyncio.sleep(0.5)
        raise last_err  # type: ignore[misc]


class SerialEscposPrinter(BaseEscposPrinter):
    """Printer exposed as a serial device (e.g. rfcomm-bound SPP)."""

    def __init__(
        self, hass: Any, path: str, name: str | None = None
    ) -> None:
        super().__init__(name)
        self.hass = hass
        self.path = path

    def _sync_send(self, payload: bytes) -> None:
        fd = None
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_NOCTTY)
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        except OSError as err:
            raise PrinterError(f"Falha escrevendo em {self.path}: {err}") from err
        finally:
            if fd is not None:
                os.close(fd)

    async def async_send(self, payload: bytes) -> None:
        await self.hass.async_add_executor_job(self._sync_send, payload)


async def async_find_printers(hass: Any) -> list[DiscoveredPrinter]:
    """List nearby Bluetooth printers known to Home Assistant."""
    from .const import NAME_KEYWORDS

    if _ha_bluetooth is None:
        return []

    seen: dict[str, DiscoveredPrinter] = {}
    for info in _ha_bluetooth.async_discovered_service_info(hass):
        adv_name = (info.advertisement.local_name or "").strip()
        haystack = f"{adv_name} {info.name}".lower()
        if not any(kw in haystack for kw in NAME_KEYWORDS):
            continue
        existing = seen.get(info.address)
        if existing is None or info.advertisement.rssi > existing.rssi:
            seen[info.address] = DiscoveredPrinter(
                address=info.address,
                name=adv_name or info.name,
                rssi=info.advertisement.rssi,
            )
    return sorted(seen.values(), key=lambda p: -p.rssi)
