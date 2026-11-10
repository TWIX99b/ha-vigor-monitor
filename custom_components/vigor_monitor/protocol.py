"""DSL status model and the wire format of the DrayOS 5 web API.

Pure functions only (no Home Assistant, no aiohttp), so the tests run without them.

Web API ("v5" firmware, e.g. Vigor167), protocol as documented by
SuperQ/draytek_exporter (Apache-2.0, see NOTICE), reimplemented here:

* POST form to /cgi-bin/webproc.cgi with the fields pid, op and ct.
* ct and the answer are JSON in base64 whose padding is moved to the front:
  the number of "=" becomes the first character, the trailing "=" are dropped.
* HTTP status is always 200; success is {"rid": "0000"} in the payload.
* Login: pid "event", op "552", password as SHA-512 hex digest.
  Logout: pid "event", op "553".
* CSRF: the device sends a token in the x-csrf-token response header; the
  client returns the latest one as that header and as the form field _token.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

WEB_PATH = "/cgi-bin/webproc.cgi"
RID_OK = "0000"
CSRF_HEADER = "x-csrf-token"

EVENT_PID = "event"
LOGIN_OP = "552"
LOGOUT_OP = "553"
DSL_PID = "0MONITORING_DSL_GENERAL"
DSL_OP = "501"
DSL_QUERY: dict[str, Any] = {
    "param": [],
    "ct": [
        {"0MONITORING_DSL_GENERAL": []},
        {"1MON_DSL_STREAM_TABLE": []},
        {"1MON_DSL_END_TABLE": []},
    ],
}

SYNCED_STATUS = "showtime"


class ProtocolError(Exception):
    """The answer could not be decoded or parsed."""


@dataclass(slots=True)
class DslStatus:
    """DSL line values, independent of the source (web API or SNMP)."""

    status: str | None = None
    mode: str | None = None
    profile: str | None = None
    annex: str | None = None
    dsl_version: str | None = None
    # Rates in kbit/s.
    rate_down: float | None = None
    rate_up: float | None = None
    attainable_down: float | None = None
    attainable_up: float | None = None
    # dB. Attenuation: near end = downstream, far end = upstream.
    snr_down: float | None = None
    snr_up: float | None = None
    attenuation_down: float | None = None
    attenuation_up: float | None = None
    # Error counters (reset on resync). Near end = measured by the Vigor.
    crc_near: int | None = None
    crc_far: int | None = None
    es_near: int | None = None
    es_far: int | None = None
    ses_near: int | None = None
    ses_far: int | None = None
    uas_near: int | None = None
    uas_far: int | None = None
    source: str = "web"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def synced(self) -> bool | None:
        """True while the line is in showtime."""
        if self.status is None:
            return None
        return SYNCED_STATUS in self.status.lower()

    @property
    def mode_profile(self) -> str | None:
        """'VDSL2 35b'."""
        parts = [
            p for p in (self.mode, self.profile) if p and p.strip() not in ("", "--")
        ]
        return " ".join(parts) or None


def encode(payload: dict[str, Any]) -> str:
    """JSON -> base64 with the padding count in front."""
    raw = base64.b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    stripped = raw.rstrip("=")
    return f"{len(raw) - len(stripped)}{stripped}"


def decode(body: str) -> dict[str, Any]:
    """Inverse of encode(); raises ProtocolError for anything else (e.g. HTML)."""
    body = body.strip()
    if not body or body[0] not in "012":
        raise ProtocolError("answer is not prefix-padded base64")
    try:
        raw = base64.b64decode(body[1:] + "=" * int(body[0]), validate=True)
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as err:
        raise ProtocolError(f"cannot decode answer: {err}") from err
    if not isinstance(data, dict):
        raise ProtocolError("answer is not a JSON object")
    return data


def is_ok(data: dict[str, Any]) -> bool:
    """True if the device accepted the request."""
    return str(data.get("rid", "")).split("@")[0] == RID_OK


def login_payload(username: str, password: str) -> dict[str, Any]:
    """Login request body; the password is sent as SHA-512 hex digest."""
    digest = hashlib.sha512(password.encode()).hexdigest()
    return {"param": [], "ct": [{"Name": username, "Password": digest, "locales": "en"}]}


def logout_payload(username: str) -> dict[str, Any]:
    """Logout request body."""
    return {"param": [], "ct": [{"Username": username}]}


_RATE_FACTORS = {"bps": 0.001, "kbps": 1, "mbps": 1000, "gbps": 1_000_000}


def _number(value: Any) -> float | None:
    """'6.2 dB' -> 6.2, '12 s' -> 12, '7' -> 7, '--' -> None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        number = float(value.split()[0])
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def _int(value: Any) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _kbps(value: Any) -> float | None:
    """Rate in kbit/s: '124999 kbps' -> 124999, '116.8 Mbps' -> 116800."""
    number = _number(value)
    if number is None or not isinstance(value, str):
        return number
    parts = value.split()
    factor = _RATE_FACTORS.get(parts[1].lower()) if len(parts) > 1 else 1
    if factor is None:
        return None
    result = number * factor
    return int(result) if float(result).is_integer() else round(result, 3)


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def parse_web_dsl_status(data: dict[str, Any]) -> DslStatus:
    """Parse the answer to the DSL_PID/DSL_OP request."""
    try:
        general = data["ct"][0][DSL_PID]
        setting = next(e for e in general if e.get("Name") == "Setting")
    except (KeyError, IndexError, TypeError, StopIteration, AttributeError) as err:
        raise ProtocolError("no DSL 'Setting' block in answer") from err

    status = DslStatus(
        status=_text(setting.get("Status")),
        mode=_text(setting.get("Mode")),
        profile=_text(setting.get("Profile")),
        annex=_text(setting.get("Annex")),
        dsl_version=_text(setting.get("DSL_Version")),
        source="web",
        raw=setting,
    )

    for row in setting.get("Stream_Table") or []:
        name = str(row.get("Name", "")).strip().lower()
        down, up = row.get("Downstream"), row.get("Upstream")
        if name == "actual rate":
            status.rate_down, status.rate_up = _kbps(down), _kbps(up)
        elif name == "attainable rate":
            status.attainable_down, status.attainable_up = _kbps(down), _kbps(up)
        elif name == "snr margin":
            status.snr_down, status.snr_up = _number(down), _number(up)

    for row in setting.get("End_Table") or []:
        name = str(row.get("Name", "")).strip().lower()
        near, far = row.get("Near_End"), row.get("Far_End")
        if name == "attenuation":
            status.attenuation_down, status.attenuation_up = _number(near), _number(far)
        elif name == "crc":
            status.crc_near, status.crc_far = _int(near), _int(far)
        elif name == "es":
            status.es_near, status.es_far = _int(near), _int(far)
        elif name == "ses":
            status.ses_near, status.ses_far = _int(near), _int(far)
        elif name == "uas":
            status.uas_near, status.uas_far = _int(near), _int(far)

    return status


def dsl_status_from_mib(
    *,
    rate_down_bps: int | None,
    rate_up_bps: int | None,
    attainable_down_bps: int | None,
    attainable_up_bps: int | None,
    snr_down: int | None,
    snr_up: int | None,
    attenuation_down: int | None,
    attenuation_up: int | None,
) -> DslStatus | None:
    """Build a DslStatus from xDSL MIB values (DrayOS 4). None if nothing answered."""
    values = (
        rate_down_bps,
        rate_up_bps,
        attainable_down_bps,
        attainable_up_bps,
        snr_down,
        snr_up,
        attenuation_down,
        attenuation_up,
    )
    if all(v is None for v in values):
        return None

    def kbps(bps: int | None) -> float | None:
        return None if bps is None else round(bps / 1000, 3)

    return DslStatus(
        rate_down=kbps(rate_down_bps),
        rate_up=kbps(rate_up_bps),
        attainable_down=kbps(attainable_down_bps),
        attainable_up=kbps(attainable_up_bps),
        snr_down=snr_down,
        snr_up=snr_up,
        attenuation_down=attenuation_down,
        attenuation_up=attenuation_up,
        source="snmp",
    )
