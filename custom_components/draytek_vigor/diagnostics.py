"""Diagnostics support for DrayTek Vigor."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import DrayTekConfigEntry
from .const import (
    CONF_COMMUNITY,
    CONF_SSH_PASSWORD,
    CONF_SSH_USERNAME,
    MAX_INTERFACE_INDEX,
    OID_IF_DESCR,
)

TO_REDACT = {CONF_COMMUNITY, CONF_SSH_USERNAME, CONF_SSH_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: DrayTekConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry (helps supporting other models)."""
    runtime = entry.runtime_data
    coordinator = runtime.snmp
    dsl = runtime.dsl
    indexes = range(1, MAX_INTERFACE_INDEX + 1)
    try:
        names = await coordinator.client.async_get(
            [f"{OID_IF_DESCR}.{i}" for i in indexes]
        )
        interfaces = {str(i): n for i, n in zip(indexes, names, strict=True) if n}
    except Exception as err:  # noqa: BLE001
        interfaces = {"error": str(err)}
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "interface_index": coordinator.interface_index,
        "interfaces": interfaces,
        "data": asdict(coordinator.data) if coordinator.data else None,
        "dsl": None
        if dsl is None
        else {
            "last_update_success": dsl.last_update_success,
            "last_exception": repr(dsl.last_exception) if dsl.last_exception else None,
            "data": asdict(dsl.data) if dsl.data else None,
        },
    }
