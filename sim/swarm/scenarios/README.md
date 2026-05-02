# Swarm scenarios

Each scenario YAML reuses the single-drone scenario format from
`sim/scenarios/`. The only swarm-specific extension is an optional
`drones:` list inside `payload`, which targets the event at specific
drone ids. If `drones` is absent, the event applies fleet-wide BUT only
fires on the primary drone (`{drone_id_prefix}01`) to avoid 3x
amplification of a single physical event.

| File                          | Purpose                                                   |
| ----------------------------- | --------------------------------------------------------- |
| `three_drone_patrol.yaml`     | Clean patrol, no detections. Smoke test for fleet ticking.|
| `consensus_smoke.yaml`        | All 3 drones see same plume. k-of-3 consensus fires.      |
| `single_witness_anomaly.yaml` | Only 1 drone sees an event. Consensus must NOT fire.      |
| `partition_recovery.yaml`     | Comms partition splits the swarm; reconverge after recovery. |

Drone ids are auto-assigned: `wfw-sim01`, `wfw-sim02`, ..., `wfw-sim{N:02d}`.
