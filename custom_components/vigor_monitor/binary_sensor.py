"""Binary sensors for DrayTek Vigor Monitor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VigorConfigEntry
from .coordinator import VigorRuntimeData, VigorSnmpCoordinator, VigorWebCoordinator
from .entity import VigorEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [VigorLinkSensor(runtime)]
    if runtime.web is not None:
        entities.append(VigorDslSyncSensor(runtime.web, runtime))
    async_add_entities(entities)


class VigorLinkSensor(VigorEntity[VigorSnmpCoordinator], BinarySensorEntity):
    """WAN link up or down (IF-MIB ifOperStatus)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "link"

    def __init__(self, runtime: VigorRuntimeData) -> None:
        """Initialise the binary sensor."""
        super().__init__(runtime.snmp, runtime, "link")

    @property
    def is_on(self) -> bool | None:
        """Return true if the link is up."""
        return self.coordinator.data.link_up


class VigorDslSyncSensor(VigorEntity[VigorWebCoordinator], BinarySensorEntity):
    """DSL line in showtime (web API)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "dsl_synced"

    def __init__(self, coordinator: VigorWebCoordinator, runtime: VigorRuntimeData) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, runtime, "dsl_synced")

    @property
    def is_on(self) -> bool | None:
        """Return true while the line is synced."""
        return self.coordinator.data.synced if self.coordinator.data else None
