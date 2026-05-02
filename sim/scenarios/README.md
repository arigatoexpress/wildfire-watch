# Sim scenarios

A scenario is a small YAML doc that schedules detection events while
the runner flies a mission. The scenario engine fires events at one of
two trigger types:

- `{waypoint: N, offset_s: S}` — fires once the drone has reached the
  N-th waypoint (1-based, like `single_smoke_plume.yaml`) **and** at
  least S seconds have elapsed since reach time.
- `{t_seconds: T}` — fires at absolute simulator time T.

## Event types

`rgb_score_burst`
- `rgb_score`: 0..1 — sustained RGB confidence.
- `thermal_delta_c`: degrees C above local median.
- `duration_s`: how long the burst persists (default 8.0).
- `target_offset_m` + `target_bearing_deg`: where the detection target
  is relative to the drone (used to fill `target_coords` in the signal).

`thermal_only_anomaly`
- Same payload as `rgb_score_burst` but rgb_score should stay below
  `confidence_threshold`. The fusion gate (defined in
  `ml/fire_detection/infer.py`) requires both RGB and thermal positives
  plus a persistence run, so this MUST NOT fire a signal. The
  `thermal_only_anomaly.yaml` scenario verifies that contract.

`wind_shift`
- `wind_dir_deg`, `wind_speed_mps` — mutates ambient wind. (The
  current runner does not yet feed `wind_consistent=False` from this;
  reserved for future fidelity.)

`battery_drain`
- `multiplier`: float — accelerates the per-second battery drain.

## Adding a scenario

Drop a new YAML file in this folder. Pass its name (without `.yaml`)
to `python -m sim.cli run ... --scenario <name>` and it will be
auto-discovered.
