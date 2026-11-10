"""Data update coordinators for DrayTek Vigor Monitor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import re
import time
from typing import TYPE_CHECKING

from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DSL_SCAN_INTERVAL,
    CONF_INTERFACE_INDEX,
    CURR_ATTAINABLE_RATE,
    CURR_ATTENUATION,
    CURR_SNR_MARGIN,
    DEFAULT_DSL_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    DSL_IF_TYPES,
    IF_OPER_STATUS_UP,
    MAX_INTERFACE_INDEX,
    OID_ATUC_CURR,
    OID_ATUR_CURR,
    OID_DRAYTEK_FIRMWARE,
    OID_DRAYTEK_MODEL,
    OID_HR_PROCESSOR_LOAD,
    OID_IF_HC_IN_OCTETS,
    OID_IF_HC_OUT_OCTETS,
    OID_IF_IN_OCTETS,
    OID_IF_LAST_CHANGE,
    OID_IF_OPER_STATUS,
    OID_IF_OUT_OCTETS,
    OID_IF_TYPE,
    OID_MEMORY_USAGE,
    OID_SYS_DESCR,
    OID_SYS_UPTIME,
    OID_UCD_CPU_IDLE,
    OID_XDSL2_ACT_DATA_RATE,
)
from .protocol import DslStatus, dsl_status_from_mib
from .snmp_client import VigorSnmpClient, VigorSnmpError
from .web_client import VigorWebAuthError, VigorWebClient, VigorWebError

if TYPE_CHECKING:
    from . import VigorConfigEntry

_LOGGER = logging.getLogger(__name__)

_COUNTER32_WRAP = 2**32
# Ignore rates above 100 Gbit/s - that is a counter reset, not traffic.
_MAX_PLAUSIBLE_RATE_MBIT = 100_000
# Only move a derived timestamp when it drifts more than this (avoids jitter).
_SINCE_TOLERANCE = timedelta(seconds=90)

_AUTH_FAILURES_BEFORE_REAUTH = 3

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


def stable_since(current: datetime | None, seconds_ago: float | None) -> datetime | None:
    """Turn an uptime into a timestamp that only moves on a real change."""
    if seconds_ago is None:
        return current
    since = (dt_util.utcnow() - timedelta(seconds=seconds_ago)).replace(
        second=0, microsecond=0
    )
    if current is None or abs(since - current) > _SINCE_TOLERANCE:
        return since
    return current


def counter_delta(previous: int | None, current: int | None) -> int | None:
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


@dataclass(slots=True)
class VigorSnmpData:
    """Values read via SNMP."""

    sys_descr: str | None
    model: str | None
    firmware: str | None
    memory_usage: int | None
    cpu_load: int | None
    boot_time: datetime | None
    link_up: bool | None
    link_since: datetime | None
    bytes_in: int | None
    bytes_out: int | None
    rate_in: float | None  # Mbit/s
    rate_out: float | None  # Mbit/s
    dsl: DslStatus | None  # xDSL MIBs, DrayOS 4 only


class VigorSnmpCoordinator(DataUpdateCoordinator[VigorSnmpData]):
    """Poll the Vigor via SNMP."""

    config_entry: VigorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VigorConfigEntry,
        client: VigorSnmpClient,
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
        self._discovered = False
        self._cpu_oid: str | None = None
        self._cpu_from_idle = False
        self._dsl_if_index: int | None = None
        self._prev_counters: tuple[float, int | None, int | None] | None = None
        self._boot_time: datetime | None = None
        self._link_since: datetime | None = None

    async def _async_discover(self) -> None:
        """One-time probing of optional values (CPU OID, DSL interface)."""
        found = await self.client.async_get_next(OID_HR_PROCESSOR_LOAD)
        if found is not None and isinstance(found[1], int):
            self._cpu_oid = found[0]
        else:
            (idle,) = await self.client.async_get([OID_UCD_CPU_IDLE])
            if isinstance(idle, int):
                self._cpu_oid, self._cpu_from_idle = OID_UCD_CPU_IDLE, True

        indexes = range(1, MAX_INTERFACE_INDEX + 1)
        types = await self.client.async_get([f"{OID_IF_TYPE}.{i}" for i in indexes])
        self._dsl_if_index = next(
            (i for i, t in zip(indexes, types, strict=True) if t in DSL_IF_TYPES), None
        )
        _LOGGER.debug(
            "Discovery: cpu_oid=%s (idle=%s), dsl_if_index=%s",
            self._cpu_oid,
            self._cpu_from_idle,
            self._dsl_if_index,
        )
        self._discovered = True

    def _oids(self) -> dict[str, str]:
        idx = self.interface_index
        oids = {
            "sys_descr": OID_SYS_DESCR,
            "uptime": OID_SYS_UPTIME,
            "memory": OID_MEMORY_USAGE,
            "dt_model": OID_DRAYTEK_MODEL,
            "dt_firmware": OID_DRAYTEK_FIRMWARE,
            "oper_status": f"{OID_IF_OPER_STATUS}.{idx}",
            "last_change": f"{OID_IF_LAST_CHANGE}.{idx}",
            "hc_in": f"{OID_IF_HC_IN_OCTETS}.{idx}",
            "hc_out": f"{OID_IF_HC_OUT_OCTETS}.{idx}",
            "in": f"{OID_IF_IN_OCTETS}.{idx}",
            "out": f"{OID_IF_OUT_OCTETS}.{idx}",
        }
        if self._cpu_oid:
            oids["cpu"] = self._cpu_oid
        if (dsl := self._dsl_if_index) is not None:
            oids |= {
                "dsl_rate_down": f"{OID_XDSL2_ACT_DATA_RATE}.{dsl}.1",
                "dsl_rate_up": f"{OID_XDSL2_ACT_DATA_RATE}.{dsl}.2",
                "dsl_att_rate_down": f"{OID_ATUC_CURR}.{CURR_ATTAINABLE_RATE}.{dsl}",
                "dsl_att_rate_up": f"{OID_ATUR_CURR}.{CURR_ATTAINABLE_RATE}.{dsl}",
                "dsl_snr_down": f"{OID_ATUC_CURR}.{CURR_SNR_MARGIN}.{dsl}",
                "dsl_snr_up": f"{OID_ATUR_CURR}.{CURR_SNR_MARGIN}.{dsl}",
                "dsl_atten_down": f"{OID_ATUC_CURR}.{CURR_ATTENUATION}.{dsl}",
                "dsl_atten_up": f"{OID_ATUR_CURR}.{CURR_ATTENUATION}.{dsl}",
            }
        return oids

    async def _async_update_data(self) -> VigorSnmpData:
        try:
            if not self._discovered:
                await self._async_discover()
            oids = self._oids()
            raw = await self.client.async_get(list(oids.values()))
        except VigorSnmpError as err:
            self._prev_counters = None
            raise UpdateFailed(f"Error talking to {self.client.host}: {err}") from err
        values = dict(zip(oids, raw, strict=True))

        model, firmware = parse_sys_descr(values["sys_descr"])
        model = model or _str(values["dt_model"])
        firmware = firmware or _str(values["dt_firmware"])

        # Prefer the 64-bit counters, fall back to 32-bit ones.
        bytes_in = values["hc_in"] if values["hc_in"] is not None else values["in"]
        bytes_out = values["hc_out"] if values["hc_out"] is not None else values["out"]

        now = time.monotonic()
        rate_in = rate_out = None
        if self._prev_counters is not None:
            prev_time, prev_in, prev_out = self._prev_counters
            elapsed = now - prev_time
            if elapsed >= 1:
                rate_in = _rate(counter_delta(prev_in, bytes_in), elapsed)
                rate_out = _rate(counter_delta(prev_out, bytes_out), elapsed)
        self._prev_counters = (now, bytes_in, bytes_out)

        uptime = values["uptime"]
        self._boot_time = stable_since(
            self._boot_time, None if uptime is None else uptime / 100
        )

        oper_status = values["oper_status"]
        link_up = None if oper_status is None else oper_status == IF_OPER_STATUS_UP
        last_change = values["last_change"]
        if link_up and isinstance(uptime, int) and isinstance(last_change, int):
            # ifLastChange = sysUpTime when the link entered its current state.
            self._link_since = stable_since(
                self._link_since, max(uptime - last_change, 0) / 100
            )
        elif link_up is False:
            self._link_since = None

        cpu = values.get("cpu")
        if isinstance(cpu, int) and self._cpu_from_idle:
            cpu = 100 - cpu

        return VigorSnmpData(
            sys_descr=values["sys_descr"],
            model=model,
            firmware=firmware,
            memory_usage=values["memory"],
            cpu_load=cpu if isinstance(cpu, int) else None,
            boot_time=self._boot_time,
            link_up=link_up,
            link_since=self._link_since,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            rate_in=rate_in,
            rate_out=rate_out,
            dsl=dsl_status_from_mib(
                rate_down_bps=values.get("dsl_rate_down"),
                rate_up_bps=values.get("dsl_rate_up"),
                attainable_down_bps=values.get("dsl_att_rate_down"),
                attainable_up_bps=values.get("dsl_att_rate_up"),
                snr_down=values.get("dsl_snr_down"),
                snr_up=values.get("dsl_snr_up"),
                attenuation_down=values.get("dsl_atten_down"),
                attenuation_up=values.get("dsl_atten_up"),
            ),
        )


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _rate(delta_bytes: int | None, elapsed: float) -> float | None:
    if delta_bytes is None:
        return None
    mbit = delta_bytes * 8 / elapsed / 1_000_000
    if mbit > _MAX_PLAUSIBLE_RATE_MBIT:
        return None
    return round(mbit, 2)


class VigorWebCoordinator(DataUpdateCoordinator[DslStatus]):
    """Poll the DSL status via the DrayOS 5 web API (optional)."""

    config_entry: VigorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: VigorConfigEntry,
        client: VigorWebClient,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_dsl",
            update_interval=timedelta(
                seconds=entry.options.get(
                    CONF_DSL_SCAN_INTERVAL, DEFAULT_DSL_SCAN_INTERVAL
                )
            ),
        )
        self.client = client
        self._auth_failures = 0

    async def _async_update_data(self) -> DslStatus:
        try:
            status = await self.client.async_get_dsl_status()
        except VigorWebAuthError as err:
            # The device gives no reason for a rejected login; "too many
            # sessions" looks the same as a wrong password. Only ask the user
            # for new credentials after several rejections in a row.
            self._auth_failures += 1
            if self._auth_failures >= _AUTH_FAILURES_BEFORE_REAUTH:
                raise ConfigEntryAuthFailed(f"Web login rejected: {err}") from err
            raise UpdateFailed(f"Web login rejected: {err}") from err
        except VigorWebError as err:
            raise UpdateFailed(f"Error reading DSL status: {err}") from err
        self._auth_failures = 0
        return status


@dataclass(slots=True)
class VigorRuntimeData:
    """Objects stored in the config entry while it is loaded."""

    snmp: VigorSnmpCoordinator
    web: VigorWebCoordinator | None
