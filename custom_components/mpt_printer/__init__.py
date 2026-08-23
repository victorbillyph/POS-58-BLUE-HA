"""The MPT-II Bluetooth Printer integration."""

from __future__ import annotations

import base64
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ALIGN_LEFT,
    CONF_ADDRESS,
    CONF_CONNECTION,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_BOLD,
    CONF_DEFAULT_CUT,
    CONF_DEFAULT_FEED,
    CONF_DEFAULT_SIZE,
    CONF_SERIAL_PATH,
    CONN_BLE,
    CONN_SERIAL,
    DOMAIN,
)
from .printer import (
    BaseEscposPrinter,
    BleEscposPrinter,
    PrinterError,
    SerialEscposPrinter,
    build_text_payload,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = []


def _printer_from_entry(hass: HomeAssistant, entry: ConfigEntry) -> BaseEscposPrinter:
    printers = hass.data.setdefault(DOMAIN, {})
    printer = printers.get(entry.entry_id)
    if printer is None:
        raise HomeAssistantError(f"Impressora da entrada {entry.title} não carregada")
    return printer


def _resolve_printers(hass: HomeAssistant, call: ServiceCall) -> list[tuple[ConfigEntry, BaseEscposPrinter]]:
    printers = hass.data.get(DOMAIN, {})
    entries = {
        entry_id: (hass.config_entries.async_get_entry(entry_id), printer)
        for entry_id, printer in printers.items()
    }
    entries = {k: v for k, v in entries.items() if v[0] is not None}

    device_ids = call.data.get("device_id")
    if isinstance(device_ids, str):
        device_ids = [device_ids]
    if not device_ids:
        return list(entries.values())

    dev_reg = dr.async_get(hass)
    resolved: list[tuple[ConfigEntry, BaseEscposPrinter]] = []
    for device_id in device_ids:
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        for entry_id in device.config_entries:
            if entry_id in entries:
                resolved.append(entries[entry_id])
    return resolved


def _merge_options(call_data, options: dict) -> dict:
    def pick(key: str):
        if key in call_data and call_data[key] is not None:
            return call_data[key]
        return options.get(key)

    return {
        "align": pick("align") or options.get(CONF_DEFAULT_ALIGN, ALIGN_LEFT),
        "size": pick("size") or options.get(CONF_DEFAULT_SIZE, "normal"),
        "bold": bool(pick("bold")),
        "underline": bool(pick("underline")),
        "feed": pick("feed"),
        "cut": bool(pick("cut")),
    }


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Register domain services."""

    async def handle_print_text(call: ServiceCall) -> None:
        pairs = _resolve_printers(hass, call)
        if not pairs:
            raise HomeAssistantError("Nenhuma impressora MPT configurada")
        for entry, printer in pairs:
            params = _merge_options(call.data, dict(entry.options))
            payload = build_text_payload(
                call.data["message"],
                align=params["align"],
                size=params["size"],
                bold=params["bold"],
                underline=params["underline"],
                feed=int(params["feed"] if params["feed"] is not None else 3),
                cut=params["cut"],
                width=int(entry.data.get("width", 32)),
            )
            try:
                await printer.async_send(payload)
            except PrinterError as err:
                _LOGGER.error("Erro imprimindo em %s: %s", printer.name, err)

    async def handle_print_raw(call: ServiceCall) -> None:
        pairs = _resolve_printers(hass, call)
        if not pairs:
            raise HomeAssistantError("Nenhuma impressora MPT configurada")
        raw_b64 = call.data["payload_base64"].replace("\n", "").strip()
        payload = base64.b64decode(raw_b64)
        for _, printer in pairs:
            await printer.async_send(payload)

    hass.services.async_register(
        DOMAIN,
        "print_text",
        handle_print_text,
        schema=vol.Schema(
            {
                vol.Required("message"): cv.string,
                vol.Optional("align"): vol.In(["left", "center", "right"]),
                vol.Optional("size"): vol.In(["normal", "tall", "wide", "double"]),
                vol.Optional("bold"): cv.boolean,
                vol.Optional("underline"): cv.boolean,
                vol.Optional("feed"): vol.All(vol.Coerce(int), vol.Range(min=0, max=20)),
                vol.Optional("cut"): cv.boolean,
                vol.Optional("device_id"): vol.Any(str, [str]),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        "print_raw",
        handle_print_raw,
        schema=vol.Schema(
            {
                vol.Required("payload_base64"): cv.string,
                vol.Optional("device_id"): vol.Any(str, [str]),
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a configured printer."""
    connection = entry.data[CONF_CONNECTION]
    name = entry.title.split(" [")[0]

    if connection == CONN_BLE:
        printer = BleEscposPrinter(hass, entry.data[CONF_ADDRESS], name)
    elif connection == CONN_SERIAL:
        printer = SerialEscposPrinter(hass, entry.data[CONF_SERIAL_PATH], name)
    else:
        raise HomeAssistantError(f"Tipo de conexão inválida: {connection}")

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = printer

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer="Generic",
        model="MPT-II 58mm Thermal Printer",
        name=name,
    )

    async def _update_listener(hass: HomeAssistant, updated: ConfigEntry) -> None:
        """Keep nothing cached; options are read at call time."""

    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove a configured printer."""
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
