"""Sensors for DrayTek Vigor Monitor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import VigorConfigEntry
from .coordinator import VigorRuntimeData, VigorSnmpCoordinator, VigorSnmpData
from .entity import VigorEntity
from .protocol import DslStatus

PARALLEL_UPDATES = 0

type StateValue = float | int | str | datetime | None


@dataclass(frozen=True, kw_only=True)
class VigorSensorDescription(SensorEntityDescription):
    """Describes an SNMP sensor."""

    value_fn: Callable[[VigorSnmpData], StateValue]
    # Only create the entity if the device delivers a value for it.
    optional: bool = False


@dataclass(frozen=True, kw_only=True)
class VigorDslSensorDescription(SensorEntityDescription):
    """Describes a DSL line sensor."""

    value_fn: Callable[[DslStatus], StateValue]
    # False: only the web API provides it (not the xDSL MIBs of DrayOS 4).
    snmp_capable: bool = False


SENSORS: tuple[VigorSensorDescription, ...] = (
    VigorSensorDescription(
        key="download",
        translation_key="download",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.rate_in,
    ),
    VigorSensorDescription(
        key="upload",
        translation_key="upload",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.rate_out,
    ),
    VigorSensorDescription(
        key="bytes_received",
        translation_key="bytes_received",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bytes_in,
    ),
    VigorSensorDescription(
        key="bytes_sent",
        translation_key="bytes_sent",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIGABYTES,
        suggested_display_precision=2,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bytes_out,
    ),
    VigorSensorDescription(
        key="link_since",
        translation_key="link_since",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: d.link_since,
        optional=True,
    ),
    VigorSensorDescription(
        key="cpu_load",
        translation_key="cpu_load",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.cpu_load,
        optional=True,
    ),
    VigorSensorDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.memory_usage,
        optional=True,
    ),
    VigorSensorDescription(
        key="last_boot",
        translation_key="last_boot",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.boot_time,
    ),
)


def _rate(key: str, fn: Callable[[DslStatus], StateValue], *, enabled: bool = True) -> VigorDslSensorDescription:
    return VigorDslSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.KILOBITS_PER_SECOND,
        suggested_unit_of_measurement=UnitOfDataRate.MEGABITS_PER_SECOND,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        value_fn=fn,
        snmp_capable=True,
    )


def _db(key: str, fn: Callable[[DslStatus], StateValue]) -> VigorDslSensorDescription:
    return VigorDslSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=fn,
        snmp_capable=True,
    )


def _errors(key: str, fn: Callable[[DslStatus], StateValue], unit: str | None) -> VigorDslSensorDescription:
    # Counters restart at 0 on every resync -> total_increasing.
    return VigorDslSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=fn,
    )


DSL_SENSORS: tuple[VigorDslSensorDescription, ...] = (
    _rate("dsl_sync_download", lambda d: d.rate_down),
    _rate("dsl_sync_upload", lambda d: d.rate_up),
    _rate("dsl_attainable_download", lambda d: d.attainable_down),
    _rate("dsl_attainable_upload", lambda d: d.attainable_up),
    _db("dsl_snr_downstream", lambda d: d.snr_down),
    _db("dsl_snr_upstream", lambda d: d.snr_up),
    _db("dsl_attenuation_downstream", lambda d: d.attenuation_down),
    _db("dsl_attenuation_upstream", lambda d: d.attenuation_up),
    VigorDslSensorDescription(
        key="dsl_status",
        translation_key="dsl_status",
        value_fn=lambda d: d.status,
    ),
    VigorDslSensorDescription(
        key="dsl_mode",
        translation_key="dsl_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.mode_profile,
    ),
    VigorDslSensorDescription(
        key="dsl_firmware",
        translation_key="dsl_firmware",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.dsl_version,
    ),
    _errors("dsl_crc_near", lambda d: d.crc_near, None),
    _errors("dsl_crc_far", lambda d: d.crc_far, None),
    _errors("dsl_es_near", lambda d: d.es_near, UnitOfTime.SECONDS),
    _errors("dsl_es_far", lambda d: d.es_far, UnitOfTime.SECONDS),
    _errors("dsl_ses_near", lambda d: d.ses_near, UnitOfTime.SECONDS),
    _errors("dsl_ses_far", lambda d: d.ses_far, UnitOfTime.SECONDS),
    _errors("dsl_uas_near", lambda d: d.uas_near, UnitOfTime.SECONDS),
    _errors("dsl_uas_far", lambda d: d.uas_far, UnitOfTime.SECONDS),
)


def dsl_source(
    runtime: VigorRuntimeData,
) -> tuple[DataUpdateCoordinator[Any], Callable[[Any], DslStatus | None]] | None:
    """Pick where DSL values come from: web API, else SNMP xDSL MIBs, else nothing."""
    if runtime.web is not None:
        return runtime.web, lambda data: data
    if runtime.snmp.data and runtime.snmp.data.dsl is not None:
        return runtime.snmp, lambda data: data.dsl
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VigorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    runtime = entry.runtime_data
    snmp_data = runtime.snmp.data
    entities: list[SensorEntity] = [
        VigorSensor(runtime, description)
        for description in SENSORS
        if not description.optional or description.value_fn(snmp_data) is not None
    ]
    if (source := dsl_source(runtime)) is not None:
        coordinator, getter = source
        from_snmp = coordinator is runtime.snmp
        entities.extend(
            VigorDslSensor(coordinator, runtime, description, getter)
            for description in DSL_SENSORS
            if not from_snmp
            or (
                description.snmp_capable
                and description.value_fn(snmp_data.dsl) is not None
            )
        )
    async_add_entities(entities)


class VigorSensor(VigorEntity[VigorSnmpCoordinator], SensorEntity):
    """An SNMP sensor."""

    entity_description: VigorSensorDescription

    def __init__(
        self, runtime: VigorRuntimeData, description: VigorSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(runtime.snmp, runtime, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateValue:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)


class VigorDslSensor(VigorEntity[DataUpdateCoordinator[Any]], SensorEntity):
    """A DSL line sensor (web API or SNMP)."""

    entity_description: VigorDslSensorDescription

    def __init__(
        self,
        coordinator: DataUpdateCoordinator[Any],
        runtime: VigorRuntimeData,
        description: VigorDslSensorDescription,
        getter: Callable[[Any], DslStatus | None],
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, runtime, description.key)
        self.entity_description = description
        self._getter = getter

    @property
    def native_value(self) -> StateValue:
        """Return the state."""
        if self.coordinator.data is None:
            return None
        if (dsl := self._getter(self.coordinator.data)) is None:
            return None
        return self.entity_description.value_fn(dsl)
