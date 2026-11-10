"""The DrayTek Vigor integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_COMMUNITY, DEFAULT_PORT
from .coordinator import DrayTekCoordinator
from .snmp_client import DrayTekSnmpClient

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type DrayTekConfigEntry = ConfigEntry[DrayTekCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DrayTekConfigEntry) -> bool:
    """Set up DrayTek Vigor from a config entry."""
    client = DrayTekSnmpClient(
        hass,
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        entry.data[CONF_COMMUNITY],
    )
    coordinator = DrayTekCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: DrayTekConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: DrayTekConfigEntry) -> None:
    """Reload the entry when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
