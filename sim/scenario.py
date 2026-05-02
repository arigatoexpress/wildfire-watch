"""Scenario engine — schedules detection events at script time T.

A scenario YAML lists events keyed either to absolute sim time
(`{t_seconds: 240}`) or to a waypoint reach with an offset
(`{waypoint: 3, offset_s: 5.0}`). The runner queries the engine every
tick and applies any event whose trigger condition has been satisfied.

Supported event types:

  rgb_score_burst
      Pumps a sustained RGB+thermal positive into the fusion gate.
      Persists for `duration_s` seconds (default 8.0). After the
      duration ends, scores decay back toward baseline.

  wind_shift
      Mutates ambient wind (direction + speed). Used by future logic
      that wants to flip the `wind_consistent` gate-input.

  battery_drain
      Multiplier applied to the per-second battery drain. >1 = faster
      drain. Useful for cold-day or aggressive-flight scenarios.

  thermal_only_anomaly
      Like rgb_score_burst but with rgb_score below threshold — the
      fusion gate must NOT fire. Used to verify gate correctness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TriggerWaypoint:
    waypoint_index: int  # zero-based: WP "3" in YAML is index 2
    offset_s: float = 0.0


@dataclass(frozen=True)
class TriggerTime:
    t_seconds: float


Trigger = TriggerWaypoint | TriggerTime


@dataclass
class ScenarioEvent:
    name: str
    trigger: Trigger
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    fired: bool = False
    # When the event actually fires (sim seconds), recorded by the engine.
    fired_at_s: float | None = None


@dataclass
class Scenario:
    name: str
    description: str
    events: list[ScenarioEvent] = field(default_factory=list)


def _parse_trigger(d: dict[str, Any]) -> Trigger:
    if "t_seconds" in d:
        return TriggerTime(t_seconds=float(d["t_seconds"]))
    if "waypoint" in d:
        # Convention: YAML uses 1-based waypoint numbers, like the rest of the
        # mission files. The runner reaches waypoints in 0-based order.
        idx_one_based = int(d["waypoint"])
        return TriggerWaypoint(
            waypoint_index=max(0, idx_one_based - 1),
            offset_s=float(d.get("offset_s", 0.0)),
        )
    raise ValueError(f"trigger needs 't_seconds' or 'waypoint': {d}")


def parse_scenario_dict(data: dict[str, Any]) -> Scenario:
    events_in = data.get("events", []) or []
    events: list[ScenarioEvent] = []
    for i, e in enumerate(events_in):
        trigger = _parse_trigger(e["at"])
        events.append(
            ScenarioEvent(
                name=str(e.get("name", f"event_{i}")),
                trigger=trigger,
                event_type=str(e["type"]),
                payload=dict(e.get("payload", {})),
            )
        )
    return Scenario(
        name=str(data.get("name", "unnamed-scenario")),
        description=str(data.get("description", "")),
        events=events,
    )


def load_scenario(path: str | Path) -> Scenario:
    """Load and parse a scenario YAML file."""
    import yaml  # noqa: PLC0415

    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"scenario file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"scenario file must contain a YAML mapping: {p}")
    return parse_scenario_dict(data)


@dataclass
class DetectionState:
    """Mutable inputs to the fusion gate that the scenario engine updates."""

    rgb_score: float = 0.0
    thermal_delta_c: float = 0.0
    wind_dir_deg: float = 0.0
    wind_speed_mps: float = 0.0
    battery_drain_multiplier: float = 1.0
    target_offset_m: float = 0.0
    target_bearing_deg: float = 0.0
    burst_remaining_s: float = 0.0
    in_burst: bool = False
    last_event_name: str = ""


class ScenarioEngine:
    """Evaluates scenario events against (sim_time, last_reached_wp_index)."""

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        # Baseline numbers between bursts.
        self.baseline_rgb = 0.05
        self.baseline_thermal = 0.5

    def step(
        self,
        *,
        sim_time_s: float,
        dt: float,
        last_reached_waypoint_index: int,
        waypoint_reach_time_s: dict[int, float],
        state: DetectionState,
    ) -> list[ScenarioEvent]:
        """Advance the engine by `dt`. Returns the list of events that
        fired this tick."""
        fired_now: list[ScenarioEvent] = []

        # 1. Decay any active burst.
        if state.in_burst:
            state.burst_remaining_s -= dt
            if state.burst_remaining_s <= 0.0:
                state.in_burst = False
                state.burst_remaining_s = 0.0
                # Decay scores back toward baseline.
                state.rgb_score = self.baseline_rgb
                state.thermal_delta_c = self.baseline_thermal

        # 2. Check each unfired event.
        for ev in self.scenario.events:
            if ev.fired:
                continue
            if not self._trigger_satisfied(
                ev.trigger,
                sim_time_s=sim_time_s,
                last_reached_waypoint_index=last_reached_waypoint_index,
                waypoint_reach_time_s=waypoint_reach_time_s,
            ):
                continue
            self._apply(ev, state)
            ev.fired = True
            ev.fired_at_s = sim_time_s
            fired_now.append(ev)

        return fired_now

    def _trigger_satisfied(
        self,
        trigger: Trigger,
        *,
        sim_time_s: float,
        last_reached_waypoint_index: int,
        waypoint_reach_time_s: dict[int, float],
    ) -> bool:
        if isinstance(trigger, TriggerTime):
            return sim_time_s >= trigger.t_seconds
        # TriggerWaypoint
        if last_reached_waypoint_index < trigger.waypoint_index:
            return False
        reach_t = waypoint_reach_time_s.get(trigger.waypoint_index)
        if reach_t is None:
            return False
        return sim_time_s >= (reach_t + trigger.offset_s)

    def _apply(self, ev: ScenarioEvent, state: DetectionState) -> None:
        state.last_event_name = ev.name
        if ev.event_type == "rgb_score_burst":
            state.rgb_score = float(ev.payload.get("rgb_score", 0.9))
            state.thermal_delta_c = float(ev.payload.get("thermal_delta_c", 15.0))
            state.burst_remaining_s = float(ev.payload.get("duration_s", 8.0))
            state.in_burst = True
            state.target_offset_m = float(ev.payload.get("target_offset_m", 0.0))
            state.target_bearing_deg = float(ev.payload.get("target_bearing_deg", 0.0))
        elif ev.event_type == "thermal_only_anomaly":
            # rgb stays low so fusion gate cannot fire.
            state.rgb_score = float(ev.payload.get("rgb_score", 0.20))
            state.thermal_delta_c = float(ev.payload.get("thermal_delta_c", 18.0))
            state.burst_remaining_s = float(ev.payload.get("duration_s", 8.0))
            state.in_burst = True
            state.target_offset_m = float(ev.payload.get("target_offset_m", 0.0))
            state.target_bearing_deg = float(ev.payload.get("target_bearing_deg", 0.0))
        elif ev.event_type == "wind_shift":
            state.wind_dir_deg = float(ev.payload.get("wind_dir_deg", 0.0))
            state.wind_speed_mps = float(ev.payload.get("wind_speed_mps", 0.0))
        elif ev.event_type == "battery_drain":
            state.battery_drain_multiplier = float(ev.payload.get("multiplier", 1.0))
        # Unknown event types are silently ignored — keeps forward-compat
        # with future scenarios that this runner version doesn't know yet.
