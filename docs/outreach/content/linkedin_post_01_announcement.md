---
platform: linkedin
target_date: 2026-05-06
length_words: 500
hashtags: [wildfire, defensetech, opensource, dronesforgood, Colorado, NDAA, BlueUAS, AIP, Lattice]
---

I have been quietly building a project for the last few weeks and it is at the point where it is more useful in the open than in a private repo. Here is the snapshot.

The project is called wildfire-watch. The premise is simple: the first 30 minutes of a wildfire decide whether it stays under an acre or becomes a Marshall Fire. Existing detection layers — fixed-camera networks like ALERTCalifornia (1,240 cameras, fixed viewpoints), GOES / VIIRS satellites (~375 m resolution, hours of revisit latency), and 911 calls — all have documented blind spots in canyon and wildland-urban-interface terrain. wildfire-watch is the small, open-source, NDAA-clean civilian patrol layer that fills that gap.

The operational area is the Gunnison Valley plus Crested Butte corridor in Colorado, where I live. High-elevation montane forest at 7,700–9,000+ ft. Beetle-killed lodgepole pine and Engelmann spruce. Sharp wildland-urban interface. Short, explosive June-to-September fire season. Partner agencies of record: Crested Butte Fire Protection District, Gunnison County FPD, and the GMUG National Forest — Gunnison Ranger District. Wilderness boundaries (West Elk, Maroon Bells-Snowmass, Raggeds) are non-negotiable no-fly zones per 36 CFR 261.16, encoded as hard exclusion polygons in the mission planner.

What is in the repo today, all working:

- A kinematic flight simulator with a Mavic-shaped airframe profile, deterministic seeding, scripted detection events, a browser viewer, and a JSONL flight log per tick.
- Multi-drone swarm with k-of-N consensus voting over a lossy mesh-comms model. Three drones over a 1 km² mission produced a CONFIRMED smoke event at risk_score 97.33 with recommended_action = notify_fire_dept.
- GNSS-denied vision navigation primitive: visual odometry + terrain-relative-nav + IMU + complementary fusion + GPS-spoof discriminator. 60-second outage at 80 m AGL stayed within 1.39 m mean / 2.15 m max of truth.
- TAK / Cursor-on-Target XML emitter — every signal can be published as a CoT event into ATAK, WinTAK, Anduril Lattice, Palantir Apollo, or any TAK-federated platform. Same wire format, three universes.
- A Blue UAS lineage document tracing every line of the Phase-1 BOM to its NDAA / Sec. 848 substitution path.
- 240 tests passing in under 7 seconds. ~13,700 lines of Python across 142 source files.

What is NOT in the repo today: zero flight hours. Zero printed parts. No signed Letter of Authorization. No trained production ML model. Phase 0 first flight is a few weeks out, gated behind Part 107 study, LAANC pre-auth at KGUC, and an LOA from Crested Butte FPD.

The civilian-wildfire mission is the wedge. The platform underneath — autonomous patrol, multimodal sensor fusion, swarm consensus, GNSS-denied perception, TAK/CoT interop, NDAA-substitutable BOM — is what makes it strategically defensible. I am one operator, this is early, and the most useful thing right now is feedback from people who do this work for a living.

If you are a fire chief, a USFS coordinator, a defense-tech engineer, a 3D-printer maker, an ArduPilot tinkerer, or a wildfire researcher — I would value 15 minutes of your time. Reply here or email aristotlespec@gmail.com.

Repo: https://github.com/arigatoexpress/wildfire-watch
