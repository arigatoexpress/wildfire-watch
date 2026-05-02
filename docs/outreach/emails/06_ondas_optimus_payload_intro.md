---
to: Stewart Kantor (CEO) or Joe Popolo (CFO), Ondas Holdings — investor relations channel at ir.ondas.com (TBD — confirm best inbound BD contact)
subject: Mission payload candidate for Optimus — wildfire detection, NDAA-clean, Blue UAS-aligned by design
priority: medium
intent: partnership-explore
gated_on: a Phase 0 flight to demonstrate end-to-end signal pipeline; an Optimus payload-API spec we could target; willingness from OAS to host a payload-partner conversation
---

Hi,

Optimus going on the DCMA Blue UAS Cleared List on January 28, 2026 was the public signal that pulled me here. The Ondas / OAS investor day reset of the 2026 revenue guide, and the structural framing of Optimus as a flight-and-charge platform with up-to-9 mission payloads, are all consistent with what I am building toward as a payload candidate.

The project is wildfire-watch (https://github.com/arigatoexpress/wildfire-watch). Open source under Apache-2.0. The pitch in one sentence: I am building the wildfire-detection mission payload + edge perception stack that runs on Optimus — or, if the timing is wrong for that, the cheaper-frame complement that lets OAS address the patrol-density market segment Optimus is too expensive to own alone. Either framing works.

What is in the repo today, all working:

- A `wildfire_signal v1` JSON schema — UUIDv4 signal IDs, regex-validated drone IDs, six signal types (smoke / fire / thermal anomaly / wildlife / anomaly / system event), a deterministic `build_signal()` and `should_emit()` that every emit path composes against. Schema is the kind of thing a payload-partner program would expect at the wire-format layer.
- A multimodal fusion gate — RGB + LWIR + acoustic + behavioral wildlife, designed to run on a $249 Jetson Orin Nano Super at flight-relevant FPS. Phase 0 placeholder is a colour heuristic; Phase 1 is FASDD → FLAME-2 fine-tune.
- A TAK / Cursor-on-Target XML emitter — every signal can be published to a TAK Server, ATAK, WinTAK, iTAK, or any TAK-federated platform. Same wire format as Lattice and Apollo.
- A swarm + k-of-N consensus voter with a lossy-comms model — three drones over a 1 km² mission, consensus_smoke scenario, CONFIRMED smoke at risk_score 97.33.
- A GNSS-denied vision-nav primitive — VO + TRN + IMU + complementary-fusion, plus a GPS-spoof discriminator.
- A `BLUE-UAS-LINEAGE.md` documenting the substitution path from current Phase 0 BOM (DJI Mavic Mini, placeholder) to Phase 1 NDAA-eligible BOM (Cube Orange+, Holybro X500 V2, Jetson Orin Nano Super, FLIR Lepton 3.5, Sony IMX477) and the Blue UAS Cleared substitutes per part. Section 848 diligence is pre-done.

The specific ask: does Ondas / OAS have a payload-partner intake channel I should formally apply through? American Robotics's payload-bay integration spec (or whatever the current internal equivalent is) is the artifact I would build against. Even a "we will look at this when you have a flight on the books" response would be useful — that lets me sequence Phase 0 flight + Phase 1 BOM build correctly.

Lower-priority second ask: if there is a public-safety reference customer Ondas would want a wildfire-vertical partnership to land at — a CAL FIRE pilot, a Colorado DFPC engagement, a power-line corridor with an IOU — I would value the steer. The AOR I am working in is Gunnison Valley plus Crested Butte, Colorado; partner agencies of record are Crested Butte FPD, Gunnison County FPD, and the GMUG National Forest Gunnison Ranger District.

Honest gap: zero flight hours today, no signed LOA, no trained ML model. Phase 0 first flight is a few weeks out behind Part 107 cert, LAANC at KGUC, and an LOA from Crested Butte FPD.

No rush. I understand investor-relations channels are not always the right route — point me at the right one if this is mis-routed.

— TBD (operator name)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch
