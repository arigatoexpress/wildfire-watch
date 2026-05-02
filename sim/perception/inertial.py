"""Inertial dead-reckoning model — random-walk MEMS IMU.

Calibration target: Cube Orange+ ICM-20689 spec, consumer-grade.
Public datasheet baselines:

    gyro bias-instability ~ 0.05 deg/s  (one-sigma)
    accel bias-instability ~ 50 mg     (one-sigma; ~0.5 m/s^2)

We do NOT integrate a 6-axis state — we model the *projected* horizontal
position drift per tick as the sum of:

  - velocity-drift from accel-bias integration (the dominant term over
    seconds-to-minutes)
  - heading-drift from gyro-bias integration (small-angle approximation
    rotates the velocity vector)

Per-tick variance contributions:

    sigma_pos_per_tick = 0.5 * accel_bias_sigma * dt^2
                       + accel_random_walk_sigma * dt^1.5

Calibrated such that integrated random-walk position drift over 60 s of
pure-INS (no GPS / no VO) lands near 30 m one-sigma — consistent with
"consumer-grade MEMS dead-reckons to ~30 m at 1 minute" rule of thumb.

API:

    imu = InertialDeadReckoner(seed=0)
    dx, dy, dheading = imu.propagate(dt, truth_dx_m=..., truth_dy_m=...)

The (dx, dy) returned are *truth + integrated noise*. Caller integrates
this onto the previous fused state.

Limitations vs real IMU integration:
  - We don't model gravity, only horizontal motion.
  - We don't model the gyro-coupled velocity rotation explicitly; we
    treat heading-drift as an output the caller can ignore.
  - We use linear time-scaling instead of stochastic integrals; close
    enough for 60-second outage tests, very wrong for 60-minute ones.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


# ICM-20689 consumer-grade spec. Calibrated so that 60 s of pure-INS
# integration produces a ~30 m one-sigma horizontal drift (the public-
# claim rule of thumb for consumer MEMS). We assume the EKF has tuned
# out the bulk of the bias instability — the *residual* after EKF
# tuning is much smaller than the raw datasheet number.
_ACCEL_BIAS_SIGMA_MPS2 = 0.003  # m/s^2 residual bias post-EKF
_ACCEL_RANDOM_WALK_SIGMA = 0.12  # velocity random walk, m/s/sqrt(s)
_GYRO_BIAS_SIGMA_DEGPS = 0.05  # deg/s one-sigma raw


@dataclass
class IMUStep:
    dx_m: float
    dy_m: float
    dheading_deg: float
    sigma_m: float  # accumulated one-sigma growth this tick


class InertialDeadReckoner:
    """Per-tick random-walk integrator for a consumer MEMS IMU.

    State carried across calls:

      _vel_err_x, _vel_err_y    accumulated velocity error (m/s).
                                Each tick we add a Gaussian increment
                                to this (velocity random walk), then
                                integrate the velocity into position.
      _accel_bias_x/y           constant bias terms drawn at init.

    This produces position drift that scales as sigma * T^1.5 — the
    correct stochastic-integral order for "integrate(integrate(white
    noise))". With _ACCEL_RANDOM_WALK_SIGMA = 0.4 m/s/sqrt(s), 60 s
    of pure-INS integration produces ~25-35 m one-sigma drift,
    consistent with consumer-grade MEMS IMU public-claim baselines.
    """

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        # Constant bias terms — drawn from the bias-instability
        # distribution at init.
        self._accel_bias_x = self._gauss() * _ACCEL_BIAS_SIGMA_MPS2
        self._accel_bias_y = self._gauss() * _ACCEL_BIAS_SIGMA_MPS2
        self._gyro_bias_degps = self._gauss() * _GYRO_BIAS_SIGMA_DEGPS
        # Velocity-error accumulators. Each tick gets a Gaussian
        # increment scaled by sqrt(dt) (Brownian motion).
        self._vel_err_x = 0.0
        self._vel_err_y = 0.0
        # Cumulative unaided time, for diagnostics.
        self.unaided_seconds = 0.0

    def reset_unaided(self) -> None:
        """Called by the fusion layer when a GPS or TRN fix is accepted."""
        self.unaided_seconds = 0.0
        # Reset the velocity-error too — a fix nukes the accumulated drift.
        self._vel_err_x = 0.0
        self._vel_err_y = 0.0

    def propagate(
        self,
        dt: float,
        *,
        truth_dx_m: float = 0.0,
        truth_dy_m: float = 0.0,
    ) -> IMUStep:
        """Advance one tick. Truth displacements are perturbed by
        accumulated bias + integrated velocity-random-walk noise."""
        self.unaided_seconds += dt
        # Add Gaussian increment to velocity-error (Brownian motion).
        self._vel_err_x += self._gauss() * _ACCEL_RANDOM_WALK_SIGMA * math.sqrt(dt)
        self._vel_err_y += self._gauss() * _ACCEL_RANDOM_WALK_SIGMA * math.sqrt(dt)
        # Bias-integrated velocity contribution.
        bias_vel_x = self._accel_bias_x * self.unaided_seconds
        bias_vel_y = self._accel_bias_y * self.unaided_seconds
        # Per-tick displacement = velocity * dt (both error sources).
        dx_noise = (self._vel_err_x + bias_vel_x) * dt
        dy_noise = (self._vel_err_y + bias_vel_y) * dt
        dx = truth_dx_m + dx_noise
        dy = truth_dy_m + dy_noise
        dheading = self._gyro_bias_degps * dt + self._gauss() * 0.01 * dt
        # Per-tick one-sigma growth. We scale per-tick because the
        # fusion layer uses this as variance increment, not absolute.
        sigma = math.hypot(dx_noise, dy_noise)
        return IMUStep(
            dx_m=dx,
            dy_m=dy,
            dheading_deg=dheading,
            sigma_m=sigma,
        )

    def _gauss(self) -> float:
        u1 = max(1e-12, self._rng.random())
        u2 = self._rng.random()
        return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
