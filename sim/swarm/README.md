# sim.swarm — multi-drone swarm primitives

Composition-only extension of the single-drone simulator. Reuses
`sim.kinematics`, `sim.airframe`, `sim.mission`, `sim.scenario`, and the
fusion gate / signal builder from `ml/fire_detection/infer.py`. Does
not modify any sister files.

## Surface

```
Fleet              N drones, lockstep tick, per-drone state.
CoveragePlanner    bbox-grid partition of an inclusion polygon.
ConsensusVoter     k-of-N spatial+temporal+type confirmation.
MeshCommsModel     lossy peer-to-peer with latency + partitions.
SwarmRunner        composes Fleet + ConsensusVoter + MeshCommsModel.
SwarmRecorder      writes drones / signals / consensus / comms jsonl.
```

## CLI

```
python -m sim.swarm.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario consensus_smoke --drones 3 --k 2 --speed-multiplier 5
```

`--pipe-to-sapphire` only forwards CONFIRMED consensus signals (not raw
single-drone emits) to reduce noise downstream.

## Output layout

```
~/wildfire-watch-flights/SWARM-<timestamp>_<scenario>/
    manifest.json      mission, scenario, n_drones, k, R, T, counts, sub-zones
    drones.jsonl       one row per drone per tick
    signals.jsonl      raw single-drone emits (each tagged _emitter_drone_id)
    consensus.jsonl    CONFIRMED consensus_signal_v1 emits
    comms.jsonl        every (sender, receiver, outcome) decision
```

## Design notes

- **bbox grid, not Voronoi.** Lloyd's centroidal Voronoi tessellation
  is overkill for stdlib; a `ceil(sqrt(N)) x floor(sqrt(N))` grid is
  deterministic, O(N), and good enough for a 1 km^2 inclusion polygon
  with N <= 9.
- **Self-vote + peer-relay.** Each drone's own emit always counts toward
  its own consensus tally; peer signals only count after the comms model
  delivers them. Loss / latency / partitions can therefore block
  consensus realistically.
- **Strictest type wins.** A cluster spanning fire + smoke emits as fire.
- **Action escalation.** Consensus moves recommended_action one tier up
  (`notify_operator -> loiter_and_capture -> notify_fire_dept -> ...`).
- **Risk score bump.** `+min(20, 100 - current)` on consensus.

## Limitations vs. real Lattice / Saber autonomy

- No Byzantine fault tolerance — a malicious drone could fake an emit
  that lands inside R/T and manufacture consensus.
- No leader election or task allocation; sub-zones are static for the
  whole flight, so a drone failure leaves its cell uncovered.
- No graceful drone-loss recovery; if a drone's battery dies mid-flight,
  the others don't take over its sub-zone.
- No bandwidth / queueing model; comms model is "single envelope per
  emit", no congestion or back-pressure.
- No collision avoidance between drones (single launch point).

## Tests

```
python3 -m pytest sim/swarm/tests/ -q
```

`test_coverage_planner.py`, `test_consensus.py`, `test_comms.py`,
`test_runner.py`.
