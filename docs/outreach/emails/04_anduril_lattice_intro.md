---
to: Lattice Partnerships / Mission Autonomy team, Anduril Industries (partners@anduril.com — Lattice Sandbox program)
subject: Wildfire patrol layer for Lattice — civilian wedge, NDAA-clean from day one, 1 km² Colorado polygon teed up
priority: medium
intent: partnership-explore
gated_on: Lattice Sandbox slot; one in-person Phase 0 flight over Slate River drainage to add operational credibility; CBFPD LOA in hand
---

Hi,

The Korean Air partnership announced in April and Palmer Luckey's XPRIZE Wildfire team are public signals that Anduril is buying into autonomous wildfire response. I am building a project that fits as the small, cheap, civilian patrol-density layer that funnels signals into Lattice for the Fury / Ghost-X tier to react to — not a competitor, a tile.

The project is wildfire-watch. Open source under Apache-2.0 at https://github.com/arigatoexpress/wildfire-watch. Operational area is the Gunnison Valley plus Crested Butte corridor in Colorado, where I live. What is in the repo today, all working with 240 tests passing in under seven seconds:

- A kinematic flight simulator with a Mavic-shaped airframe, scripted detection events, and a browser viewer.
- An N-drone swarm with k-of-N consensus voting over a lossy mesh-comms model. Three drones over a 1 km² mission, k=2, consensus_smoke scenario produced a CONFIRMED smoke event at risk_score 97.33 with `recommended_action=notify_fire_dept`.
- A GNSS-denied vision-nav primitive — VO + TRN + IMU + complementary-fusion + GPS-spoof discriminator. 60-second outage at 80 m AGL stayed within 1.39 m mean / 2.15 m max of truth.
- A TAK / Cursor-on-Target XML emitter that publishes every wildfire signal as a CoT event over TCP / UDP / TLS / multicast. Same wire format as ATAK on a fire chief's tablet, same wire format as Lattice — that overlap is the whole point. The CoT type-code mappings are already enumerated for smoke, fire, thermal anomaly, wildlife, anomaly, system event, drone self-position, and AOR geofence.
- A `BLUE-UAS-LINEAGE.md` that traces every component in the Phase-1 BOM (Cube Orange+, Holybro X500 V2, Jetson Orin Nano Super, FLIR Lepton 3.5, Sony IMX477) to its NDAA / Sec. 848 substitution path. Phase 0 uses a DJI Mavic Mini for prototyping; Phase 1 is on Blue UAS-substitutable components from day one.

The specific ask is small. I would like a Lattice Sandbox slot — the partner-accessible developer tier — so I can publish wildfire-watch CoT events into a Lattice instance and demonstrate the tile-into-Lattice integration on a real Sandbox rather than a synthetic mock. If there is a more appropriate program (e.g., the XPRIZE Wildfire team's integration channel, or a Mission Autonomy partner intake form), point me at it.

A second, lower-priority ask: if there is a Lattice partner-engineering contact who has worked on a TAK / CoT integration in the last six months, I would value 15 minutes of their time on the schema mapping. The 8 type-code mappings I have today were derived from MIL-STD-2525 and the FreeTAKServer reference — a Lattice engineer's read on whether they match Lattice's expectations would be useful before I publish.

Honest gap, said up front. Zero flight hours, zero printed Phase-1 frames, no signed customer. Phase 0 first flight is a few weeks out behind Part 107 study, LAANC pre-auth at KGUC, and a Letter of Authorization from Crested Butte FPD. I am not pitching an acquisition. I am pitching a sandbox slot and a 30-minute conversation, and asking what would have to be true on my end for that to be worth Anduril's time.

No rush. Happy to send the simulator video, the swarm-consensus log, or the 4-quarter roadmap as standalone artifacts if any of those help.

— TBD (operator name)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch
