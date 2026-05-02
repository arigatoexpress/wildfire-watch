---
to: Jeff Thompson (CEO) or BD/partner intake, Red Cat Holdings (TBD — confirm best inbound BD contact via redcatholdings.com)
subject: Wildfire-watch perception stack as a software augmentation for Black Widow / ARACHNID — paid eval proposal
priority: medium
intent: partnership-explore
gated_on: A short Phase 0 flight log and a swarm-consensus demo recording; Black Widow / ARACHNID payload-API or Jetson-class compute spec to target
---

Hi,

The Black Widow / ARACHNID Army SRR win in late 2024 made the Red Cat hardware story clear. The piece I noticed afterward, talking with people who follow the program, is that the software stack on top is partner-stitched — Palladyne for autonomy, Booz Allen for mission planning, Palantir VNav for navigation. There is a real software gap in the middle, and I am building something that fits inside it.

The project is wildfire-watch (https://github.com/arigatoexpress/wildfire-watch). Open source, Apache-2.0. The wedge is civilian wildfire detection in Colorado; the moat is the stack underneath. What is portable to a Black Widow / ARACHNID-class airframe today, all working with 240 tests passing:

- **Multimodal edge fusion gate** — RGB + LWIR + acoustic + behavioral wildlife, fused on a Jetson-class compute target. Single `wildfire_signal v1` schema with UUIDv4 IDs and per-signal evidence URIs.
- **k-of-N swarm consensus voter** — three Black Widows over an AOR, k=2, false-positive suppression by independent corroboration within a 75 m / 60 s window. With `loss_rate=1.0` no consensus fires (correct); with `loss_rate=0.0` every emit propagates instantly. The lossy-comms model is the part I think Red Cat does not currently own internally.
- **GNSS-denied vision navigation** — VO + TRN + IMU + complementary-fusion + GPS-spoof discriminator. 60-second outage at 80 m AGL stayed within 1.39 m mean / 2.15 m max of truth. Smoke kills GPS lock; canyons block GPS; this primitive is the precondition for any wildfire-mission flight.
- **TAK / Cursor-on-Target XML emitter** — Black Widow signals out into ATAK / WinTAK / Lattice / Apollo over TCP / UDP / TLS / multicast, same wire format. 8 type-code mappings already built.
- **Blue UAS lineage document** — every line of the Phase-1 BOM traced to NDAA / Sec. 848 substitution. The diligence work is pre-done. Public-safety civilian wedge is exactly the dual-use narrative Red Cat's press posture has been wanting more of.

The specific ask, framed as a paid evaluation rather than an acquisition: would Red Cat be open to a 90-day paid evaluation slot on a Black Widow / ARACHNID? I would port the perception head and the consensus voter to whatever Red Cat uses for onboard compute, run a wildfire-detection scenario, and ship Red Cat back the integration artifacts (model, schema, TAK adapter) plus a public reference. Pricing and SOW are open — I am not optimizing for revenue from the eval; I am optimizing for one Red Cat SKU running a public-safety perception stack that Red Cat does not currently own internally.

If a paid eval is too early, the lower-priority ask is a 30-minute conversation with whoever runs Black Widow / ARACHNID software product. The honest read on whether the gap I think I see is real, or is one Red Cat is already filling another way, would shape my roadmap.

Honest state: zero flight hours, no signed customer, AOR is Gunnison Valley plus Crested Butte in Colorado. Phase 0 first flight is a few weeks out behind Part 107 cert and an LOA from Crested Butte FPD. Repo is open.

No rush. If the right inbound channel is a partner-supplier intake form, point me at it.

— TBD (operator name)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch
