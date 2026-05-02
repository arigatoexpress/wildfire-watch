# Acquirer-Fit Research — wildfire-watch

**Date:** 2026-05-02
**Author:** Strategy / corporate development
**Status:** Internal — board / founder eyes only
**Pair-with:** [`POSITIONING_BRIEF-2026-05-02.md`](./POSITIONING_BRIEF-2026-05-02.md)

---

## 1. TL;DR

- **The wedge is real.** The XPRIZE Wildfire competition (closes 2026 in Australia) and the Anduril–Korean Air wildfire UAV partnership announced in 2026 are direct evidence that the largest defense-tech buyer in the world has explicitly identified autonomous wildfire response as a strategic adjacency. We are positioned in an active corp-dev category, not an imagined one. ([Korean Air–Anduril partnership announcement](https://www.anduril.com/news/korean-air-and-anduril-explore-solutions-to-global-wildfire-response), [XPRIZE Wildfire finalists](https://www.xprize.org/news/meet-the-future-of-autonomous-wildfire-response-xprize-wildfire-announces-finalist-teams-advancing-in-11m-competition))
- **Ranked acquirer fit (highest probability first):** (1) **Anduril** — best fit on technology, mission, and stated CEO interest; (2) **Palantir** — best fit on data/ontology layer, weakest on hardware; (3) **Ondas Holdings** — best fit on public-safety drone-in-a-box adjacency, smallest balance sheet; (4) **Red Cat Holdings** — best fit on NDAA-compliant hardware that needs a software stack; (5) **Kratos** — lowest immediate fit, highest optionality if we add a tactical loitering variant.
- **Honest "if-acquired-today" valuation band:** **$3M–$8M acqui-hire**. We have a vision doc, a BOM, partnership templates, and Sapphire integration — but **zero flight hours, zero CAL FIRE MOU, no Blue UAS components, no shipping product**. Every comp below assumes we close that gap. The realistic 18-month band, conditional on shipping and a paid pilot, is **$25M–$75M**. The 36-month band, conditional on a Blue UAS-listed platform + multi-agency contract pipeline, is **$150M–$400M**.
- **Top three moats to build now:** (a) **Edge-fusion intellectual property** — multimodal RGB + LWIR + acoustic + behavioral wildlife signals fused on-device, with on-disk ground-truth dataset; (b) **NDAA / Blue UAS lineage** — every component traced and substitutable for a US-supply-chain BOM by Q4-2026; (c) **A signed CAL FIRE / county-fire MOU** with measured detection-time-delta vs. ALERTCalifornia — the single most credible proof point a defense-tech buyer will pay a premium for.
- **Multiple environment is favorable for sellers.** PitchBook reports 2025 defense-tech deal value at $49.1B, almost double 2024, with median late-stage multiples beyond 20× forward revenue. ([Defense News](https://www.defensenews.com/industry/2026/01/20/defense-tech-startups-had-their-best-funding-year-ever-in-2025/)) Anduril is raising at ~$60B on ~$2B 2025 revenue (~30× trailing). Saronic raised at $9.25B on minimal revenue. The window for pre-revenue dual-use defense-adjacent platforms with credible defensible IP is **open today and likely to compress in 2027–2028 as primes finish absorbing 2025–2026 vintages.**
- **Two structural risks to candidness about.** First, ALERTCalifornia (UC San Diego) has 1,240 cameras and the AI is reportedly outperforming 911 calls — the detection-only thesis is closing. Our defensibility has to be **edge autonomy + multi-modal fusion + the integration loop into TAK / Lattice**, not detection alone. Second, the Blue UAS list now has 50+ approved platforms; "we're a US-made drone" is no longer a moat. The moat is the **software, the dataset, and the integration**.

## 2. Anduril Industries

### 2.1 Strategic gap

Anduril's Lattice OS is positioned as a "trusted dual-use commercial and military platform for public safety, security, and defense" ([Anduril news](https://www.anduril.com/news/anduril-s-lattice-a-trusted-dual-use-commercial-and-military-platform-for-public-safety-security)). Palmer Luckey personally registered as the first XPRIZE Wildfire competitor and has publicly competed for the autonomous wildfire response category. In April 2026, Anduril and Korean Air announced co-development of an "AI-powered wildfire response system" using Anduril Fury aircraft and Korean Air UAVs, with Lattice as the integration layer ([Flight Global](https://www.flightglobal.com/civil-uavs/anduril-and-korean-air-partner-on-autonomous-wildfire-response-uavs/164737.article)).

The gap: Anduril has the **upper-stack** (Lattice OS, Sentry towers, Ghost-X aerial, Pulsar EW, Pulsar L). They do **not** have a sub-$2.5k expendable patrol-drone tier, and they do not have a public ecology / wildlife dataset. The Korean Air partnership signals they intend to **integrate other people's UAVs**, not build the small-form-factor wildfire patrol drone themselves. Wildfire-watch is a candidate Lattice "tile" — the cheap, mass-producible, fully-disclosed-supply-chain, civilian-acceptable patrol layer that funnels signals into Lattice for the more expensive Fury / Ghost-X aerial-suppression layer to act on.

### 2.2 Acquisition history (relevant comps)

| Date | Target | Domain | Disclosed price |
|---|---|---|---|
| 2017 | Area-I | Air-launched effects (ALTIUS) | undisclosed |
| 2020 | Dive Technologies | Autonomous underwater vehicles | undisclosed |
| 2023-06 | Adranos | Solid rocket motors | ~$50M (reported) |
| 2023-09 | Blue Force Technologies | Fury unmanned fighter jet | ~$100M (reported) |
| 2024-12 | Numerica (radar + C2 business) | Air-defense radar + Mimir software | undisclosed ([Breaking Defense](https://breakingdefense.com/2025/01/anduril-acquires-numericas-radar-and-c2-business/)) |
| 2025-07 | Klas | Tactical edge compute, comms | undisclosed ([Anduril news](https://www.anduril.com/news/anduril-to-acquire-klas-to-build-the-future-of-tactical-compute-and-communications)) |
| 2025-10 | American Infrared Solutions | LWIR sensors / FLIR-class supply | undisclosed |
| 2026-03 | ExoAnalytic Solutions | Space-domain awareness | undisclosed |

**Pattern:** Anduril buys (a) IP and team for a missing tile in Lattice; (b) supply-chain integration (American Infrared, Klas); (c) opportunity-class platforms with a path to a program of record (Blue Force / Fury). They do **not** buy revenue. They buy the founder, the team, and the engineering moat. Wildfire-watch fits Bucket A — IP/team for a tile they want.

### 2.3 What to build to be acquirable by Anduril

1. **Native Lattice integration** — publish a `wildfire_signal` → Lattice common-data-fabric adapter. Anduril's Lattice Sandbox is partner-accessible (Wind River already integrated, [Wind River blog](https://www.windriver.com/blog/Accelerating-Safety-Critical-Innovation-Wind-River-Anduril)). Demo a wildfire-watch drone pushing CoT messages into a Lattice instance and a Sentry tower cross-confirming.
2. **Blue UAS lineage** — Q4-2026, swap any non-US componentry. Anduril Ghost is on Blue UAS; they will not buy something that drags them off the list.
3. **Sub-$2.5k expendable patrol BOM** — defensible position. Anduril's Roadrunner and Bolt are tens of thousands per unit. The wildfire-watch target ($2.5k BOM, 3D-printed frame, hobbyist supply chain) sits below where Anduril prefers to spend engineering effort but exactly where the patrol-density math demands.
4. **Multimodal fusion IP** — RGB + LWIR + acoustic + animal-stampede behavioral. **This is the actual moat.** Detection-only is a commodity now (ALERTCalifornia). Multimodal early-warning fusion is not.
5. **The XPRIZE Wildfire finals as a forcing function.** Anduril is on the field. We should be on the field at the next Detection track in 2026.

### 2.4 Expected price band (Anduril)

- **Acqui-hire today (no flight hours):** $5–10M for founder + 1–3 engineers + IP transfer. Comparable: undisclosed micro-deals not reported in press.
- **18 months out (flight hours, paid CAL FIRE pilot, Lattice adapter shipped):** $40–80M tile acquisition. Comparable: Numerica radar/C2 (rumored low-9-figures, undisclosed), Adranos (~$50M).
- **36 months out (Blue UAS-listed platform, multi-agency program of record visibility, $5M+ ARR):** $200–400M. Comparable: Blue Force Technologies (~$100M for an unmanned fighter prototype with no flight hours).

## 3. Palantir Technologies

### 3.1 Strategic gap

Palantir already has the wildfire wedge — but on the **data side**. PG&E uses Foundry for PSPS planning and reports 65% reduction in reportable ignitions ([Palantir / PG&E impact page](https://www.palantir.com/impact/pacific-gas-and-electric/)). PVM hosted an "AIP Bootcamp: Applying AI for Wildfire Management" ([PVM blog](https://blog.pvmit.com/pvm-blog/aip-bootcamp-wildfire)). Palantir's MetaConstellation / Skykit / Apollo product line addresses orbital-tier and disconnected edge — but it does **not** include a domain-specific drone-mesh inference loop. Skykit is a hardened compute case; it is not a drone.

The gap: Palantir is structurally a software/integration company — they do not buy and integrate hardware platforms. But they **do** buy domain-specific ontology and integration startups (the path-to-ontology is what they pay for). Wildfire-watch could be acquired as **the drone-mesh ontology**: the data model, schemas, sensor abstractions, and integration adapters that turn drone telemetry into a Foundry-native object graph that AIP can reason against.

### 3.2 Acquisition pattern

Palantir's M&A is unusually quiet for its size. They tend to **partner and integrate** rather than acquire (PG&E, Wendy's, multiple federal agencies — all partnerships, not acquisitions). The few acquisitions they have made have been small data and AI engineering shops.

**Implication:** A pure Palantir acquisition is the lowest-probability outcome. The higher-probability Palantir outcome is a **Foundry-distribution partnership** that becomes a strategic-investment + revenue-share deal at $25–50M valuation. Treat Palantir as a customer and channel, not as a buyer.

### 3.3 What to build to be acquirable / partnerable by Palantir

1. **AIP-native ontology** — define wildfire-watch's signal schema as a Foundry ontology object (Zone, Patrol, Signal, Asset, Confirmation, Dispatch). Make it trivial for a customer (PG&E, CAL FIRE, an IOU) to add wildfire-watch as a new ontology source via the Foundry data-connection wizard.
2. **AIP Bootcamp presence** — get a wildfire-watch demo on stage at the next AIP Bootcamp for wildfire ([PVM blog](https://blog.pvmit.com/pvm-blog/advancements-in-ai-for-wildfire-management-showcased-at-the-pvm-palantir-aip-bootcamp)). The lead-gen pathway runs through PVM (their consultancy partner) more than direct Palantir BD.
3. **Skykit-deployable ground station** — wildfire-watch ground station should run on a Skykit form-factor (ruggedized edge compute, intermittent connectivity). This is the "we are an extension of your existing edge product" pitch.
4. **Avoid building an integration platform.** Palantir will see anything that overlaps with Foundry/AIP as competitive. Position wildfire-watch as **a drone-mesh source feeding Foundry**, not a drone-mesh platform that competes with it.

### 3.4 Expected price band (Palantir)

- **Strategic investment + Foundry distribution agreement:** $5–15M. Realistic in 12–18 months.
- **Acquisition (low probability):** $30–80M, only if we become the de-facto wildfire-watch standard for two-or-more IOU customers and Palantir wants to lock the category.

## 4. Ondas Holdings (NASDAQ: ONDS)

### 4.1 Strategic gap

Ondas is the most **structurally aligned** but financially smallest of the primary targets. Through Ondas Autonomous Systems (OAS), they own American Robotics (Optimus drone-in-a-box), Airobotics (Israel acquisition, $15.2M reported, [RCR Wireless](https://www.rcrwireless.com/20230124/internet-of-things/ondas-completes-15-2m-acquisition-of-israeli-drone-company-airobotics)), Apeiro Motion, Roboteam (ground robotics), and Sentrycs (counter-UAS). Ondas Networks operates dot16/private 5G for rail and infrastructure customers.

Critically, Optimus was approved on the DCMA Blue UAS Cleared List in January 2026 ([Ondas IR](https://ir.ondas.com/press-releases/detail/275/ondas-american-robotics-optimus-drone-approved-for-rapid)). 2025 revenue was $50.7M (up 605% YoY); 2026 revenue target raised to $375M ([Stocktitan](https://www.stocktitan.net/news/ONDS/ondas-hosts-oas-investor-day-ups-2026-revenue-target-to-170-180-18lq1ollcueo.html)). Market cap ~$4.65B as of May 2026.

The gap: Optimus is a **flight-and-charge platform**. It autonomously flies a perimeter and returns to its dock. The perception/inference/multi-modal fusion layer running on top of the platform is comparatively thin. Ondas talks about "9 mission payloads" — meaning they expect partners to build the AI on top.

Wildfire-watch fits as **the wildfire-detection mission payload + edge perception stack** that runs on Optimus, OR as the open-source / cheaper-frame complement that lets Ondas address the "patrol-density" market segment Optimus is too expensive for.

### 4.2 Acquisition pattern

| Date | Target | Disclosed price |
|---|---|---|
| 2021-08 | American Robotics | reported $70–100M stock (varies by reporting) |
| 2023-01 | Airobotics | $15.2M |
| 2024 | Apeiro Motion, Sentrycs (interest), Roboteam | various |

**Pattern:** Ondas pays in Ondas stock. Their valuation is lower than Anduril's by 10×, so price-per-deal will be smaller in absolute terms but the percentage of company is meaningful. They buy **whole platforms**, not just IP — they want the team and the deployments.

### 4.3 What to build to be acquirable by Ondas

1. **Mission payload for Optimus** — design wildfire-watch's edge inference stack so it can run on the Optimus dock + payload bay rather than only our 3D-printed frame. This is the most acquirable single deliverable.
2. **Public-safety reference customer that Ondas can resell.** Ondas's existing customer base is rail (their oldest), critical infrastructure, and Israeli MoD. They want public-safety wins for the Optimus narrative. A CAL FIRE pilot using wildfire-watch + Optimus is mutual gold.
3. **Counter-UAS bridge via Sentrycs.** Sentrycs is Ondas's counter-UAS unit. Wildfire-watch zones are already geofenced; we already have a manned-aircraft ADS-B receiver in the architecture. The CONOPS overlap is real.
4. **NDAA-compliant supply chain.** Optimus is already on Blue UAS. Anything Ondas acquires has to be Blue-list compatible. (See section 9.)

### 4.4 Expected price band (Ondas)

- **Stock-only acqui-hire:** $5–10M today, payable in ONDS shares.
- **Mission-payload + customer-pilot acquisition (12–18 months):** $20–50M, 60–100% stock.
- **Full platform acquisition (Ondas's American Robotics 2.0 — wildfire vertical):** $50–150M, 36 months out, conditional on multi-agency revenue. Ondas's acquisition history (American Robotics ~$70–100M) is the natural ceiling for this archetype.

## 5. Red Cat Holdings (NASDAQ: RCAT)

### 5.1 Strategic gap

Red Cat won the U.S. Army Short-Range Reconnaissance (SRR) program of record in November 2024 with the Black Widow / ARACHNID family, displacing Skydio. Initial Army acquisition target: 5,880 systems over five years ([The Robot Report](https://www.therobotreport.com/red-cat-wins-u-s-army-next-gen-drone-contract-over-skydio/)). The FANG FPV drone is Blue UAS-certified. Red Cat's revenue is small ($2.8M Q1-2025, growing fast on SRR).

The gap (and this is consequential): Red Cat is a **hardware company** with a known **software stack weakness**. They partner with Palladyne AI for autonomy ([Palladyne press](https://www.palladyneai.com/press-releases/palladyne-ai-and-red-cat-announce-successful-completion-of-cross-platform-collaborative-drone-flight/)) and Palantir VNav for navigation. They use Booz Allen for mission planning (WEB / ATAK UAS Tool). **They do not own the software stack on top of their drones.** Fuzzy Panda Research has publicly criticized them for hype and for FOIA evidence of Chinese parts ([Fuzzy Panda](https://fuzzypandaresearch.com/rcat-army-contract-smaller-than-claimed/)) — software / supply-chain credibility is a material concern for them.

Wildfire-watch is exactly the kind of **mission-software + multi-modal perception** layer Red Cat does not build internally.

### 5.2 Acquisition pattern

Red Cat's M&A history: Skypersonic (2022, ~$8M reported, **not** $32M as sometimes cited — the rumored $32M figure does not match the Red Cat 10-K disclosure), Fat Shark, Teal Drones (2021, reverse merger). They buy hardware + IP, paid mostly in stock. They are **not** a high-multiple buyer.

### 5.3 What to build to be acquirable by Red Cat

1. **Mission software for ARACHNID / Black Widow.** Wildfire-watch's edge perception stack is portable — the ML head can run on the same Jetson-class compute Red Cat ships. Demo a Black Widow flying a patrol with the wildfire-watch perception head.
2. **Public-safety wedge for civilian sales.** Red Cat is military-first. A wildfire-watch-branded civilian product line gives them Title-32-funded customers (state public safety).
3. **NDAA / Blue UAS clean lineage.** Red Cat is under press scrutiny for supply-chain. Any acquisition has to enhance, not weaken, that posture.

### 5.4 Expected price band (Red Cat)

- **Stock-only acqui-hire:** $3–8M today, payable in RCAT shares (volatile).
- **Software-stack acquisition (12–18 months):** $10–30M, mostly stock. Red Cat does not have the cash for larger.
- **Strategic acquisition (36 months, low probability):** $40–100M. They'd more plausibly be acquired *themselves* before this fires.

## 6. Kratos Defense (NASDAQ: KTOS)

### 6.1 Strategic gap

Kratos is a publicly-traded, ~$10B-ish-market-cap defense prime focused on tactical drones (XQ-58 Valkyrie, target drones), space, hypersonics, and microwave systems. The Valkyrie is now under a Marine Corps MUX TACAIR deal with Northrop Grumman as prime ([Breaking Defense](https://breakingdefense.com/2026/01/northrop-kratos-team-picked-for-marine-corps-drone-wingmen/)). Q3 2025 unmanned systems revenue up 35.8% organically. They have been called out as a **potential acquisition target** themselves by sector advisors ([ION Analytics](https://ionanalytics.com/insights/mergermarket/kratos-defense-pegged-as-potential-acquisition-target-sector-advisors-say/)).

The gap: Kratos has **large autonomous platforms** (Valkyrie), **target drones** (BQM-167 etc.), and **mission systems**. They do **not** have a small-form-factor autonomous patrol product. Their software autonomy is now being built by Northrop on top of Valkyrie, not in-house. They are not naturally a buyer of small-drone IP.

### 6.2 Why Kratos is the lowest-probability fit

Kratos is consolidation-focused in **larger** form factors. A wildfire-watch-class platform is below their attention threshold. Their relevant adjacency is **target drones** — and the relevant question is whether wildfire-watch's BVLOS, autonomous-patrol, low-cost-airframe IP transfers to **expendable target / decoy drones** for adversary-air training. That transfer is real but is a different product, and would require us to build it.

### 6.3 What to build to be acquirable by Kratos

1. **A tactical patrol variant** — a longer-endurance, fixed-wing or hybrid-VTOL airframe with the same edge perception stack but targeted at adversary-air training, range surveillance, or perimeter patrol. This is a **product expansion**, not a feature.
2. **A "loitering eyes" CONOPS** — wildfire-watch's edge fusion + low cost + autonomous operation IS the kind of capability that could feed a tactical decoy / target drone. Frame the IP that way in the SOFIC / AUSA conversations.

### 6.4 Expected price band (Kratos)

Treat Kratos as a **last-resort, optional second-tier buyer**. Realistic price band: $5–15M acqui-hire, only if we have the tactical variant. Probability: <15%.

## 7. Adjacent comparables

### Shield AI ($12.7B, March 2026 Series G — [press release](https://shield.ai/shield-ai-raises-240m-at-5-3b-valuation-to-scale-hivemind-enterprise-an-ai-powered-autonomy-developer-platform/))

Shield AI's Hivemind is the closest analog to what wildfire-watch's autonomy stack should aspire to. They acquired Sentient Vision Systems (Australia, ViDAR — wide-area motion imaging) in April 2024. **Implication:** the "autonomy software + niche perception IP" combination is a known acquirable pattern. Shield AI itself is too large to be a buyer; they are a comp.

### Skydio (~$2.5B private valuation, ~$180M 2024 revenue per Sacra)

Skydio's X10 / X10D are on Blue UAS. They have a fire-service product page and explicit thermal-camera positioning. Skydio lost the Army SRR to Red Cat. They could plausibly buy a wildfire-watch-class product to claw back the public-safety vertical they pivoted toward. Probability moderate. Likely price band: $20–60M.

### AeroVironment (NASDAQ: AVAV, post-BlueHalo)

May 2025 close of the $4.1B BlueHalo all-stock merger created an integrated "all-domain defense technology" company ([AeroVironment IR](https://www.avinc.com/resources/press-releases/view/aerovironment-and-bluehalo-complete-transaction-creating-a-global-defense-technology)). Switchblade is the loitering-munition flagship. Wildfire-watch fits as a Puma / Wasp public-safety adjacent product. Probability low-moderate.

### Saronic ($9.25B post-Series-D, March 2026)

Pure transfer comp: Saronic raised $1.75B at $9.25B post-money on minimal revenue ([CNBC](https://www.cnbc.com/2026/03/31/autonomous-boat-startup-saronic-raises-1point75-billion-.html)). They are a **swarm autonomy company that happens to operate boats**. The valuation thesis transfers directly: a swarm-autonomy company that happens to operate small drones, with a clear DoD-adjacent CONOPS, can support extreme multiples without revenue. They are not a buyer.

## 8. NDAA / Section 848 / Blue UAS architecture implications

### 8.1 The legal and procurement reality

- **Section 848 of the FY2020 NDAA** prohibits DoD procurement or operation of UAS made in or containing critical components from China, Russia, Iran, North Korea ([DIU policy](https://www.diu.mil/blue-uas-policy)). Critical components: flight controllers, radios, data-transmission devices, cameras, gimbals, ground control systems, operating software, data-storage units.
- **American Security Drone Act (FY2024 NDAA)** extended this **government-wide** as of December 22, 2025 — federal agencies cannot operate or use federal grant funds to buy non-compliant UAS.
- **Blue UAS Cleared List** is the DoD's vetted-and-approved roster, transitioned in 2025 from DIU to DCMA ([UAS Magazine](https://uasmagazine.com/articles/diu-transfers-blue-uas-cleared-list-to-dcma-to-accelerate-secure-drone-procurement)). Now 50+ platforms.
- **FCC exempted Blue UAS / domestic-end-product UAS from the Covered List** in January 2026 ([Holland & Knight](https://www.hklaw.com/en/insights/publications/2026/01/fcc-exempts-certain-drones-from-covered-list)) — meaningful unlock for radio-comms components on Blue UAS gear.

### 8.2 Architecture implications for wildfire-watch

The current docs (`hardware/bom.csv`, `firmware/`, `ml/fire_detection/`) reference Cube Orange+ (Australian-designed, made in Australia — likely OK), Pixhawk 6X (Holybro — needs check), Jetson Orin Nano Super (NVIDIA, US — fine), Sony IMX477 (Japanese — fine), FLIR Lepton 3.5 (US Teledyne — fine). **The exposure points are radios, ESCs, motors, and any default DJI-class accessory.** As of 2026:

1. **Replace any 5.8 GHz video TX of unknown origin with TBS Crossfire / TBS Tracer Express** (Czech) or Doodle Labs (US, Blue UAS).
2. **Motors and ESCs need provenance.** T-Motor (Chinese) is the dominant hobbyist supply — it must be substituted with Iris Dynamics, Brisson, or domestic suppliers for the Blue lineage.
3. **915 MHz LoRa / Meshtastic** — RAK and Heltec dominate; both have China-supply-chain exposure. Doodle Labs Helix or domestic alternative is the Blue-list-safe path.
4. **3D-printed frame** — material is fine; **filament supplier matters** for documentation. PrintedSolid (US) or MatterHackers source disclosure is sufficient.
5. **Airframe firmware** — ArduPilot is open-source, vendor-agnostic; PX4 is similarly fine. The risk is in **bundled flight-controller firmware** that ships with non-compliant defaults.

**The deliverable: a `BLUE-UAS-LINEAGE.md` doc by Q3 2026** that traces every bill-of-materials line item to its provenance and the Blue-list-substitutable alternative. This single document is worth a 1.5–2× multiple uplift at acquisition time. Anduril, Ondas, Red Cat, AeroVironment will all pay for the diligence work to be already done.

### 8.3 What NOT to build

- Do not build **for** Section 848 only as the moat. Blue UAS is now a 50+ vendor list. Compliance is a **necessary precondition**, not the moat.
- Do not source **anything** from DJI, Autel, or any Shenzhen-supply-chain hub. Even if a part is technically not on the Covered List, the **diligence overhead** during acquisition will eat the deal.

## 9. Outreach playbook

### 9.1 Who to email (ranked by acquirer)

**Anduril** — **Mission Autonomy / Lattice partnerships team.** Public path: `partners@anduril.com` (Lattice Sandbox program) plus the XPRIZE Wildfire shared-context channel. Personal path: anyone in the operator's network connected to Christian Brose (Chief Strategy Officer, ex-SASC), Brian Schimpf (CEO), or directly to Palmer Luckey (he reads Twitter/X DMs and personally responds; mentioning XPRIZE Wildfire is a credible opener).

**Palantir** — **PVM (Palantir Value Multiplier consultancy)** at the AIP Bootcamp for Wildfire is the lowest-friction entry. Direct: Akash Jain (President, Government), Shyam Sankar (CTO), or AIP-level PMs through Palantir's public partner program. PG&E's wildfire team is a reference — being on a PG&E Foundry-instance pilot is the ticket in.

**Ondas** — **Joe Popolo (CFO) or Stewart Kantor (CEO)** at OAS. Investor-relations emails are responsive given their stock-promotion mode. The fastest path is via American Robotics's Optimus payload-partner program.

**Red Cat** — **Jeff Thompson (CEO)** is publicly accessible (interviews, podcasts). They have an active partner / supplier intake form.

**Kratos** — **Steve Fendley (President of Unmanned Systems Division)** is the right contact, but the path through SOFIC, Modern Day Marine, or AUSA is more productive than cold email.

### 9.2 Conferences to be at (next 12 months)

- **AUSA Annual** (October 2026, DC) — Red Cat, Anduril, AeroVironment all present; small-drone software is a track.
- **AFCEA WEST** (February 2026 — already passed; February 2027) — Lattice + USNI; the right room for Anduril BD.
- **Modern Day Marine** (April 2026) — Kratos, Anduril Marine, the right room for tactical-variant pitches.
- **SOFIC** (May 2026) — special-operations user crowd; fastest feedback on the "expendable patrol" CONOPS.
- **Commercial UAV Expo** (September 2026, Las Vegas) — public-safety + civilian focus, the natural venue for the wildfire wedge.
- **XPRIZE Wildfire finals** (announced in Australia, 2026) — most important. Be present even if not competing.

### 9.3 Content that gets noticed

- A **published, public dataset** — wildfire-watch's first 100 hours of patrol producing labeled multi-modal frames. This is the single highest-leverage content asset; defense-tech corp-dev reads HuggingFace and Kaggle.
- A **technical paper** (arXiv) on multimodal RGB+LWIR+acoustic+behavioral fusion for early-stage smoke detection, with a delta-vs-ALERTCalifornia benchmark. arXiv hits twitter, twitter hits Palmer Luckey.
- A **fire-department case study** — even one MOU + one season of patrol + one measured detection-time delta. The single most credible artifact.
- **Open-source frame + closed-source perception stack** — apparent paradox, valuable signal. Apache-2.0 the airframe and ArduPilot config (as already chosen). Keep the ML weights and the fusion algorithm proprietary.

## 10. Valuation comps table

| Archetype | Recent transaction | Multiple |
|---|---|---|
| Pure DoD prime (revenue-mature) | LMT/RTX trading | 1.5–2.0× revenue |
| Defense tech (private, scaling) | Anduril ~$60B / ~$2B 2025 rev (TSG, Sacra estimates) | 25–30× trailing rev |
| Defense tech (private, pre-revenue swarm) | Saronic $9.25B post-Series-D | not measurable; pure narrative |
| Defense tech (public, growth) | Ondas $4.65B / $50.7M 2025 rev | ~90× trailing, ~12× 2026 guide |
| Public-safety SaaS | Axon, Mark43, Motorola | 5–12× revenue |
| Vertical-AI startup (private) | qubit.capital reports 10–50× ARR for AI startups generally | 10–50× ARR |
| Sub-platform IP+team acqui-hire (defense) | Sentient Vision (undisclosed) | $0 revenue → ~team-size multiple ($1–3M / engineer) |
| Sub-platform with one Army RFP win | Adranos ~$50M, Numerica undisclosed | high single-digit / low double-digit M$ per program-of-record path |

**The right multiple for a pre-revenue civilian wildfire platform with defense-adjacent IP** is, today: **engineer-count × $1–3M** for an acqui-hire. Once there is a paid CAL FIRE MOU + one season of measurable detection-time-delta + a Blue-list-safe BOM: **8–15× plausible 18-month-forward revenue** ($25M revenue plausible → $200–375M). That's the realistic asymptote.

## 11. Build roadmap (4 quarters)

### Q3 2026 — proof of life

- First flight on a printed frame with the Cube Orange+ + Jetson Orin Nano Super stack.
- First end-to-end signal: drone → ground station → Sapphire `signal_logger:18081` → Telegram alert. (Sapphire side already works; the work is the drone half.)
- First MegaDetector + YOLOv8-fire dual-head running on the Jetson at flight-relevant FPS.
- Open-sourced frame + ArduPilot config. Closed-sourced perception stack. Apache-2.0 LICENSE already chosen ([wildfire-watch repo](https://github.com/arigatoexpress/wildfire-watch)).

### Q4 2026 — first MOU

- Signed MOU with **one** California county fire department or land manager (Marin, Sonoma, San Bernardino, or a power-line corridor with PG&E).
- 50+ patrol hours over fire season tail.
- First labeled multi-modal frame dataset published (~5,000 frames).
- BLUE-UAS-LINEAGE.md drafted; non-compliant components substituted in BOM v2.
- arXiv paper drafted on multimodal fusion benchmark vs. ALERTCalifornia.

### Q1 2027 — measured delta + first paid pilot

- Dataset paper on arXiv. HuggingFace dataset card.
- 2nd MOU + 1st **paid** pilot ($25–100k ARR).
- Lattice Sandbox integration POC with Anduril (publicly demo-able).
- AIP Bootcamp wildfire demo (Palantir / PVM).
- BOM v2 fully Blue-UAS-component-substitutable.

### Q2 2027 — onboarding to acquirer-evaluation territory

- 3rd MOU + 2nd paid pilot → ~$250k ARR.
- DCMA Blue UAS application submitted (timeline ~12 months from submit to listing).
- 4-engineer team with a public technical reputation (papers, conference talks, OSS contributions).
- Concurrent Series A conversation with at least 2 of: a16z American Dynamism, Founders Fund, Lux, USIT — same investors who fund the comparables. Use the round as a price-anchor for the strategic conversation.

This roadmap puts the company in position for a **$25–75M strategic acquisition** by mid-2027 if a single SRR-class RFP lands or a single buyer has a strategic emergency (XPRIZE Wildfire winner, e.g.). The **$200–400M outcome is a 36-month outcome** that requires either a real revenue ramp or a category-defining acquisition by Anduril.

---

## Source bibliography (most-cited first)

1. [Anduril — Korean Air partnership announcement (2026)](https://www.anduril.com/news/korean-air-and-anduril-explore-solutions-to-global-wildfire-response)
2. [XPRIZE Wildfire — finalists announcement (2025)](https://www.xprize.org/news/meet-the-future-of-autonomous-wildfire-response-xprize-wildfire-announces-finalist-teams-advancing-in-11m-competition)
3. [Anduril — Lattice as dual-use platform for public safety](https://www.anduril.com/news/anduril-s-lattice-a-trusted-dual-use-commercial-and-military-platform-for-public-safety-security)
4. [Anduril — Numerica radar / C2 acquisition (Breaking Defense, 2025-01)](https://breakingdefense.com/2025/01/anduril-acquires-numericas-radar-and-c2-business/)
5. [Anduril — Klas acquisition (2025-07)](https://www.anduril.com/news/anduril-to-acquire-klas-to-build-the-future-of-tactical-compute-and-communications)
6. [Palantir — PG&E PSPS impact](https://www.palantir.com/impact/pacific-gas-and-electric/)
7. [Palantir — Skykit](https://www.palantir.com/offerings/skykit/)
8. [Ondas — Optimus Blue UAS approval (2026-01)](https://ir.ondas.com/press-releases/detail/275/ondas-american-robotics-optimus-drone-approved-for-rapid)
9. [Ondas — 2026 revenue target $375M (Stocktitan)](https://www.stocktitan.net/news/ONDS/ondas-hosts-oas-investor-day-ups-2026-revenue-target-to-170-180-18lq1ollcueo.html)
10. [Ondas — Airobotics close ($15.2M, RCR Wireless)](https://www.rcrwireless.com/20230124/internet-of-things/ondas-completes-15-2m-acquisition-of-israeli-drone-company-airobotics)
11. [Red Cat — Army SRR production selection](https://ir.redcatholdings.com/news-events/press-releases/detail/160/red-cat-announces-production-selection-for-u-s-army-short-range-reconnaissance-program)
12. [Red Cat — Palladyne autonomous flight test (2025-05)](https://www.palladyneai.com/press-releases/palladyne-ai-and-red-cat-announce-successful-completion-of-cross-platform-collaborative-drone-flight/)
13. [Fuzzy Panda Research — Red Cat critique](https://fuzzypandaresearch.com/rcat-army-contract-smaller-than-claimed/)
14. [Kratos — Marine Corps MUX / Northrop teaming (Breaking Defense, 2026-01)](https://breakingdefense.com/2026/01/northrop-kratos-team-picked-for-marine-corps-drone-wingmen/)
15. [ION Analytics — Kratos as acquisition target](https://ionanalytics.com/insights/mergermarket/kratos-defense-pegged-as-potential-acquisition-target-sector-advisors-say/)
16. [Shield AI — Hivemind Series F (2025-03)](https://shield.ai/shield-ai-raises-240m-at-5-3b-valuation-to-scale-hivemind-enterprise-an-ai-powered-autonomy-developer-platform/)
17. [Shield AI — Sentient Vision acquisition](https://www.businessnewsaustralia.com/articles/sentient-vision-systems-acquired-by-us-defence-tech-giant-shield-ai.html)
18. [Saronic Series C — $4B (Pulse 2.0)](https://pulse2.com/saronic-600-million-series-c-raised-at-4-billion-for-autonomous-surface-vessels/)
19. [Saronic Series D — $9.25B (CNBC, 2026-03)](https://www.cnbc.com/2026/03/31/autonomous-boat-startup-saronic-raises-1point75-billion-.html)
20. [AeroVironment + BlueHalo close ($4.1B, 2025-05)](https://www.avinc.com/resources/press-releases/view/aerovironment-and-bluehalo-complete-transaction-creating-a-global-defense-technology)
21. [Skydio X10 fire-service product page](https://www.skydio.com/solutions/dfr/fire-service)
22. [Skydio U.S. Army $52M X10D order (2026-03)](https://www.skydio.com/blog/u-s-army-usd52-million-order-skydio-x10d)
23. [DCMA Blue UAS Cleared List transition (UAS Magazine)](https://uasmagazine.com/articles/diu-transfers-blue-uas-cleared-list-to-dcma-to-accelerate-secure-drone-procurement)
24. [DIU — Blue UAS policy + Section 848 guidance](https://www.diu.mil/blue-uas-policy)
25. [Holland & Knight — FCC exemption of Blue UAS (2026-01)](https://www.hklaw.com/en/insights/publications/2026/01/fcc-exempts-certain-drones-from-covered-list)
26. [The Drone Girl — 2026 Blue UAS Cleared List explainer](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/)
27. [PVM — AIP Bootcamp for Wildfire Management](https://blog.pvmit.com/pvm-blog/aip-bootcamp-wildfire)
28. [Defense News — defense-tech 2025 best year ever (2026-01)](https://www.defensenews.com/industry/2026/01/20/defense-tech-startups-had-their-best-funding-year-ever-in-2025/)
29. [Sacra — Anduril revenue / valuation comps](https://sacra.com/c/anduril/)
30. [TSG Invest — Anduril at $60B](https://tsginvest.com/anduril-industries/)
31. [ALERTCalifornia](https://alertcalifornia.org/)
