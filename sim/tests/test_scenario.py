"""ScenarioEngine tests — events fire at the right tick."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sim.scenario import (  # noqa: E402
    DetectionState,
    Scenario,
    ScenarioEngine,
    ScenarioEvent,
    TriggerTime,
    TriggerWaypoint,
    parse_scenario_dict,
    load_scenario,
)


SCENARIO_DIR = Path(__file__).resolve().parent.parent / "scenarios"


def test_load_each_bundled_scenario_parses():
    for path in SCENARIO_DIR.glob("*.yaml"):
        s = load_scenario(path)
        assert s.name


def test_time_trigger_fires_after_threshold():
    s = Scenario(name="t", description="", events=[
        ScenarioEvent(name="e", trigger=TriggerTime(t_seconds=5.0),
                      event_type="rgb_score_burst",
                      payload={"rgb_score": 0.9, "thermal_delta_c": 10.0,
                               "duration_s": 2.0}),
    ])
    eng = ScenarioEngine(s)
    state = DetectionState()
    # Tick at t=4.9 — should NOT fire.
    fired = eng.step(sim_time_s=4.9, dt=0.1, last_reached_waypoint_index=-1,
                     waypoint_reach_time_s={}, state=state)
    assert fired == []
    # Tick at t=5.0 — should fire.
    fired = eng.step(sim_time_s=5.0, dt=0.1, last_reached_waypoint_index=-1,
                     waypoint_reach_time_s={}, state=state)
    assert len(fired) == 1
    assert state.rgb_score == 0.9
    assert state.in_burst is True


def test_event_fires_only_once():
    s = Scenario(name="t", description="", events=[
        ScenarioEvent(name="e", trigger=TriggerTime(t_seconds=1.0),
                      event_type="rgb_score_burst",
                      payload={"rgb_score": 0.9}),
    ])
    eng = ScenarioEngine(s)
    state = DetectionState()
    fired = eng.step(sim_time_s=1.0, dt=0.1, last_reached_waypoint_index=-1,
                     waypoint_reach_time_s={}, state=state)
    assert len(fired) == 1
    fired = eng.step(sim_time_s=2.0, dt=0.1, last_reached_waypoint_index=-1,
                     waypoint_reach_time_s={}, state=state)
    assert fired == []


def test_waypoint_trigger_with_offset():
    s = Scenario(name="t", description="", events=[
        ScenarioEvent(name="e",
                      trigger=TriggerWaypoint(waypoint_index=2, offset_s=5.0),
                      event_type="rgb_score_burst",
                      payload={"rgb_score": 0.9, "duration_s": 2.0}),
    ])
    eng = ScenarioEngine(s)
    state = DetectionState()
    # WP not reached -> no fire.
    fired = eng.step(sim_time_s=10.0, dt=0.1, last_reached_waypoint_index=1,
                     waypoint_reach_time_s={1: 5.0}, state=state)
    assert fired == []
    # WP reached at t=20, offset_s=5 -> still too early at t=24.
    fired = eng.step(sim_time_s=24.0, dt=0.1, last_reached_waypoint_index=2,
                     waypoint_reach_time_s={1: 5.0, 2: 20.0}, state=state)
    assert fired == []
    # t=25 -> fires.
    fired = eng.step(sim_time_s=25.0, dt=0.1, last_reached_waypoint_index=2,
                     waypoint_reach_time_s={1: 5.0, 2: 20.0}, state=state)
    assert len(fired) == 1


def test_burst_decays_after_duration():
    s = Scenario(name="t", description="", events=[
        ScenarioEvent(name="e", trigger=TriggerTime(t_seconds=0.0),
                      event_type="rgb_score_burst",
                      payload={"rgb_score": 0.9, "thermal_delta_c": 12.0,
                               "duration_s": 1.0}),
    ])
    eng = ScenarioEngine(s)
    state = DetectionState()
    eng.step(sim_time_s=0.0, dt=0.1, last_reached_waypoint_index=-1,
             waypoint_reach_time_s={}, state=state)
    assert state.in_burst
    # Drive forward enough ticks to drain duration.
    for _ in range(15):
        eng.step(sim_time_s=99.0, dt=0.1, last_reached_waypoint_index=-1,
                 waypoint_reach_time_s={}, state=state)
    assert state.in_burst is False
    assert state.rgb_score < 0.5


def test_yaml_dict_parsing_one_based_waypoint():
    """YAML uses 1-based waypoint numbers; engine stores 0-based."""
    data = {
        "name": "x",
        "events": [
            {"at": {"waypoint": 3, "offset_s": 5.0},
             "type": "rgb_score_burst",
             "payload": {"rgb_score": 0.9}},
        ],
    }
    s = parse_scenario_dict(data)
    trig = s.events[0].trigger
    assert isinstance(trig, TriggerWaypoint)
    assert trig.waypoint_index == 2  # 3 -> 2 (0-based)


def test_thermal_only_does_not_set_high_rgb():
    """thermal_only_anomaly must keep rgb below normal gate threshold."""
    s = Scenario(name="t", description="", events=[
        ScenarioEvent(name="thermal", trigger=TriggerTime(t_seconds=0.0),
                      event_type="thermal_only_anomaly",
                      payload={"rgb_score": 0.20, "thermal_delta_c": 22.0,
                               "duration_s": 5.0}),
    ])
    eng = ScenarioEngine(s)
    state = DetectionState()
    eng.step(sim_time_s=0.0, dt=0.1, last_reached_waypoint_index=-1,
             waypoint_reach_time_s={}, state=state)
    assert state.rgb_score < 0.65
    assert state.thermal_delta_c >= 5.0
