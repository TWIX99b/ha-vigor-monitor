"""Diagnostics support for DrayTek Vigor Monitor (helps supporting other models)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import VigorConfigEntry
from .const import (
    CONF_COMMUNITY,
    CONF_WEB_PASSWORD,
    CONF_WEB_USERNAME,
    MAX_INTERFACE_INDEX,
    OID_IF_DESCR,
    OID_IF_TYPE,
)

TO_REDACT = {CONF_COMMUNITY, CONF_WEB_USERNAME, CONF_WEB_PASSWORD}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VigorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime = entry.runtime_data
    snmp = runtime.snmp
    web = runtime.web

    indexes = list(range(1, MAX_INTERFACE_INDEX + 1))
    try:
        values = await snmp.client.async_get(
            [f"{OID_IF_DESCR}.{i}" for i in indexes]
            + [f"{OID_IF_TYPE}.{i}" for i in indexes]
        )
        names, types = values[: len(indexes)], values[len(indexes) :]
        interfaces: dict[str, Any] = {
            str(i): {"name": n, "type": t}
            for i, n, t in zip(indexes, names, types, strict=True)
            if n
        }
    except Exception as err:  # noqa: BLE001
        interfaces = {"error": str(err)}

    web_info: dict[str, Any] | None = None
    if web is not None:
        dsl = web.data
        web_info = {
            "last_update_success": web.last_update_success,
            "last_exception": repr(web.last_exception) if web.last_exception else None,
            "data": None if dsl is None else {**asdict(dsl), "synced": dsl.synced},
        }

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "interface_index": snmp.interface_index,
        "interfaces": interfaces,
        "snmp": asdict(snmp.data) if snmp.data else None,
        "web": web_info,
    }
