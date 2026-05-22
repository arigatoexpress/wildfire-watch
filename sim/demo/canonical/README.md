# sim/demo/canonical/

Output directory for `python -m sim.demo.cli all` — gitignored.

After a successful run this folder contains:

- `single/SIM-<ts>_single_smoke_plume/` — single-drone recorded flight
  (manifest, flight_log.jsonl, signals.jsonl, flight.srt)
- `swarm/SWARM-<ts>_consensus_smoke/` — 3-drone consensus-swarm
  recorded flight (manifest, drones.jsonl, signals.jsonl,
  consensus.jsonl, comms.jsonl)
- `manifest.json` — top-level demo manifest pointing at both runs
- `wildfire_watch_demo.html` — the single-file HTML report ready to
  email or embed in a README

Re-running `record` or `all` wipes and rewrites the `single/` and
`swarm/` subdirs so the artifact set is deterministic on (seed,
mission, scenario).
