---
platform: substack
target_date: 2026-05-15
length_words: 1500
hashtags: [wildfire, defensetech, opensource, dronesforgood, Colorado, longform]
---

# wildfire-watch, Phase 0: a county-scale autonomous wildfire patrol mesh you can run on a Mac mini

## The dream

A county-scale autonomous drone fleet that detects wildfires before human spotters, generates an open ecological data stream as a side effect, and runs on a decentralized volunteer-builder model that does not depend on any one vendor.

That is the north star. It is unreasonable, on purpose. Civilian-first, defense-adjacent, NDAA-clean from day one. The wedge is the sub-30-minute ignition window that satellites and mountain-camera networks miss; the moat is the platform underneath — autonomous patrol, multimodal edge fusion, swarm consensus, GNSS-denied perception, TAK interop, a Blue UAS-substitutable BOM.

I am one operator. The project is a few weeks old. There is no funded round, no team, no flight hours. There are 240 tests passing in under seven seconds, ~13,700 lines of Python across 142 source files, and a working simulator that anyone reading this can have running on their laptop in sixty seconds. That is what Phase 0 means: enough infrastructure to be honest about what comes next.

## The AOR

The operational area is the Gunnison Valley plus Crested Butte corridor, in Gunnison County, Colorado. I live here. Field elevation 7,700 to 9,000+ ft. Beetle-killed lodgepole pine and Engelmann spruce across the GMUG (Grand Mesa, Uncompahgre, Gunnison) National Forest is the dominant wildfire-risk amplifier — multi-decade fuel-load build-up that does not show up in any one-year drought metric. Wildland-urban interface is sharp on the Crested Butte side, with high second-home density adjacent to dead-timber stands. Fire season is short and explosive, late-June through mid-September, with peaks in July-August dry-lightning episodes.

The regulatory environment is real and has teeth. KGUC (Gunnison-Crested Butte Airport) class E airspace requires LAANC authorization within 5 nm. Above 10,000 ft MSL, ADS-B is mandatory and Part 107's 400 ft AGL ceiling gets terrain-relative interpretation. West Elk Wilderness, Maroon Bells-Snowmass Wilderness, and Raggeds Wilderness are hard-no-fly per 36 CFR 261.16 — encoded in the wildfire-watch mission planner as exclusion polygons that are physically impossible to violate without rewriting the geofence model. Colorado Revised Statute 33-14.5 makes drone harassment of wildlife a state misdemeanor, especially relevant during deer / elk rut and sage-grouse lekking seasons.

Partner agencies, in priority order: Crested Butte Fire Protection District (high-WUI, second-home tax base, ~970-349-5333, 700 6th Street). Gunnison County FPD (broader AOR, county seat). Mt. Crested Butte FPD (resort + above-town). GMUG National Forest — Gunnison Ranger District (USFS coordination, 216 N Colorado St, Gunnison). Colorado Division of Fire Prevention and Control at the state level. Western State Colorado University as a potential academic-partner pathway. The repo's `AOR.md` is the source of truth for all of the above.

## Phase 0: the cheapest possible way to be useful

The hardware tier table in the repo:

| Tier | Cost | Stack | Mission |
|---|---:|---|---|
| Phase 0 | $0 | DJI Mavic Mini 1/2 + Mac mini + Raspberry Pis (rari1 / rari2) — already owned | Manual scout flights, post-flight YOLO on Mac, Pi heartbeat, simulator-only autonomy |
| Phase 0.5 | $215 | + RTL-SDR Blog v4, Plantower PMS5003, Bosch BME688, 2× Heltec V3 Meshtastic, Pi 5 AI HAT+ Hailo-8L | ADS-B + RAWS receive, direct smoke sensing, license-free LoRa mesh, edge YOLOv8-fire at 30+ FPS |
| Phase 1 | $2,613 | Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super 8 GB + Arducam IMX477 + FLIR Lepton 3.5 + uAvionix pingRX/pingRID | Autonomous patrol, RGB + LWIR multimodal fusion, ADS-B In + Remote ID compliant |

The DJI Mavic in Phase 0 is a stopgap, not a foundation. The 2026 NDAA, the Countering CCP Drones Act / Section 1709 carve-outs, the December 2025 FCC Covered List addition, and the DCMA-takeover of the Blue UAS Cleared List on January 1, 2026 mean any DJI bet expires by 2027. The repo's `BLUE-UAS-LINEAGE.md` traces every line of the Phase 1 BOM to a Blue UAS-substitutable alternative; the valuation engine flips `ndaa_blue_uas_eligible=False` whenever a covered component is in the BOM. It is a feature.

## The walk-through

```bash
git clone https://github.com/arigatoexpress/wildfire-watch
cd wildfire-watch
python3 -m pytest -q
```

That last command runs in under seven seconds and reports 240 passing tests. The test suite covers the kinematic flight simulator (84 tests), the swarm + k-of-N consensus voter (34), the GNSS-denied vision-nav primitive (27), the TAK / Cursor-on-Target XML emitter (62), and the four-method valuation engine (33). Stdlib-first by policy — no NumPy, no SciPy, no SimPy in `sim/`. That is deliberate. Anyone reading this can run the suite on a five-year-old laptop.

```bash
python3 -m sim.cli run \
    sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5
```

The simulator flies a Mavic-shaped airframe profile through a YAML-defined mission over the Slate River drainage west of Mt. Crested Butte. Deterministic with `--seed` — same seed, same flight tick-for-tick. The detection events are scripted; the kinematics are physical. Every signal emitted goes through `ml/fire_detection/infer.build_signal()` and `infer.should_emit()` — the single source of truth that the post-flight processor, the swarm voter, and the TAK emitter all compose against. Schema is `wildfire_signal v1`: UUIDv4 signal IDs, regex-validated drone IDs, six signal types, deterministic JSONL.

[ screenshot placeholder: terminal output of the simulator run, showing a smoke detection at risk_score 84 with recommended_action=notify_operator ]

```bash
python3 -m sim.web.server
# http://127.0.0.1:8088
```

The browser viewer is Flask + Leaflet + Chart.js + Server-Sent-Events. Vanilla JS, no npm, no webpack. The map shows the AOR polygon (the canonical zones live at `missions/zones/gunnison_crested_butte_corridor.geojson`, with the wilderness exclusion baked in), the planned route, the flown polyline, and signal pins for every emit. The Chart.js panel shows fusion-gate confidence over time. The replay is SSE at configurable speed. The whole web subtree is ~700 LOC.

[ screenshot placeholder: browser viewer showing the Slate River drainage map, the planned route in blue, the flown polyline in green, a red smoke pin at the plume location, and the confidence chart climbing past 0.7 at the moment of detection ]

That is Phase 0. Everything above runs on a Mac mini with no GPU, no drone, and no internet. The operator (me) can be looking at a post-flight map within sixty seconds of cloning a fresh repo.

## The wedge-vs-moat thesis

The civilian wildfire mission is the wedge because the market is unambiguous (the first 30 minutes determine whether an ignition stays under an acre or becomes a Marshall Fire), the political-economic optics are clean (a dual-use platform whose first proof point is "we found a fire in 8 minutes that ALERTCalifornia could not see for 23" is the highest-trust origin story for crossover into public safety, infrastructure protection, and eventually defense-adjacent), and there is no NDAA risk in civilian-first. Building Blue UAS-substitutable from day one strengthens the defense path — it does not foreclose it.

The platform underneath is the moat because each of the five capabilities I built into the repo this week is hard to replicate without writing the code:

1. **Multimodal edge fusion** — RGB + LWIR + acoustic + behavioral-wildlife reasoned about jointly on a $249 Jetson Orin Nano Super.
2. **k-of-N swarm consensus + lossy-comms model** — three drones over a 1 km² mission produced a CONFIRMED smoke event at risk_score 97.33 by two-of-three corroboration within a 75 m / 60 s window, even with realistic packet loss.
3. **GNSS-denied vision navigation** — VO + TRN + IMU + complementary fusion + GPS-spoof discriminator. 60-second outage at 80 m AGL, fused position within 1.39 m mean / 2.15 m max of truth. Smoke kills GPS lock; canyons block GPS; this is the precondition for any wildfire-mission flight.
4. **TAK / Cursor-on-Target interop** — every signal is one stdlib socket call from ATAK, Lattice, Apollo, FreeTAKServer, or any TAK-federated platform. One wire format, three universes.
5. **NDAA / Blue UAS-substitutable BOM with documented lineage** — the diligence work is pre-done. Anduril, Ondas, Red Cat, AeroVironment will all pay for that.

Detection-only is now a commodity (ALERTCalifornia, satellite). The five capabilities above are not. The repo's `docs/strategy/POSITIONING_BRIEF-2026-05-02.md` lays out the four-method intrinsic-value math: today's consensus band is $0–$2.83M (mid $1.38M), the 18-month plan moves to a defensible $25–75M strategic-acquisition band by mid-2027, and the 36-month optionality stays alive for $150–400M.

## What is honest about today

Zero flight hours. Zero printed parts. No signed Letter of Authorization. No trained production ML model — the detector running today is a placeholder colour heuristic; the FASDD → FLAME-2 fine-tune is a Phase 1 deliverable. Phase 0 first flight is a few weeks out, gated behind Part 107 study (in progress), LAANC pre-auth at KGUC, and a signed LOA from Crested Butte FPD.

The single highest-leverage move on the entire dashboard right now is one cold email to the Crested Butte Fire Protection District. The valuation engine credits a signed LOA at +$3M to the mid-band. Same cost as a stamp.

## Closing

If you do this work for a living — fire department leadership, USFS coordinator, defense-tech engineer, ML/CV researcher, ArduPilot tinkerer, 3D-printer maker, drone pilot in the Gunnison Valley — the project wants you. Repo is at https://github.com/arigatoexpress/wildfire-watch under Apache-2.0. Reply on this post or email aristotlespec@gmail.com.

Phase 1 is on the calendar. Phase 0 is on your laptop in sixty seconds. The next $5M of value is on the other side of three pieces of paperwork (Part 107, LAANC, LOA) and one season of flight hours.

The valley is here. The forest is dying. The simulator works. Time to fly.
