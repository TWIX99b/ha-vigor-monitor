"""Data update coordinator for DrayTek Vigor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
import time
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INTERFACE_INDEX,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    IF_OPER_STATUS_UP,
    OID_IF_HC_IN_OCTETS,
    OID_IF_HC_OUT_OCTETS,
    OID_IF_IN_OCTETS,
    OID_IF_OPER_STATUS,
    OID_IF_OUT_OCTETS,
    OID_MEMORY_USAGE,
    OID_SYS_DESCR,
    OID_SYS_UPTIME,
)
from .snmp_client import DrayTekError, DrayTekSnmpClient

if TYPE_CHECKING:
    from . import DrayTekConfigEntry

_LOGGER = logging.getLogger(__name__)

_COUNTER32_WRAP = 2**32
# Ignore rates above 100 Gbit/s - that is a counter reset, not traffic.
_MAX_PLAUSIBLE_RATE_MBIT = 100_000
# Only move the boot time when it drifts more than this (avoids minute jitter).
_BOOT_TIME_TOLERANCE = timedelta(seconds=90)

_MODEL_RE = re.compile(r"Router Model:\s*([^,]+)", re.IGNORECASE)
_VERSION_RE = re.compile(r"Version:\s*([^,]+)", re.IGNORECASE)


def parse_sys_descr(descr: str | None) -> tuple[str | None, str | None]:
    """Extract model and firmware from a DrayTek sysDescr string.

    Example: "DrayTek Corporation, Router Model: Vigor167, Version: 5.2.9, ..."
    """
    if not descr:
        return None, None
    model = m.group(1).strip() if (m := _MODEL_RE.search(descr)) else None
    version = v.group(1).strip() if (v := _VERSION_RE.search(descr)) else None
    return model, version


@dataclass(slots=True)
class DrayTekData:
    """Values read from the device."""

    sys_descr: str | None
    model: str | None
    firmware: str | None
    memory_usage: int | None
    boot_time: datetime | None
    link_up: bool | None
    bytes_in: int | None
    bytes_out: int | None
    rate_in: float | None  # Mbit/s
    rate_out: float | None  # Mbit/s


def _counter_delta(previous: int | None, current: int | None) -> int | None:
    """Return the increase of a counter, handling a 32-bit wrap."""
    if previous is None or current is None:
        return None
    delta = current - previous
    if delta >= 0:
        return delta
    if previous < _COUNTER32_WRAP:
        # 32-bit counter wrapped (DrayOS 5 reports 32-bit values even on ifHC*).
        return delta + _COUNTER32_WRAP
    return None  # 64-bit counter went backwards: device reboot / counter reset


class DrayTekCoordinator(DataUpdateCoordinator[DrayTekData]):
    """Poll the DrayTek Vigor via SNMP."""

    config_entry: DrayTekConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: DrayTekConfigEntry,
        client: DrayTekSnmpClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.interface_index: int = int(
            entry.options.get(CONF_INTERFACE_INDEX, entry.data[CONF_INTERFACE_INDEX])
        )
        self._prev_counters: tuple[float, int | None, int | None] | None = None
        self._boot_time: datetime | None = None

    def _oids(self) -> dict[str, str]:
        idx = self.interface_index
        return {
            "sys_descr": OID_SYS_DESCR,
            "uptime": OID_SYS_UPTIME,
            "memory": OID_MEMORY_USAGE,
            "oper_status": f"{OID_IF_OPER_STATUS}.{idx}",
            "hc_in": f"{OID_IF_HC_IN_OCTETS}.{idx}",
            "hc_out": f"{OID_IF_HC_OUT_OCTETS}.{idx}",
            "in": f"{OID_IF_IN_OCTETS}.{idx}",
            "out": f"{OID_IF_OUT_OCTETS}.{idx}",
        }

    async def _async_update_data(self) -> DrayTekData:
        oids = self._oids()
        try:
            raw = await self.client.async_get(list(oids.values()))
        except DrayTekError as err:
            self._prev_counters = None
            raise UpdateFailed(f"Error talking to {self.client.host}: {err}") from err
        values = dict(zip(oids, raw, strict=True))

        model, firmware = parse_sys_descr(values["sys_descr"])

        # Prefer the 64-bit counters, fall back to 32-bit ones.
        bytes_in = values["hc_in"] if values["hc_in"] is not None else values["in"]
        bytes_out = values["hc_out"] if values["hc_out"] is not None else values["out"]

        now = time.monotonic()
        rate_in = rate_out = None
        if self._prev_counters is not None:
            prev_time, prev_in, prev_out = self._prev_counters
            elapsed = now - prev_time
            if elapsed >= 1:
                rate_in = self._rate(_counter_delta(prev_in, bytes_in), elapsed)
                rate_out = self._rate(_counter_delta(prev_out, bytes_out), elapsed)
        self._prev_counters = (now, bytes_in, bytes_out)

        oper_status = values["oper_status"]
        return DrayTekData(
            sys_descr=values["sys_descr"],
            model=model,
            firmware=firmware,
            memory_usage=values["memory"],
            boot_time=self._calc_boot_time(values["uptime"]),
            link_up=None if oper_status is None else oper_status == IF_OPER_STATUS_UP,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            rate_in=rate_in,
            rate_out=rate_out,
        )

    @staticmethod
    def _rate(delta_bytes: int | None, elapsed: float) -> float | None:
        if delta_bytes is None:
            return None
        mbit = delta_bytes * 8 / elapsed / 1_000_000
        if mbit > _MAX_PLAUSIBLE_RATE_MBIT:
            return None
        return round(mbit, 2)

    def _calc_boot_time(self, uptime_ticks: int | None) -> datetime | None:
        """sysUpTime is in 1/100 s; turn it into a stable boot timestamp."""
        if uptime_ticks is None:
            return self._boot_time
        boot = (dt_util.utcnow() - timedelta(seconds=uptime_ticks / 100)).replace(
            second=0, microsecond=0
        )
        if self._boot_time is None or abs(boot - self._boot_time) > _BOOT_TIME_TOLERANCE:
            self._boot_time = boot
        return self._boot_time
