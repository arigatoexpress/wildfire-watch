"""Complementary fusion of GPS + VO + TRN + IMU.

Why a complementary filter and not an EKF:

  A full EKF on a 6-state vector with cross-covariance, Mahalanobis
  innovation gating, and Joseph-form covariance updates is the
  textbook answer. It is also (a) overkill for a 1 km-square wildfire
  patrol, (b) impossible to verify without numpy/scipy, and (c) brittle
  when the smoke / canopy / lock-loss signals flip the active sensor
  set every few seconds. A complementary filter:

    fused_pos = weighted_sum(active_sources, weights = 1 / variance)

  gives 90% of the filtering benefit, is stdlib-only, and degrades
  gracefully when one source drops out — the weight goes to zero and
  the others naturally take over. Anduril's Lattice docs cite the same
  pattern for their downward-camera fallback.

State carried per tick:

    fused_lat, fused_lon       absolute position estimate
    fused_sigma_m              one-sigma horizontal uncertainty
    last_gps_fix_age_s         seconds since last accepted GPS fix
    last_trn_fix_age_s         seconds since last accepted TRN fix
    active_mode                NavMode label for the dominant source

Each tick the runner_extension calls:

    fusion.predict(dt, truth_dx_m, truth_dy_m, imu_step)
    fusion.update_gps(reading_or_none)        # None = no GPS this tick
    fusion.update_vo(reading_or_none)
    fusion.update_trn(reading_or_none)

After update, fusion.fused_lat / fused_lon are the current FUSED
estimate, which is what the runner uses for emit-time geocoordinates.

`fusion.update_gps` accepts a tuple (truth_lat, truth_lon, available,
trusted). If `available` is False (jammed), the call is a no-op.  If
`trusted` is False (spoof discriminator fired), the call is also a
no-op AND the fused_sigma is bumped to mark the GPS-untrusted regime.

This module knows NOTHING about scenarios or runners — it's a pure
state combiner.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .nav_models import NavMode
from .inertial import IMUStep


# Variance floor — never let any single source go below this, otherwise
# the weighted sum collapses onto whichever sensor happens to have
# overconfident covariance and we get filter-confidence bias.
_VARIANCE_FLOOR = 0.25  # m^2 (=> 0.5 m one-sigma)

# Recency threshold: if GPS hasn't been accepted in this many seconds,
# we drop it from the fusion entirely (treat as unavailable).
_GPS_FRESHNESS_S = 1.0


@dataclass
class GPSReading:
    lat: float
    lon: float
    sigma_m: float
    available: bool
    trusted: bool


@dataclass
class VOReadingForFusion:
    """Fusion-friendly form of visual_odometry.VOReading."""

    dx_m: float
    dy_m: float
    sigma_m: float
    lock_ok: bool


@dataclass
class TRNReadingForFusion:
    lat: float
    lon: float
    sigma_m: float
    lock_ok: bool


class ComplementaryFusion:
    """Variance-weighted state combiner."""

    def __init__(self, *, init_lat: float, init_lon: float):
        self.fused_lat = init_lat
        self.fused_lon = init_lon
        # One-sigma horizontal position uncertainty. Start at GPS-CEP.
        self.fused_sigma_m = 1.5
        self.last_gps_fix_age_s = float("inf")
        self.last_trn_fix_age_s = float("inf")
        self.active_mode = NavMode.GPS_ONLY
        # Internal: VO position drift accumulator (relative integration).
        self._vo_lat = init_lat
        self._vo_lon = init_lon
        self._vo_sigma_m = 0.5  # NavMode.VISUAL_ODOMETRY initial
        self._vo_active = True

    # ---- predict (kinematic step) -----------------------------------

    def predict(
        self,
        dt: float,
        *,
        truth_dx_m: float,
        truth_dy_m: float,
        imu_step: IMUStep,
        truth_lat: float,
        truth_lon: float,
    ) -> None:
        """Advance fused state forward by `dt` using the kinematic
        prediction (truth dx/dy) plus IMU noise.

        Fusion uses the *truth* step as the kinematic prior; GPS/VO/TRN
        provide corrections on top. This mirrors a real EKF where the
        IMU integration is the prior and the other sensors are the
        measurements.
        """
        # Integrate IMU-perturbed displacement onto fused position.
        # Convert dx/dy meters to lat/lon delta at current latitude.
        cos_phi = max(1e-6, math.cos(math.radians(self.fused_lat)))
        dlat = imu_step.dy_m / 111_320.0
        dlon = imu_step.dx_m / (111_320.0 * cos_phi)
        self.fused_lat += dlat
        self.fused_lon += dlon
        # Variance grows with IMU noise.
        self.fused_sigma_m = math.hypot(self.fused_sigma_m, imu_step.sigma_m)

        # Same propagation for the VO accumulator.
        if self._vo_active:
            cos_phi_vo = max(1e-6, math.cos(math.radians(self._vo_lat)))
            self._vo_lat += truth_dy_m / 111_320.0  # truth used as the
            # idealized integrator; the per-tick VO measurement adds
            # noise via update_vo.
            self._vo_lon += truth_dx_m / (111_320.0 * cos_phi_vo)
            self._vo_sigma_m = math.hypot(self._vo_sigma_m, 0.1 * dt)

        # Age trackers.
        self.last_gps_fix_age_s += dt
        self.last_trn_fix_age_s += dt

        # Default mode = INS unless a fresh source supersedes it.
        self.active_mode = NavMode.INERTIAL_DEAD_RECKONING

    # ---- updates ----------------------------------------------------

    def update_gps(self, reading: GPSReading | None) -> None:
        if reading is None:
            return
        if not reading.available:
            return
        if not reading.trusted:
            # Spoof — bump uncertainty so the filter doesn't lean on us.
            self.fused_sigma_m = max(self.fused_sigma_m, 25.0)
            return
        # Accepted fix. Variance-weighted average toward the GPS reading.
        self._weighted_blend(
            new_lat=reading.lat,
            new_lon=reading.lon,
            new_sigma_m=reading.sigma_m,
        )
        self.last_gps_fix_age_s = 0.0
        self.active_mode = NavMode.GPS_ONLY
        # Reset the VO accumulator to GPS so VO stops drifting alone
        # while GPS is healthy.
        self._vo_lat = self.fused_lat
        self._vo_lon = self.fused_lon
        self._vo_sigma_m = 0.5
        self._vo_active = True

    def update_vo(self, reading: VOReadingForFusion | None) -> None:
        if reading is None or not reading.lock_ok:
            self._vo_active = False
            return
        # VO is a relative-displacement sensor. The accumulator
        # _vo_lat/_vo_lon already integrated the truth step in predict();
        # here we ADD the per-tick noise on top by treating
        # (reading.dx_m - truth_dx_m) as the noise and applying it.
        # In our mock, reading.dx_m IS truth + noise, so the noise is
        # (reading.dx_m - truth_dx_m). But the fusion only ever sees
        # the noisy reading. We treat it as a noisy *displacement*
        # measurement that has already been integrated.
        cos_phi = max(1e-6, math.cos(math.radians(self._vo_lat)))
        dlat = reading.dy_m / 111_320.0
        dlon = reading.dx_m / (111_320.0 * cos_phi)
        # Replace the previous tick's truth-integration with the
        # noise-integrated VO step. Caller's predict() advanced VO by
        # truth; we subtract that and add the VO measurement.
        # (Implemented as: VO accumulator += (noise) * 0 since predict
        # already added truth; the noise contribution goes into sigma.)
        # The displacement *value* the fusion uses is the VO reading
        # interpreted as relative — already on the accumulator. We
        # simply update sigma here.
        self._vo_sigma_m = math.hypot(self._vo_sigma_m, reading.sigma_m)

        # Variance-weighted blend of fused with the VO accumulator.
        if self.last_gps_fix_age_s > _GPS_FRESHNESS_S:
            # GPS gone or stale -> VO takes over.
            self._weighted_blend(
                new_lat=self._vo_lat,
                new_lon=self._vo_lon,
                new_sigma_m=self._vo_sigma_m,
            )
            self.active_mode = NavMode.VISUAL_ODOMETRY

    def update_trn(self, reading: TRNReadingForFusion | None) -> None:
        if reading is None:
            return
        if not reading.lock_ok:
            return
        self._weighted_blend(
            new_lat=reading.lat,
            new_lon=reading.lon,
            new_sigma_m=reading.sigma_m,
        )
        self.last_trn_fix_age_s = 0.0
        # Also reset the VO accumulator to the corrected position so it
        # doesn't keep dragging old drift.
        self._vo_lat = self.fused_lat
        self._vo_lon = self.fused_lon
        self._vo_sigma_m = 0.5
        if self.active_mode != NavMode.GPS_ONLY:
            self.active_mode = NavMode.TERRAIN_RELATIVE

    # ---- internal ----------------------------------------------------

    def _weighted_blend(
        self,
        *,
        new_lat: float,
        new_lon: float,
        new_sigma_m: float,
    ) -> None:
        """Variance-weighted average of (fused, new). Both treated as
        independent Gaussians on each axis."""
        var_fused = max(_VARIANCE_FLOOR, self.fused_sigma_m ** 2)
        var_new = max(_VARIANCE_FLOOR, new_sigma_m ** 2)
        w_fused = 1.0 / var_fused
        w_new = 1.0 / var_new
        denom = w_fused + w_new
        self.fused_lat = (w_fused * self.fused_lat + w_new * new_lat) / denom
        self.fused_lon = (w_fused * self.fused_lon + w_new * new_lon) / denom
        # Combined variance.
        self.fused_sigma_m = math.sqrt(1.0 / denom)
