"""Shared fixtures for the TAK / CoT test suite.

Fixtures aim to mirror real wildfire_signal v1 records as `build_signal()`
in `ml/fire_detection/infer.py` would emit them, plus a few corner cases
(missing optional fields, unknown signal_type).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest


def _base_signal(**overrides: Any) -> dict[str, Any]:
    sig: dict[str, Any] = {
        "schema_version": "1.0.0",
        "signal_id": str(uuid.uuid4()),
        "drone_id": "wfw-unit01",
        "zone_id": "slate-river-drainage",
        "timestamp": "2026-05-02T20:14:00Z",
        "coords": {
            "lat": 38.9100000,
            "lon": -107.0000000,
            "alt_agl_m": 80.0,
            "alt_msl_m": 2820.0,
            "heading_deg": 270.0,
            "ground_speed_mps": 6.0,
        },
        "target_coords": {
            "lat": 38.9105000,
            "lon": -107.0010000,
            "alt_msl_m": 2810.0,
            "estimation_method": "visual_geolocation",
            "horizontal_uncertainty_m": 18.0,
        },
        "signal_type": "smoke",
        "signal_subtype": "smoke/persistent_plume",
        "confidence": 0.86,
        "evidence": {
            "frame_uris": ["gs://wfw/zone/2026-05-02/sig/frame_0001.jpg"],
            "model_outputs": {
                "rgb_yolo_score": 0.92,
                "rgb_yolo_class": "smoke",
                "thermal_max_temp_c": 38.5,
                "thermal_delta_c": 18.5,
            },
            "model_versions": {"fire_yolo": "v0.3.1@sha256:abcd"},
        },
        "environment": {
            "wind_dir_deg": 220.0,
            "wind_speed_mps": 4.5,
            "ambient_temp_c": 19.0,
            "humidity_pct": 22.0,
            "fire_weather_index": 41.0,
        },
        "risk_score": 78.0,
        "recommended_action": "notify_operator",
        "geofence_status": {
            "in_authorized_zone": True,
            "tfr_active": False,
            "remote_id_active": True,
        },
    }
    sig.update(overrides)
    return sig


@pytest.fixture
def smoke_signal() -> dict[str, Any]:
    """Canonical smoke signal — RGB+thermal high, target offset from drone."""
    return _base_signal()


@pytest.fixture
def fire_signal() -> dict[str, Any]:
    """Confirmed fire — both modalities very high."""
    return _base_signal(
        signal_type="fire",
        signal_subtype="fire/active_flame",
        confidence=0.99,
        risk_score=95.0,
        recommended_action="notify_fire_dept",
        evidence={
            "frame_uris": ["gs://wfw/zone/2026-05-02/sig/frame_fire.jpg"],
            "model_outputs": {
                "rgb_yolo_score": 0.97,
                "thermal_max_temp_c": 412.0,
                "thermal_delta_c": 380.0,
            },
        },
    )


@pytest.fixture
def thermal_anomaly_signal() -> dict[str, Any]:
    return _base_signal(
        signal_type="thermal_anomaly",
        signal_subtype="thermal/hot_spot",
        confidence=0.71,
        target_coords=None,  # no visual geolocation, drone coords used
        evidence={
            "frame_uris": ["gs://wfw/zone/2026-05-02/sig/frame_th.tiff"],
            "model_outputs": {
                "rgb_yolo_score": 0.05,
                "thermal_max_temp_c": 95.0,
                "thermal_delta_c": 47.0,
            },
        },
    )


@pytest.fixture
def wildlife_signal() -> dict[str, Any]:
    return _base_signal(
        signal_type="wildlife",
        signal_subtype="wildlife/megadetector_animal",
        confidence=0.91,
        risk_score=10.0,
        recommended_action="log_only",
        evidence={
            "frame_uris": ["gs://wfw/zone/2026-05-02/sig/frame_elk.jpg"],
            "model_outputs": {"wildlife_class": "elk", "wildlife_score": 0.91},
        },
    )


@pytest.fixture
def system_event_signal() -> dict[str, Any]:
    return _base_signal(
        signal_type="system_event",
        signal_subtype="system/rtl_low_battery",
        confidence=1.0,
        risk_score=0.0,
        recommended_action="rtl",
        target_coords=None,
        evidence={
            "frame_uris": ["gs://wfw/system/2026-05-02/heartbeat.json"],
        },
    )


@pytest.fixture
def anomaly_signal() -> dict[str, Any]:
    return _base_signal(
        signal_type="anomaly",
        signal_subtype="anomaly/unusual_human_activity",
        confidence=0.72,
        target_coords=None,
        evidence={
            "frame_uris": ["gs://wfw/zone/2026-05-02/sig/frame_anom.jpg"],
            "model_outputs": {"anomaly_score": 0.72},
        },
    )


@pytest.fixture
def signal_minimal() -> dict[str, Any]:
    """Smallest legal signal: only required fields, no target_coords."""
    return {
        "schema_version": "1.0.0",
        "signal_id": str(uuid.uuid4()),
        "drone_id": "wfw-unit01",
        "zone_id": "z1",
        "timestamp": "2026-05-02T20:14:00Z",
        "coords": {"lat": 38.9, "lon": -107.0, "alt_agl_m": 80.0},
        "signal_type": "smoke",
        "confidence": 0.7,
        "evidence": {"frame_uris": ["gs://wfw/x.jpg"]},
        "risk_score": 50.0,
        "recommended_action": "notify_operator",
    }
