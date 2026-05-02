"""SimulationRunner integration tests — fusion gate + signal emit."""

from __future__ import annotations

import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sim.mission import load_mission  # noqa: E402
from sim.runner import RunnerConfig, SimulationRunner  # noqa: E402
from sim.scenario import ScenarioEngine, load_scenario  # noqa: E402

SIM_ROOT = Path(__file__).resolve().parent.parent
MISSION_PATH = SIM_ROOT / "missions" / "monterey_pinnacles_east_1km2.yaml"
SCHEMA_PATH = (
    SIM_ROOT.parent / "sapphire_integration" / "wildfire_signal_schema.json"
)
DRONE_ID_RE = re.compile(r"^wfw-[a-z0-9]{4,16}$")
ALLOWED_SIGNAL_TYPES = {"smoke", "fire", "thermal_anomaly", "wildlife", "anomaly", "system_event"}
ALLOWED_RECOMMENDED = {"log_only", "notify_operator", "notify_fire_dept", "loiter_and_capture", "rtl"}


def _load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _assert_signal_valid(sig: dict) -> None:
    """Lightweight contract check against wildfire_signal_schema.json.

    We do not pull in jsonschema (no new deps); we verify required keys,
    enum membership, and the regex constraints that matter at runtime.
    """
    schema = _load_schema()
    for required in schema["required"]:
        assert required in sig, f"missing required field: {required}"
    assert sig["schema_version"] == "1.0.0"
    assert isinstance(sig["signal_id"], str)
    uuid.UUID(sig["signal_id"])  # raises if not a valid UUID string
    assert DRONE_ID_RE.match(sig["drone_id"]), sig["drone_id"]
    assert sig["signal_type"] in ALLOWED_SIGNAL_TYPES
    assert sig["recommended_action"] in ALLOWED_RECOMMENDED
    assert 0.0 <= sig["confidence"] <= 1.0
    assert 0.0 <= sig["risk_score"] <= 100.0
    coords = sig["coords"]
    assert -90.0 <= coords["lat"] <= 90.0
    assert -180.0 <= coords["lon"] <= 180.0
    assert "alt_agl_m" in coords
    assert sig["evidence"]["frame_uris"], "frame_uris must be non-empty"
    # additionalProperties is false in the schema — verify no unknown keys.
    allowed_keys = set(schema["properties"].keys())
    extra = set(sig.keys()) - allowed_keys
    assert not extra, f"unexpected top-level keys: {extra}"


def test_clean_patrol_emits_zero_signals():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "clean_patrol.yaml")
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    result = runner.run(max_sim_seconds=600.0)
    assert result.signals_emitted == 0
    assert result.waypoints_reached >= len(mission.waypoints)


def test_single_smoke_plume_fires_at_least_one_signal():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "single_smoke_plume.yaml")
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
        on_signal=captured.append,
    )
    result = runner.run(max_sim_seconds=600.0)
    assert result.signals_emitted >= 1
    assert len(captured) == result.signals_emitted


def test_emitted_signal_is_schema_valid():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "single_smoke_plume.yaml")
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
        on_signal=captured.append,
    )
    runner.run(max_sim_seconds=600.0)
    assert captured, "expected at least one signal"
    for sig in captured:
        _assert_signal_valid(sig)


def test_thermal_only_anomaly_does_not_emit():
    """If RGB stays below threshold, fusion gate must NOT open."""
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "thermal_only_anomaly.yaml")
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    result = runner.run(max_sim_seconds=600.0)
    assert result.signals_emitted == 0


def test_runner_advances_through_waypoints():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "clean_patrol.yaml")
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    result = runner.run(max_sim_seconds=600.0)
    # All planned WPs reached.
    assert result.waypoints_reached >= len(mission.waypoints)
    # And we have a tick log we can inspect.
    assert len(result.drone_path_log) > 0
    # Final tick should be at or near home (RTH true).
    last = result.drone_path_log[-1]
    assert abs(last.lat - mission.home.lat) < 0.001
    assert abs(last.lon - mission.home.lon) < 0.001


def test_battery_drains_monotonically():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "clean_patrol.yaml")
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    result = runner.run(max_sim_seconds=600.0)
    log = result.drone_path_log
    # Battery never increases.
    for a, b in zip(log, log[1:]):
        assert b.battery_pct <= a.battery_pct + 1e-9


def test_multi_zone_anomaly_emits_more_than_one_signal():
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "multi_zone_anomaly.yaml")
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
        on_signal=captured.append,
    )
    runner.run(max_sim_seconds=600.0)
    # Each event burst lasts 6-10s; at 10 Hz with persistence_min=5 we expect
    # multiple signals across the three events.
    assert len(captured) >= 3
