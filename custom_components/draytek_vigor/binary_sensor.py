"""Binary sensors for DrayTek Vigor."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DrayTekConfigEntry
from .coordinator import DrayTekCoordinator, DrayTekRuntimeData
from .entity import DrayTekEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DrayTekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up DrayTek binary sensors."""
    async_add_entities([DrayTekLinkSensor(entry.runtime_data)])


class DrayTekLinkSensor(DrayTekEntity[DrayTekCoordinator], BinarySensorEntity):
    """DSL/WAN link up or down (IF-MIB ifOperStatus)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_translation_key = "link"

    def __init__(self, runtime: DrayTekRuntimeData) -> None:
        """Initialise the binary sensor."""
        super().__init__(runtime.snmp, runtime, "link")

    @property
    def is_on(self) -> bool | None:
        """Return true if the link is up."""
        return self.coordinator.data.link_up
