---
platform: x
target_date: 2026-05-08
length_words: 220
hashtags: [wildfire, defensetech, opensource, dronesforgood]
---

**Tweet 1/8** (open with the hook)
The first 30 minutes of a wildfire decide whether it stays under an acre or becomes a Marshall Fire. ALERTCalifornia (1,240 fixed cameras) and GOES/VIIRS (~375m, hours of revisit) both have documented WUI blind spots. wildfire-watch is the missing layer.

**Tweet 2/8** (what)
Open-source autonomous patrol drone fleet for the Gunnison Valley + Crested Butte corridor in Colorado. Apache-2.0. Built dual-use from day one — civilian wedge, defense-adjacent moat. https://github.com/arigatoexpress/wildfire-watch

**Tweet 3/8** (the simulator demo)
You can run the simulator on a laptop in 60 seconds. Browser viewer at :8088, Leaflet 2D map, planned route + flown polyline + signal pins, fusion-gate confidence chart, SSE replay at configurable speed. No drone required, no GPU. [ video placeholder ]

**Tweet 4/8** (swarm + consensus)
3 drones over 1 km², k-of-N consensus voting, lossy mesh-comms model. Two-of-three corroboration within 75m / 60s = CONFIRMED smoke event at risk_score 97.33, recommended_action=notify_fire_dept. Single-drone false positives suppressed.

**Tweet 5/8** (GNSS-denied vision-nav)
60-second GPS outage at 80m AGL: VO + TRN + IMU + complementary-fusion stayed within 1.39m mean / 2.15m max of truth. GPS-spoof discriminator catches deliberate jam bursts every tick. Smoke kills GPS lock — this primitive is a precondition.

**Tweet 6/8** (TAK / CoT interop)
Every signal can be published as a Cursor-on-Target XML event over TCP/UDP/TLS/multicast. Same wire format as ATAK on a fire chief's tablet. Same wire format as Anduril Lattice. Same wire format as Palantir Apollo. 8 type-codes, three universes.

**Tweet 7/8** (Blue UAS / NDAA posture)
BLUE-UAS-LINEAGE.md traces every BOM line to its NDAA / Sec. 848 substitution path. Phase 1 BOM is already NDAA-eligible at major-component level (Cube Orange+, Jetson Orin Nano, FLIR Lepton 3.5, uAvionix). The diligence work is pre-done.

**Tweet 8/8** (the ask)
240 tests passing. ~13,700 LOC. Zero flight hours, zero LOAs — first flight is a few weeks out behind Part 107 + LAANC + a Letter of Authorization from Crested Butte FPD. If you do this work for a living, reply or DM. https://github.com/arigatoexpress/wildfire-watch
