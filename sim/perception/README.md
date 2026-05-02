# sim/perception — GNSS-denied vision navigation

A composable perception primitive that lets the wildfire-watch simulator
fly under GPS-jamming and GPS-spoofing conditions. It does NOT modify
`sim/runner.py` or `sim/swarm/`. It wraps an existing
`SimulationRunner` instance via `wrap_with_fused_nav(...)`.

## Why

The Ukraine drone playbook
(`docs/intel/ukraine-drone-playbook-2026-05-01.md`) identifies vision-
based GNSS-denied navigation (OSCAR, KrattWorks Ghost Dragon, Bavovna
AI) as the pattern that solves three intersecting wildfire problems:

1. **Smoke kills GPS.** Dense smoke columns degrade GPS signal-to-noise.
2. **Canyons shadow GPS.** Below ridgeline, half the constellation
   drops out of view (Gunnison-Crested Butte AOR).
3. **Hostile actors jam.** Even non-state forest-fire arsonists could
   trivially jam consumer GPS bands.

A real airframe must still navigate when GPS dies. This package models
that capability so we can stress-test the wildfire_signal pipeline
*before* putting hardware over a fire.

## Architecture

```
                        SimulationRunner (truth)
                                |
                                v
              wrap_with_fused_nav(runner, jamming)
                                |
   each tick:                   v
   +------------------ wrapped_tick(state, dt) ------------------+
   |                                                              |
   |  1. truth advances (original SimulationRunner._tick)          |
   |  2. IMU.propagate(dt)        -> dx, dy, dheading + sigma     |
   |  3. fusion.predict(...)      kinematic prior + IMU noise     |
   |  4. VO.tick(...)             dx, dy with feature-flow noise  |
   |  5. fusion.update_vo(...)                                    |
   |  6. TRN.step(dt, ...)        periodic absolute correction    |
   |  7. fusion.update_trn(...)                                   |
   |  8. jamming.step(...)        -> available, trusted, reported |
   |  9. fusion.update_gps(...)                                   |
   |  10. record FusedTickRecord  (truth + fused + error)         |
   +--------------------------------------------------------------+
                                |
                                v
                wildfire_signal coords = FUSED estimate
                (truth still drives waypoint navigation)
```

## Drift envelopes (per-mode)

| Mode | Initial CEP | Drift growth | Source |
|------|-------------|--------------|--------|
| GPS_ONLY | 1.5 m | 0 | u-blox M10 open-sky CEP |
| VISUAL_ODOMETRY | 0.5 m | 0.1 m/s | Bavovna AI <=0.5%-of-distance |
| TERRAIN_RELATIVE | 5 m | 0 | USGS DEM 1/3 arc-second |
| INERTIAL_DEAD_RECKONING | 0 m | 0.5 m/s | ICM-20689 random walk |
| FUSED | computed | computed | complementary filter |

## Why complementary filter, not EKF

A full 6-state EKF with cross-covariance and Joseph-form updates is the
textbook answer. It is also impossible to verify without numpy/scipy
and brittle when the active sensor set flips every few seconds (smoke
on, smoke off, GPS in, GPS out). A variance-weighted complementary
filter gives ~90% of the benefit, is stdlib-only, and degrades
gracefully — the weight on a dropped sensor goes to zero and the
others naturally take over. Anduril's Lattice docs cite the same
pattern for their downward-camera fallback.

## Spoof detection

Per tick we compare GPS-reported position-delta against VO+IMU
position-delta. If they disagree by more than 3*sigma (sigma = combined
VO+IMU per-tick uncertainty), we mark `trusted=False` and the fusion
filter bumps its sigma to 25 m so GPS stops dominating. This is the
*inertial-consistency* branch only — real anti-spoofing also uses
multi-band L1/L5 receivers, CRPA antennas, and spoofing-signature
databases.

## Honest limitations

1. **No actual camera frames.** VO is a feature-flow scalar. Real VIO
   cares about feature distribution, exposure, motion blur, rolling
   shutter — none of which we model.
2. **No loop closure.** Real VO closes loops at revisited scenes,
   bounding drift; ours integrates per-tick noise forever.
3. **No scale ambiguity.** Real monocular VO has unobservable absolute
   scale; we cheat with truth.
4. **Simplified spoof detection.** Production systems combine inertial
   consistency, multi-band, CRPA, and L5 anti-jam — we model only
   inertial.
5. **Linear drift growth, not stochastic-integral.** sigma(t) ~= sigma_0
   + drift*t, instead of sigma_0 + drift*sqrt(t). Close enough for
   60-second tests, very wrong for 60-minute ones.
6. **No DEM / orthoimagery.** TRN is mocked: a Gaussian-perturbed truth
   when the matcher *would* lock; nothing when canopy/smoke/water/
   altitude rule out a lock.

## Usage

```python
from sim.runner import SimulationRunner, RunnerConfig
from sim.perception.runner_extension import wrap_with_fused_nav, SceneProfile
from sim.perception.jamming import JammingScenario
import sim.mission as M
import sim.scenario as S

mission = M.load_mission("sim/missions/gunnison_slate_river_1km2.yaml")
scenario = S.load_scenario("sim/scenarios/single_smoke_plume.yaml")
jamming = JammingScenario.load("sim/perception/scenarios/canyon_gps_outage.yaml")

runner = SimulationRunner(
    mission=mission,
    scenario_engine=S.ScenarioEngine(scenario),
    config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
)
wrapped = wrap_with_fused_nav(runner, jamming=jamming)
wrapped.run(max_sim_seconds=600.0)

for rec in wrapped.fused_log[-10:]:
    print(f"t={rec.sim_time_s:.1f}s mode={rec.active_mode} err={rec.error_m:.2f}m")
```

## Tests

```
cd ~/Code/wildfire-watch
python3 -m pytest sim/perception/tests/ -q
```

The end-to-end test runs a full Gunnison Slate River patrol with a
60-second GPS outage at T=30s and asserts fused-vs-truth error < 10 m
at outage end.
