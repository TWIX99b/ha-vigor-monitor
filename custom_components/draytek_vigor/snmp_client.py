"""Small async SNMP (v2c) client for DrayTek Vigor devices."""

from __future__ import annotations

from collections.abc import Sequence
import logging
from typing import Any

from pysnmp.hlapi.asyncio import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    get_cmd,
)
from pysnmp.proto import rfc1902, rfc1905

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Keep a single PDU reasonably small; DrayTek agents are slow with big requests.
_MAX_OIDS_PER_REQUEST = 16

_INTEGER_TYPES = (
    rfc1902.Integer,
    rfc1902.Integer32,
    rfc1902.Unsigned32,
    rfc1902.Gauge32,
    rfc1902.Counter32,
    rfc1902.Counter64,
    rfc1902.TimeTicks,
)
_MISSING_TYPES = (rfc1905.NoSuchObject, rfc1905.NoSuchInstance, rfc1905.EndOfMibView)


class DrayTekError(Exception):
    """Generic SNMP error."""


class DrayTekConnectionError(DrayTekError):
    """The device did not answer (timeout, wrong community, unreachable)."""


async def _async_get_engine(hass: HomeAssistant) -> SnmpEngine:
    """Return a shared SNMP engine.

    Prefer the engine of Home Assistant's own SNMP integration: it is created in
    the executor with the MIBs preloaded, so no blocking I/O happens in the loop.
    """
    try:
        from homeassistant.components.snmp.util import (  # noqa: PLC0415
            async_get_snmp_engine,
        )
    except ImportError:  # pragma: no cover - fallback if core internals change
        return await hass.async_add_executor_job(SnmpEngine)
    return await async_get_snmp_engine(hass)


def _convert(value: Any) -> Any:
    """Convert a pysnmp value into a plain Python value (None if missing)."""
    if isinstance(value, _MISSING_TYPES):
        return None
    if isinstance(value, _INTEGER_TYPES):
        return int(value)
    if isinstance(value, rfc1902.OctetString):
        return value.asOctets().decode("utf-8", errors="replace").strip("\x00 \r\n\t")
    if isinstance(value, rfc1902.ObjectName):
        return str(value)
    return value.prettyPrint() if hasattr(value, "prettyPrint") else value


class DrayTekSnmpClient:
    """Read values from a DrayTek Vigor via SNMP v2c."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        community: str,
        timeout: float = 3,
        retries: int = 1,
    ) -> None:
        """Initialise the client."""
        self._hass = hass
        self._host = host
        self._port = port
        self._auth = CommunityData(community, mpModel=1)  # mpModel=1 -> SNMP v2c
        self._timeout = timeout
        self._retries = retries
        self._engine: SnmpEngine | None = None
        self._target: UdpTransportTarget | None = None

    @property
    def host(self) -> str:
        """Return the host."""
        return self._host

    async def _async_prepare(self) -> tuple[SnmpEngine, UdpTransportTarget]:
        if self._engine is None:
            self._engine = await _async_get_engine(self._hass)
        if self._target is None:
            try:
                self._target = await UdpTransportTarget.create(
                    (self._host, self._port),
                    timeout=self._timeout,
                    retries=self._retries,
                )
            except Exception as err:  # noqa: BLE001 - DNS errors etc.
                raise DrayTekConnectionError(
                    f"Cannot resolve {self._host}: {err}"
                ) from err
        return self._engine, self._target

    async def async_get(self, oids: Sequence[str]) -> list[Any]:
        """Fetch the given OIDs. Missing OIDs are returned as None."""
        engine, target = await self._async_prepare()
        results: list[Any] = []
        for start in range(0, len(oids), _MAX_OIDS_PER_REQUEST):
            chunk = oids[start : start + _MAX_OIDS_PER_REQUEST]
            error_indication, error_status, error_index, var_binds = await get_cmd(
                engine,
                self._auth,
                target,
                ContextData(),
                *(ObjectType(ObjectIdentity(oid)) for oid in chunk),
                lookupMib=False,
            )
            if error_indication:
                raise DrayTekConnectionError(str(error_indication))
            if error_status:
                # SNMPv1-style error (e.g. noSuchName): fall back to one-by-one.
                _LOGGER.debug(
                    "SNMP error %s at %s, retrying OIDs individually",
                    error_status.prettyPrint(),
                    error_index,
                )
                results.extend([await self._async_get_single(oid) for oid in chunk])
                continue
            results.extend(_convert(value) for _, value in var_binds)
        return results

    async def _async_get_single(self, oid: str) -> Any:
        engine, target = await self._async_prepare()
        error_indication, error_status, _, var_binds = await get_cmd(
            engine,
            self._auth,
            target,
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
            lookupMib=False,
        )
        if error_indication:
            raise DrayTekConnectionError(str(error_indication))
        if error_status or not var_binds:
            return None
        return _convert(var_binds[0][1])
