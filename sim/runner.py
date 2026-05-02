"""SimulationRunner — ticks at 10 Hz and emits per-tick state.

Responsibilities each tick:
  1. Advance the drone toward the next waypoint at cruise speed.
  2. Geofence check: if the proposed next position would breach a hard
     exclusion (e.g. West Elk Wilderness, 36 CFR 261.16), clamp the
     drone to the last legal position and emit a system_event signal
     with recommended_action=rtl. If it would breach a warn-type zone
     (e.g. KGUC Class E surface area), emit a single warning system_event
     and continue flying.
  3. Apply scheduled scenario events (delegated to ScenarioEngine).
  4. Update fusion gate inputs (rgb_score, thermal_delta_c, persistence).
  5. If the gate fires (using `should_emit` from infer.py), build a
     wildfire_signal v1 (using `build_signal` from infer.py) and write
     it to the recorder.
  6. Log per-tick state for the recorder (flight_log + SRT).

REUSES `should_emit` and `build_signal` from ml/fire_detection/infer.py.
Does NOT reimplement the schema.
"""

from __future__ import annotations

import logging
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

# Import the real fusion gate + signal builder. Path-injected so we can
# run the simulator from anywhere without packaging gymnastics.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_INFER_DIR = _REPO_ROOT / "ml" / "fire_detection"
if str(_INFER_DIR) not in sys.path:
    sys.path.insert(0, str(_INFER_DIR))
from infer import build_signal, should_emit  # noqa: E402

from .geofence import segment_intersects_polygon  # noqa: E402
from .kinematics import (  # noqa: E402
    haversine_m,
    initial_bearing_deg,
    move_along_bearing,
)
from .mission import GeofenceExclusion, Mission, Waypoint  # noqa: E402
from .scenario import DetectionState, ScenarioEngine  # noqa: E402

logger = logging.getLogger("sim.runner")

# Fusion-gate defaults — match infer.py demo defaults.
DEFAULT_CONF_THRESHOLD = 0.65
DEFAULT_AUTO_LOITER_THRESHOLD = 0.85
DEFAULT_PERSISTENCE_FRAMES = 5  # at 10 Hz that's 0.5 s of sustained signal
DEFAULT_TICK_HZ = 10.0
WAYPOINT_REACH_TOLERANCE_M = 2.0


@dataclass
class DroneState:
    lat: float
    lon: float
    alt_agl_m: float
    alt_msl_m: float
    heading_deg: float
    speed_mps: float
    battery_pct: float
    next_wp_index: int
    sim_time_s: float
    wallclock: datetime
    gate_state: str = "closed"


@dataclass
class TickRecord:
    """Per-tick observation passed to the recorder."""

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
class RunnerConfig:
    drone_id: str = "wfw-sim01"
    tick_hz: float = DEFAULT_TICK_HZ
    confidence_threshold: float = DEFAULT_CONF_THRESHOLD
    auto_loiter_threshold: float = DEFAULT_AUTO_LOITER_THRESHOLD
    persistence_frames: int = DEFAULT_PERSISTENCE_FRAMES
    seed: int = 0
    # When True, the runner stops as soon as RTH completes. When False,
    # it stops at the last waypoint without flying back home.
    return_to_home: bool = True
    start_wallclock: datetime | None = None
    # Soft real-time multiplier applied by the CLI (1.0 = real-time).
    speed_multiplier: float = 1.0


@dataclass
class RunResult:
    ticks: int
    sim_seconds: float
    signals_emitted: int
    waypoints_reached: int
    final_battery_pct: float
    drone_path_log: list[TickRecord] = field(default_factory=list)


def _rth_waypoint(mission: Mission) -> Waypoint:
    """Synthetic waypoint representing the home position for RTH."""
    return Waypoint(
        lat=mission.home.lat,
        lon=mission.home.lon,
        alt_agl_m=mission.flight_params.altitude_agl_m,
        action="rtl",
    )


def _waypoint_sequence(mission: Mission) -> list[Waypoint]:
    seq = list(mission.waypoints)
    if mission.return_to_home:
        seq.append(_rth_waypoint(mission))
    return seq


class SimulationRunner:
    """Drives the drone along the mission and emits signals."""

    def __init__(
        self,
        mission: Mission,
        scenario_engine: ScenarioEngine,
        config: RunnerConfig,
        *,
        on_signal: Callable[[dict[str, Any]], None] | None = None,
        on_tick: Callable[[TickRecord], None] | None = None,
    ):
        self.mission = mission
        self.scenario_engine = scenario_engine
        self.config = config
        self.on_signal = on_signal or (lambda _s: None)
        self.on_tick = on_tick or (lambda _t: None)
        self.detection = DetectionState()
        self.persistence: deque[bool] = deque(maxlen=config.persistence_frames)
        self.waypoints = _waypoint_sequence(mission)
        # Track when each waypoint was first reached, so the scenario
        # engine can apply waypoint-relative offsets.
        self.waypoint_reach_time_s: dict[int, float] = {}
        self.signals_emitted = 0
        self.tick_records: list[TickRecord] = []
        self._battery_drain_per_s = 100.0 / max(
            1.0, mission.airframe.battery_minutes * 60.0
        )
        # Geofence enforcement state. Once a hard exclusion is breached
        # we stop advancing waypoints and switch to RTL.
        self._geofence_locked = False
        self._warned_exclusions: set[str] = set()
        self._validate_planned_path()

    # ------------------------------------------------------------------
    # Pre-flight: planned-path validation
    # ------------------------------------------------------------------

    def _validate_planned_path(self) -> None:
        """Walk the planned waypoint sequence and warn (don't refuse) if
        any leg crosses a hard exclusion or any waypoint sits outside
        the inclusion. The user can still opt in — this is advisory only.
        """
        fence = self.mission.geofence
        hard = self.mission.hard_exclusions()
        if not fence.inclusion and not hard:
            return
        # Walk: home -> wp1 -> wp2 ... -> last -> (home if RTH).
        path: list[tuple[float, float]] = [
            (self.mission.home.lat, self.mission.home.lon)
        ]
        for w in self.mission.waypoints:
            path.append((w.lat, w.lon))
        if self.mission.return_to_home:
            path.append((self.mission.home.lat, self.mission.home.lon))
        for i, pt in enumerate(path):
            if not fence.contains(pt[0], pt[1]):
                logger.warning(
                    "planned waypoint %d at (%.6f, %.6f) is outside "
                    "the geofence (inclusion or hard exclusion)",
                    i, pt[0], pt[1],
                )
        for i, (a, b) in enumerate(zip(path, path[1:])):
            for excl in hard:
                if segment_intersects_polygon(a, b, list(excl.polygon)):
                    logger.warning(
                        "planned leg %d crosses hard-exclusion %r (%s) — "
                        "runner will block at the boundary at flight time",
                        i, excl.name, excl.regulatory_basis,
                    )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, max_sim_seconds: float = 3600.0) -> RunResult:
        """Run the sim. Returns when the mission completes or budget exhausts."""
        wall0 = self.config.start_wallclock or datetime.now(UTC).replace(microsecond=0)
        state = DroneState(
            lat=self.mission.home.lat,
            lon=self.mission.home.lon,
            alt_agl_m=0.0,
            alt_msl_m=self.mission.home.alt_msl_m,
            heading_deg=0.0,
            speed_mps=0.0,
            battery_pct=100.0,
            next_wp_index=0,
            sim_time_s=0.0,
            wallclock=wall0,
        )
        # Seed climb to the cruise altitude in the first second of flight.
        state.alt_agl_m = self.mission.flight_params.altitude_agl_m
        state.alt_msl_m = self.mission.home.alt_msl_m + state.alt_agl_m

        dt = 1.0 / self.config.tick_hz
        ticks = 0
        max_ticks = int(max_sim_seconds * self.config.tick_hz) + 1

        while ticks < max_ticks:
            self._tick(state, dt)
            ticks += 1
            if state.next_wp_index >= len(self.waypoints):
                break
            if self._geofence_locked:
                # Run a short coast-down so the recorder gets a clean
                # final state, then break. The drone is already clamped
                # at the last legal position with speed_mps=0.0.
                break
            if state.battery_pct <= 0.0:
                logger.warning("battery exhausted at tick %d", ticks)
                break

        return RunResult(
            ticks=ticks,
            sim_seconds=state.sim_time_s,
            signals_emitted=self.signals_emitted,
            waypoints_reached=len(self.waypoint_reach_time_s),
            final_battery_pct=state.battery_pct,
            drone_path_log=list(self.tick_records),
        )

    # ------------------------------------------------------------------
    # Single tick
    # ------------------------------------------------------------------

    def _tick(self, state: DroneState, dt: float) -> None:
        # --- 1. Move drone toward next waypoint ---
        if state.next_wp_index < len(self.waypoints) and not self._geofence_locked:
            wp = self.waypoints[state.next_wp_index]
            prev = (state.lat, state.lon)
            self._step_toward(state, wp, dt)
            # Geofence enforcement: clamp to `prev` if the new position
            # entered a hard exclusion (or left the inclusion).
            self._enforce_geofence(state, prev)
            if not self._geofence_locked:
                dist = haversine_m(state.lat, state.lon, wp.lat, wp.lon)
                if dist <= WAYPOINT_REACH_TOLERANCE_M:
                    if state.next_wp_index not in self.waypoint_reach_time_s:
                        self.waypoint_reach_time_s[state.next_wp_index] = state.sim_time_s
                    state.next_wp_index += 1

        # --- 2. Scenario engine ---
        last_reached = max(self.waypoint_reach_time_s.keys()) if self.waypoint_reach_time_s else -1
        self.scenario_engine.step(
            sim_time_s=state.sim_time_s,
            dt=dt,
            last_reached_waypoint_index=last_reached,
            waypoint_reach_time_s=self.waypoint_reach_time_s,
            state=self.detection,
        )

        # --- 3. Persistence buffer for fusion gate ---
        rgb = self.detection.rgb_score
        thermal = self.detection.thermal_delta_c
        self.persistence.append(rgb >= self.config.confidence_threshold)
        run_length = sum(self.persistence)

        gate_open = should_emit(
            rgb_score=rgb,
            thermal_delta_c=thermal,
            persistence_frames=run_length,
            geofence_ok=True,
            wind_consistent=True,
            threshold=self.config.confidence_threshold,
            persistence_min=self.config.persistence_frames,
        )
        state.gate_state = "OPEN" if gate_open else "closed"

        # --- 4. Emit signal if gate open ---
        if gate_open:
            sig = self._build_signal(state, rgb, thermal)
            self.signals_emitted += 1
            self.on_signal(sig)

        # --- 5. Telemetry log ---
        rec = TickRecord(
            ts_iso=state.wallclock.isoformat().replace("+00:00", "Z"),
            sim_time_s=round(state.sim_time_s, 3),
            lat=state.lat,
            lon=state.lon,
            alt_agl_m=state.alt_agl_m,
            alt_msl_m=state.alt_msl_m,
            heading_deg=state.heading_deg,
            speed_mps=state.speed_mps,
            battery_pct=round(state.battery_pct, 3),
            gate_state=state.gate_state,
            rgb_score=round(rgb, 3),
            thermal_delta_c=round(thermal, 3),
        )
        self.tick_records.append(rec)
        self.on_tick(rec)

        # --- 6. Advance time + battery ---
        state.sim_time_s += dt
        state.wallclock = state.wallclock + timedelta(seconds=dt)
        drain = self._battery_drain_per_s * dt * self.detection.battery_drain_multiplier
        state.battery_pct = max(0.0, state.battery_pct - drain)

    def _step_toward(self, state: DroneState, wp: Waypoint, dt: float) -> None:
        dist = haversine_m(state.lat, state.lon, wp.lat, wp.lon)
        cruise = self.mission.flight_params.cruise_speed_mps
        max_h = self.mission.airframe.max_horizontal_speed_mps
        v = min(cruise, max_h)
        step_m = v * dt
        if dist <= step_m or dist <= WAYPOINT_REACH_TOLERANCE_M:
            # Snap to waypoint and zero ground speed.
            state.lat = wp.lat
            state.lon = wp.lon
            state.speed_mps = 0.0
            return
        bearing = initial_bearing_deg(state.lat, state.lon, wp.lat, wp.lon)
        state.heading_deg = bearing
        new_lat, new_lon = move_along_bearing(state.lat, state.lon, bearing, step_m)
        state.lat = new_lat
        state.lon = new_lon
        state.speed_mps = v
        # Climb-rate-limited altitude tracking.
        alt_err = wp.alt_agl_m - state.alt_agl_m
        max_climb = self.mission.airframe.max_climb_rate_mps * dt
        if abs(alt_err) <= max_climb:
            state.alt_agl_m = wp.alt_agl_m
        elif alt_err > 0:
            state.alt_agl_m += max_climb
        else:
            state.alt_agl_m -= max_climb
        state.alt_msl_m = self.mission.home.alt_msl_m + state.alt_agl_m

    # ------------------------------------------------------------------
    # Geofence enforcement
    # ------------------------------------------------------------------

    def _enforce_geofence(
        self,
        state: DroneState,
        prev: tuple[float, float],
    ) -> None:
        """If the move from `prev` to (state.lat, state.lon) breached
        a hard exclusion or left the inclusion, clamp position to `prev`,
        emit a system_event signal with recommended_action=rtl, and
        latch the runner into RTL mode (no further waypoint advance).

        For warn-type exclusions, emit a warning system_event the FIRST
        time the drone enters that zone and continue flying.
        """
        fence = self.mission.geofence
        new = (state.lat, state.lon)

        # Hard exclusion check (highest priority).
        for excl in self.mission.hard_exclusions():
            entered = (
                segment_intersects_polygon(prev, new, list(excl.polygon))
                or self._point_in_polygon(new[0], new[1], excl.polygon)
            )
            if entered:
                self._lock_at_boundary(state, prev, excl, breach="hard")
                return

        # Inclusion check (only when an inclusion polygon is present).
        if fence.inclusion and not fence.contains(new[0], new[1]):
            # Synthesize an "inclusion-edge" event — same hard semantics.
            self._lock_at_boundary(state, prev, None, breach="inclusion")
            return

        # Warn-type exclusions: emit once per name.
        for excl in self.mission.warn_exclusions():
            inside_now = self._point_in_polygon(new[0], new[1], excl.polygon)
            if inside_now and excl.name not in self._warned_exclusions:
                self._warned_exclusions.add(excl.name)
                sig = self._make_system_event(
                    state=state,
                    summary=f"entered warn-zone {excl.name!r}",
                    regulatory_basis=excl.regulatory_basis,
                    recommended_action="notify_operator",
                    breach_kind="warn",
                    exclusion_name=excl.name,
                )
                self.signals_emitted += 1
                self.on_signal(sig)

    @staticmethod
    def _point_in_polygon(
        lat: float, lon: float, polygon: tuple[tuple[float, float], ...]
    ) -> bool:
        # Local indirection so tests / subclasses can monkey-patch.
        from .geofence import point_in_polygon as _pip
        return _pip(lat, lon, list(polygon))

    def _lock_at_boundary(
        self,
        state: DroneState,
        prev: tuple[float, float],
        excl: GeofenceExclusion | None,
        breach: str,
    ) -> None:
        # Clamp position to last legal point.
        state.lat, state.lon = prev
        state.speed_mps = 0.0
        self._geofence_locked = True
        if excl is not None:
            summary = f"hard exclusion {excl.name!r} would be breached"
            basis = excl.regulatory_basis
            name = excl.name
        else:
            summary = "would exit inclusion polygon"
            basis = ""
            name = "inclusion-edge"
        logger.warning(
            "geofence breach prevented at sim_t=%.2f s: %s — switching to RTL",
            state.sim_time_s, summary,
        )
        sig = self._make_system_event(
            state=state,
            summary=summary,
            regulatory_basis=basis,
            recommended_action="rtl",
            breach_kind=breach,
            exclusion_name=name,
        )
        self.signals_emitted += 1
        self.on_signal(sig)

    def _make_system_event(
        self,
        *,
        state: DroneState,
        summary: str,
        regulatory_basis: str,
        recommended_action: str,
        breach_kind: str,
        exclusion_name: str,
    ) -> dict[str, Any]:
        """Build a schema-conforming system_event signal via build_signal.

        We cannot stash arbitrary keys on the signal (additionalProperties
        is false in the schema), so we encode breach metadata into
        `signal_subtype` and into the synthetic frame URI.
        """
        coords = {
            "lat": state.lat,
            "lon": state.lon,
            "alt_agl_m": state.alt_agl_m,
            "alt_msl_m": state.alt_msl_m,
            "heading_deg": state.heading_deg,
            "ground_speed_mps": state.speed_mps,
        }
        # Encode the breach metadata into the frame URI so downstream
        # log readers can correlate without a schema bump.
        safe_name = exclusion_name.replace("/", "_").replace(" ", "_")
        frame_uri = (
            f"file:///tmp/wildfire-watch-sim/{self.mission.zone_id}/"
            f"system_event/{breach_kind}/{safe_name}/"
            f"t{state.sim_time_s:.2f}.json"
        )
        sig = build_signal(
            drone_id=self.config.drone_id,
            zone_id=self.mission.zone_id,
            coords=coords,
            target_coords=None,
            signal_type="system_event",
            confidence=1.0,
            rgb_yolo_score=0.0,
            thermal_delta_c=0.0,
            frame_uris=[frame_uri],
            risk_score=100.0 if breach_kind == "hard" else 50.0,
            recommended_action=recommended_action,
        )
        sig["signal_subtype"] = (
            f"sim/geofence_{breach_kind}_breach:{exclusion_name}"
            + (f" ({regulatory_basis})" if regulatory_basis else "")
        )
        sig["timestamp"] = state.wallclock.isoformat().replace("+00:00", "Z")
        # Mark geofence_status accurately for hard breaches.
        if breach_kind != "warn":
            sig["geofence_status"] = {
                "in_authorized_zone": False,
                "tfr_active": False,
                "remote_id_active": True,
            }
        return sig

    # ------------------------------------------------------------------
    # Signal construction (delegates to infer.build_signal)
    # ------------------------------------------------------------------

    def _build_signal(self, state: DroneState, rgb: float, thermal: float) -> dict[str, Any]:
        coords = {
            "lat": state.lat,
            "lon": state.lon,
            "alt_agl_m": state.alt_agl_m,
            "alt_msl_m": state.alt_msl_m,
            "heading_deg": state.heading_deg,
            "ground_speed_mps": state.speed_mps,
        }
        target_coords: dict[str, float] | None = None
        if self.detection.target_offset_m > 0.0:
            t_lat, t_lon = move_along_bearing(
                state.lat,
                state.lon,
                self.detection.target_bearing_deg,
                self.detection.target_offset_m,
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
            if confidence >= self.config.auto_loiter_threshold
            else "notify_operator"
        )
        # Synthetic frame URI — the simulator does not write real frames.
        # Schema requires at least one URI; we use a deterministic file URI
        # so downstream tools can correlate by signal_id.
        frame_uri = (
            f"file:///tmp/wildfire-watch-sim/{self.mission.zone_id}/"
            f"t{state.sim_time_s:.2f}.jpg"
        )
        sig = build_signal(
            drone_id=self.config.drone_id,
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
        sig["signal_subtype"] = "sim/scenario_burst"
        # Override timestamp to use the simulated wallclock so replays line
        # up with flight_log + SRT. infer.build_signal stamps real now().
        sig["timestamp"] = state.wallclock.isoformat().replace("+00:00", "Z")
        return sig
