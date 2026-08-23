"""Config flow to set up MPT-II Bluetooth printers."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    ALIGNS,
    CONF_ADDRESS,
    CONF_CONNECTION,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_DEFAULT_FEED,
    CONF_DEFAULT_SIZE,
    CONF_SERIAL_PATH,
    CONF_WIDTH,
    CONNECTIONS,
    CONN_BLE,
    CONN_SERIAL,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_FEED,
    DEFAULT_NAME,
    DEFAULT_SIZE,
    DOMAIN,
)
from .printer import (
    BleEscposPrinter,
    PrinterError,
    SerialEscposPrinter,
    async_find_printers,
)

METHOD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CONNECTION, default=CONN_BLE): SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=value, label=label)
                    for value, label in CONNECTIONS.items()
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
    }
)


def _align_selector(default: str) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=v, label=v) for v in ALIGNS],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _size_selector() -> SelectSelector:
    from .const import SIZES

    return SelectSelector(
        SelectSelectorConfig(
            options=[SelectOptionDict(value=v, label=v) for v in SIZES],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


def _defaults_from(source: dict[str, Any]) -> dict[str, Any]:
    return {
        CONF_DEFAULT_ALIGN: source.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
        CONF_DEFAULT_SIZE: source.get(CONF_DEFAULT_SIZE, DEFAULT_SIZE),
        CONF_DEFAULT_FEED: int(source.get(CONF_DEFAULT_FEED, DEFAULT_FEED)),
        CONF_DEFAULT_CUT: bool(source.get(CONF_DEFAULT_CUT, DEFAULT_CUT)),
    }


class MptPrinterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the MPT-II printer config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None
        self._discovered_name: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MptOptionsFlowHandler:
        return MptOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            if user_input[CONF_CONNECTION] == CONN_BLE:
                return await self.async_step_ble()
            return await self.async_step_serial()
        return self.async_show_form(step_id="user", data_schema=METHOD_SCHEMA)

    async def async_step_bluetooth(self, discovery_info) -> FlowResult:
        """Handle discovery advertised by the manifest bluetooth matcher."""
        address = discovery_info.address
        await self.async_set_unique_id(address.lower())
        self._abort_if_unique_id_configured()
        self._discovered_address = address
        self._discovered_name = (
            getattr(discovery_info.advertisement, "local_name", None)
            or getattr(discovery_info, "name", None)
            or DEFAULT_NAME
        )
        self.context["title_placeholders"] = {
            "name": self._discovered_name,
            "address": address,
        }
        return await self.async_step_ble()

    async def async_step_ble(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        discovered = await async_find_printers(self.hass)
        choices = {p.address: f"{p.name} ({p.address})" for p in discovered}

        suggested = self._discovered_address or ""
        schema_dict: dict = {}
        if choices and not suggested:
            schema_dict[vol.Optional("discovered")] = SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value="", label="-- manual --")
                    ]
                    + [
                        SelectOptionDict(value=key, label=label)
                        for key, label in sorted(
                            choices.items(), key=lambda kv: kv[1]
                        )
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        schema_dict[
            vol.Optional(CONF_ADDRESS, description={"suggested_value": suggested})
        ] = TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT))
        schema_dict[
            vol.Optional("name", description={"suggested_value": DEFAULT_NAME})
        ] = str

        if user_input is not None:
            address = str(
                user_input.get("discovered") or user_input.get(CONF_ADDRESS) or ""
            ).strip()
            name = str(user_input.get("name") or "").strip() or DEFAULT_NAME
            if not address:
                errors["base"] = "no_address"
            else:
                await self.async_set_unique_id(address.lower())
                self._abort_if_unique_id_configured()
                printer = BleEscposPrinter(self.hass, address, name)
                try:
                    await printer.async_test()
                except PrinterError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        title=f"{name} [{address}]",
                        data={
                            CONF_CONNECTION: CONN_BLE,
                            CONF_ADDRESS: address,
                            CONF_WIDTH: 32,
                        },
                        options=_defaults_from({}),
                    )
        elif suggested and not discovered:
            errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="ble",
            data_schema=vol.Schema(schema_dict),
            errors=errors,
            description_placeholders=self.context.get("title_placeholders", {}),
        )

    async def async_step_serial(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PATH, default="/dev/rfcomm0"): str,
                vol.Optional(CONF_WIDTH, default=32): NumberSelector(
                    NumberSelectorConfig(min=16, max=96, step=1)
                ),
                vol.Optional(CONF_DEFAULT_ALIGN, default=DEFAULT_ALIGN): _align_selector(DEFAULT_ALIGN),
                vol.Optional(CONF_DEFAULT_SIZE, default=DEFAULT_SIZE): _size_selector(),
                vol.Optional(CONF_DEFAULT_FEED, default=DEFAULT_FEED): NumberSelector(
                    NumberSelectorConfig(min=0, max=20, step=1)
                ),
                vol.Optional(CONF_DEFAULT_CUT, default=DEFAULT_CUT): BooleanSelector(),
            }
        )
        if user_input is not None:
            path = str(user_input[CONF_SERIAL_PATH]).strip()
            await self.async_set_unique_id(f"serial-{path.replace('/', '_')}")
            self._abort_if_unique_id_configured()
            printer = SerialEscposPrinter(self.hass, path)
            try:
                await printer.async_test()
            except PrinterError:
                errors["base"] = "invalid_path"
            else:
                return self.async_create_entry(
                    title=f"{DEFAULT_NAME} [{path}]",
                    data={
                        CONF_CONNECTION: CONN_SERIAL,
                        CONF_SERIAL_PATH: path,
                        CONF_WIDTH: int(user_input.get(CONF_WIDTH, 32)),
                    },
                    options=_defaults_from(user_input),
                )
        return self.async_show_form(step_id="serial", data_schema=schema, errors=errors)


class MptOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for an existing printer entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = dict(self.config_entry.options)
        current.setdefault(CONF_WIDTH, self.config_entry.data.get(CONF_WIDTH, 32))
        current.update({k: v for k, v in _defaults_from(current).items()})
        schema = vol.Schema(
            {
                vol.Optional(CONF_WIDTH, default=int(current[CONF_WIDTH])): NumberSelector(
                    NumberSelectorConfig(min=16, max=96, step=1)
                ),
                vol.Optional(
                    CONF_DEFAULT_ALIGN, default=current[CONF_DEFAULT_ALIGN]
                ): _align_selector(current[CONF_DEFAULT_ALIGN]),
                vol.Optional(
                    CONF_DEFAULT_SIZE, default=current[CONF_DEFAULT_SIZE]
                ): _size_selector(),
                vol.Optional(
                    CONF_DEFAULT_FEED, default=int(current[CONF_DEFAULT_FEED])
                ): NumberSelector(NumberSelectorConfig(min=0, max=20, step=1)),
                vol.Optional(
                    CONF_DEFAULT_CUT, default=bool(current[CONF_DEFAULT_CUT])
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
