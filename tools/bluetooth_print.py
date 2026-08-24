#!/usr/bin/env python3
"""Standalone CLI to print text on MPT-II style printers.

BLE example:
    python3 bluetooth_print.py --ble AA:BB:CC:DD:EE:FF "Ola mundo"

Serial (rfcomm) example:
    python3 bluetooth_print.py --serial /dev/rfcomm0 "Ola mundo"
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
import types


def _load_printer_module():
    """Load mpt_printer.printer without triggering Home Assistant imports."""
    base = (
        pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "mpt_printer"
    )
    if str(base.parent) not in sys.path:
        sys.path.insert(0, str(base.parent))
    pkg = types.ModuleType("mpt_printer")
    pkg.__path__ = [str(base)]
    sys.modules.setdefault("mpt_printer", pkg)
    from mpt_printer.printer import (  # noqa: E402
        BleEscposPrinter,
        SerialEscposPrinter,
        build_text_payload,
    )

    return BleEscposPrinter, SerialEscposPrinter, build_text_payload


async def main() -> int:
    BleEscposPrinter, SerialEscposPrinter, build_text_payload = _load_printer_module()
    parser = argparse.ArgumentParser(description="Print text on an MPT-II printer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ble", metavar="MAC", help="Bluetooth MAC address")
    group.add_argument("--serial", metavar="PATH", help="Serial device path")
    parser.add_argument("--align", choices=["left", "center", "right"], default="left")
    parser.add_argument("--size", choices=["normal", "tall", "wide", "double"], default="normal")
    parser.add_argument("--bold", action="store_true")
    parser.add_argument("--underline", action="store_true")
    parser.add_argument("--feed", type=int, default=3)
    parser.add_argument("--cut", action="store_true")
    parser.add_argument("message")
    args = parser.parse_args()

    payload = build_text_payload(
        args.message,
        align=args.align,
        size=args.size,
        bold=args.bold,
        underline=args.underline,
        feed=args.feed,
        cut=args.cut,
    )

    if args.ble:
        printer = BleEscposPrinter(None, args.ble)
    else:
        printer = SerialEscposPrinter(None, args.serial)

    await printer.async_send(payload)
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
