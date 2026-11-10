"""Tests for the pure protocol module (no Home Assistant needed)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "vigor_protocol", _ROOT / "custom_components/vigor_monitor/protocol.py"
)
protocol = importlib.util.module_from_spec(_SPEC)
sys.modules["vigor_protocol"] = protocol
_SPEC.loader.exec_module(protocol)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> dict:
    data = json.loads((FIXTURES / name).read_text())
    data.pop("_comment", None)
    return data


@pytest.mark.parametrize(
    "payload", [{"a": 1}, {"ab": 1}, {"abc": 1}, protocol.DSL_QUERY, {}]
)
def test_encode_decode_roundtrip(payload: dict) -> None:
    encoded = protocol.encode(payload)
    assert encoded[0] in "012"
    assert not encoded.endswith("=")
    assert protocol.decode(encoded) == payload


def test_encode_padding_prefix() -> None:
    # {"a":1} -> eyJhIjoxfQ== -> two "=" moved to the front
    assert protocol.encode({"a": 1}) == "2eyJhIjoxfQ"
    assert base64.b64decode("eyJhIjoxfQ==") == b'{"a":1}'


@pytest.mark.parametrize("body", ["", "<html>login</html>", "9abc", "2!!!", "0" + "W10"])
def test_decode_rejects_garbage(body: str) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(body)


def test_login_payload_hashes_password() -> None:
    payload = protocol.login_payload("admin", "secret")
    entry = payload["ct"][0]
    assert entry["Name"] == "admin"
    assert entry["Password"] == hashlib.sha512(b"secret").hexdigest()
    assert "secret" not in json.dumps(payload)


def test_is_ok() -> None:
    assert protocol.is_ok({"rid": "0000"})
    assert protocol.is_ok({"rid": "0000@OK"})
    assert not protocol.is_ok({"rid": "2033"})
    assert not protocol.is_ok({})


def test_parse_synced_line() -> None:
    """Real capture from a Vigor167 (fw 5.2.9) on a synced VDSL2 line."""
    status = protocol.parse_web_dsl_status(_fixture("dsl_status_synced_fw5.json"))
    assert status.status == "Showtime"
    assert status.synced is True
    assert status.mode_profile == "VDSL2 35b"
    assert status.annex == "ANNEX B"
    assert status.dsl_version == "5.12.31.0_B_A60901"
    assert (status.rate_down, status.rate_up) == (124999, 42438)
    # The device writes "Kbps" here (capital K) and "kbps" for the actual rate.
    assert (status.attainable_down, status.attainable_up) == (182771, 43761)
    assert (status.snr_down, status.snr_up) == (9.8, 8.1)
    assert (status.attenuation_down, status.attenuation_up) == (11.8, 3.1)
    assert (status.crc_near, status.crc_far) == (76, 7)
    assert (status.es_near, status.es_far) == (82, 5)
    assert (status.ses_near, status.ses_far) == (49, 0)
    assert (status.uas_near, status.uas_far) == (138, 138)
    assert status.source == "web"


def test_parse_idle_line() -> None:
    status = protocol.parse_web_dsl_status(_fixture("dsl_status_idle_fw5.json"))
    assert status.synced is False
    assert status.status == "Idle"
    assert status.mode_profile == "DSL"
    assert status.annex is None
    assert status.rate_down is None and status.snr_down is None


def test_parse_rate_units() -> None:
    data = _fixture("dsl_status_synced_fw5.json")
    rows = data["ct"][0][protocol.DSL_PID][0]["Stream_Table"]
    rows[0]["Downstream"] = "116.8 Mbps"
    rows[0]["Upstream"] = "--"
    status = protocol.parse_web_dsl_status(data)
    assert status.rate_down == 116800
    assert status.rate_up is None


@pytest.mark.parametrize(
    "data", [{}, {"ct": []}, {"ct": [{"0MONITORING_DSL_GENERAL": []}]}, {"ct": "x"}]
)
def test_parse_missing_block(data: dict) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_web_dsl_status(data)


def test_dsl_from_mib() -> None:
    assert protocol.dsl_status_from_mib(
        rate_down_bps=None,
        rate_up_bps=None,
        attainable_down_bps=None,
        attainable_up_bps=None,
        snr_down=None,
        snr_up=None,
        attenuation_down=None,
        attenuation_up=None,
    ) is None
    status = protocol.dsl_status_from_mib(
        rate_down_bps=51_385_000,
        rate_up_bps=10_047_000,
        attainable_down_bps=None,
        attainable_up_bps=None,
        snr_down=10,
        snr_up=7,
        attenuation_down=None,
        attenuation_up=None,
    )
    assert status is not None
    assert (status.rate_down, status.rate_up) == (51385, 10047)
    assert status.snr_down == 10
    assert status.synced is None
    assert status.source == "snmp"
