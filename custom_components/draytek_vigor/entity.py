"""Base entity for DrayTek Vigor."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN, MANUFACTURER
from .coordinator import DrayTekRuntimeData


class DrayTekEntity[_CoordinatorT: DataUpdateCoordinator[Any]](
    CoordinatorEntity[_CoordinatorT]
):
    """Common base for all DrayTek Vigor entities (SNMP and DSL)."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: _CoordinatorT, runtime: DrayTekRuntimeData, key: str
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        entry = runtime.snmp.config_entry
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"
        data = runtime.snmp.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            manufacturer=MANUFACTURER,
            model=data.model if data else None,
            sw_version=data.firmware if data else None,
            name=entry.title,
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )
