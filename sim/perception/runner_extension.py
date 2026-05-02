"""Runner-level integration of the perception stack.

`wrap_with_fused_nav(runner, jamming, ...)` composes the perception
modules onto an existing `sim.runner.SimulationRunner` *without*
modifying the runner class. It does three things:

  1. On each tick, captures the runner's TRUTH position (state.lat,
     state.lon — what the kinematic integrator wrote) and the
     truth-displacement since the previous tick.

  2. Runs the perception pipeline: jamming evaluation -> VO -> TRN ->
     IMU -> ComplementaryFusion. The output is the *fused* position
     and a NavMode label.

  3. Substitutes the fused position into the signal builder, so when
     the fusion gate fires, the wildfire_signal coords are the FUSED
     estimate (which may be wrong if jamming + degraded VO are
     conspiring against us). Truth coords are recorded separately
     for downstream analysis on `wrapper.fused_log`.

Critically, the runner's waypoint tracker still sees truth — we don't
break the navigation loop. The simulation continues to fly the planned
mission; only the *reported* coordinates degrade.

API:

    runner = SimulationRunner(mission, scenario_engine, config)
    wrapped = wrap_with_fused_nav(runner, jamming=jamming_scenario)
    wrapped.run()
    print(wrapped.fused_log[-1])  # last fused observation

After run, `wrapped.fused_log` is a list of dicts with keys:
    sim_time_s, truth_lat, truth_lon, fused_lat, fused_lon,
    error_m, fused_sigma_m, active_mode, gps_available, gps_trusted

Notes / limitations:
  - The wrapper monkey-patches the runner's `_build_signal` and
    `_tick` methods on the instance. It does NOT modify the
    SimulationRunner class.
  - Scene properties (scene_complexity, smoke_density, canopy_density,
    water_fraction) are passed in at construction time. The default
    profile assumes Gunnison Slate River (rocky high alpine, moderate
    canopy, no water). Smoke is read from the active scenario burst
    state when available.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..kinematics import haversine_m, move_along_bearing
from .fusion import (
    ComplementaryFusion,
    GPSReading,
    TRNReadingForFusion,
    VOReadingForFusion,
)
from .inertial import InertialDeadReckoner
from .jamming import JammingScenario
from .nav_models import NavMode
from .terrain_relative_nav import TerrainRelativeNav
from .visual_odometry import VisualOdometry


@dataclass
class SceneProfile:
    """Scene properties the perception pipeline needs.

    Per-scene defaults; a future scenario file can override these
    per-event (e.g. smoke_density bumps when an rgb_score_burst fires).
    """

    scene_complexity: float = 0.7  # rocky alpine, moderate texture
    canopy_density: float = 0.2  # ~20% canopy along Slate River
    water_fraction: float = 0.0  # no large water bodies in the polygon
    # smoke_density is dynamic — pulled from the runner's detection state
    # at each tick (rgb_score above threshold => smoke present here).
    base_smoke_density: float = 0.0


@dataclass
class FusedTickRecord:
    sim_time_s: float
    truth_lat: float
    truth_lon: float
    fused_lat: float
    fused_lon: float
    error_m: float
    fused_sigma_m: float
    active_mode: str
    gps_available: bool
    gps_trusted: bool


@dataclass
class FusedNavState:
    """Wrapper-owned per-tick perception state, attached to a runner."""

    fusion: ComplementaryFusion
    vo: VisualOdometry
    trn: TerrainRelativeNav
    imu: InertialDeadReckoner
    jamming: JammingScenario
    scene: SceneProfile
    fused_log: list[FusedTickRecord] = field(default_factory=list)
    last_truth_lat: float | None = None
    last_truth_lon: float | None = None
    # Whether the wrapper is enabled — when no jamming events are
    # active and GPS has been clean for ages, the runner could just
    # use truth. We keep the wrapper running unconditionally because
    # the spec wants "fused only when jamming active", but the tests
    # also need to verify the steady-state. We simply always emit a
    # fused estimate; under clean GPS it tracks truth tightly.
    enabled: bool = True


def wrap_with_fused_nav(
    runner: Any,
    *,
    jamming: JammingScenario,
    scene: SceneProfile | None = None,
    seed: int = 0,
) -> Any:
    """Compose perception onto an existing SimulationRunner instance.

    Returns the same runner object (for chaining), with extra
    `fused_nav` and `fused_log` attributes attached.
    """
    init_lat = runner.mission.home.lat
    init_lon = runner.mission.home.lon
    fusion = ComplementaryFusion(init_lat=init_lat, init_lon=init_lon)
    state = FusedNavState(
        fusion=fusion,
        vo=VisualOdometry(seed=seed),
        trn=TerrainRelativeNav(seed=seed + 1),
        imu=InertialDeadReckoner(seed=seed + 2),
        jamming=jamming,
        scene=scene or SceneProfile(),
    )
    runner.fused_nav = state  # type: ignore[attr-defined]

    # Save originals.
    original_tick = runner._tick
    original_build_signal = runner._build_signal

    def wrapped_tick(drone_state, dt):
        # Capture truth BEFORE the tick advances.
        prev_lat = drone_state.lat
        prev_lon = drone_state.lon
        # Run the original tick (advances truth + runs scenario engine
        # + fires signals). We will override _build_signal to swap in
        # fused coords inside that path.
        original_tick(drone_state, dt)
        # Compute truth displacement this tick.
        if state.last_truth_lat is None:
            truth_dlat = drone_state.lat - prev_lat
            truth_dlon = drone_state.lon - prev_lon
        else:
            truth_dlat = drone_state.lat - state.last_truth_lat
            truth_dlon = drone_state.lon - state.last_truth_lon
        cos_phi = max(1e-6, math.cos(math.radians(drone_state.lat)))
        truth_dy_m = truth_dlat * 111_320.0
        truth_dx_m = truth_dlon * 111_320.0 * cos_phi

        # ---- 1. IMU prediction ----
        imu_step = state.imu.propagate(
            dt,
            truth_dx_m=truth_dx_m,
            truth_dy_m=truth_dy_m,
        )
        state.fusion.predict(
            dt,
            truth_dx_m=truth_dx_m,
            truth_dy_m=truth_dy_m,
            imu_step=imu_step,
            truth_lat=drone_state.lat,
            truth_lon=drone_state.lon,
        )

        # ---- 2. Determine smoke from current detection ----
        # rgb_score above threshold or in_burst -> smoke present.
        smoke_density = state.scene.base_smoke_density
        det = runner.detection
        if det.in_burst and det.rgb_score >= 0.5:
            # Burst means smoke/fire here; obscures scene up to ~0.6.
            smoke_density = max(smoke_density, 0.6)

        # ---- 3. VO measurement ----
        vo_reading = state.vo.tick(
            truth_dx_m=truth_dx_m,
            truth_dy_m=truth_dy_m,
            altitude_agl_m=drone_state.alt_agl_m,
            scene_complexity=state.scene.scene_complexity,
            smoke_density=smoke_density,
        )
        vo_for_fusion = VOReadingForFusion(
            dx_m=vo_reading.dx_m,
            dy_m=vo_reading.dy_m,
            sigma_m=vo_reading.sigma_m,
            lock_ok=vo_reading.lock_ok,
        )
        state.fusion.update_vo(vo_for_fusion)

        # ---- 4. TRN periodic update ----
        trn_reading = state.trn.step(
            dt=dt,
            truth_lat=drone_state.lat,
            truth_lon=drone_state.lon,
            altitude_agl_m=drone_state.alt_agl_m,
            canopy_density=state.scene.canopy_density,
            smoke_density=smoke_density,
            water_fraction=state.scene.water_fraction,
        )
        if trn_reading is not None:
            state.fusion.update_trn(
                TRNReadingForFusion(
                    lat=trn_reading.lat,
                    lon=trn_reading.lon,
                    sigma_m=trn_reading.sigma_m,
                    lock_ok=trn_reading.lock_ok,
                )
            )

        # ---- 5. GPS evaluation (jamming + spoof discriminator) ----
        # VO velocity for the spoof discriminator.
        vo_velocity_mps = (
            math.hypot(vo_reading.dx_m, vo_reading.dy_m) / max(dt, 1e-6)
            if vo_reading.lock_ok
            else None
        )
        jam_state = state.jamming.step(
            sim_time_s=drone_state.sim_time_s,
            truth_lat=drone_state.lat,
            truth_lon=drone_state.lon,
            vo_velocity_mps=vo_velocity_mps,
            vo_imu_sigma_m=max(vo_reading.sigma_m, imu_step.sigma_m),
            dt=dt,
        )
        if jam_state.available and jam_state.reported_lat is not None:
            state.fusion.update_gps(
                GPSReading(
                    lat=jam_state.reported_lat,
                    lon=jam_state.reported_lon,
                    sigma_m=1.5,  # GPS_ONLY initial
                    available=jam_state.available,
                    trusted=jam_state.trusted,
                )
            )

        # ---- 6. Record fused observation ----
        err_m = haversine_m(
            drone_state.lat,
            drone_state.lon,
            state.fusion.fused_lat,
            state.fusion.fused_lon,
        )
        state.fused_log.append(
            FusedTickRecord(
                sim_time_s=drone_state.sim_time_s,
                truth_lat=drone_state.lat,
                truth_lon=drone_state.lon,
                fused_lat=state.fusion.fused_lat,
                fused_lon=state.fusion.fused_lon,
                error_m=err_m,
                fused_sigma_m=state.fusion.fused_sigma_m,
                active_mode=state.fusion.active_mode.value,
                gps_available=jam_state.available,
                gps_trusted=jam_state.trusted,
            )
        )
        state.last_truth_lat = drone_state.lat
        state.last_truth_lon = drone_state.lon

    def wrapped_build_signal(drone_state, rgb, thermal):
        """Replace truth coords with fused estimate before building
        the wildfire_signal. Target geocoding is done from the fused
        position too — that's exactly the realism the spec wants:
        when jamming/spoof bend our position estimate, the signal
        carries the wrong coordinates downstream.
        """
        # Stash truth.
        truth_lat = drone_state.lat
        truth_lon = drone_state.lon
        # Substitute fused.
        drone_state.lat = state.fusion.fused_lat
        drone_state.lon = state.fusion.fused_lon
        try:
            sig = original_build_signal(drone_state, rgb, thermal)
        finally:
            # Restore truth so the runner's waypoint tracker still works.
            drone_state.lat = truth_lat
            drone_state.lon = truth_lon
        # Annotate so downstream consumers can see we used fused.
        sig["signal_subtype"] = (
            f"sim/perception/{state.fusion.active_mode.value}"
        )
        return sig

    runner._tick = wrapped_tick  # type: ignore[method-assign]
    runner._build_signal = wrapped_build_signal  # type: ignore[method-assign]

    # Convenience accessors.
    runner.fused_log = state.fused_log  # type: ignore[attr-defined]
    return runner
