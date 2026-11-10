"""Config flow for the DrayTek Vigor integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from . import DrayTekConfigEntry
from .const import (
    CONF_COMMUNITY,
    CONF_INTERFACE_INDEX,
    DEFAULT_COMMUNITY,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DRAYTEK_ENTERPRISE_OID,
    MANUFACTURER,
    MAX_INTERFACE_INDEX,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OID_IF_DESCR,
    OID_SYS_DESCR,
    OID_SYS_OBJECT_ID,
    PREFERRED_INTERFACE_HINTS,
)
from .coordinator import parse_sys_descr
from .snmp_client import DrayTekConnectionError, DrayTekError, DrayTekSnmpClient

_LOGGER = logging.getLogger(__name__)


class NotDrayTekError(Exception):
    """The device answered but is not a DrayTek."""


async def _async_probe(
    hass: HomeAssistant, host: str, port: int, community: str
) -> tuple[str | None, dict[int, str]]:
    """Read sysDescr and the interface table. Returns (sysDescr, {index: name})."""
    client = DrayTekSnmpClient(hass, host, port, community)
    sys_descr, sys_object_id = await client.async_get(
        [OID_SYS_DESCR, OID_SYS_OBJECT_ID]
    )
    if sys_descr is None and sys_object_id is None:
        raise DrayTekConnectionError("No answer to sysDescr/sysObjectID")
    if not str(sys_object_id or "").startswith(DRAYTEK_ENTERPRISE_OID) and (
        MANUFACTURER.lower() not in str(sys_descr or "").lower()
    ):
        raise NotDrayTekError(str(sys_descr))

    indexes = range(1, MAX_INTERFACE_INDEX + 1)
    names = await client.async_get([f"{OID_IF_DESCR}.{i}" for i in indexes])
    interfaces = {i: str(n) for i, n in zip(indexes, names, strict=True) if n}
    return sys_descr, interfaces


def _guess_interface(interfaces: dict[int, str]) -> int | None:
    """Pick the interface that most likely carries the DSL link."""
    for hint in PREFERRED_INTERFACE_HINTS:
        for index, name in interfaces.items():
            if hint in name.lower():
                return index
    return next(iter(interfaces), None)


def _interface_selector(interfaces: dict[int, str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=str(index), label=f"{name} (#{index})")
                for index, name in interfaces.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class DrayTekConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DrayTek Vigor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._data: dict[str, Any] = {}
        self._interfaces: dict[int, str] = {}
        self._title: str = MANUFACTURER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for host and community."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            try:
                sys_descr, interfaces = await _async_probe(
                    self.hass,
                    host,
                    int(user_input[CONF_PORT]),
                    user_input[CONF_COMMUNITY],
                )
            except DrayTekConnectionError:
                errors["base"] = "cannot_connect"
            except NotDrayTekError:
                errors["base"] = "not_draytek"
            except DrayTekError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while probing %s", host)
                errors["base"] = "unknown"
            else:
                if not interfaces:
                    errors["base"] = "no_interfaces"
                else:
                    model, _ = parse_sys_descr(sys_descr)
                    self._title = f"{MANUFACTURER} {model}" if model else MANUFACTURER
                    self._data = {
                        CONF_HOST: host,
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_COMMUNITY: user_input[CONF_COMMUNITY],
                    }
                    self._interfaces = interfaces
                    return await self.async_step_interface()

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_HOST): str,
                        vol.Required(CONF_COMMUNITY, default=DEFAULT_COMMUNITY): str,
                        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                            vol.Coerce(int), vol.Range(min=1, max=65535)
                        ),
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_interface(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick the DSL/WAN interface."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._title,
                data={
                    **self._data,
                    CONF_INTERFACE_INDEX: int(user_input[CONF_INTERFACE_INDEX]),
                },
            )

        guess = _guess_interface(self._interfaces)
        return self.async_show_form(
            step_id="interface",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERFACE_INDEX,
                        default=str(guess) if guess is not None else vol.UNDEFINED,
                    ): _interface_selector(self._interfaces),
                }
            ),
            description_placeholders={"title": self._title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: DrayTekConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return DrayTekOptionsFlow()


class DrayTekOptionsFlow(OptionsFlow):
    """Change interface and polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_INTERFACE_INDEX: int(user_input[CONF_INTERFACE_INDEX]),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                }
            )

        entry = self.config_entry
        try:
            _, interfaces = await _async_probe(
                self.hass,
                entry.data[CONF_HOST],
                entry.data.get(CONF_PORT, DEFAULT_PORT),
                entry.data[CONF_COMMUNITY],
            )
        except Exception:  # noqa: BLE001 - device offline: keep current choice only
            interfaces = {}
        current_index = int(
            entry.options.get(CONF_INTERFACE_INDEX, entry.data[CONF_INTERFACE_INDEX])
        )
        interfaces.setdefault(current_index, f"Interface {current_index}")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERFACE_INDEX, default=str(current_index)
                    ): _interface_selector(dict(sorted(interfaces.items()))),
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL,
                            max=MAX_SCAN_INTERVAL,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
        )
