"""Navigation-mode enumeration + per-mode drift envelopes.

Each NavMode has two scalar attributes used by the fusion filter:

  initial_uncertainty_m   one-sigma horizontal CEP at t=0 of relying on
                          this source alone, in meters.
  drift_growth_mps        rate at which that one-sigma uncertainty grows
                          per second of unaided operation, in m/s.
                          (Bounded estimators — TRN — report 0.0 here:
                          their error is set by map resolution, not by
                          dead-reckoning integration.)

The numbers below are public-claim baselines. They are meant to be
plausible bounds for the kinematic integrator, not certified envelopes:

  GPS_ONLY                  consumer GPS in clear sky: 1.5 m CEP, no
                            growth.  (u-blox M10 spec sheet open-sky
                            CEP.)
  VISUAL_ODOMETRY           Bavovna AI public claim is "<= 0.5% of
                            distance traveled" — at 6 m/s that's about
                            0.03 m/s drift growth, but feature-flow
                            uncertainty in degraded scenes (low texture,
                            smoke, water) bumps it. We model 0.1 m/s as
                            the headline growth rate; visual_odometry.py
                            scales it by altitude / scene-complexity /
                            smoke.
  TERRAIN_RELATIVE          USGS DEM 1/3 arc-second ~10 m horizontal
                            resolution; we round down to 5 m one-sigma
                            and ZERO drift growth (TRN is bounded — it
                            doesn't drift, it just sometimes can't lock).
  INERTIAL_DEAD_RECKONING   Cube Orange+ ICM-20689 consumer-grade MEMS.
                            Random-walk drift over 60 s of pure-INS
                            ~30 m one-sigma in horizontal position; we
                            model 0.5 m/s growth from a 0 m start.
  FUSED                     Computed; included as a tag, never used as
                            a source.  fusion.py drives the actual
                            variance combination.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass


class NavMode(enum.Enum):
    GPS_ONLY = "gps_only"
    VISUAL_ODOMETRY = "visual_odometry"
    TERRAIN_RELATIVE = "terrain_relative"
    INERTIAL_DEAD_RECKONING = "inertial_dead_reckoning"
    FUSED = "fused"


@dataclass(frozen=True)
class DriftEnvelope:
    """One-sigma initial CEP + per-second drift-growth, in meters."""

    initial_uncertainty_m: float
    drift_growth_mps: float


# Per-mode public-claim envelopes. See module docstring for sourcing.
DRIFT_ENVELOPES: dict[NavMode, DriftEnvelope] = {
    NavMode.GPS_ONLY: DriftEnvelope(initial_uncertainty_m=1.5, drift_growth_mps=0.0),
    NavMode.VISUAL_ODOMETRY: DriftEnvelope(
        initial_uncertainty_m=0.5, drift_growth_mps=0.1
    ),
    NavMode.TERRAIN_RELATIVE: DriftEnvelope(
        initial_uncertainty_m=5.0, drift_growth_mps=0.0
    ),
    NavMode.INERTIAL_DEAD_RECKONING: DriftEnvelope(
        initial_uncertainty_m=0.0, drift_growth_mps=0.5
    ),
    # FUSED is computed by fusion.py; envelope here is a placeholder so
    # callers iterating over the mapping don't crash. fusion.py never
    # consults this row.
    NavMode.FUSED: DriftEnvelope(initial_uncertainty_m=0.0, drift_growth_mps=0.0),
}


def envelope(mode: NavMode) -> DriftEnvelope:
    """Lookup helper — raises KeyError on unknown mode."""
    return DRIFT_ENVELOPES[mode]


def projected_uncertainty_m(mode: NavMode, seconds_unaided: float) -> float:
    """One-sigma horizontal uncertainty after `seconds_unaided` seconds.

    Integrates the simple linear-growth envelope:

        sigma(t) = sigma_0 + drift_growth * t

    No square-root scaling — even though IMU random walk is
    technically sigma * sqrt(t), the linear approximation is well
    inside the noise floor of the public-claim numbers we're
    calibrating against, and it makes the fusion variance update
    deterministic across replays.
    """
    env = envelope(mode)
    return env.initial_uncertainty_m + env.drift_growth_mps * max(0.0, seconds_unaided)
