"""Mock visual-odometry sensor.

We do NOT render real frames. The class returns a noisy per-tick
displacement (dx_m, dy_m) given:

  - the truth-displacement that *actually* happened this tick
  - flight altitude AGL (meters)
  - scene complexity in [0, 1]   1 = lots of texture / features;
                                  0 = uniform low-feature scene
  - smoke_density   in [0, 1]    1 = full smoke obscuration; lock lost

Modeling rationale (documented for the test suite to point at):

  Real VIO drift scales roughly with distance traveled, with a multiplier
  set by scene quality. Bavovna AI publicly claims <= 0.5% of distance
  traveled in clear-sky conditions; OpenVINS / Kimera / ORB-SLAM3 with a
  global-shutter camera land in the 2-5 cm/s range at low altitudes in
  good texture (forest canopy edges, urban-style features).

  We model per-tick noise as Gaussian (Box-Muller) with sigma:

      sigma_per_tick = base_sigma * altitude_factor * (2 - complexity) *
                       (1 + 4 * smoke_density)

      base_sigma = 0.005 m / tick at 80 m AGL, complexity=1, smoke=0
                   (target: ~0.5%-of-distance at 6 m/s cruise, 10 Hz)

  Altitude factor: scenes seen from higher altitude lose feature density
  and small parallax — we scale as max(0.5, altitude / 80). At 40 m AGL
  drift halves; at 160 m AGL it doubles.

  Smoke: when smoke_density >= 0.85 the VO module declares LOCK_LOST and
  the fusion filter must drop our weight to ~zero. Below that, smoke
  amplifies noise but a partial lock survives.

This module is deliberately simple:
  - No loop closure (real VO would close loops at revisited scenes;
    we just integrate per-tick noise forever).
  - No scale ambiguity (real monocular VO has unobservable absolute
    scale; we have a perfect baseline so we cheat).
  - No camera intrinsics, no feature flow vectors, no IMU coupling.

These limitations are listed honestly in README.md.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


# Per-tick base sigma. Calibrated so that integrated drift over 60 s at
# 80 m AGL with scene_complexity=0.7 lands inside the 6 m budget the test
# suite asserts (Bavovna AI's 1%-of-distance claim at 6 m/s cruise).
_BASE_SIGMA_M_PER_TICK = 0.005

# Smoke density above which we declare LOCK_LOST (no useful estimate).
_LOCK_LOST_SMOKE_THRESHOLD = 0.85

# Altitude reference. Below this we do better; above, worse.
_REFERENCE_ALTITUDE_M = 80.0


@dataclass
class VOReading:
    """Per-tick VO output."""

    dx_m: float  # noisy estimate of horizontal displacement east (m)
    dy_m: float  # noisy estimate of horizontal displacement north (m)
    sigma_m: float  # one-sigma per-tick error on each axis
    lock_ok: bool  # False when we lost the feature lock (e.g. heavy smoke)


class VisualOdometry:
    """Mock VO sensor with deterministic seeded noise.

    Caller pattern each tick:

        truth_dx, truth_dy = ... # what the kinematic integrator did
        reading = vo.tick(
            truth_dx_m=truth_dx,
            truth_dy_m=truth_dy,
            altitude_agl_m=80.0,
            scene_complexity=0.7,
            smoke_density=ambient_smoke,
        )
        if reading.lock_ok:
            fuse(reading)

    Note: scene_complexity and smoke_density are scene properties; the
    runner_extension reads them from the active scenario / sim state and
    feeds them in.
    """

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        self.tick_count = 0

    def tick(
        self,
        *,
        truth_dx_m: float,
        truth_dy_m: float,
        altitude_agl_m: float,
        scene_complexity: float,
        smoke_density: float,
    ) -> VOReading:
        self.tick_count += 1
        # Heavy smoke -> we report no lock. Caller drops VO from fusion.
        if smoke_density >= _LOCK_LOST_SMOKE_THRESHOLD:
            return VOReading(dx_m=0.0, dy_m=0.0, sigma_m=float("inf"), lock_ok=False)

        scene_complexity = max(0.0, min(1.0, scene_complexity))
        smoke_density = max(0.0, min(1.0, smoke_density))

        altitude_factor = max(0.5, altitude_agl_m / _REFERENCE_ALTITUDE_M)
        # complexity=1 -> factor 1; complexity=0 -> factor 2.
        complexity_factor = 2.0 - scene_complexity
        # smoke=0 -> factor 1; smoke=0.5 -> factor 3; near threshold -> factor 5.
        smoke_factor = 1.0 + 4.0 * smoke_density

        sigma = (
            _BASE_SIGMA_M_PER_TICK
            * altitude_factor
            * complexity_factor
            * smoke_factor
        )

        # Box-Muller for Gaussian noise on each axis.
        nx = self._gauss() * sigma
        ny = self._gauss() * sigma

        return VOReading(
            dx_m=truth_dx_m + nx,
            dy_m=truth_dy_m + ny,
            sigma_m=sigma,
            lock_ok=True,
        )

    def _gauss(self) -> float:
        u1 = max(1e-12, self._rng.random())
        u2 = self._rng.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
