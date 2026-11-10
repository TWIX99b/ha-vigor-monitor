"""DrayTek Vigor Monitor: SNMP traffic and DSL line values of DrayTek Vigor devices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .const import (
    CONF_COMMUNITY,
    CONF_WEB_PASSWORD,
    CONF_WEB_SSL,
    CONF_WEB_USERNAME,
    DEFAULT_PORT,
)
from .coordinator import VigorRuntimeData, VigorSnmpCoordinator, VigorWebCoordinator
from .snmp_client import VigorSnmpClient
from .web_client import VigorWebClient

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type VigorConfigEntry = ConfigEntry[VigorRuntimeData]


def create_web_client(
    hass: HomeAssistant, host: str, settings: Mapping[str, Any]
) -> VigorWebClient:
    """Create a web client with its own cookie jar.

    Own session: the device cookie must not leak into Home Assistant's shared
    jar, and unsafe=True keeps cookies set by an IP address. Created with
    auto_cleanup=False; VigorWebClient.async_close() detaches it.
    """
    session = async_create_clientsession(
        hass,
        verify_ssl=False,
        auto_cleanup=False,
        cookie_jar=aiohttp.CookieJar(unsafe=True),
    )
    return VigorWebClient(
        session,
        host,
        settings[CONF_WEB_USERNAME],
        settings.get(CONF_WEB_PASSWORD, ""),
        use_ssl=bool(settings.get(CONF_WEB_SSL, False)),
    )


async def async_setup_entry(hass: HomeAssistant, entry: VigorConfigEntry) -> bool:
    """Set up DrayTek Vigor Monitor from a config entry."""
    host = entry.data[CONF_HOST]
    snmp_client = VigorSnmpClient(
        hass,
        host,
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data[CONF_COMMUNITY],
    )
    snmp = VigorSnmpCoordinator(hass, entry, snmp_client)
    await snmp.async_config_entry_first_refresh()

    web: VigorWebCoordinator | None = None
    if entry.options.get(CONF_WEB_USERNAME):
        web_client = create_web_client(hass, host, entry.options)
        entry.async_on_unload(web_client.async_close)

        async def _logout_on_stop(_event: Event) -> None:
            # Entries are not unloaded on shutdown; do not leave web sessions
            # behind on the device (it only allows a few at once).
            await web_client.async_logout()

        entry.async_on_unload(
            hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _logout_on_stop)
        )
        web = VigorWebCoordinator(hass, entry, web_client)
        # Optional part: a web problem must not block the SNMP sensors.
        await web.async_refresh()

    entry.runtime_data = VigorRuntimeData(snmp=snmp, web=web)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VigorConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: VigorConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
