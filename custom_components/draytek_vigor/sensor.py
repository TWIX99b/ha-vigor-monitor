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
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DrayTekConfigEntry
from .coordinator import (
    DrayTekCoordinator,
    DrayTekData,
    DrayTekDslCoordinator,
    DrayTekDslData,
    DrayTekRuntimeData,
)
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


@dataclass(frozen=True, kw_only=True)
class DrayTekDslSensorDescription(SensorEntityDescription):
    """Describes a DSL line sensor (SSH)."""

    value_fn: Callable[[DrayTekDslData], float | int | str | datetime | None]


def _mode(data: DrayTekDslData) -> str | None:
    parts = [p for p in (data.info.mode, data.info.profile) if p]
    return " ".join(parts) or None


DSL_SENSORS: tuple[DrayTekDslSensorDescription, ...] = (
    DrayTekDslSensorDescription(
        key="dsl_sync_download",
        translation_key="dsl_sync_download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.info.downstream_kbps,
    ),
    DrayTekDslSensorDescription(
        key="dsl_sync_upload",
        translation_key="dsl_sync_upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.info.upstream_kbps,
    ),
    DrayTekDslSensorDescription(
        key="dsl_snr_downstream",
        translation_key="dsl_snr_downstream",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.info.snr_downstream,
    ),
    DrayTekDslSensorDescription(
        key="dsl_snr_upstream",
        translation_key="dsl_snr_upstream",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.info.snr_upstream,
    ),
    DrayTekDslSensorDescription(
        key="dsl_status",
        translation_key="dsl_status",
        value_fn=lambda d: d.info.status,
    ),
    DrayTekDslSensorDescription(
        key="dsl_line_since",
        translation_key="dsl_line_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.line_since,
    ),
    DrayTekDslSensorDescription(
        key="dsl_mode",
        translation_key="dsl_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_mode,
    ),
    DrayTekDslSensorDescription(
        key="dsl_firmware",
        translation_key="dsl_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.info.dsl_version,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DrayTekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up DrayTek sensors."""
    runtime = entry.runtime_data
    coordinator = runtime.snmp
    entities: list[SensorEntity] = [
        DrayTekSensor(runtime, description)
        for description in SENSORS
        if not description.optional or description.value_fn(coordinator.data) is not None
    ]
    if runtime.dsl is not None:
        entities.extend(
            DrayTekDslSensor(runtime.dsl, runtime, description)
            for description in DSL_SENSORS
        )
    async_add_entities(entities)


class DrayTekSensor(DrayTekEntity[DrayTekCoordinator], SensorEntity):
    """A DrayTek SNMP sensor."""

    entity_description: DrayTekSensorDescription

    def __init__(
        self, runtime: DrayTekRuntimeData, description: DrayTekSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(runtime.snmp, runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class DrayTekDslSensor(DrayTekEntity[DrayTekDslCoordinator], SensorEntity):
    """A DSL line sensor read via the SSH CLI."""

    entity_description: DrayTekDslSensorDescription

    def __init__(
        self,
        coordinator: DrayTekDslCoordinator,
        runtime: DrayTekRuntimeData,
        description: DrayTekDslSensorDescription,
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | datetime | None:
        """Return the state."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
