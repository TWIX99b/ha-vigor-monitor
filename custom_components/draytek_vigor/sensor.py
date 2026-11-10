"""Sensors for DrayTek Vigor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DrayTekConfigEntry
from .coordinator import DrayTekCoordinator, DrayTekData
from .entity import DrayTekEntity

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class DrayTekSensorDescription(SensorEntityDescription):
    """Describes a DrayTek sensor."""

    value_fn: Callable[[DrayTekData], float | int | datetime | None]
    # Only create the entity if the device delivers a value for it.
    optional: bool = False


SENSORS: tuple[DrayTekSensorDescription, ...] = (
    DrayTekSensorDescription(
        key="download",
        translation_key="download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.rate_in,
    ),
    DrayTekSensorDescription(
        key="upload",
        translation_key="upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.rate_out,
    ),
    DrayTekSensorDescription(
        key="bytes_received",
        translation_key="bytes_received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bytes_in,
    ),
    DrayTekSensorDescription(
        key="bytes_sent",
        translation_key="bytes_sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bytes_out,
    ),
    DrayTekSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.memory_usage,
        optional=True,
    ),
    DrayTekSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.boot_time,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DrayTekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up DrayTek sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        DrayTekSensor(coordinator, description)
        for description in SENSORS
        if not description.optional or description.value_fn(coordinator.data) is not None
    )


class DrayTekSensor(DrayTekEntity, SensorEntity):
    """A DrayTek sensor."""

    entity_description: DrayTekSensorDescription

    def __init__(
        self, coordinator: DrayTekCoordinator, description: DrayTekSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)
