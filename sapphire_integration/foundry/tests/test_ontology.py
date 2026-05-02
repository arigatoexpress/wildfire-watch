"""Tests for the Foundry ontology bindings.

Round-trip serialization, adapter correctness, schema-version pinning.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from sapphire_integration.foundry import (  # noqa: E402
    SCHEMA_VERSION,
    BatteryCycle,
    Drone,
    FireDepartmentUnit,
    FlightLog,
    WildfireSignal,
    Zone,
    from_foundry_json,
    to_foundry_json,
    wildfire_signal_from_v1,
    zone_from_geojson_feature,
)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------


def test_schema_version_matches_v1() -> None:
    assert SCHEMA_VERSION == "1.0.0"


# ---------------------------------------------------------------------------
# Drone
# ---------------------------------------------------------------------------


def test_drone_roundtrip() -> None:
    d = Drone(
        drone_id="wfw-unit01",
        airframe_class="mavic_mini_2",
        rpic_pilot_license_id=None,
        insurance_policy_ref=None,
        maintenance_log_uri=None,
    )
    text = to_foundry_json(d)
    parsed = json.loads(text)
    assert parsed["type"] == "wfw.Drone"
    assert parsed["primaryKey"] == "wfw-unit01"
    assert parsed["properties"]["airframe_class"] == "mavic_mini_2"

    back = from_foundry_json(text)
    assert isinstance(back, Drone)
    assert back == d


# ---------------------------------------------------------------------------
# Zone
# ---------------------------------------------------------------------------


def test_zone_from_geojson_feature() -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "zone_id": "slate-river-drainage",
            "fuel_load_class": "high",
            "primary_risk": "beetle-kill spruce/fir",
            "elevation_min_m": 2743,
            "elevation_max_m": 3200,
        },
        "geometry": {"type": "Polygon", "coordinates": [[]]},
    }
    z = zone_from_geojson_feature(feature, corridor="gunnison-crested-butte-corridor")
    assert z.zone_id == "slate-river-drainage"
    assert z.corridor == "gunnison-crested-butte-corridor"
    assert z.fuel_load_class == "high"
    assert z.elevation_min_m == 2743
    assert not z.is_exclusion


def test_zone_from_geojson_with_exclusion() -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "zone_id": "west-elk-wilderness-exclusion",
            "fuel_load_class": "high",
            "primary_risk": "regulatory",
            "elevation_min_m": 2500,
            "elevation_max_m": 3900,
            "exclusion": True,
            "regulatory_basis": "36 CFR 261.16",
        },
        "geometry": {"type": "Polygon", "coordinates": [[]]},
    }
    z = zone_from_geojson_feature(feature, corridor="gunnison-crested-butte-corridor")
    assert z.is_exclusion is True
    assert z.regulatory_basis == "36 CFR 261.16"


def test_zone_roundtrip() -> None:
    z = Zone(
        zone_id="slate-river-drainage",
        corridor="gunnison-crested-butte-corridor",
        polygon_geojson={"type": "Polygon", "coordinates": []},
        fuel_load_class="high",
        primary_risk="beetle-kill",
        elevation_min_m=2743.0,
        elevation_max_m=3200.0,
    )
    back = from_foundry_json(to_foundry_json(z))
    assert back == z


# ---------------------------------------------------------------------------
# FireDepartmentUnit
# ---------------------------------------------------------------------------


def test_fire_department_unit_roundtrip() -> None:
    fd = FireDepartmentUnit(
        unit_id="cbfpd",
        name="Crested Butte Fire Protection District",
        aor_geojson={"type": "Polygon", "coordinates": []},
        primary_contact_name=None,
        primary_contact_role="Fire Chief",
        dispatch_phone="(970) 349-5333",
        physical_address="700 6th Street, Crested Butte, CO 81224",
    )
    back = from_foundry_json(to_foundry_json(fd))
    assert back == fd
    assert back.dispatch_phone == "(970) 349-5333"
    assert back.engagement_status == "not_contacted"


# ---------------------------------------------------------------------------
# FlightLog
# ---------------------------------------------------------------------------


def test_flight_log_roundtrip() -> None:
    f = FlightLog(
        drone_id="wfw-sim01",
        mission_yaml_uri="sim/missions/gunnison_slate_river_1km2.yaml",
        is_sim=True,
        signals_emitted=77,
        consensus_signals_emitted=1,
    )
    back = from_foundry_json(to_foundry_json(f))
    assert back == f


# ---------------------------------------------------------------------------
# BatteryCycle
# ---------------------------------------------------------------------------


def test_battery_cycle_roundtrip() -> None:
    b = BatteryCycle(
        battery_serial="HRB-3S-5500-001",
        chemistry="lipo",
        capacity_mah=5500,
        starting_voltage_v=12.6,
        ending_voltage_v=11.4,
        coldest_temp_c=-3.0,
    )
    back = from_foundry_json(to_foundry_json(b))
    assert back == b


# ---------------------------------------------------------------------------
# WildfireSignal
# ---------------------------------------------------------------------------


def _v1_signal() -> dict:
    return {
        "schema_version": "1.0.0",
        "signal_id": str(uuid.uuid4()),
        "drone_id": "wfw-unit01",
        "zone_id": "slate-river-drainage",
        "timestamp": "2026-05-02T22:00:00+00:00",
        "coords": {"lat": 38.9105, "lon": -107.0010, "alt_agl_m": 80.0},
        "signal_type": "smoke",
        "confidence": 0.91,
        "evidence": {"frame_uris": ["gs://bucket/frame.jpg"]},
        "risk_score": 78.0,
        "recommended_action": "notify_operator",
    }


def test_wildfire_signal_from_v1_payload() -> None:
    payload = _v1_signal()
    s = wildfire_signal_from_v1(payload)
    assert s.signal_id == payload["signal_id"]
    assert s.drone_id == "wfw-unit01"
    assert s.zone_id == "slate-river-drainage"
    assert s.coords_lat == 38.9105
    assert s.coords_lon == -107.0010
    assert s.coords_alt_agl_m == 80.0
    assert s.signal_type == "smoke"
    assert s.recommended_action == "notify_operator"
    assert s.schema_version == "1.0.0"
    assert s.raw_payload == payload


def test_wildfire_signal_roundtrip() -> None:
    payload = _v1_signal()
    s = wildfire_signal_from_v1(payload)
    back = from_foundry_json(to_foundry_json(s))
    assert back == s


def test_invalid_type_rejected() -> None:
    with pytest.raises(TypeError):
        to_foundry_json("not a dataclass")


def test_unknown_foundry_type_rejected() -> None:
    bad = json.dumps({"type": "wfw.NotAType", "primaryKey": "x", "properties": {}})
    with pytest.raises(ValueError):
        from_foundry_json(bad)


# ---------------------------------------------------------------------------
# Stable serialization (Foundry ingestion idempotency)
# ---------------------------------------------------------------------------


def test_serialization_is_deterministic() -> None:
    """Two serializations of the same object produce identical bytes (no random key order)."""
    d = Drone(
        drone_id="wfw-unit01",
        airframe_class="mavic_mini_2",
        rpic_pilot_license_id=None,
        insurance_policy_ref=None,
        maintenance_log_uri=None,
    )
    a = to_foundry_json(d)
    b = to_foundry_json(d)
    assert a == b
