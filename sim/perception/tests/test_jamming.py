"""Tests for JammingScenario events + spoof discriminator."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.perception.jamming import JammingScenario  # noqa: E402

SCENARIOS = Path(__file__).resolve().parent.parent / "scenarios"


def _make_outage_scenario(t_start: float = 30.0, dur: float = 60.0) -> JammingScenario:
    return JammingScenario.from_dict({
        "name": "test_outage",
        "events": [
            {
                "name": "outage1",
                "at": {"t_seconds": t_start},
                "type": "gps_outage",
                "duration_s": dur,
            },
        ],
    })


def _make_spoof_scenario(
    t_start: float = 30.0, dur: float = 5.0,
    false_lat: float = 38.7, false_lon: float = -107.05,
) -> JammingScenario:
    return JammingScenario.from_dict({
        "name": "test_spoof",
        "events": [
            {
                "name": "spoof1",
                "at": {"t_seconds": t_start},
                "type": "gps_spoof",
                "duration_s": dur,
                "payload": {"false_lat": false_lat, "false_lon": false_lon},
            },
        ],
    })


def test_outage_window_flips_available_false():
    sc = _make_outage_scenario(t_start=30.0, dur=60.0)
    # Before the outage.
    s = sc.step(
        sim_time_s=10.0, truth_lat=38.91, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.05, dt=0.1,
    )
    assert s.available is True
    # During the outage.
    s = sc.step(
        sim_time_s=45.0, truth_lat=38.91, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.05, dt=0.1,
    )
    assert s.available is False
    # After the outage.
    s = sc.step(
        sim_time_s=120.0, truth_lat=38.91, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.05, dt=0.1,
    )
    assert s.available is True


def test_spoof_event_marks_untrusted_when_discriminator_fires():
    sc = _make_spoof_scenario(t_start=30.0, dur=5.0)
    # Seed the discriminator with a clean prior.
    sc.step(
        sim_time_s=29.9, truth_lat=38.91, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.05, dt=0.1,
    )
    # Now within the spoof window — reported jumps to (38.7, -107.05).
    s = sc.step(
        sim_time_s=30.0, truth_lat=38.910001, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.05, dt=0.1,
    )
    # GPS reports the spoofed location.
    assert s.reported_lat is not None
    assert abs(s.reported_lat - 38.7) < 0.001
    # And the discriminator should reject it as untrusted.
    assert s.trusted is False


def test_clean_gps_stays_trusted():
    sc = _make_outage_scenario(t_start=10000.0, dur=1.0)  # outage far away
    sc.step(
        sim_time_s=0.0, truth_lat=38.91, truth_lon=-107.0,
        vo_velocity_mps=6.0, vo_imu_sigma_m=0.5, dt=0.1,
    )
    # Tiny truth motion, GPS reports it — should remain trusted.
    s = sc.step(
        sim_time_s=0.1, truth_lat=38.910001, truth_lon=-107.0,
        vo_velocity_mps=0.1, vo_imu_sigma_m=0.5, dt=0.1,
    )
    assert s.available
    assert s.trusted


def test_load_canyon_scenario_from_yaml():
    sc = JammingScenario.load(SCENARIOS / "canyon_gps_outage.yaml")
    assert sc.name == "canyon_gps_outage"
    assert len(sc.events) == 1
    assert sc.events[0].type == "gps_outage"
    assert sc.events[0].t_start_s == 30.0


def test_load_spoof_scenario_from_yaml():
    sc = JammingScenario.load(SCENARIOS / "deliberate_jam_burst.yaml")
    types = [e.type for e in sc.events]
    assert "gps_spoof" in types
    spoof_event = [e for e in sc.events if e.type == "gps_spoof"][0]
    assert spoof_event.payload.get("false_lat") == 38.7
