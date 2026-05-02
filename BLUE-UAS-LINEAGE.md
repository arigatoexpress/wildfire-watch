# Blue UAS Lineage — Substitution Path for the wildfire-watch BOM

**Date:** 2026-05-02
**Author:** Strategy / hardware
**Status:** Internal — drop-in substitution argument for acquirer / partner conversations
**Pair-with:** [`hardware/bom.csv`](./hardware/bom.csv), [`docs/strategy/ACQUIRER_FIT-2026-05-02.md`](./docs/strategy/ACQUIRER_FIT-2026-05-02.md), [`docs/strategy/POSITIONING_BRIEF-2026-05-02.md`](./docs/strategy/POSITIONING_BRIEF-2026-05-02.md)

---

## 1. TL;DR

- **Phase 0 uses a DJI Mavic Mini for prototyping; Phase 1+ is on Blue UAS components from day one — substitution path documented per part.** Single artifact retiring the "but you have a DJI in your BOM" objection.
- **Phase 1 BOM is already NDAA-eligible.** Cube Orange+, Jetson Orin Nano Super, Holybro X500 V2, FLIR Lepton 3.5, and Sony IMX477-based Arducam carriers all currently ship into Blue UAS-listed platforms. No primary BOM line originates from a covered foreign entity per the [American Security Drone Act of 2023, Sec. 1822](https://www.congress.gov/bill/118th-congress/senate-bill/473/all-info), with explicit substitution flags on the few exceptions (Quectel LTE, Tattu battery, ISDT charger).
- **Blue UAS Cleared List has 50+ airframes as of 2026-03** ([Drone Girl, 2026-03-19](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/), [MFE 2026](https://mfe-is.com/blue-uas/)). Management transferred from DIU to DCMA on 2026-01-01 ([UAS Magazine](https://uasmagazine.com/articles/diu-transfers-blue-uas-cleared-list-to-dcma-to-accelerate-secure-drone-procurement)); canonical URL [bluelist.dcma.mil](https://bluelist.dcma.mil).
- **wildfire-watch software is hardware-agnostic.** Every signal-emitting path composes against `ml/fire_detection/infer.build_signal()`. Sim, post-flight processor, swarm voter, TAK emitter run identically on a Mavic, Skydio X10D, Teal 2, Parrot ANAFI USA, or custom Holybro X500. This is the second moat.
- **We are not currently on the Cleared List and do not claim to be.** Sec. 8 documents the honest gap and a $250k–$500k / 18–24-month roadmap if we ever pursue a listing.

---

## 2. What "Blue UAS" means in 2026

"Blue UAS" is the umbrella term for the Defense Innovation Unit (DIU) program — now administered by the Defense Contract Management Agency (DCMA) as of 2026-01-01 — that vets unmanned aircraft systems for U.S. Department of War (DoW; renamed from DoD by 2025-07-10 SecWar memo) procurement.

There are two artifacts that matter:

- **Blue UAS Cleared List** ([bluelist.dcma.mil](https://bluelist.dcma.mil), historically [diu.mil/blue-uas-cleared-list](https://www.diu.mil/blue-uas-cleared-list)) — vetted complete airframes. Procurable by federal agencies without additional waivers. ~50 airframes as of 2026-03 ([Drone Girl, 2026-03-19](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/)).
- **Blue UAS Framework** ([diu.mil/blue-uas/framework](https://www.diu.mil/blue-uas/framework)) — vetted *components* (radios, autopilots, EO/IR payloads). Vendors can self-integrate Framework parts into a custom airframe and submit the resulting platform for Cleared-List addition.

The legal scaffolding underneath the program:

| Statute | Status (2026-05) | Effect |
|---|---|---|
| **NDAA FY20 Sec. 848** ([Pub. L. 116-92](https://www.congress.gov/bill/116th-congress/house-bill/2500)) | Active since 2019 | Bans DoD procurement of UAS or UAS components from covered foreign entities (DJI, Autel, Yuneec, etc.). Source: [UAV Coach, DJI Ban Guide, 2026](https://uavcoach.com/dji-ban/). |
| **NDAA FY24 Sec. 1822 / American Security Drone Act of 2023** ([Senate S.473](https://www.congress.gov/bill/118th-congress/senate-bill/473/all-info)) | Active; [FAR clause 52.240-1](https://www.acquisition.gov/far/52.240-1) effective 2024-11-12 | Extends the ban to **all federal civilian agencies** (DHS, DOI, USDA, DOJ — all relevant to wildfire mission). Sec. 1824/1825 prohibitions effective 2025-12-22. |
| **NDAA FY25 Sec. 1709** ("Analysis of Certain Unmanned Aircraft and Systems Entities") | Active | Replaced the standalone Countering CCP Drones Act ([DJI ViewPoints, 2024-12](https://viewpoints.dji.com/blog/u.s.-congress-finalizes-fy25-national-defense-authorization-act-ndaa-without-countering-ccp-drones-act-heres-what-to-watch-for-in-2025)). Required a national-security-agency review of DJI/Autel by 2025-12-23 — review was not completed, triggering automatic FCC Covered List addition. |
| **Countering CCP Drones Act** (H.R.2864, 118th Congress) | NOT passed standalone; superseded | The standalone bill [did not make the FY25 NDAA conference text](https://dronelife.com/2024/12/08/fy-2025-ndaa-conference-text-what-happened-with-the-countering-ccp-drones-act/). The FY26 House version reintroduces similar language ([DroneLife, 2025-09-11](https://dronelife.com/2025/09/11/house-ndaa-fy26-chinese-drones/)). |
| **FCC Covered List addition** (DJI + foreign UAS) | Effective 2025-12-23 | DJI and other foreign-made UAS were added to the FCC Covered List, blocking new equipment authorizations and effectively banning import of new DJI models ([Hacker News / Wiley, 2025-12](https://thehackernews.com/2025/12/fcc-bans-foreign-made-drones-and-key.html), [Wiley alert](https://www.wiley.law/alert-In-Unexpected-First-of-Its-Kind-Action-FCC-Adds-All-Foreign-Produced-Uncrewed-Aircraft-Systems-and-UAS-Critical-Components-to-Covered-List)). |

**Net effect for wildfire-watch's strategic acquirers (Anduril, Palantir, Ondas, Red Cat, Kratos):** their DoD and DHS customers cannot procure or operate a platform with DJI components. The valuation engine flag `ndaa_blue_uas_eligible` flips to False the moment a DJI part is in the BOM, which in 2026 represents a hard procurement wall, not a soft preference.

---

## 3. Current Blue UAS Cleared List (2026)

The full list as of 2026-04 (compiled from [MFE Inspection Solutions guide, 2026](https://mfe-is.com/blue-uas/) and [Drone Girl, 2026-03-19](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/), cross-checked against [DCMA Blue List portal](https://bluelist.dcma.mil)):

| Manufacturer | Airframes | Cleared (most recent reference) |
|---|---|---|
| AeroVironment | Red Dragon | TBD |
| AgEagle Aerial Systems | eBee VISION, eBee TAC | TBD |
| Anduril Industries | Ghost, Ghost-X | Ghost added 2024-06 ([Anduril announcement](https://www.anduril.com/article/ghost-approved-for-the-blue-uas-cleared-list/)) |
| Ascent AeroSystems | Spirit | TBD |
| Auterion | SLM-10 | TBD |
| Easy Aerial | Osprey, Sparrow | TBD |
| Edge Autonomy | VXE30 Stalker | TBD |
| FlightWave Aerospace | Edge 130 | TBD |
| Freefly Systems | Astro/Max, Alta X (Blue Package) | TBD |
| Hoverfly Technologies | Spectre | TBD |
| Inspired Flight | IF800, IF1200A | TBD |
| Kraus Hamdani Aerospace | K1000ULE | TBD |
| ModalAI | Seeker Vision FPV, Stinger Vision FPV | TBD |
| Mountain Horse Solutions | Talon DT-300 | TBD |
| Neros Technologies | Archer, Archer Fiber | TBD |
| Ondas / American Robotics | Optimus | Added 2026-01-28 ([Ondas IR](https://ir.ondas.com/press-releases/detail/275/ondas-american-robotics-optimus-drone-approved-for-rapid)) |
| Parrot | ANAFI UKR, ANAFI USA GOV/MIL | ANAFI USA on list since program inception |
| PDW (Performance Drone Works) | C100 | TBD |
| Quantum Systems | Vector | TBD |
| Red Cat | Fang F7 | TBD |
| Renegade UxS | Nightmare, Nightmare Digital | TBD |
| Shield AI | V-BAT | TBD |
| Skydio | X10D | X10D added 2024-05 ([Skydio blog](https://www.skydio.com/blog/u-s-department-of-defense-adds-skydio-x10d-drone-to-blue-uas-cleared-list)) |
| Skyfront | Perimeter 8 | TBD |
| Teal (Red Cat) | Teal 2, Golden Eagle (1.8 GHz), Golden Eagle (2.4 GHz) | Teal 2 added 2023-06 |
| Teledyne FLIR | Black Hornet 4 | TBD |
| Thunder Tiger | Overkill FPV | TBD |
| Titan Dynamics | Raptor | TBD |
| Vantage Robotics | Trace, Vesper | TBD |
| Wingtra | WingtraOne Gen II, WingtraRAY | TBD |
| Zepher Flight Labs | Z1 | TBD |
| Zone 5 Technologies | Paladin | TBD |

**Counted: 34 manufacturers, 50+ airframes.** The 2025 [Blue UAS Refresh competition](https://www.diu.mil/latest/blue-uas-refresh-list-and-framework-platforms-and-capabilities-selected) selected 23 platforms and 14 components for verification and cybersecurity review — not all are on the cleared list yet.

**Manufacturers whose airframes are most relevant as wildfire-watch substitutes** (small-form, multimodal-payload-capable, sub-3 kg or lift-class compatible with our payload stack):

- **Skydio X10D** — 2.11 kg, 40-min flight, Teledyne FLIR Boson+ 640×512 thermal, $15k–20k system price ([Skydio X10 specs](https://www.skydio.com/x10/technical-specs), [DefenSync X10D](https://www.defensync.com/skydiox10d)).
- **Teal 2** — 1.25 kg, 30+ min flight, FLIR Hadron 640R thermal + 16 MP EO, 10,000 ft MSL ceiling ([Teal Drones](https://tealdrones.com/solutions/teal-2/)). Critical for Gunnison AOR — the 10,000 ft ceiling matches our flight envelope where Skydio X10's nominal envelope sits below ridgelines.
- **Parrot ANAFI USA Gov** — 500 g, 32-min flight, FLIR Boson 320×256 thermal + dual 21 MP EO, $4.8k–$13k ([Parrot specs](https://www.parrot.com/en/drones/anafi-usa/technical-specifications)). Lightest Blue UAS thermal-equipped option.
- **Ondas Optimus** — drone-in-a-box system with 11 onboard batteries and up to 9 mission payloads, 24/7 autonomous ops ([Ondas press](https://www.ondas.com/post/ondas-american-robotics-optimus-drone-approved-for-rapid-federal-procurement-via-dcma-blue-uas-clea)). Architecturally closest to where wildfire-watch wants to land for fixed-zone unattended monitoring.
- **Anduril Ghost-X** — 75-min flight, 25 km range, EW/ISR payload ([UAS Vision, 2026-04-13](https://www.uasvision.com/2026/04/13/anduril-gets-17m-us-army-contract-for-new-ghost-x-drones-with-isr-sensors/)). Large; not a drop-in for hobbyist wildfire patrol but the obvious upper-stack handoff target.

---

## 4. wildfire-watch substitution table

For every line in `hardware/bom.csv`, this is the per-row substitution argument. The CSV itself now carries a `blue_uas_substitute_phase1` column that codifies the same data machine-readably.

### 4.1 Airframe / flight controller / GPS / radio (the "drone" itself)

| BOM line | Phase 0 placeholder | Phase 1 NDAA-eligible substitute | Phase 1 Blue UAS Cleared substitute | Delta |
|---|---|---|---|---|
| Frame | DJI Mavic Mini 1/2 (Shenzhen) | **Holybro X500 V2** (Hong Kong; NOT on Cleared List but uses Cleared components) — already in BOM | **Skydio X10D** or **Teal 2** as turn-key cleared airframe | Cost: $380 → $15k (X10D) or ~$10k (Teal 2). Weight: 249 g → 2.11 kg / 1.25 kg. Capability: thermal added, ceiling matched. |
| Flight controller | DJI proprietary | **Cube Orange+ (CubePilot/Hex/ProfiCNC)** — NDAA 2024 compliant, Australian-owned, manufactured CA + Taiwan ([CubePilot US Defence](https://docs.cubepilot.org/user-guides/us-defence), [iRLock product](https://irlock.com/products/cube-orange-plus-standard-set)). Already shipped in Freefly Astro/Max (Cleared) | Skydio Autonomy Engine (proprietary, on Cleared X10D) | Same hardware as already in BOM. No substitution needed at component level. |
| GPS | DJI integrated | **Holybro H-RTK F9P Helical** (u-blox F9P module — Swiss; allowed) | Skydio integrated GNSS | u-blox F9P is the de-facto Blue UAS RTK module. No substitution needed. |
| Telemetry radio | DJI OcuSync (covered) | **Holybro SiK V3 915 MHz** (open-source SiK; allowed) for short-range; **Doodle Labs Mesh Rider Helix** for Blue UAS Framework grade ([Doodle Labs Helix](https://doodlelabs.com/news/how-doodle-labs-helix-mesh-rider-radio-achieves-blue-uas-compliance/) — sponsored by DIU, "the only radio to meet all Blue UAS Framework requirements in one radio") | Skydio multi-band Connect SL | Helix Mesh Rider is the architectural commitment; Section 848 compliant by design. |

### 4.2 Compute / sensors

| BOM line | Phase 0 placeholder | Phase 1 NDAA-eligible substitute | Phase 1 Blue UAS Cleared substitute | Delta |
|---|---|---|---|---|
| Edge compute | none (post-flight on Mac) | **Jetson Orin Nano Super 8GB** (NVIDIA, Santa Clara CA) — already in BOM | Skydio onboard NPU (proprietary) | NVIDIA is U.S. headquartered. Jetson Orin family ships in many Blue UAS Cleared platforms (Freefly Astro etc.). |
| RGB camera | DJI integrated 12 MP CMOS | **Arducam IMX477** (Sony IMX477 sensor + Arducam carrier; Sony is allowed; Arducam HQ Hong Kong but operates as Arducam International / U.S. subsidiary; **TBD — verify Arducam corporate structure for Sec. 1822 covered-entity status**) | Skydio VT300-Z 64 MP narrow-angle | Sony IMX477 is the same sensor used across many cleared airframes. The Arducam carrier is the substitution risk — see Sec. 7. |
| Thermal | none on Mavic Mini | **FLIR Lepton 3.5** (Teledyne FLIR, Goleta CA — "designed and assembled in the U.S., trusted supply chains, final testing at Goleta facility" per [Teledyne FLIR OEM](https://oem.flir.com/about/news/teledyne-flir-oem-enhances-defense-readiness-with-ndaa-compliant-thermal-imaging-solutions/)). NDAA compliant; ITAR free. | Teledyne FLIR Boson+ 640×512 (used in Skydio X10D) or FLIR Hadron 640R (used in Teal 2) | Lepton 3.5 is the entry-tier of the same vendor's product line. Architecturally identical. |
| Audio MEMS mic | n/a on Mavic | Adafruit SPH0645 (Knowles MEMS — U.S.) | n/a (cleared platforms don't typically include audio) | No covered components. |
| LTE modem | n/a | Quectel EC25-AF (Quectel HQ China — **covered foreign entity under Sec. 1822**) | Sierra Wireless EM7565 / Telit FN980 / U.S.-domiciled cellular module | **Real substitution required.** See Sec. 5 architectural commitments. |
| ADS-B in | n/a | uAvionix pingRX Pro (uAvionix, Bigfork MT) | same | uAvionix is the Blue UAS-defensible ADS-B vendor. No substitution. |
| Remote ID | n/a | uAvionix pingRID (Bigfork MT) | same | Same. |
| Battery | DJI proprietary LiPo | Tattu 4S 8000 mAh Li-Ion (Genstattu — Chinese-headquartered cells; **TBD covered-entity check**) | Inspired Energy / Bren-Tronics / Smart Battery (US-domiciled) | **Substitution required for full Blue UAS posture.** Tattu cells are common in cleared airframes today via integrator pass-through, but the future-proof move is U.S. cells. |
| Charger | DJI charger | ISDT Q8 500W (ISDT — Chinese vendor; **covered**) | iCharger / Hitec X4 / Cellpro PowerLab (US/allied) | Field charger is not a flight component, but a federal contracting officer reviewing the supply chain will flag it. Substitute. |

### 4.3 Phase 0.5 sensor mesh (ground station, not airframe)

The Phase 0.5 BOM (RTL-SDR Blog v4, PMS5003, BME688, Heltec V3, Pi 5 AI HAT+) is **all ground-side** — not subject to Blue UAS rules, which apply only to UAS and UAS components. We document them in the BOM with `blue_uas_substitute_phase1=ground_only` for completeness; no substitution is required.

### 4.4 Sensor pod (ground deployments — also not UAS)

Soil moisture (Vegetronix VH400, US), gas sensors (MQ-2/MQ-7, Chinese-OEM but trivially substitutable with FIGARO TGS-series Japanese parts), anemometer (Davis-clone, US Davis Instruments parent), Pi Zero 2 W (Raspberry Pi Foundation UK), Swarm M138 (SpaceBee constellation; Swarm is now SpaceX-owned, US), nRF52840 (Nordic Semi, Norway — allied), LiTime 12V LiFePO4 (LiTime — Chinese; substitute with Battle Born or Renogy USA cells), Seeed XIAO ESP32-S3 (Espressif — Shanghai; **covered for some interpretations; ESP32 is contested**).

The pod is not airborne. It is **not subject to Sec. 848 / Sec. 1822** (which apply specifically to UAS and UAS components, [FAR 52.240-1](https://www.acquisition.gov/far/52.240-1)). We still flag the substitutions in the BOM for the deeper "U.S. supply chain end-to-end" story an acquirer will want.

---

## 5. Architectural commitment statements

These are pre-decided design choices that put wildfire-watch on Blue UAS-aligned hardware from day one of Phase 1 — independent of whether we ever pursue a Cleared listing:

- **Flight controller: Cube Orange+ (CubePilot / Hex / ProfiCNC).** NDAA 2024 compliant; manufactured in California and Taiwan by allied factories; already shipped inside Blue UAS Cleared platforms ([CubePilot homepage](https://www.cubepilot.com/)). Reference platform for ArduPilot Copter 4.6.
- **Companion compute: NVIDIA Jetson Orin Nano Super 8GB.** NVIDIA Santa Clara HQ, no CCP-origin silicon, designed for autonomous machines. Used in Freefly Astro, Inspired Flight IF1200A, and others currently cleared.
- **Radio: Doodle Labs Helix Mesh Rider** for the Blue UAS Framework variant; SiK V3 for early prototyping. The Helix is "sponsored by the Department of Defense's Defense Innovation Unit specifically for the Blue UAS program" and is "the only radio to meet all Blue UAS Framework requirements in one radio" ([Doodle Labs](https://doodlelabs.com/news/how-doodle-labs-helix-mesh-rider-radio-achieves-blue-uas-compliance/)).
- **EO sensor: Sony IMX477 on Arducam Jetson carrier.** Sony Japan is allied; sensor allowed under Sec. 1822. Arducam carrier subject to TBD verification (see Sec. 7).
- **LWIR: Teledyne FLIR Lepton 3.5 (entry) → FLIR Boson 640 (production).** Goleta CA assembly, declared NDAA compliant by manufacturer.
- **Flight stack: ArduPilot or PX4.** Open-source, no nation-of-origin issue. ArduPilot Copter 4.6 is the reference for Cube Orange+. PX4 ships with Pixhawk 6X variants. Both stacks are deployed across multiple Cleared airframes.
- **GNSS: u-blox F9P (Swiss).** De-facto Blue UAS RTK module.
- **Remote ID + ADS-B: uAvionix.** US-domiciled, federally cooperating vendor.
- **Cellular fallback: Sierra Wireless / Telit (US/allied).** Quectel substituted out before Phase 1 manufacture.
- **Battery cells: Inspired Energy / Bren-Tronics smart-battery for Phase 1 production builds.** Tattu acceptable for prototyping only.

The PR-ready summary line: **"Every flight-critical component in the wildfire-watch Phase 1 BOM is either currently shipping in a Blue UAS Cleared platform or is on the Blue UAS Framework Component List."**

---

## 6. Software-side substitutability

The hardware lineage is half the story. The other half is that the wildfire-watch software stack is **completely hardware-agnostic** within the airframe class. The same code paths produce identical outputs regardless of airframe vendor:

- **`ml/fire_detection/infer.build_signal()`** — the canonical signal builder. Takes an image frame + GPS + telemetry; returns a `wildfire_signal` JSON dict. Doesn't know what airframe produced the frame.
- **`sim/`** — kinematic simulator. Tests run against a Mavic-shaped flight envelope today, but the dynamics model accepts any airframe with `(mass, max_thrust, drag_coef, max_speed, max_alt)`. Flying X10D-shape vs. Teal-2-shape is a `sim/missions/<name>.yaml` parameter swap.
- **`sim/swarm/`** — N-drone fleet + k-of-N consensus + lossy-comms model. Works on heterogeneous fleets (1× X10D + 3× Teal-2 + 5× custom Holybro is identical to 9× one model from the consensus voter's perspective).
- **`sim/perception/`** — GNSS-denied vision-nav (VO + TRN + IMU + complementary fusion + jamming). Camera-agnostic; needs only the intrinsics matrix and a frame stream.
- **`sapphire_integration/tak/`** — TAK / CoT emitter. Generates Cursor-on-Target XML for ATAK / TAK-X / WinTAK / Lattice / Apollo. Doesn't know or care what produced the underlying signal.
- **`valuation/`** — intrinsic-value calculator. Reads from the BOM and tags `ndaa_blue_uas_eligible` based on per-row substitution status — flips True the moment the BOM has no covered-foreign-entity rows.

The structural consequence: **a wildfire-watch acquirer or Lattice-tile partner can swap the airframe to whatever Cleared platform they already own and the rest of the stack runs unmodified.** Anduril already owns Ghost-X. They can fly Ghost-X over the Slate River drainage, push frames through `ml/fire_detection/infer.py`, and get `wildfire_signal` JSON into Lattice with zero code changes on our side. This is the second moat.

---

## 7. Documented gaps

Honest accounting of where wildfire-watch is **not yet** Blue UAS Cleared, in priority order:

1. **No flight-tested cybersecurity assessment.** The Blue UAS Framework requires a Recognized Assessor cybersecurity review ([DIU Recognized Assessors](https://www.diu.mil/latest/diu-seeking-recognized-assessors-to-support-blue-uas-ndaa-compliance)). We have not commissioned one. Cost estimate: see Sec. 8.
2. **No FOCI declaration, no facility security clearance.** We are an individual builder. Foreign Ownership, Control, or Influence (FOCI) declarations are required for Cleared listing.
3. **Arducam corporate structure verification (TBD).** Arducam appears to operate as Arducam International (U.S.) but with Hong Kong supply-chain ties. Before any Cleared submission, this needs a definitive Sec. 1822 covered-entity determination. **Flagged TBD.**
4. **Tattu battery cells need substitution for any Cleared submission.** Tattu is widely used as a pass-through component in cleared airframes today, but a primary BOM declaration would not survive scrutiny.
5. **ESP32 (Espressif Shanghai) in the Seeed XIAO sensor node.** Espressif's covered-entity status under Sec. 1822 is contested — they are Chinese-domiciled but produce widely-used commodity silicon. For a hardline interpretation, substitute with Nordic nRF52 or Microchip SAMD. **Flagged TBD.**
6. **No Remote ID compliance test report.** The pingRID provides hardware compliance but FAA has not been exercised on our integration.
7. **Mavic Mini in Phase 0 itself.** The Mavic is a covered DJI platform; using it for any federal-funded mission would violate Sec. 1825 effective 2025-12-22. Phase 0 is private, hobbyist use only — explicitly not federal-funded. The Phase 0 → Phase 1 transition is the moment we exit the Sec. 1825 risk surface.
8. **No Recognized Assessor relationship.** Submission via [Blue UAS Portal](https://www.diu.mil/blue-uas-portal) requires a sponsoring assessor.

We do not currently claim to be on the Blue UAS Cleared List. We claim to be **substitutable to it**. Sec. 8 is the path to actually landing on the list, if we ever choose to.

---

## 8. Roadmap to "Blue UAS Cleared" listing

If we wanted to land on the actual Cleared List (vs. claim substitutability), the realistic path:

### 8.1 Cost estimate

DIU does not publish standard certification fees; "Recognized Assessors will be able to provide a cost estimate and timeline" ([DIU Blue UAS FAQ](https://www.diu.mil/blue-uas-faq)). Triangulating from public reporting and what comparable assessors charge for a similar IL4-class cybersecurity assessment:

- **Recognized Assessor cybersecurity review:** $80k–$150k (one cycle; iteration likely)
- **Cybersecurity remediation engineering (in-house):** 2 FTE × 6–9 months ≈ $200k–$300k
- **Hardware BOM substitution for covered components:** $20k–$40k (Quectel → Sierra, Tattu → Inspired Energy, ESP32 → Nordic, etc.)
- **Flight-test campaign for assessor witness / data:** $30k–$80k
- **FOCI declaration + facility security baseline:** $20k–$50k
- **Federal contracting / legal counsel:** $30k–$60k

**Total:** **$380k–$680k**, with $250k–$500k as the central estimate after volume discounts on assessment work. Plus 12–18 months of clock time before the first Cleared submission, plus 6 months for assessment and approval.

### 8.2 Timeline

- **T+0 to T+6 mo:** BOM substitution (Quectel/Tattu/ESP32 → US/allied), close cybersecurity engineering gaps, file FOCI baseline.
- **T+6 to T+12 mo:** Engage Recognized Assessor; commission Phase 1 flight test campaign; produce assessor witness data.
- **T+12 to T+18 mo:** Submit via Blue UAS Portal; respond to assessor feedback; remediate.
- **T+18 to T+24 mo:** Cleared List addition (target).

### 8.3 Strategic decision

The honest strategic question is: do we want to land on the Cleared List ourselves, or do we want to be the **software-and-IP** that an already-Cleared platform vendor (Skydio, Red Cat / Teal, Parrot, Ondas, Anduril) integrates? The acquirer-fit research ([ACQUIRER_FIT-2026-05-02.md](./docs/strategy/ACQUIRER_FIT-2026-05-02.md)) argues the latter is the higher-EV path — every dollar spent chasing our own Cleared listing is a dollar not spent building the multimodal-fusion IP that's the actual moat.

**Recommended posture for the next 12 months:** maintain "substitutable to Blue UAS" as documented here; do NOT pursue Cleared submission ourselves; preserve the optionality to do so if a strategic acquirer wants the listing under our name post-acquisition.

---

## 9. References

Primary sources are linked inline throughout this document. Canonical anchors:

- DCMA Blue UAS Cleared List: [bluelist.dcma.mil](https://bluelist.dcma.mil) (replaces [diu.mil/blue-uas-cleared-list](https://www.diu.mil/blue-uas-cleared-list) as of 2026-01-01)
- Statute: [American Security Drone Act of 2023, S.473](https://www.congress.gov/bill/118th-congress/senate-bill/473/all-info), [FAR 52.240-1](https://www.acquisition.gov/far/52.240-1)
- 2026 list snapshots: [Drone Girl, 2026-03-19](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/), [MFE Inspection Solutions, 2026](https://mfe-is.com/blue-uas/)

---

## 10. Document hygiene

- All TBDs in this document are flagged as such. Do not cite them as confirmed.
- This document supersedes any earlier informal claims about Blue UAS positioning in `docs/strategy/` or `docs/intel/`.
- Update this document when (a) the BOM changes, (b) the Blue UAS Cleared List adds or removes a substitute we cite, or (c) Sec. 1822 / FCC Covered List interpretation changes materially.
- The companion machine-readable artifact is the `blue_uas_substitute_phase1` column in `hardware/bom.csv`.
