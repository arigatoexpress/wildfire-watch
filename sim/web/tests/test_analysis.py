"""Math-correctness coverage for sim/web/analysis.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim.web.analysis import (
    bounding_box_km2,
    haversine_m,
    path_length_m,
    summarize,
)


def test_haversine_zero():
    assert haversine_m(36.49, -121.18, 36.49, -121.18) == 0.0


def test_haversine_known_distance():
    """1 deg of latitude at the equator is ~111 km."""
    d = haversine_m(0.0, 0.0, 1.0, 0.0)
    assert 110_000 < d < 112_000


def test_path_length_haversine_sum():
    pts = [(36.49, -121.18), (36.50, -121.18), (36.50, -121.17)]
    expected = (
        haversine_m(36.49, -121.18, 36.50, -121.18)
        + haversine_m(36.50, -121.18, 36.50, -121.17)
    )
    assert path_length_m(pts) == pytest.approx(expected)


def test_bounding_box_zero_for_single_point():
    assert bounding_box_km2([(36.49, -121.18)]) == 0.0


def test_summarize_synthetic_flight(tmp_path: Path):
    """Synthesize a minimal 3-waypoint flight + one signal; verify the rollup."""
    rows = [
        {
            "ts": "2026-05-01T16:00:00Z",
            "lat": 36.49, "lon": -121.18, "alt_agl_m": 0.0,
            "alt_msl_m": 320.0, "heading_deg": 0.0, "speed_mps": 0.0,
            "battery_pct": 100.0,
            "gate_state": {"rgb_score": 0.0, "thermal_delta_c": 0.0,
                           "persistence": 0, "open": False},
        },
        {
            "ts": "2026-05-01T16:00:30Z",
            "lat": 36.50, "lon": -121.18, "alt_agl_m": 80.0,
            "alt_msl_m": 400.0, "heading_deg": 0.0, "speed_mps": 8.0,
            "battery_pct": 96.0,
            "gate_state": {"rgb_score": 0.6, "thermal_delta_c": 5.5,
                           "persistence": 4, "open": True},
        },
        {
            "ts": "2026-05-01T16:01:00Z",
            "lat": 36.50, "lon": -121.17, "alt_agl_m": 80.0,
            "alt_msl_m": 400.0, "heading_deg": 90.0, "speed_mps": 8.0,
            "battery_pct": 92.0,
            "gate_state": {"rgb_score": 0.0, "thermal_delta_c": 0.0,
                           "persistence": 0, "open": False},
        },
    ]
    sig = {
        "schema_version": "1.0.0",
        "signal_id": "00000000-0000-4000-8000-000000000000",
        "drone_id": "wfw-test01",
        "zone_id": "synthetic",
        "timestamp": "2026-05-01T16:00:30Z",
        "coords": {"lat": 36.50, "lon": -121.18, "alt_agl_m": 80.0},
        "signal_type": "smoke",
        "confidence": 0.81,
        "evidence": {"frame_uris": ["gs://x/y.jpg"]},
        "risk_score": 65.0,
        "recommended_action": "loiter_and_capture",
    }
    manifest = {
        "mission_name": "test", "scenario_name": "synth",
        "started_at": "2026-05-01T16:00:00Z", "ended_at": "2026-05-01T16:01:00Z",
        "duration_s": 60.0, "total_signals_emitted": 1,
        "geofence_polygon": [[36.48, -121.19], [36.51, -121.19],
                             [36.51, -121.16], [36.48, -121.16]],
        "waypoints": [
            {"index": 0, "lat": 36.49, "lon": -121.18},
            {"index": 1, "lat": 36.50, "lon": -121.18},
            {"index": 2, "lat": 36.50, "lon": -121.17},
        ],
        "home": {"lat": 36.49, "lon": -121.18, "alt_msl_m": 320.0},
        "airframe": "mavic_mini_2",
    }

    flight = tmp_path / "SIM-test"
    flight.mkdir()
    (flight / "manifest.json").write_text(json.dumps(manifest))
    with (flight / "flight_log.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    (flight / "signals.jsonl").write_text(json.dumps(sig) + "\n")

    summary = summarize(flight)

    # Path length ≈ haversine sum
    expected_path_m = (
        haversine_m(36.49, -121.18, 36.50, -121.18)
        + haversine_m(36.50, -121.18, 36.50, -121.17)
    )
    assert summary["path_length_km"] == pytest.approx(expected_path_m / 1000.0, abs=0.005)

    assert summary["signals_total"] == 1
    assert summary["signals_by_type"] == {"smoke": 1}
    assert summary["signals_by_priority"] == {"p2": 1}
    assert summary["max_risk_score"] == 65.0
    assert summary["max_alt_agl_m"] == 80.0
    assert summary["battery_consumed_pct"] == pytest.approx(8.0, abs=0.01)

    # The middle row has both candidate gate flags and open=True; it's a single
    # approach that immediately becomes a hit.
    assert summary["gate_approaches"] == 1
    assert summary["gate_hits"] == 1
    assert summary["gate_hit_rate"] == 1.0


def test_summarize_handles_missing_files(tmp_path: Path):
    """summarize() on an empty directory should not crash."""
    summary = summarize(tmp_path)
    assert summary["signals_total"] == 0
    assert summary["row_count"] == 0
    assert summary["path_length_km"] == 0.0


def test_summarize_fixture():
    """Bundled fixture exercises the full pipeline end-to-end."""
    fix = Path(__file__).resolve().parents[1] / "fixtures" / "sample_flight"
    s = summarize(fix)
    assert s["signals_total"] == 1
    assert s["row_count"] >= 30
    assert s["path_length_km"] > 0
    assert "smoke" in s["signals_by_type"]
    assert s["gate_approaches"] >= 1
