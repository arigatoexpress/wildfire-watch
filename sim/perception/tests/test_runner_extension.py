"""End-to-end test of the runner_extension wrapper.

Loads the Gunnison Slate River mission, the single_smoke_plume scenario,
and the canyon_gps_outage jamming scenario. Runs the wrapped runner and
verifies the fused_log captures the GPS outage and that fused position
stays within tolerance of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from sim.mission import load_mission  # noqa: E402
from sim.perception.jamming import JammingScenario  # noqa: E402
from sim.perception.runner_extension import wrap_with_fused_nav  # noqa: E402
from sim.runner import RunnerConfig, SimulationRunner  # noqa: E402
from sim.scenario import ScenarioEngine, load_scenario  # noqa: E402

SIM_ROOT = Path(__file__).resolve().parent.parent.parent
MISSION_PATH = SIM_ROOT / "missions" / "gunnison_slate_river_1km2.yaml"
FALLBACK_MISSION = SIM_ROOT / "missions" / "monterey_pinnacles_east_1km2.yaml"
SCENARIO_PATH = SIM_ROOT / "scenarios" / "clean_patrol.yaml"
JAMMING_PATH = (
    SIM_ROOT / "perception" / "scenarios" / "canyon_gps_outage.yaml"
)


def _get_mission():
    if MISSION_PATH.exists():
        return load_mission(MISSION_PATH)
    return load_mission(FALLBACK_MISSION)


def test_wrapper_runs_end_to_end_and_records_fused_log():
    mission = _get_mission()
    scenario = load_scenario(SCENARIO_PATH)
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    jamming = JammingScenario.load(JAMMING_PATH)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming, seed=0)
    result = wrapped.run(max_sim_seconds=600.0)
    assert result.ticks > 0
    assert len(wrapped.fused_log) > 0
    # All records have valid coordinates.
    for r in wrapped.fused_log:
        assert -90.0 <= r.fused_lat <= 90.0
        assert -180.0 <= r.fused_lon <= 180.0


def test_gps_outage_window_shows_active_mode_change():
    """During the canyon outage (T=30..90s), at least one tick should
    record active_mode != GPS_ONLY."""
    mission = _get_mission()
    scenario = load_scenario(SCENARIO_PATH)
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    jamming = JammingScenario.load(JAMMING_PATH)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming, seed=0)
    wrapped.run(max_sim_seconds=600.0)
    in_outage = [
        r for r in wrapped.fused_log
        if 30.0 <= r.sim_time_s <= 90.0
    ]
    assert len(in_outage) > 0
    non_gps = [r for r in in_outage if r.active_mode != "gps_only"]
    assert len(non_gps) > 0
    # During outage, GPS should have been marked unavailable.
    unavailable = [r for r in in_outage if not r.gps_available]
    assert len(unavailable) > 0


def test_fused_position_stays_within_10m_of_truth_at_outage_end():
    """At the end of the 60-second outage (T=90s), fused position
    deviation from truth must be < 10 m. This is the headline
    performance number for the demo."""
    mission = _get_mission()
    scenario = load_scenario(SCENARIO_PATH)
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    jamming = JammingScenario.load(JAMMING_PATH)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming, seed=0)
    wrapped.run(max_sim_seconds=600.0)
    # Find the record closest to T=89s (last second of outage).
    end_outage = [
        r for r in wrapped.fused_log
        if 88.0 <= r.sim_time_s <= 90.0
    ]
    assert len(end_outage) > 0
    worst = max(r.error_m for r in end_outage)
    assert worst < 10.0, f"worst end-of-outage error {worst:.2f} m"


def test_smoke_plume_fused_signal_carries_perception_subtype():
    """When a fire signal fires under the wrapper, signal_subtype
    should reflect the active nav mode."""
    mission = _get_mission()
    # Use single_smoke_plume so we get at least one signal.
    scenario = load_scenario(SIM_ROOT / "scenarios" / "single_smoke_plume.yaml")
    captured: list[dict] = []
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
        on_signal=captured.append,
    )
    jamming = JammingScenario.load(JAMMING_PATH)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming, seed=0)
    wrapped.run(max_sim_seconds=600.0)
    assert len(captured) > 0
    for sig in captured:
        # Subtype must reflect perception, not the original sim/scenario_burst.
        assert sig["signal_subtype"].startswith("sim/perception/")


def test_truth_path_unaffected_by_wrapper():
    """The truth waypoint trajectory must still complete — wrapping
    should not break navigation."""
    mission = _get_mission()
    scenario = load_scenario(SCENARIO_PATH)
    runner = SimulationRunner(
        mission=mission,
        scenario_engine=ScenarioEngine(scenario),
        config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
    )
    jamming = JammingScenario.load(JAMMING_PATH)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming, seed=0)
    result = wrapped.run(max_sim_seconds=900.0)
    assert result.waypoints_reached >= len(mission.waypoints)
