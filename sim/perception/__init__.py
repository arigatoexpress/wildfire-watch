"""GNSS-denied vision-navigation primitives for the wildfire-watch sim.

Composable, side-by-side with the existing single-drone runner. Nothing
in this package mutates `sim.runner` — it wraps a runner instance via
`runner_extension.wrap_with_fused_nav` and substitutes the per-tick
GPS-only position update with a fused estimate that degrades gracefully
when GPS is jammed or spoofed.

Why this exists:

  Smoke kills GPS lock. Canyon walls shadow GPS. Hostile actors jam and
  spoof GPS. The Ukraine drone playbook (docs/intel/ukraine-drone-
  playbook-2026-05-01.md) identifies vision-based GNSS-denied navigation
  (OSCAR / KrattWorks Ghost Dragon / Bavovna AI) as the pattern that
  solves all three. This sim primitive lets us stress-test the
  wildfire_signal pipeline under those conditions BEFORE we put a real
  airframe over a real fire.

Public surface:

  nav_models.NavMode             — enumeration of position-source modes
  visual_odometry.VisualOdometry — mock VO sensor (feature-flow scalar)
  terrain_relative_nav.TerrainRelativeNav
                                 — periodic absolute-position correction
  inertial.InertialDeadReckoner  — random-walk MEMS IMU model
  fusion.ComplementaryFusion     — variance-weighted state combiner
  jamming.JammingScenario        — YAML-loadable GPS-outage / spoof events
  runner_extension.wrap_with_fused_nav(runner, jamming=...)
                                 — composes the above onto an existing
                                   SimulationRunner without touching
                                   single-drone or swarm code

No NumPy, no SciPy, no filterpy — stdlib + pyyaml only.
"""

from __future__ import annotations

__all__ = [
    "fusion",
    "inertial",
    "jamming",
    "nav_models",
    "runner_extension",
    "terrain_relative_nav",
    "visual_odometry",
]
