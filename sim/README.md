# wildfire-watch flight simulator

Pure-Python kinematic drone-flight simulator. No NumPy, no SciPy, no
SimPy, no PX4. Drives a virtual airframe (Mavic Mini 2 by default)
along a planned mission, emits Mavic-style telemetry and DJI-Fly SRT
subtitles, injects scripted detection events, and produces a stream of
valid `wildfire_signal v1` events through the existing fusion gate in
`ml/fire_detection/infer.py`.

## Quickstart

```bash
cd ~/Code/wildfire-watch
python3 -m sim.cli run sim/missions/monterey_pinnacles_east_1km2.yaml \
    --scenario single_smoke_plume \
    --speed-multiplier 5
```

This produces a fresh run directory under `~/wildfire-watch-flights/`
containing:

```
SIM-YYYY-MM-DDTHHMMSS_single_smoke_plume/
    flight_log.jsonl   one JSON row per tick (10 Hz)
    flight.srt         DJI-Fly compatible subtitle track (1 cue/sec)
    signals.jsonl      one wildfire_signal v1 per emit
    manifest.json      run metadata and final counts
```

The SRT format intentionally mirrors what
`ml/fire_detection/mavic_post_flight.parse_srt` already accepts, so the
post-flight detector can ingest simulator output directly.

## Pipe to Sapphire

Add `--pipe-to-sapphire` to forward each emitted signal through
`~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` exactly the
same way `ml/fire_detection/demo.py` does.

## Run tests

```bash
cd ~/Code/wildfire-watch
python3 -m pytest sim/tests/ -q
```

## What this simulator is NOT

- It is not PX4 SITL. There is no flight-controller-in-the-loop, no
  IMU noise model, no aerodynamics, no ESC modelling. A waypoint is
  reached on the first tick that lands within tolerance.
- It does not render frames. Frame URIs in emitted signals are
  synthetic placeholders.
- The geofence polygon is parsed but not enforced — the runner trusts
  the planner. Real-flight geofence enforcement happens in the ground
  station, not here.

## Layout

```
sim/
  kinematics.py    WGS84 great-circle math
  airframe.py      AirframeProfile dataclass + registry
  mission.py       YAML mission parser + ground-distance budget
  scenario.py      ScenarioEngine — schedules detection events
  runner.py        10 Hz tick loop, fusion-gate-aware
  recorder.py      Writes flight_log.jsonl + flight.srt + signals.jsonl
  cli.py           python -m sim.cli run / info / airframes
  scenarios/       Bundled YAML scenarios
  missions/        Bundled YAML missions
  tests/           Pytest suite
```

## Determinism

The runner is deterministic — same inputs produce the same flight log
and same signal stream. The `--seed` flag is plumbed through
`RunnerConfig` for future scenarios that introduce random noise (none
of the current ones do).
