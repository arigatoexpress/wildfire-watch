# wildfire-watch

3D-printed AI-enabled drones for wildfire monitoring + wildlife/ecology data + decentralized fire-risk intelligence. Civilian wedge into a defense-adjacent autonomy platform. The user's articulated dream — first project he's named that way.

**Read this whole file before working on the repo.**

## North star

> A county-scale autonomous drone fleet that detects wildfires before human spotters, generates an open ecological data stream as a side effect, and runs on a decentralized volunteer-builder model that doesn't depend on any one vendor.

The civilian wildfire mission is the **wedge**. The platform technology — autonomous patrol, multimodal sensor fusion, mesh-comms, ontology integration, GNSS-denied vision navigation — is the **moat**. Five strategic acquirers we design toward (none promised): **Anduril, Palantir, Ondas Holdings, Red Cat Holdings, Kratos Defense**. Detail in `docs/strategy/`.

## AOR (operational area)

**Gunnison Valley + Crested Butte corridor, Gunnison County, Colorado.** Field elevation 7,700–9,000+ ft. High beetle-kill fuel load. Short fire season (June–September). KGUC class E airspace, LAANC required within 5 nm. **West Elk Wilderness is hard no-fly per 36 CFR 261.16.** Partner FDs: Crested Butte FPD, Gunnison County FPD, Mt. Crested Butte FPD; coordinator GMUG National Forest — Gunnison Ranger District.

Source of truth: `AOR.md`. Phase-0 mission: `sim/missions/gunnison_slate_river_1km2.yaml`. AOR zones: `missions/zones/gunnison_crested_butte_corridor.geojson`.

## Hardware tiers

- **Phase 0 ($0):** DJI Mavic Mini 1 or 2 + Mac mini + Raspberry Pis rari1 / rari2. Already owned. Manual scout flights, post-flight YOLO on the Mac, heartbeat from the Pis.
- **Phase 0.5 ($215):** RTL-SDR Blog v4 + PMS5003 PM2.5/PM10 + Bosch BME688 + 2× Heltec V3 Meshtastic + Pi 5 AI HAT+ Hailo-8L. Documented in `docs/intel/low-cost-hardware-2026-05-01.md`. **Skip Flipper Zero** — not the right tool here.
- **Phase 1 ($2,613):** Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super 8GB + Arducam IMX477 + FLIR Lepton 3.5 + uAvionix pingRX/pingRID. BOM at `hardware/bom.csv`. Long-lead items, order only after Phase 0 ships.

**The DJI Mavic Mini is a Phase-0 stopgap, not a foundation.** 2026 NDAA + Countering CCP Drones Act + DoD Section 848 Blue UAS list: any DJI bet expires by 2027. Plan migration to the Holybro/Cube/Jetson stack from day one. The valuation engine flags `ndaa_blue_uas_eligible=False` while DJI components are in the BOM.

## Schema

Single source of truth: `sapphire_integration/wildfire_signal_schema.json` v1.0.0. Required fields: signal_id (UUIDv4), drone_id (regex `^wfw-[a-z0-9]{4,16}$`), zone_id, timestamp, coords (lat/lon/alt_agl_m), signal_type (smoke|fire|thermal_anomaly|wildlife|anomaly|system_event), confidence [0..1], evidence.frame_uris (≥1), risk_score [0..100], recommended_action (log_only|notify_operator|notify_fire_dept|loiter_and_capture|rtl), schema_version.

**Every signal-emitting code path uses `ml/fire_detection/infer.build_signal()` and `infer.should_emit()`.** Don't reimplement either. The simulator, the post-flight processor, the swarm consensus voter, and the TAK emitter all compose against these.

## Module map

| Path | Purpose |
|---|---|
| `ml/fire_detection/` | The detector: `infer.py` (live loop), `train.py` (FASDD→FLAME-2 plan), `demo.py` (synthetic replay), `mavic_post_flight.py` (Mavic SD-card post-process), `test_*.py` |
| `ground_station/pi_telemetry_collector.py` | Pi (rari1/rari2) heartbeat + system-event emitter |
| `sapphire_integration/` | The bridge to Sapphire — schema, README; under `tak/` is the TAK/CoT emitter for ATAK/Lattice/Apollo interop |
| `sim/` | Kinematic flight simulator (Mavic-shaped). 84 tests. CLI `python -m sim.cli run <mission> --scenario <name>` |
| `sim/web/` | Browser viewer — Flask + Leaflet + Chart.js + SSE. `python -m sim.web.server` → :8088 |
| `sim/swarm/` | N-drone fleet + k-of-N consensus + lossy-comms model |
| `sim/perception/` | GNSS-denied vision-nav primitive (VO + TRN + IMU + complementary fusion + jamming) |
| `valuation/` | Continuous intrinsic-value calculator + KPI dashboard |
| `docs/strategy/` | Acquirer-fit research + positioning brief |
| `docs/intel/` | 4 deep-research docs (Foundry, Ukraine drones, low-cost hardware, Phase 0) + SYNTHESIS |
| `docs/SIMULATION_LADDER.md` | Tier 1 kinematic → Tier 2 ArduPilot SITL → Tier 3 PX4+Gazebo → Tier 4 HITL |
| `docs/PHASE_0_QUICKSTART.md` | Operator quickstart for the Mavic + Mac + Pis stack |
| `hardware/bom.csv` | Phased BOM. `phase` column tags rows phase-0.5 / phase-1 |
| `missions/zones/gunnison_crested_butte_corridor.geojson` | Canonical AOR zones (5 features incl. wilderness exclusion) |

## Gotchas

- **Brew Python (3.14) often lacks pytest** — use `/usr/local/bin/python3` explicitly when running tests.
- **The simulator is deterministic with `--seed`** — same seed, same flight. Use this for regression testing.
- **Schema changes are versioned.** Bumping `schema_version` requires updating `infer.build_signal()`, the bridge tool, the validator, all tests, and the example XML in `sapphire_integration/tak/examples/`.
- **The Sapphire bridge runs as a subprocess** — every `--pipe-to-sapphire` invocation forks `python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py`. Slow but isolation-safe. Future: HTTP shim.
- **`build_signal()` returns a `dict`** that is JSONL-appendable. Don't add non-JSON-serializable values.
- **Wilderness boundaries are NON-NEGOTIABLE.** West Elk + Maroon Bells-Snowmass + Raggeds. The geofence model needs exclusion-polygon support (Phase-0.5 follow-up).
- **High-altitude derating is real:** Mavic Mini 2 service ceiling 13,123 ft on paper, but battery duration drops 25-35% above 9,000 ft. Plan with 70% nominal endurance.
- **No emoji in code.** None. The user has not asked for it; defaults apply.

## How to verify everything

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m pytest -q                          # all tests
/usr/local/bin/python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml --scenario single_smoke_plume --speed-multiplier 5
/usr/local/bin/python3 -m sim.web.server                     # browser viewer at :8088
/usr/local/bin/python3 -m valuation.cli snapshot             # current intrinsic-value band
```

## Sapphire integration

The Sapphire bridge at `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` (PR #551, MERGED 2026-05-02) ingests v1 wildfire_signals into `~/Code/Sapphire/data/wildfire_signals.jsonl` and emits `wildfire.signal.detected` event_bus envelopes. Idempotent on signal_id.

**The bridge does NOT call Telegram directly.** A future operator-supervised hermes `wildfire-alert` skill (separate PR to NousResearch/hermes-agent) will be the actual pager, gated by `recommended_action`.

Sapphire CLAUDE.md is at `~/Code/Sapphire/CLAUDE.md`. Memory is at `~/.claude/projects/-Users-aribs/memory/MEMORY.md`. The wildfire-watch project memory is `project_wildfire_watch_2026-05-01.md`.

## Repo state

- Branch `main`. NO remote yet — user adds when ready (`git remote add origin git@github.com:arigatoexpress/wildfire-watch.git` then `git push -u origin main`).
- Don't rewrite history without confirmation.
- 11+ commits, ~50+ tracked files, 84+ tests passing pre-Day-2 dispatch (more after the 5 agents currently running land).
