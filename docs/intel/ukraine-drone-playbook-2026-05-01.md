# Ukrainian Drone Playbook for Decentralized Wildfire-Watch

**Author**: research compiled 2026-05-01
**Scope**: civilian wildfire monitoring, decentralized-volunteer model, county scale (~1,000 sq mi)
**Hardware on hand**: 1× DJI Mavic Mini (1 or 2), Mac mini (commander), planned X8 quad
**Audience**: a single operator + a small volunteer network in California

---

## 1. TL;DR

- **Ukraine wins the drone war on logistics, not on chips.** Brave1 + ePoints + ~500 small manufacturers + ~10,000 volunteer 3D-printers (DrukArmy) is the actual moat. The stack underneath is ArduPilot/Betaflight/INAV — the same tools available to a kid in Sacramento.
- **Decentralized creation = catalog + standards + many small vendors.** Brave1 is essentially "Amazon for drones" with codified specifications and an ePoints currency. The wildfire-watch equivalent is a public BOM, public mission profiles, and a CalFire/county-fire-department procurement catalog.
- **For wildfire-watch, the three directly transferable patterns are:** (a) **codified open BOMs** so any volunteer can build the same airframe, (b) **distributed 3D-print + small-shop assembly** instead of a single factory, and (c) **vision-based GNSS-denied navigation** — which is exactly what you need flying through smoke and canyons even without an adversary.
- **Phase-0 today with the Mavic Mini:** waypoint missions via Litchi (supported on Mini 1/2), manual perimeter recon, post-flight YOLOv8 smoke/fire inference on the Mac mini. Sub-250g exempts you from FAA Remote ID and registration but not from California Penal Code 402 / wildfire TFRs.
- **Cheapest practical airframe under $400 is a Ukrainian-pattern 7" or 10" FPV with ArduPilot, not a Mavic clone.** ZOHD Dart 250G is the closest <$300 fixed-wing platform; sub-250g exempts you from a lot of paperwork but limits payload to a tiny RGB camera (no thermal under 250g end-to-end).
- **Comms: Meshtastic for ground-ground, Starlink Mini for command-uplink, LoRa+Reticulum as the resilience fallback.** Skip Helium for fire camps; not enough coverage outside metros.

---

## 2. Decentralized Creation Playbook

### Brave1 (the procurement layer)

Brave1 is a Ministry-of-Digital-Transformation cluster launched 26 April 2023 as a single front door for defense-tech startups. Its breakthrough is **Brave1 Market**, a catalog of certified, combat-tested drones and EW kit, paired with an "ePoints" currency that frontline units earn from verified action and spend directly on the catalog. As of April 2026, Ukraine has delivered **~181,000 systems** through ePoints in 2026 alone, and Brave1 Market has served **>$235M** in orders. The US Army has explicitly cloned the model. ([dronexl](https://dronexl.co/2026/04/05/ukraine-military-drone-marketplace-brave1/), [Brave1 official](https://brave1.gov.ua/en/), [Euromaidan Press](https://euromaidanpress.com/2026/04/24/ukraines-epoints-system-supplies-181000-systems-2026/))

**Lesson for wildfire-watch:** the market is the moat. A county-scale catalog of approved, drop-in-replaceable airframes — with a unit-cost ceiling and an interface contract (mission file format, telemetry schema, image-capture format) — beats any single bespoke airframe.

### Aerorozvidka (the volunteer-engineer template)

Founded May 2014 by Volodymyr Kochetov-Sukach as an NGO of volunteer IT and aerospace engineers; eventually absorbed into the Armed Forces. Built the **Delta** situational-awareness platform (handed off to the MoD's Center for Innovation and Defense Technologies in 2023) and the **R18 octocopter** (40-min endurance, 5 kg lift, vertical takeoff). Their philosophy: open standards, networked sensors, human-in-the-loop for kinetic decisions. ([Wikipedia: Aerorozvidka](https://en.wikipedia.org/wiki/Aerorozvidka), [aerorozvidka.ngo](https://aerorozvidka.ngo/en), [ORF Online](https://www.orfonline.org/expert-speak/ukraine-s-drone-war-from-improvisation-to-systematised-combat))

**Lesson:** start as a 5-engineer NGO with a clear deliverable (situational awareness for fire chiefs, not "drone hobby club"). Hand the platform off to the agency once it works.

### Wild Hornets (the small-shop civilian production template)

Charitable fund founded spring 2023. Started in an apartment producing 30 drones/month; by 2026 producing 1,500/month with ~30 people in a "small facility." Their **Sting interceptor** (3D-printed) had downed >3,900 enemy drones by early 2026. **They were the first to localize Ukrainian flight-controller production**, cutting cost by ~12%. ([Wikipedia](https://en.wikipedia.org/wiki/Wild_Hornets), [Wild Hornets](https://wildhornets.com/en/), [Ukraine's Arms Monitor](https://ukrainesarmsmonitor.substack.com/p/sting-interceptor-drone-by-wild-hornets))

**Lesson:** a 25-person volunteer engineering team can produce hundreds of units a week. The bottleneck is not chips, it's hands.

### Vyriy Drone (the import-substitution template)

Founded 2023, started 100% Chinese supply chain. By 2025 had localized FCs, ESCs, radio modems, and video TX. Their **Sokil** is a **$5,000, hand-launched, 170-km range, 2,500m ceiling fixed-wing recon drone with 20-minute deploy time** — that is exactly the spec sheet a fire-watch program would want, minus the warhead. ([Ukrainska Pravda](https://www.pravda.com.ua/eng/news/2026/03/01/8023343/), [VGI on FPV components](https://vgi.com.ua/en/the-race-for-drone-independence-ukraines-fpv-component-ecosystem/), [Militarnyi](https://militarnyi.com/en/news/ukraine-produces-first-thousand-fully-domestic-fpv-drones/))

**Lesson:** spec the recon-class drone first, then iteratively replace imported parts. Don't try to be 100% domestic on day one.

### DrukArmy / 3D Print Army (the volunteer manufacturing layer)

PrintArmy unites **~10,000 distributed 3D printer operators**. They run a job board; the army uploads STL + instructions, printers claim jobs, parts ship to the front. Output: tens of thousands of parts per week — drone bomb-release clips, Mavic battery adapters, Starlink mounts, scope rings. Models published openly at [drukarmy.org.ua](https://drukarmy.org.ua/en) and aggregated mirrors like [techagainsttanks.com/en/models](https://techagainsttanks.com/en/models/). ([rubryka](https://rubryka.com/en/2024/10/31/drukarmiya/), [dev.ua](https://dev.ua/en/news/3d-druk-dlia-zsu-iak-doluchytys-do-armii-drukariv-1763447555))

**Lesson:** the volunteer 3D print network is the single highest-leverage idea for a county-scale fire-watch fleet. Recruit local makerspaces. Publish an STL repo. Ship CalFire-painted gimbal mounts, antenna brackets, and Pelican-case inserts.

### Army of Drones / United24

UNITED24 has raised **>$3.5B** since launch (Feb 2026 figure), of which ~$3.3B routed to defense. Army of Drones is the procurement+training+replacement program. The crowdfunding-as-procurement loop is replicable for civilian use. ([UNITED24](https://u24.gov.ua/news/army_of_drones), [u24 Mark Hamill page](https://u24.gov.ua/dronation), [Bukvy on largest donors](https://bukvy.org/en/the-largest-donors-to-the-armed-forces-of-ukraine/))

**Lesson:** fire is the same kind of mass-casualty, mass-property-loss threat that motivates donor crowdfunding. A "Wildfire Watch / California" GoFundMe with a transparent BOM and per-drone naming-rights tier could fund a 10-drone fleet for ~$10–20K.

---

## 3. What Ukrainians Actually Fly

| Class | Example | Frame / size | Flight stack | Unit cost | Civilian wildfire-watch equivalent |
|---|---|---|---|---|---|
| Consumer-mod recon | Modified DJI Mavic 2/3 Enterprise | OEM | DJI + Litchi/Dronelink overlay | $1,500–6,000 | DJI Mini / Mavic 3T (you have the Mini) |
| Sub-250g recon | Sokil (Vyriy) | Hand-launched fixed-wing | Custom (likely INAV/ArduPilot derivative) | ~$5,000 | ZOHD Dart 250G + Pixhawk-mini (~$300) |
| 5"–7" FPV | Wild Hornets Sting / Vampire-class derivatives | Carbon X-frame, ~700–1,500g | Betaflight / INAV | $400–700 | Same — direct civilian build |
| 10" heavy FPV | Vyriy MAX 15 | 10-12" carbon frame | INAV/ArduPilot | ~$1,200 | Long-loiter overwatch — direct civilian build |
| Octocopter heavy | R18 (Aerorozvidka) | 5 kg lift, 40 min endurance | ArduPilot | $15K+ | Comparable to commercial Freefly Astro |
| Heavy bomber | Vampire / "Baba Yaga" | 1.5–2m hex/octo, 5–10kg payload | ArduPilot | $20K+ | Not relevant for fire-watch |
| Long-range strike | Khaki-20 + Starlink | Plywood/foam fixed-wing, 100kg payload | Custom + Starlink uplink | $5–15K | Not relevant; loitering-spotter analog only |

Sources: [The Ukrainian FPV component ecosystem (VGI-9)](https://vgi.com.ua/en/the-race-for-drone-independence-ukraines-fpv-component-ecosystem/), [Vyriy/Sokil reporting](https://www.pravda.com.ua/eng/news/2026/03/01/8023343/), [Starlink-on-drones](https://militarnyi.com/en/blogs/starlink-on-russian-drones-how-ukraine-can-protect-its-satcom-domain/), [orbitaltoday DIY-to-warforce](https://orbitaltoday.com/2026/04/16/how-ukraine-turned-diy-drones-into-a-powerful-war-force-and-what-europe-can-learn/).

**Cheapest reliable Ukrainian-pattern airframe under $400 in a Western market** = **ZOHD Dart 250G airframe ($150-200) + Matek/SpeedyBee mini Pixhawk-clone FC + Crossfire Nano RX + 3-cell LiPo + RunCam Phoenix** (or equivalent). Total ~$300–380 if you already own a transmitter. PNP airframe at <250g all-up means no FAA registration; you can keep adding payload up to ~500g for a Part 107 commercial config.

---

## 4. Flight-Stack + Autonomy

| Stack | Strength | Wildfire-watch fit |
|---|---|---|
| **ArduPilot** | Most mature autonomy, every vehicle class, biggest open community, MAVLink everywhere | **Pick this for the fleet.** |
| **PX4 + Auterion** | Cleaner code, faster to integrate custom sensors, good multirotor focus | Good if you have engineer-time; otherwise overkill |
| **Betaflight + INAV** | What Ukrainian FPVs run | Pick for the cheap 5/7/10" perimeter-sprint scouts |
| **DJI MSDK v4 / v5** | Mavic Mini 1 = MSDK v4 (Litchi), Mini 3/4 Pro = MSDK v5 (Litchi Pilot) | Use for Phase 0 only — DJI is closed; you'll need Part 107 anyway |
| **Saker autopilot** | On-board AI target-ID; closed source | Not available; learn from publicly known architecture |

Sources: [PX4 vs ArduPilot (Droning Co)](https://thedroningcompany.com/blog/px4-vs-ardupilot-choosing-the-right-open-source-flight-stack), [ArduPilot wiki](https://en.wikipedia.org/wiki/ArduPilot), [Litchi Help](https://flylitchi.com/help), [Litchi waypoint utilities](https://www.litchiutilities.com/docs/waypoint.php).

What's known publicly about **Saker Scout**: AI-enabled target detection trained on ~64 classes of military equipment, runs on a custom on-board mission computer (likely Jetson Nano or Orin-class), uses inertial nav as GPS-denied fallback, integrates with Delta. The autopilot itself is closed; the architecture (lightweight YOLO-class model + INS + flight-controller MAVLink bridge) is **fully reproducible with Jetson Orin Nano + ArduPilot + a custom Python/C++ mission-computer service**. ([Defense Express](https://en.defence-ua.com/weapon_and_tech/ukrainian_forces_get_an_ai_powered_saker_scout_drone_and_its_algorithms_can_solve_an_important_problem-7842.html), [Pravda](https://www.pravda.com.ua/eng/news/2023/09/04/7418331/), [Automated Decision Research](https://automatedresearch.org/weapon/saker-scout-uav/))

**Recommended wildfire-watch stack:** ArduPilot 4.5 → MAVLink → Mac mini ground station running QGroundControl + a custom Python "mission supervisor" wrapped around the Sapphire control-plane. Mission-computer payload is Jetson Orin Nano running YOLOv8 fire/smoke + CLIP-based scene-tagging.

---

## 5. GNSS-Denial + Perception (smoke and canyons)

The wildfire-watch problem is structurally **identical to GNSS-denied combat flight**: smoke kills GPS L1/L5 fix in dense plumes (multipath + scattering), canyons and ridgelines block satellites, and thermal updrafts confuse magnetometers. Ukrainian techniques apply directly.

- **OSCAR (Optical System of Coordinates with Automatic Relocalization):** downward-facing camera matches live frames against pre-loaded satellite imagery; positions without GNSS. ([Ukraine War Analytics](https://ukraine-war-analytics.com/technology/gps-gnss-denial-navigation-alternatives.html))
- **KrattWorks Ghost Dragon** ships a neural network that compares the downward-camera view against stored satellite tiles. Production system, not a paper. ([IEEE Spectrum](https://spectrum.ieee.org/ukraine-killer-drones), [The Defense Post](https://thedefensepost.com/2026/01/29/ukraine-drones-vision-navigation/))
- **TERCOM** (terrain-contour-matching via radar altimeter): passive, can't be jammed, but needs a pre-loaded DEM. USGS 3DEP gives you California at 1m resolution for free.
- **Visual-Inertial Odometry (VIO):** the most practical for a $300–600 mission computer. OpenVINS, Kimera, and ORB-SLAM3 are all open-source; running on a Jetson Orin Nano with a global-shutter camera gets you 2–5 cm/s drift in good conditions, ~50 cm/s in smoke. ([ScienceDirect terrain-weighted VO](https://www.sciencedirect.com/science/article/pii/S1569843224006332))
- **Bavovna AI** publishes their architecture for an AI-enhanced INS. Worth reading. ([Bavovna AI](https://bavovna.ai/uav-jamming/))

**Recommendation for wildfire-watch:** every airframe gets (1) a redundant GPS (u-blox F9P or M10), (2) a downward camera + VIO running on the mission computer, (3) a pre-loaded California DEM on SD card, (4) terrain-relative-altitude rules ("never < 50m AGL by DEM"). This isn't optional in smoke.

---

## 6. Open Datasets + Models

| Resource | License | Wildfire-watch applicability |
|---|---|---|
| **D-Fire dataset** ([gaiasd/DFireDataset](https://github.com/gaiasd/DFireDataset/)) | Open | Mixed ground/aerial fire+smoke, ~21K images. Direct fit. |
| **VisDrone** ([docs.ultralytics.com/datasets/detect/visdrone](https://docs.ultralytics.com/datasets/detect/visdrone/)) | Research | Aerial benchmark; useful for transfer learning to your altitude regime |
| **Smoke-Fire-Detection-YOLO (Kaggle)** | Open | 7,000+ images for YOLO finetuning |
| **YOLOv8 multiscale wildfire (Nature Sci Reports 2025)** | Paper, weights typically released | Best published mAP; reference architecture |
| **Roboflow Universe `class:drone` and fire-and-smoke** | Mixed | Pre-annotated; good for cold-start |
| **fire-detection-from-images (robmarkcole)** | MIT | Reference repo, good baselines |
| **Saker autopilot weights** | **Closed** | Architecture is reproducible, weights are not |

Sources: [YOLOv8 multiscale wildfire (Nature)](https://www.nature.com/articles/s41598-025-86239-w), [YOLO architectures study (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2590123025009454), [robmarkcole repo](https://github.com/robmarkcole/fire-detection-from-images), [VisDrone](https://docs.ultralytics.com/datasets/detect/visdrone/), [D-Fire dataset](https://github.com/gaiasd/DFireDataset/).

**Practical training plan:** start from a YOLOv8n checkpoint pre-trained on COCO → finetune on D-Fire + Kaggle Smoke-Fire → cold-start at the Mac mini (RTX-less; CPU/MPS is fine for nightly training of YOLOv8n) → migrate hot path to the Windows RTX 5070 Ti for full v8m/v8l. Keep a separate thermal model trained on FLIR's free thermal datasets when you add a thermal payload.

---

## 7. The Mavic Mini Today (Phase 0)

You own a **DJI Mavic Mini 1 or 2**. Here's the plan to use it as a Phase 0 manual scout this week.

### Regulatory (California, 2026)

- **Sub-250g** = exempt from FAA registration AND exempt from Remote ID (recreational only — see below). ([UAV Coach CA](https://uavcoach.com/drone-laws-california/), [Rotate RID guide](https://www.rotatepilot.com/guides/remote-id-guide))
- **Volunteer fire-watch counts as non-recreational.** That means **Part 107** ($175 exam, 60 questions, 24-month recurrent) and **Remote ID compliance** (broadcast module if drone lacks built-in; the Mini 1 does NOT, the Mini 2 does NOT — both need a $30–80 broadcast module like the BlueMark/Spektreworks).
- **Wildfire TFRs are absolute.** Flying any drone in an active wildfire TFR violates 14 CFR 91.137 and California Penal Code 402: up to **$5,000 fine + jail**. CalFire grounds aerial firefighting on drone incursions and pursues prosecutions. **Do not fly during active TFRs, period.** ([Dronesgator CA](https://dronesgator.com/drone-laws-in-california)) Pre-fire monitoring is the niche. Use [tfr.faa.gov](https://tfr.faa.gov) and the B4UFLY app every flight.

### Modding the Mini

- **Litchi waypoint missions** are supported on Mini 1 and Mini 2 (MSDK v4). Plan in Litchi Mission Hub on the Mac, fly the planned mission. ([Litchi help](https://flylitchi.com/help), [Litchi DJI waypoint docs](https://www.litchiutilities.com/docs/waypoint.php))
- **Thermal payload on a Mini is impractical.** A FLIR Boson core is 7.5g but the support electronics + power + mount put a working thermal rig at 60–120g, blowing the 249g limit and cooking the Mini's prop margin. Forum builds exist (DIY Mavic Mini thermal on YouTube) but they're brittle. **Do not pursue thermal on the Mini; reserve thermal for the X8 / fixed-wing fleet.**
- **FPV camera tap** is feasible but voids warranty and adds latency. Skip.
- **GPS spoof resistance** on the Mini: none. Treat it as a fair-weather tool.

### Phase 0 workflow (do this week)

1. **Plan a perimeter mission in Litchi** for the parcel/county area you want to scout. 50–100m AGL, 4–6 m/s, RGB, 70% overlap. Cache the satellite tiles before going out of LTE coverage.
2. **Fly the mission manually** as a Part-107 operator under daylight VLOS. Land. Pull the SD card.
3. **Run YOLOv8n inference on the Mac mini** (Sapphire's existing python/torch stack) against the DJI Mini's RGB. Output GeoJSON detections (use the DJI EXIF GPS tags) into Sapphire's data lake; surface them in the dashboard at `:8080`.
4. **Flight log → Sapphire**: ingest the DJI .DAT to a JSONL alongside the predictions; use the same `pipeline_id` correlation pattern Sapphire already uses for paper-trading.
5. **Move on.** The Mini is a stopgap. The real fleet is ZOHD-Dart-class fixed-wing and 7" FPV scouts running ArduPilot.

---

## 8. Decentralized Communications

| Layer | Tool | Role | Cost |
|---|---|---|---|
| **Drone-to-drone, drone-to-ground (mesh)** | Meshtastic on 915MHz LoRa | Telemetry + heartbeat fallback when 4G/5G dies | $30–80/node |
| **Long-range encrypted mesh, multi-medium** | Reticulum (RNS) over LoRa + WiFi | Sovereign comms, encrypted by default, works across radios | Free (software) + RNode hardware $80 |
| **Command uplink + livestream** | Starlink Mini | Real-time drone video out to incident commander | $599 hardware + $50/mo |
| **Tactical situational awareness** | ATAK / iTAK / WinTAK over LTE or Meshtastic | Standard CalFire / fire-dept mapping app | Free (gov't ATAK) |
| **Local short-haul** | 5.8GHz video + WiFi-HaLow | Standard FPV link | $30–80 |

Sources: [Meshtastic drone relay](https://meshnology.com/blogs/meshnology-blog-1/meshtastic-drone-relay-node-expanding-lora-mesh-communication-with-dr), [Spec5 Raven](https://specfive.com/blogs/articles/specfive-raven-meshtastic-drone-for-off-grid-ops), [Reticulum (markqvist)](https://github.com/markqvist/Reticulum), [Reticulum hardware](https://reticulum.network/manual/hardware.html), [Starlink-on-drones cost reporting](https://militarnyi.com/en/blogs/starlink-on-russian-drones-how-ukraine-can-protect-its-satcom-domain/).

**Practical recommendation:** every airframe ships with a Meshtastic node ($40 RAK4631) running as a flight-tracker beacon — gives you 25-mile range from altitude and survives the LTE/WiFi failure mode. Build a Reticulum overlay on top so node identities are stable and encrypted regardless of radio. Starlink Mini sits on the operator's vehicle as the uplink to Sapphire, **not on the drone** (cost+weight+SpaceX TOS for civilians is fine; it's the EW environment that breaks Starlink-on-drone, which doesn't apply here). Skip Helium / LongFi — coverage is metro-only and the economics don't work for static fire-camp deployments. ATAK is non-negotiable if you want fire-department adoption: that's the universal map every CA agency speaks.

---

## 9. Adapted Decentralized-Creation Model for the User

A single operator + a small volunteer network can run a 10-drone county fire-watch fleet on a Ukrainian-inspired model. Here's the sketch.

### Org shape

- **You** = founder, Part-107, system architect, operator-of-record.
- **3–5 volunteer engineers** = airframe build, mission-computer firmware, ground-station ops. Recruit from local makerspaces (NorCal: Sudo Room, Hacker Dojo, Maker Nexus; SoCal: Crashspace, FUBAR Labs).
- **20–50 distributed 3D-printer operators** = the DrukArmy analog. Recruit on r/3Dprinting, Printables, local maker Discord servers. Publish STL repo.
- **One CalFire / county fire dept liaison** = your "Brave1 Market customer." Without a public-safety partner, you have no flight authorization and no audience.

### Fleet mix (10 drones, ~$8K total airframe cost)

- 4× **ZOHD Dart 250G + Pixhawk + RGB** (~$350 each = $1,400) — perimeter sweep, sub-250g, recreational-class
- 4× **7" FPV scouts** with ArduPilot + RunCam Phoenix + Crossfire (~$500 each = $2,000) — canyon and structure overwatch
- 2× **X8 quadcopter + Jetson Orin Nano + thermal (Boson 320 or InfiRay)** (~$2,200 each = $4,400) — heavy lifters, autonomous routes, the Saker analog
- Plus: 1 Mac mini commander (have), 4 Meshtastic nodes ($160), 1 Starlink Mini ($599), Pelican cases ($600). Round up: **~$10,000 hardware, $50/mo recurring**.

### Recruitment + funding plan (12-week sketch)

- Week 1–2: cut a 5-page brief modeled on Sapphire's existing `docs/intel/`. Distribute to Maker Nexus, Sudo Room, your CalFire CAP unit. Start a public STL repo.
- Week 3–4: file Part 107 if you don't have it. Stand up a `wildfire-watch.org` GitHub org with the BOM, mission-profile JSON schema, and a tiny `claw-tools` plugin so Sapphire's existing dashboard can ingest flight logs.
- Week 5–8: build prototype #1 (the ZOHD Dart) in public. Stream the build. This is your United24 moment.
- Week 9–10: 5-volunteer build-day at a maker space. 4 airframes airworthy.
- Week 11: GoFundMe (modeled on UNITED24 — transparent BOM, named-drone tier at $500, county-deploy tier at $5,000). Realistic ceiling for a first-time campaign in a fire-aware district: $25–50K.
- Week 12: First CalFire / county-fire-dept demonstration flight.

### Catalog discipline (the Brave1 lesson)

- **One BOM file per airframe**, versioned in Git. Anyone can build the same drone.
- **One mission-profile JSON schema** for "perimeter scan", "structure overwatch", "spot-fire investigation". Mission file is the contract; airframes are interchangeable.
- **One telemetry/detection format** (MAVLink + GeoJSON + Sapphire's existing pipeline_id pattern). Fire dept gets the same data shape no matter which drone flew.

---

## 10. Risks + Ethics

This is the part you can't skip.

- **ITAR / EAR boundary.** Civilian wildfire monitoring is firmly on the EAR99 / unrestricted side of the line for the airframes and sensors named in this doc. **The line you do not cross is munitions/drop-mechanism integration.** No payload-release hardware, no autonomous targeting, no "loitering munition" software bits. Ukraine's "Drone Deals" framework is now opening surplus exports under MoD oversight, but US civilians do not get to import combat-tested Ukrainian munitions-class kit. ([Atlantic Council on Ukrainian export readiness](https://www.atlanticcouncil.org/blogs/ukrainealert/ukrainian-defense-tech-companies-must-prepare-for-export-opportunities/), [Euromaidan Press: Drone Deals](https://euromaidanpress.com/2026/04/28/ukraine-to-allow-arms-exports-under-new-drone-deals-framework-zelenskyy/), [JRupprecht export law primer](https://jrupprechtlaw.com/drone-export-control-laws-ear-itar/))
- **Recent US Treasury sanctions on Ukrainian firms** (Ekofera, Imperative Ukraine) for shipping dual-use components to Iran's Shahed program show the enforcement environment is hot. Source components from Western suppliers (Mateksys, Holybro, ModalAI, Hex/CubePilot). ([Kyiv Independent](https://kyivindependent.com/iran-buys-shahed-components-from-within-ukraine-us-treasury/))
- **DJI ban.** As of 2026, the DJI legal status in the US is contested under the Countering CCP Drones Act and pending FCC action; commercial public-safety use is increasingly NDAA-restricted. Plan for a non-DJI fleet from day one. The Mavic Mini is fine for personal use today but **don't build the program around it.** ([UAV Coach DJI Ban guide](https://uavcoach.com/dji-ban/))
- **Privacy.** California Civil Code § 1708.8 (anti-paparazzi) extends to drones. Flying RGB or thermal over private property without consent creates civil liability. Stick to public land and enrolled-property flights.
- **Wildfire TFR criminal liability** has been re-emphasized above. **This is the single most likely way a well-meaning volunteer fire-watch program ends in a felony charge.** Train every operator on TFR check-before-takeoff. CalFire has aggressively pursued these.
- **Dual-use AI:** the same YOLO-fire model can be retrained as a YOLO-person model. License your repo accordingly (e.g., MIT with a clearly-stated civilian-use intent in the README; you cannot prevent misuse, but you can document it).
- **Liability insurance.** Get $1M aviation liability before any third-party flight. Verifly, BWI, and SkyWatch.AI all sell hourly policies.

---

## Appendix A: Top 5 sources to read this week

1. **Brave1 Wikipedia + Brave1 official** ([wiki](https://en.wikipedia.org/wiki/Brave1), [brave1.gov.ua](https://brave1.gov.ua/en/)) — the marketplace model.
2. **DrukArmy / 3D Print Army** ([drukarmy.org.ua](https://drukarmy.org.ua/en)) — the volunteer print-network template.
3. **Wild Hornets profile** ([Wikipedia](https://en.wikipedia.org/wiki/Wild_Hornets), [substack profile](https://xxtomcooperxx.substack.com/p/the-wild-hornets-ukrainian-volunteer)) — small-shop civilian production at scale.
4. **IEEE Spectrum on Ukraine autonomous drones + jamming** ([spectrum.ieee.org/ukraine-killer-drones](https://spectrum.ieee.org/ukraine-killer-drones)) — best single explainer of GNSS-denied vision navigation.
5. **Ukraine FPV component ecosystem (VGI-9)** ([vgi.com.ua/en/the-race-for-drone-independence](https://vgi.com.ua/en/the-race-for-drone-independence-ukraines-fpv-component-ecosystem/)) — most concrete BOM-level breakdown of what Ukrainians actually buy and source.

---

*End of doc. Word count target: 2,500–4,000. This document is ~3,400 words.*
