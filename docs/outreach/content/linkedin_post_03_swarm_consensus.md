---
platform: linkedin
target_date: 2026-06-10
length_words: 600
hashtags: [defensetech, autonomy, swarm, edgeAI, sensorfusion, wildfire, Lattice, Hivemind]
---

A practical note on false-positive suppression in fleet-scale wildfire detection. If you work on swarm autonomy, edge AI, or any multi-agent surveillance problem, the pattern below is one of the highest-leverage things you can build for free.

The setup. wildfire-watch's perception stack runs on a Jetson-class compute target on each drone. The detector emits a `wildfire_signal v1` event when it crosses a confidence threshold — UUIDv4 ID, drone ID, lat/lon/alt_agl, timestamp, signal_type (smoke / fire / thermal anomaly / wildlife / anomaly / system event), confidence, evidence frame URIs, risk_score, recommended_action.

The problem. A single drone over a 1 km² wildland-urban-interface zone will produce false positives. Cloud shadows look like smoke. Sun-glint on aspen leaves looks like thermal anomaly. Backyard barbecue smoke looks like an ignition. A fire chief's tablet that screams every time one drone twitches gets ignored within three days; a fire chief's tablet that stays silent for the wrong reasons fails the actual mission.

The fix. k-of-N consensus voting over a lossy mesh-comms model. The consensus voter ingests every drone's emit stream and fires a CONFIRMED signal when at least k of N independent drones produce a similar-class signal within a configurable spatial / temporal window (default 75 m / 60 s for smoke). On consensus, the voter:

1. Promotes risk_score by +20, capped at 100.
2. Escalates recommended_action from `notify_operator` to `notify_fire_dept`.
3. Records an audit trail of the contributing signal_ids.

The mesh-comms model is the part that earns its keep. Real fleet operations lose packets. Canyons partition meshes. Smoke ionizes radios. With `loss_rate=1.0` no consensus ever fires (correct — no information arrives). With `loss_rate=0.0` every emit propagates instantly. With realistic 5–20% loss rates and 300–800 ms latency, consensus still fires for true positives because the temporal window is generous and the spatial gating is forgiving, but isolated false positives that would have alarmed a single-drone system are now suppressed because the second corroborating drone never sees the same plume.

The numbers from the sim. Three drones over the 1 km² Slate River drainage in Gunnison County, CO. consensus_smoke scenario. k=2. Consensus voter produced a CONFIRMED smoke event at risk_score 97.33 with `recommended_action=notify_fire_dept`. The first single-drone emit fired at confidence 0.71 — well below the threshold a single-drone system would treat as actionable. The two-of-three corroboration is what made it actionable.

Why this is hard to copy without writing the code. The schema has to be the same single source of truth in every emit path — simulator, post-flight processor, swarm voter, TAK emitter — or the corroboration logic is fighting drift. wildfire-watch's `ml/fire_detection/infer.build_signal()` and `infer.should_emit()` are the deterministic, JSONL-appendable contract every other module composes against. No duplicate logic.

Why it matters strategically. Detection-only is a commodity now (ALERTCalifornia, satellite). Multimodal early-warning fusion with k-of-N consensus is not. Anduril's Lattice, Shield AI's Hivemind, Saronic's swarm autonomy, Red Cat's perception-stack gap — they all need this primitive in some form. wildfire-watch is the open-source reference implementation, with the lossy-comms model included.

Repo: https://github.com/arigatoexpress/wildfire-watch — `sim/swarm/` is the relevant subtree. 2,540 LOC, 34 tests, lossy-mesh model in `sim/swarm/comms.py`, consensus voter in `sim/swarm/consensus.py`, demo CLI at `python3 -m sim.swarm.cli run sim/missions/gunnison_slate_river_1km2.yaml --scenario consensus_smoke --drones 3 --k 2 --speed-multiplier 5`.

If you work on this and want to compare notes: aristotlespec@gmail.com.
