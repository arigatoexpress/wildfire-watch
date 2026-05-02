"""Fleet — N drones with shared mission state, lockstep tick.

A Fleet wraps N `_DroneAgent` objects, each of which carries:
  - its own copy of the canonical Mission (so cruise speed, airframe,
    altitude, and home are shared) but with a sub-mission of waypoints
    targeted at its assigned coverage cell,
  - its own DetectionState fed by its own ScenarioEngine instance,
  - its own DroneState (lat/lon/alt/heading/speed/battery/gate),
  - its own persistence buffer for the fusion gate.

Fleet.step(dt) advances every drone by one tick. Drones do NOT see each
other through the Fleet; coordination happens at the SwarmRunner layer
via the comms model + consensus voter. The Fleet is just a collection.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

# Pull in single-drone code unchanged. We do NOT modify these.
from ..kinematics import (
    haversine_m,
    initial_bearing_deg,
    move_along_bearing,
)
from ..mission import Mission, Waypoint
from ..runner import (
    DEFAULT_AUTO_LOITER_THRESHOLD,
    DEFAULT_CONF_THRESHOLD,
    DEFAULT_PERSISTENCE_FRAMES,
    WAYPOINT_REACH_TOLERANCE_M,
    DroneState,
    TickRecord,
)
from ..scenario import DetectionState, ScenarioEngine

logger = logging.getLogger("sim.swarm.fleet")

# Lazy import the fusion gate + signal builder. We re-use the exact same
# gate the single-drone runner does. Path injection mirrors sim/runner.py.
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INFER_DIR = _REPO_ROOT / "ml" / "fire_detection"
if str(_INFER_DIR) not in sys.path:
    sys.path.insert(0, str(_INFER_DIR))
from infer import build_signal, should_emit  # noqa: E402


@dataclass
class DroneTickRecord:
    """Like single-drone TickRecord, but tagged with drone_id."""

    drone_id: str
    ts_iso: str
    sim_time_s: float
    lat: float
    lon: float
    alt_agl_m: float
    alt_msl_m: float
    heading_deg: float
    speed_mps: float
    battery_pct: float
    gate_state: str
    rgb_score: float
    thermal_delta_c: float


@dataclass
class _DroneAgent:
    """Single drone, owned by a Fleet."""

    drone_id: str
    mission: Mission
    sub_waypoints: list[Waypoint]
    state: DroneState
    detection: DetectionState
    persistence: deque
    scenario_engine: ScenarioEngine
    waypoint_reach_time_s: dict[int, float] = field(default_factory=dict)
    signals_emitted: int = 0
    battery_drain_per_s: float = 0.0
    confidence_threshold: float = DEFAULT_CONF_THRESHOLD
    auto_loiter_threshold: float = DEFAULT_AUTO_LOITER_THRESHOLD
    persistence_min: int = DEFAULT_PERSISTENCE_FRAMES


@dataclass
class FleetTickResult:
    """Snapshot of one tick's outcome across the whole fleet."""

    sim_time_s: float
    drone_records: list[DroneTickRecord] = field(default_factory=list)
    new_signals: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Each tuple: (emitter_drone_id, signal_dict).


class Fleet:
    """Collection of N drones tied to one mission, ticked together."""

    def __init__(
        self,
        *,
        mission: Mission,
        drone_ids: list[str],
        sub_waypoint_lists: list[list[Waypoint]],
        scenario_engines: list[ScenarioEngine],
        start_wallclock: datetime | None = None,
        confidence_threshold: float = DEFAULT_CONF_THRESHOLD,
        auto_loiter_threshold: float = DEFAULT_AUTO_LOITER_THRESHOLD,
        persistence_frames: int = DEFAULT_PERSISTENCE_FRAMES,
    ):
        if not (len(drone_ids) == len(sub_waypoint_lists) == len(scenario_engines)):
            raise ValueError(
                "drone_ids, sub_waypoint_lists, scenario_engines must align"
            )
        self.mission = mission
        wall0 = start_wallclock or datetime.now(UTC).replace(microsecond=0)
        self.sim_time_s = 0.0
        self.wallclock = wall0
        self.confidence_threshold = confidence_threshold
        self.auto_loiter_threshold = auto_loiter_threshold
        self.persistence_frames = persistence_frames

        self.agents: list[_DroneAgent] = []
        battery_drain_per_s = 100.0 / max(1.0, mission.airframe.battery_minutes * 60.0)

        for did, sub_wps, scen_eng in zip(
            drone_ids, sub_waypoint_lists, scenario_engines
        ):
            # Each drone takes off from the mission home (single launch
            # point in this Phase 0 model — they all stage from the same
            # truck). Realistic future extension: per-drone takeoff
            # offset so they don't collide on launch.
            state = DroneState(
                lat=mission.home.lat,
                lon=mission.home.lon,
                alt_agl_m=mission.flight_params.altitude_agl_m,
                alt_msl_m=mission.home.alt_msl_m + mission.flight_params.altitude_agl_m,
                heading_deg=0.0,
                speed_mps=0.0,
                battery_pct=100.0,
                next_wp_index=0,
                sim_time_s=0.0,
                wallclock=wall0,
            )
            self.agents.append(
                _DroneAgent(
                    drone_id=did,
                    mission=mission,
                    sub_waypoints=list(sub_wps),
                    state=state,
                    detection=DetectionState(),
                    persistence=deque(maxlen=persistence_frames),
                    scenario_engine=scen_eng,
                    battery_drain_per_s=battery_drain_per_s,
                    confidence_threshold=confidence_threshold,
                    auto_loiter_threshold=auto_loiter_threshold,
                    persistence_min=persistence_frames,
                )
            )

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def step(self, dt: float) -> FleetTickResult:
        """Advance every drone by `dt`. Returns the per-tick records and
        any wildfire_signal v1 emits this tick."""
        result = FleetTickResult(sim_time_s=self.sim_time_s)
        for agent in self.agents:
            tick_rec, emit = self._tick_agent(agent, dt)
            result.drone_records.append(tick_rec)
            if emit is not None:
                result.new_signals.append((agent.drone_id, emit))
        # Advance shared fleet clock AFTER all drones have ticked at the
        # same dt, to keep per-drone telemetry timestamps aligned.
        self.sim_time_s += dt
        self.wallclock = self.wallclock + timedelta(seconds=dt)
        return result

    def all_finished(self) -> bool:
        """True iff every drone has reached the end of its sub-waypoints."""
        return all(
            agent.state.next_wp_index >= len(agent.sub_waypoints) + (
                1 if self.mission.return_to_home else 0
            )
            for agent in self.agents
        )

    def any_battery_dead(self) -> bool:
        return any(agent.state.battery_pct <= 0.0 for agent in self.agents)

    # ------------------------------------------------------------------
    # Per-drone tick (mirrors sim/runner.py._tick but stripped of the
    # single-drone-only assumptions). We re-use should_emit/build_signal.
    # ------------------------------------------------------------------

    def _tick_agent(
        self, agent: _DroneAgent, dt: float
    ) -> tuple[DroneTickRecord, dict[str, Any] | None]:
        # Build the effective waypoint list (sub + RTH at the end).
        effective_waypoints = list(agent.sub_waypoints)
        if self.mission.return_to_home:
            effective_waypoints.append(
                Waypoint(
                    lat=self.mission.home.lat,
                    lon=self.mission.home.lon,
                    alt_agl_m=self.mission.flight_params.altitude_agl_m,
                    action="rtl",
                )
            )

        if agent.state.next_wp_index < len(effective_waypoints):
            wp = effective_waypoints[agent.state.next_wp_index]
            self._step_toward(agent, wp, dt)
            dist = haversine_m(
                agent.state.lat, agent.state.lon, wp.lat, wp.lon
            )
            if dist <= WAYPOINT_REACH_TOLERANCE_M:
                if agent.state.next_wp_index not in agent.waypoint_reach_time_s:
                    agent.waypoint_reach_time_s[
                        agent.state.next_wp_index
                    ] = self.sim_time_s
                agent.state.next_wp_index += 1

        # Scenario engine for this drone.
        last_reached = (
            max(agent.waypoint_reach_time_s.keys())
            if agent.waypoint_reach_time_s
            else -1
        )
        agent.scenario_engine.step(
            sim_time_s=self.sim_time_s,
            dt=dt,
            last_reached_waypoint_index=last_reached,
            waypoint_reach_time_s=agent.waypoint_reach_time_s,
            state=agent.detection,
        )

        rgb = agent.detection.rgb_score
        thermal = agent.detection.thermal_delta_c
        agent.persistence.append(rgb >= agent.confidence_threshold)
        run_length = sum(agent.persistence)

        gate_open = should_emit(
            rgb_score=rgb,
            thermal_delta_c=thermal,
            persistence_frames=run_length,
            geofence_ok=True,
            wind_consistent=True,
            threshold=agent.confidence_threshold,
            persistence_min=agent.persistence_min,
        )
        agent.state.gate_state = "OPEN" if gate_open else "closed"

        emitted: dict[str, Any] | None = None
        if gate_open:
            emitted = self._build_signal(agent, rgb, thermal)
            agent.signals_emitted += 1

        rec = DroneTickRecord(
            drone_id=agent.drone_id,
            ts_iso=self.wallclock.isoformat().replace("+00:00", "Z"),
            sim_time_s=round(self.sim_time_s, 3),
            lat=agent.state.lat,
            lon=agent.state.lon,
            alt_agl_m=agent.state.alt_agl_m,
            alt_msl_m=agent.state.alt_msl_m,
            heading_deg=agent.state.heading_deg,
            speed_mps=agent.state.speed_mps,
            battery_pct=round(agent.state.battery_pct, 3),
            gate_state=agent.state.gate_state,
            rgb_score=round(rgb, 3),
            thermal_delta_c=round(thermal, 3),
        )

        # Battery drain.
        drain = (
            agent.battery_drain_per_s
            * dt
            * agent.detection.battery_drain_multiplier
        )
        agent.state.battery_pct = max(0.0, agent.state.battery_pct - drain)
        agent.state.sim_time_s = self.sim_time_s
        agent.state.wallclock = self.wallclock

        return rec, emitted

    def _step_toward(
        self, agent: _DroneAgent, wp: Waypoint, dt: float
    ) -> None:
        dist = haversine_m(agent.state.lat, agent.state.lon, wp.lat, wp.lon)
        cruise = self.mission.flight_params.cruise_speed_mps
        max_h = self.mission.airframe.max_horizontal_speed_mps
        v = min(cruise, max_h)
        step_m = v * dt
        if dist <= step_m or dist <= WAYPOINT_REACH_TOLERANCE_M:
            agent.state.lat = wp.lat
            agent.state.lon = wp.lon
            agent.state.speed_mps = 0.0
            return
        bearing = initial_bearing_deg(
            agent.state.lat, agent.state.lon, wp.lat, wp.lon
        )
        agent.state.heading_deg = bearing
        new_lat, new_lon = move_along_bearing(
            agent.state.lat, agent.state.lon, bearing, step_m
        )
        agent.state.lat = new_lat
        agent.state.lon = new_lon
        agent.state.speed_mps = v
        # Altitude tracking.
        alt_err = wp.alt_agl_m - agent.state.alt_agl_m
        max_climb = self.mission.airframe.max_climb_rate_mps * dt
        if abs(alt_err) <= max_climb:
            agent.state.alt_agl_m = wp.alt_agl_m
        elif alt_err > 0:
            agent.state.alt_agl_m += max_climb
        else:
            agent.state.alt_agl_m -= max_climb
        agent.state.alt_msl_m = (
            self.mission.home.alt_msl_m + agent.state.alt_agl_m
        )

    def _build_signal(
        self, agent: _DroneAgent, rgb: float, thermal: float
    ) -> dict[str, Any]:
        coords = {
            "lat": agent.state.lat,
            "lon": agent.state.lon,
            "alt_agl_m": agent.state.alt_agl_m,
            "alt_msl_m": agent.state.alt_msl_m,
            "heading_deg": agent.state.heading_deg,
            "ground_speed_mps": agent.state.speed_mps,
        }
        target_coords: dict[str, float] | None = None
        if agent.detection.target_offset_m > 0.0:
            t_lat, t_lon = move_along_bearing(
                agent.state.lat,
                agent.state.lon,
                agent.detection.target_bearing_deg,
                agent.detection.target_offset_m,
            )
            target_coords = {
                "lat": t_lat,
                "lon": t_lon,
                "estimation_method": "visual_geolocation",
                "horizontal_uncertainty_m": 15.0,
            }
        confidence = min(1.0, 0.5 * rgb + 0.5 * min(thermal / 30.0, 1.0))
        signal_type = "fire" if thermal >= 15.0 else "smoke"
        recommended = (
            "loiter_and_capture"
            if confidence >= agent.auto_loiter_threshold
            else "notify_operator"
        )
        frame_uri = (
            f"file:///tmp/wildfire-watch-sim/{self.mission.zone_id}/"
            f"{agent.drone_id}/t{self.sim_time_s:.2f}.jpg"
        )
        sig = build_signal(
            drone_id=agent.drone_id,
            zone_id=self.mission.zone_id,
            coords=coords,
            target_coords=target_coords,
            signal_type=signal_type,
            confidence=round(confidence, 4),
            rgb_yolo_score=round(rgb, 3),
            thermal_delta_c=round(thermal, 3),
            frame_uris=[frame_uri],
            risk_score=round(confidence * 100.0, 2),
            recommended_action=recommended,
        )
        sig["signal_subtype"] = "sim/swarm_emit"
        sig["timestamp"] = self.wallclock.isoformat().replace("+00:00", "Z")
        return sig
