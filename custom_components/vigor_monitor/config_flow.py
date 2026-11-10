"""Config flow for DrayTek Vigor Monitor."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import VigorConfigEntry, create_web_client
from .const import (
    CONF_COMMUNITY,
    CONF_DSL_SCAN_INTERVAL,
    CONF_INTERFACE_INDEX,
    CONF_WEB_PASSWORD,
    CONF_WEB_SSL,
    CONF_WEB_USERNAME,
    DEFAULT_COMMUNITY,
    DEFAULT_DSL_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_WEB_USERNAME,
    DOMAIN,
    DRAYTEK_ENTERPRISE_OID,
    MANUFACTURER,
    MAX_DSL_SCAN_INTERVAL,
    MAX_INTERFACE_INDEX,
    MAX_SCAN_INTERVAL,
    MIN_DSL_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    OID_DRAYTEK_MODEL,
    OID_IF_DESCR,
    OID_SYS_DESCR,
    OID_SYS_OBJECT_ID,
    PREFERRED_INTERFACE_HINTS,
)
from .coordinator import parse_sys_descr
from .snmp_client import VigorSnmpClient, VigorSnmpConnectionError, VigorSnmpError
from .web_client import VigorWebAuthError, VigorWebError

_LOGGER = logging.getLogger(__name__)


class NotDrayTekError(Exception):
    """The device answered but is not a DrayTek."""


async def _async_probe(
    hass: HomeAssistant, host: str, port: int, community: str
) -> tuple[str | None, dict[int, str]]:
    """Read the model and the interface table. Returns (model, {index: name})."""
    client = VigorSnmpClient(hass, host, port, community)
    sys_descr, sys_object_id, dt_model = await client.async_get(
        [OID_SYS_DESCR, OID_SYS_OBJECT_ID, OID_DRAYTEK_MODEL]
    )
    if sys_descr is None and sys_object_id is None:
        raise VigorSnmpConnectionError("No answer to sysDescr/sysObjectID")
    if not str(sys_object_id or "").startswith(DRAYTEK_ENTERPRISE_OID) and (
        MANUFACTURER.lower() not in str(sys_descr or "").lower()
    ):
        raise NotDrayTekError(str(sys_descr))

    indexes = range(1, MAX_INTERFACE_INDEX + 1)
    names = await client.async_get([f"{OID_IF_DESCR}.{i}" for i in indexes])
    interfaces = {i: str(n) for i, n in zip(indexes, names, strict=True) if n}
    model = parse_sys_descr(sys_descr)[0] or (dt_model if isinstance(dt_model, str) else None)
    return model or None, interfaces


async def _async_validate_web(
    hass: HomeAssistant, host: str, settings: Mapping[str, Any]
) -> str | None:
    """Log in once and read the DSL status. Returns an error key or None."""
    client = create_web_client(hass, host, settings)
    try:
        await client.async_get_dsl_status()
    except VigorWebAuthError:
        return "web_invalid_auth"
    except VigorWebError as err:
        _LOGGER.debug("Web API test failed: %s", err)
        return "web_cannot_connect"
    except Exception:
        _LOGGER.exception("Unexpected error while testing the web API on %s", host)
        return "unknown"
    finally:
        await client.async_close()
    return None


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


def _number_selector(minimum: int, maximum: int, unit: str | None = None) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


_USERNAME_SELECTOR = TextSelector(TextSelectorConfig(autocomplete="username"))
_PASSWORD_SELECTOR = TextSelector(
    TextSelectorConfig(type=TextSelectorType.PASSWORD, autocomplete="current-password")
)


def _web_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_WEB_USERNAME): _USERNAME_SELECTOR,
            vol.Optional(CONF_WEB_PASSWORD): _PASSWORD_SELECTOR,
            vol.Optional(CONF_WEB_SSL, default=False): BooleanSelector(),
        }
    )


class VigorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DrayTek Vigor Monitor."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._data: dict[str, Any] = {}
        self._interfaces: dict[int, str] = {}
        self._title: str = MANUFACTURER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 1: address and SNMP community."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            await self.async_set_unique_id(host.lower())
            self._abort_if_unique_id_configured()
            try:
                model, interfaces = await _async_probe(
                    self.hass, host, int(user_input[CONF_PORT]), user_input[CONF_COMMUNITY]
                )
            except NotDrayTekError:
                errors["base"] = "not_draytek"
            except VigorSnmpError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while probing %s", host)
                errors["base"] = "unknown"
            else:
                if not interfaces:
                    errors["base"] = "no_interfaces"
                else:
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
        """Step 2: the DSL/WAN interface."""
        if user_input is not None:
            self._data[CONF_INTERFACE_INDEX] = int(user_input[CONF_INTERFACE_INDEX])
            return await self.async_step_dsl()

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

    async def async_step_dsl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 3 (optional): web login for the DSL line values."""
        errors: dict[str, str] = {}
        if user_input is not None:
            username = (user_input.get(CONF_WEB_USERNAME) or "").strip()
            options: dict[str, Any] = {}
            if username:
                options = {
                    CONF_WEB_USERNAME: username,
                    CONF_WEB_PASSWORD: user_input.get(CONF_WEB_PASSWORD, ""),
                    CONF_WEB_SSL: bool(user_input.get(CONF_WEB_SSL, False)),
                }
                if error := await _async_validate_web(
                    self.hass, self._data[CONF_HOST], options
                ):
                    errors["base"] = error
            if not errors:
                return self.async_create_entry(
                    title=self._title, data=self._data, options=options
                )

        suggested = {CONF_WEB_USERNAME: DEFAULT_WEB_USERNAME}
        if user_input:
            suggested = {k: v for k, v in user_input.items() if k != CONF_WEB_PASSWORD}
        return self.async_show_form(
            step_id="dsl",
            data_schema=self.add_suggested_values_to_schema(_web_schema(), suggested),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The web login was rejected repeatedly."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for new web credentials."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            options = {
                **entry.options,
                CONF_WEB_USERNAME: user_input[CONF_WEB_USERNAME].strip(),
                CONF_WEB_PASSWORD: user_input.get(CONF_WEB_PASSWORD, ""),
            }
            if not (
                error := await _async_validate_web(self.hass, entry.data[CONF_HOST], options)
            ):
                return self.async_update_reload_and_abort(entry, options=options)
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(CONF_WEB_USERNAME): _USERNAME_SELECTOR,
                        vol.Optional(CONF_WEB_PASSWORD): _PASSWORD_SELECTOR,
                    }
                ),
                {CONF_WEB_USERNAME: entry.options.get(CONF_WEB_USERNAME, "")},
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: VigorConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return VigorOptionsFlow()


class VigorOptionsFlow(OptionsFlow):
    """Interface, polling intervals and the optional web login."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        entry = self.config_entry
        options = entry.options
        errors: dict[str, str] = {}

        if user_input is not None:
            username = (user_input.get(CONF_WEB_USERNAME) or "").strip()
            # Empty password field = keep the stored one (it is never shown).
            password = user_input.get(CONF_WEB_PASSWORD) or (
                options.get(CONF_WEB_PASSWORD, "")
                if username == options.get(CONF_WEB_USERNAME)
                else ""
            )
            new_options: dict[str, Any] = {
                CONF_INTERFACE_INDEX: int(user_input[CONF_INTERFACE_INDEX]),
                CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                CONF_DSL_SCAN_INTERVAL: int(user_input[CONF_DSL_SCAN_INTERVAL]),
            }
            if username:
                web = {
                    CONF_WEB_USERNAME: username,
                    CONF_WEB_PASSWORD: password,
                    CONF_WEB_SSL: bool(user_input.get(CONF_WEB_SSL, False)),
                }
                if error := await _async_validate_web(self.hass, entry.data[CONF_HOST], web):
                    errors["base"] = error
                new_options |= web
            if not errors:
                return self.async_create_entry(data=new_options)

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
            options.get(CONF_INTERFACE_INDEX, entry.data[CONF_INTERFACE_INDEX])
        )
        interfaces.setdefault(current_index, f"Interface {current_index}")

        schema = vol.Schema(
            {
                vol.Required(CONF_INTERFACE_INDEX): _interface_selector(
                    dict(sorted(interfaces.items()))
                ),
                vol.Required(CONF_SCAN_INTERVAL): _number_selector(
                    MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL, "s"
                ),
                vol.Optional(CONF_WEB_USERNAME): _USERNAME_SELECTOR,
                vol.Optional(CONF_WEB_PASSWORD): _PASSWORD_SELECTOR,
                vol.Optional(CONF_WEB_SSL): BooleanSelector(),
                vol.Required(CONF_DSL_SCAN_INTERVAL): _number_selector(
                    MIN_DSL_SCAN_INTERVAL, MAX_DSL_SCAN_INTERVAL, "s"
                ),
            }
        )
        suggested: dict[str, Any] = {
            CONF_INTERFACE_INDEX: str(current_index),
            CONF_SCAN_INTERVAL: options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            CONF_WEB_USERNAME: options.get(CONF_WEB_USERNAME, ""),
            CONF_WEB_SSL: options.get(CONF_WEB_SSL, False),
            CONF_DSL_SCAN_INTERVAL: options.get(
                CONF_DSL_SCAN_INTERVAL, DEFAULT_DSL_SCAN_INTERVAL
            ),
        }
        if user_input is not None:
            suggested |= {k: v for k, v in user_input.items() if k != CONF_WEB_PASSWORD}
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, suggested),
            errors=errors,
        )
