# Positioning Brief — wildfire-watch

**Date:** 2026-05-02
**Audience:** Outreach (Anduril, Palantir, Ondas, Red Cat, Kratos), board, lead investor
**Pair-with:** [`ACQUIRER_FIT-2026-05-02.md`](./ACQUIRER_FIT-2026-05-02.md)

---

## Headline thesis

**wildfire-watch is the small, autonomous, NDAA-clean patrol layer that closes the 0–30 minute wildfire-detection gap that satellites, mountaintop cameras, and 911 calls miss — built dual-use from day one, with edge multimodal fusion (RGB + LWIR + acoustic + behavioral wildlife) that the same airframe can take to public safety, infrastructure protection, or tactical perimeter monitoring.**

## The wedge: civilian wildfire is the entry. Why?

- **The market is unambiguous.** California alone burns through tens of billions of dollars per fire season; the first 30 minutes determine whether an ignition stays under an acre or becomes catastrophic. Existing detection — ALERTCalifornia (1,240 cameras, fixed viewpoints), GOES/VIIRS satellites (~375 m / few-hour revisit), 911 calls (slow) — has documented blind-spots in the WUI.
- **There is no NDAA risk in civilian-first.** A federal-funds restriction (Section 848 / American Security Drone Act) puts a wide moat around any product that is Blue-UAS-aligned from day one. Building civilian-first does not foreclose the defense path; it strengthens it.
- **The political-economic optics are clean.** A dual-use platform whose first proof point is "we found a fire in 8 minutes that ALERTCalifornia couldn't see for 23" is the highest-trust origin story for crossover into public safety, infrastructure protection, and (eventually) DoD adjacent.
- **Anduril, Palantir, Ondas, Red Cat all have a wildfire-shaped hole in their product line as of 2026.** XPRIZE Wildfire (closing 2026) and the April 2026 Anduril–Korean Air partnership are direct evidence the category is being formed *now*.

## The moat

1. **Multimodal edge fusion** — RGB (12 MP IMX477) + LWIR (FLIR Lepton 3.5) + I2S MEMS acoustic (BirdNET) + behavioral (MegaDetector v6 — animal-stampede-as-fire-signal) — fused on a $249 Jetson Orin Nano Super at flight-relevant FPS. **Detection-only is now a commodity (ALERTCalifornia, satellite). Multimodal early-warning fusion is not.**
2. **Open-source frame, closed-source perception.** Apache-2.0 airframe + ArduPilot config invites community ground-truth contributions. The fusion algorithm and ML weights are proprietary and revenue-extracting.
3. **NDAA-clean lineage from day one.** BOM is engineered to be Blue-UAS-substitutable; provenance documented per component; the diligence work is pre-done for any acquirer.
4. **Sapphire intelligence-stack integration.** Drone telemetry → existing `signal_logger:18081` → existing dashboard → existing Telegram fan-out (hermes-agent) → existing TAK / CoT publish path. We are not rebuilding C2; we are bolting onto an operator-tested mesh.
5. **Public-good ecology dataset as byproduct.** Every patrol generates wildlife / fuel-load / acoustic data that we publish open. This funds grants, generates academic citations, and gives the company an unattackable civilian narrative — which is also exactly the profile a defense buyer wants when crossing into public-safety markets.

## Why each acquirer should care

**Anduril** — wildfire-watch is the cheap, mass-producible, fully-disclosed-supply-chain civilian patrol-density layer that funnels signals into Lattice for the more expensive Fury / Ghost-X / Sentry tower layer to react to. The Korean Air partnership announced April 2026 explicitly defines the integration architecture; we slot in as a tile rather than competing with one. Palmer Luckey is publicly competing in XPRIZE Wildfire with Sentry + Ghost-X + Lattice — wildfire-watch is the missing low-cost layer he doesn't want to engineer himself but needs to integrate to win.

**Palantir** — wildfire-watch is the drone-mesh ontology for Foundry / AIP. PG&E uses Foundry for PSPS planning; the next logical extension is a domain-specific drone-mesh source feeding wildfire ignition signals into the existing Foundry instance. We are not competitive with Foundry; we are an upstream ontology source AIP can reason against. Most plausibly a strategic-investment + revenue-share deal, not an outright acquisition — but a high-leverage one.

**Ondas** — wildfire-watch is either (a) the wildfire-detection mission payload + edge perception stack that runs on Optimus, or (b) the cheaper-frame complement that lets Optimus address the patrol-density market segment it's too expensive to own alone. Optimus is now Blue-UAS-listed (January 2026) and Ondas has aggressive 2026 revenue targets ($375M); a public-safety wildfire vertical is the most natural win-of-the-year for them. Stock-denominated acquirer; smallest balance sheet of the targets.

**Red Cat** — wildfire-watch is the mission software / multi-modal perception layer Black Widow / ARACHNID does not own. Red Cat is partnered with Palladyne for autonomy and Booz Allen for mission planning, but they don't own the perception stack. They are also under press scrutiny for supply-chain. A clean-lineage software-stack acquisition is exactly what their narrative needs.

**Kratos** — lower-probability fit. The transferable adjacency is **expendable target / decoy / patrol** — wildfire-watch's edge fusion + low cost + autonomous operation is the kind of capability that, in a tactical airframe, becomes a "loitering eyes" decoy for adversary-air training. Worth a SOFIC / AUSA conversation; not worth re-engineering for.

## Proof points (today, 2026-05-02)

- Vision, system architecture, BOM, ML stack, FAA compliance plan, fire-department partnership template, simulation ladder, and 4-quarter roadmap — published in `docs/`.
- Sapphire intelligence-stack integration design (signal schema + adapter to `signal_logger:18081`) — already wired through an operator-tested 4-tier compute mesh.
- Apache-2.0 license with explicit patent grant, chosen specifically to invite contributions while protecting against patent disputes from incumbent drone manufacturers.
- Operator profile: runs Sapphire (5,275+ tests, 49 plugin tools, 4-tier compute mesh), TradingView orchestrator, hermes-agent Telegram, OpenBB intel pipeline. Demonstrated capacity to ship and operate complex distributed systems.
- **Honest gap:** zero flight hours. No printed parts. No fire-department MOU. No signed customer.

## Proof points (12 months out, target 2027-05-02)

- 100+ patrol hours flown over a fire season (Q3-2026 onwards).
- Signed MOU with **at least one** California county fire department or land manager (Marin, Sonoma, San Bernardino candidates) plus PG&E or another IOU.
- Published open multi-modal dataset (~5,000 labeled frames, RGB + LWIR + acoustic + GPS-tagged behavioral) on HuggingFace.
- arXiv paper on multimodal fusion benchmark vs. ALERTCalifornia detection-time delta.
- Lattice Sandbox integration POC (Anduril) and AIP Bootcamp wildfire demo (Palantir/PVM).
- BOM v2 fully Blue-UAS-component-substitutable; `BLUE-UAS-LINEAGE.md` published.
- DCMA Blue UAS application submitted.
- 4-engineer team with public technical reputation (papers, conferences, OSS).

## Ask (per acquirer)

- **Anduril** — Lattice Sandbox access; partner status; co-presence at the next XPRIZE Wildfire demonstration; 30-minute meeting with Palmer Luckey or the Mission Autonomy product lead.
- **Palantir / PVM** — invitation to the next AIP Bootcamp for Wildfire as a presenting integration partner; sandbox access to a PG&E or CAL FIRE Foundry instance for an ontology integration POC.
- **Ondas** — Optimus payload-bay integration spec; reference customer co-pitch (American Robotics + wildfire-watch + a CAL FIRE pilot); discussion of a stock-funded mission-payload acquisition pathway in 2027.
- **Red Cat** — Black Widow / ARACHNID port of the wildfire-watch perception head; co-publish a public-safety reference; explore a Palladyne-style software-collaboration agreement that ladders to acquisition.
- **Kratos** — SOFIC / AUSA meeting; brief on the tactical-variant CONOPS (fixed-wing or hybrid-VTOL, longer-endurance, range-surveillance / decoy-eyes use cases). No near-term ask beyond mutual education.

## Honest valuation framing (used in every conversation)

- **If acquired today, $3–8M acqui-hire is the honest range.** We have IP, a thesis, and a credible founder, but no flight hours and no customer.
- **At 12 months with the milestones above: $25–75M strategic acquisition is realistic** — particularly to Anduril, Ondas, or Red Cat.
- **At 36 months with multi-agency revenue + Blue UAS listing: $150–400M** — comparable to Adranos ($50M), Numerica (undisclosed but reportedly low-9-figures), Blue Force Technologies (~$100M).
- **Multiple environment is favorable today.** Defense-tech 2025 deal value was $49.1B (almost 2× 2024); median late-stage multiples beyond 20× forward revenue. The window is open. It is unlikely to be open the same way in 2028.

The strategy is to **earn the right to a $25–75M conversation by mid-2027** while keeping the optionality alive for the $150–400M outcome by late-2028. Civilian-first is not a hedge against the defense outcome — civilian-first **is** the highest-trust path to the defense outcome.
