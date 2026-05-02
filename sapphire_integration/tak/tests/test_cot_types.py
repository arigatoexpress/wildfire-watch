"""CoT type-code mapping + stale-window tests."""

from __future__ import annotations

import pytest

from sapphire_integration.tak.cot_types import (
    COT_TYPE_DESCRIPTIONS,
    DEFAULT_STALE_SECONDS,
    DRONE_SELF_POSITION_COT_TYPE,
    GEOFENCE_POLYGON_COT_TYPE,
    SIGNAL_TYPE_TO_COT_TYPE,
    STALE_SECONDS_BY_SIGNAL_TYPE,
    cot_type_for_signal,
    describe_cot_type,
    stale_seconds_for_signal,
)


def test_known_signal_types_all_map():
    """Every signal_type defined in wildfire_signal_schema must map."""
    expected_types = {
        "smoke",
        "fire",
        "thermal_anomaly",
        "wildlife",
        "anomaly",
        "system_event",
    }
    assert expected_types <= set(SIGNAL_TYPE_TO_COT_TYPE.keys())


def test_fire_maps_to_b_r_f_h_c():
    assert SIGNAL_TYPE_TO_COT_TYPE["fire"] == "b-r-f-h-c"


def test_smoke_maps_to_b_r_f_h_s():
    assert SIGNAL_TYPE_TO_COT_TYPE["smoke"] == "b-r-f-h-s"


def test_thermal_anomaly_maps_to_b_r_f_h_h():
    assert SIGNAL_TYPE_TO_COT_TYPE["thermal_anomaly"] == "b-r-f-h-h"


def test_wildlife_maps_to_neutral_ground():
    """Wildlife is neutral, not friendly — we observe, we don't command."""
    assert SIGNAL_TYPE_TO_COT_TYPE["wildlife"] == "a-n-G"


def test_unknown_signal_type_falls_back_to_b_d():
    assert cot_type_for_signal({"signal_type": "ufo"}) == "b-d"
    assert cot_type_for_signal({}) == "b-d"


def test_cot_type_for_signal_round_trip_known():
    for sig_type, cot_type in SIGNAL_TYPE_TO_COT_TYPE.items():
        assert cot_type_for_signal({"signal_type": sig_type}) == cot_type


# --- stale windows ---


def test_fire_stale_is_one_hour():
    assert stale_seconds_for_signal({"signal_type": "fire"}) == 3600


def test_smoke_stale_is_one_hour():
    assert stale_seconds_for_signal({"signal_type": "smoke"}) == 3600


def test_wildlife_stale_is_15_min():
    assert stale_seconds_for_signal({"signal_type": "wildlife"}) == 900


def test_system_event_stale_is_24_hours():
    assert stale_seconds_for_signal({"signal_type": "system_event"}) == 86400


def test_unknown_signal_type_stale_default():
    assert stale_seconds_for_signal({"signal_type": "ufo"}) == DEFAULT_STALE_SECONDS


@pytest.mark.parametrize("sig_type", list(STALE_SECONDS_BY_SIGNAL_TYPE.keys()))
def test_all_known_types_have_positive_stale(sig_type):
    assert stale_seconds_for_signal({"signal_type": sig_type}) > 0


# --- description lookup ---


def test_describe_known_codes():
    for cot_type in SIGNAL_TYPE_TO_COT_TYPE.values():
        desc = describe_cot_type(cot_type)
        assert desc and not desc.startswith("unknown CoT type")


def test_describe_unknown_code():
    assert describe_cot_type("z-z-z").startswith("unknown CoT type")


def test_drone_and_geofence_types_described():
    for code in (DRONE_SELF_POSITION_COT_TYPE, GEOFENCE_POLYGON_COT_TYPE):
        assert code in COT_TYPE_DESCRIPTIONS
        assert describe_cot_type(code).strip()
