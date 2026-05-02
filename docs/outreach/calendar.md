# wildfire-watch outreach + content calendar

Two-week sprint plus quarterly arc. Each entry: date, action, channel, KPI delta if any. KPI deltas reference axes in the valuation engine (`valuation/engine.py`); see `docs/strategy/SYNTHESIS-2026-05-02.md` for the dollar-band math.

Today is **2026-05-01 (Friday)**. The two-week sprint starts Monday 2026-05-04.

## Week 1 (2026-05-04 → 2026-05-10)

| Date | Day | Action | Channel | KPI delta |
|---|---|---|---|---|
| 2026-05-04 | Mon | **Send Email 01 (CBFPD).** Highest-leverage email in the kit. Operator drafts final, sends from personal email. Subject: "Crested Butte resident, drone test polygon over the Slate River drainage — 30 minutes at the station?" | email | First-touch with Tier-1 partner. If accepted, +$3M to mid-band on signed LOA (downstream). |
| 2026-05-04 | Mon | **Push wildfire-watch to GitHub public.** `git remote add origin git@github.com:arigatoexpress/wildfire-watch.git && git push -u origin main`. Repo URL becomes citeable in every email and post. | git | `repo_public=True` → legibility axis +0.10. |
| 2026-05-04 | Mon | **Apply for Foundry Developer Tier.** Free, capacity-capped. Application at palantir.com partner program. | web | Pre-condition for ontology-richness axis. On approval, Palantir score 0.407 → ~0.55 (per SYNTHESIS). |
| 2026-05-05 | Tue | **Order Part 107 study guide** (King Schools or Pilot Institute, ~$175). Block 30-minute morning study slots through 2026-06-15. | commerce | Pre-condition for first flight; +$125k asset-floor on cert; P(exit) +1%. |
| 2026-05-05 | Tue | **Apply for LAANC pre-auth at KGUC** via Aloft / AirMap / Kittyhawk. Free. | web | Pre-condition for any flight within 5 nm of Gunnison airport. |
| 2026-05-06 | Wed | **Publish LinkedIn Post 01 (announcement).** 500 words, formal voice. Open the project to public scrutiny. | LinkedIn | `public_announcements=1`, makes the project legible to inbound recruiters / partners. |
| 2026-05-07 | Thu | **(passive) follow up internally on CBFPD email** if no reply by EOD. Do NOT re-email yet — the polite cadence is one re-touch at the 10-day mark. | n/a | n/a |
| 2026-05-08 | Fri | **Publish X Thread 01 (demo).** 8 tweets, threaded, with the simulator screenshot. | X | Visibility in defense-tech Twitter. Palmer Luckey reads X DMs — referenced in `ACQUIRER_FIT-2026-05-02.md` Section 9.1. |
| 2026-05-09 | Sat | **Run 10+ scenario simulations.** All 4 single-drone + 4 swarm scenarios across the gunnison_slate_river_1km2.yaml and the East River and Cement Creek polygons (file the missing YAMLs first if needed). | local | `simulator_runs_total >= 10` → consensus_swarm axis +; Anduril + Kratos rank scores up. |
| 2026-05-10 | Sun | **Operator reflection day.** No new outreach. Re-read AOR.md, re-read this calendar, adjust Week 2 based on Week 1 responses. | n/a | n/a |

## Week 2 (2026-05-11 → 2026-05-17)

| Date | Day | Action | Channel | KPI delta |
|---|---|---|---|---|
| 2026-05-11 | Mon | **Send Email 02 (GCFPD).** Five-minute heads-up to Gunnison County FPD. Subject: "Gunnison County drone fire-watch project — research introduction, nothing in the air yet". | email | Tier-1 awareness; lateral coverage on the broader AOR. |
| 2026-05-11 | Mon | **Send Email 03 (GMUG District Ranger).** Coordination request for any flight over USFS land. Subject: "Coordination request — civilian wildfire-watch UAS research over GMUG land near Crested Butte". | email | Pre-condition for any GMUG flight; relationship-build with USFS. |
| 2026-05-13 | Wed | **Publish LinkedIn Post 02 (Phase 0 demo).** 400 words, the 60-second walkthrough. Embed the screenshot of the browser viewer. | LinkedIn | Inbound makers / engineers. |
| 2026-05-14 | Thu | **(if CBFPD replied positively in Week 1) book the in-person 30-minute station visit** for the second or third week of June. Operator-driven; no email template needed. | calendar | Materializes the LOA path. |
| 2026-05-15 | Fri | **Publish blog post 01 (Phase 0 walkthrough).** 1500 words, Substack or Medium. Cross-link from LinkedIn 01 and 02. | blog | Long-form citable artifact for journalists / VC due diligence. |
| 2026-05-15 | Fri | **Send Email 05 (Palantir AIP Bootcamp)** if Foundry Developer Tier was accepted. If not, hold until acceptance lands. Subject: "Drone-mesh ontology source for Foundry / AIP wildfire — Foundry Developer Tier request". | email | Tier-2 partner outreach. Palantir score axis. |
| 2026-05-16 | Sat | **Send Email 06 (Ondas Optimus payload).** Payload-partner intake. Subject: "Mission payload candidate for Optimus — wildfire detection, NDAA-clean, Blue UAS-aligned by design". | email | Tier-2 partner outreach. `stated_buy_intent` axis for Ondas. |
| 2026-05-17 | Sun | **(if Part 107 + LAANC + CBFPD LOA all aligned)** **first Phase 0 manual flight** over Slate River drainage with the Mavic Mini. Honest probability this hits in Week 2: low. More likely Week 3 or 4. | field | First flight unlocks `flight_hours > 0` axis — single biggest valuation step in the engine. |

## Quarterly arc (2026-05 → 2026-07)

### May 2026 (the rest of the month after the 2-week sprint)

- **Week 3 (2026-05-18 → 2026-05-24):** Publish LinkedIn Post 05 (open-source maker call) on Tue 2026-05-19. If first Phase 0 flight is on the books, do it this week. Reply / triage on the 4 Tier-1 emails; expect ~1–2 actionable replies.
- **Week 4 (2026-05-25 → 2026-05-31):** **Take the Part 107 test** at the local CATS testing center (closest is in Grand Junction, ~3 hours from Gunnison; alternatives in Denver / Colorado Springs). $175. KPI delta: Part 107 axis flips True; +$125k asset-floor; unlocks BVLOS waiver application path; P(exit) +1%.

### June 2026

- **Week 1:** First operational Phase 0 flight over Slate River drainage (gated on Part 107 + LAANC + CBFPD LOA). Goal: 5 patrol hours. KPI delta: `flight_hours_total > 0` flips True; per-hour +$30k asset-floor.
- **Week 2 (2026-06-08):** Publish LinkedIn Post 03 (swarm consensus, 600 words). Time it for a defense-tech audience — coordinate with whatever conference cycle is mid-month. KPI delta: technical-credibility axis.
- **Week 3 (2026-06-15):** Send Email 09 (DFPC research collab) — by now there is a flight log to attach. KPI delta: state-level awareness, research-collab pathway.
- **Week 4 (2026-06-22):** Publish LinkedIn Post 04 (Blue UAS lineage, 500 words). Coordinate with whatever Blue UAS / AUVSI cycle is current. KPI delta: defense-tech credibility; surfaces `BLUE-UAS-LINEAGE.md` to acquirer corp-dev.
- **End of June ship target:** v0.1.0 with the first FASDD-fine-tuned YOLOv8 model card. KPI delta: `trained_ml_model=True`; ML-credibility axis.

### July 2026

- **Week 1:** Send Email 04 (Anduril Lattice Sandbox). At this point we have flight hours, an LOA, and a v0.1.0 model — the credibility floor is high enough to send. KPI delta: `stated_buy_intent` axis updates if Anduril responds. (The R-1 research at `docs/strategy/ACQUIRER_FIT-2026-05-02.md` is explicit that Anduril cold outreach is premature without flight hours and the LOA.)
- **Week 2:** Send Email 07 (Red Cat). Same logic — paid evaluation pitch lands once we have artifacts to point at. KPI delta: Red Cat partner-pipeline axis.
- **Week 3:** Reach out to Western State Colorado University's research office for academic collaboration. (No template in this kit yet — write one.) KPI delta: academic-credibility axis; potential FASDD/FLAME-2 dataset collaboration.
- **Week 4:** Publish X Thread 02 — wait, that one is timed to the Marshall Fire anniversary on December 30. Hold for end of year.

### Held for later in 2026 / early 2027

- **Email 08 (Kratos):** longshot, send only if a SOFIC / AUSA / Modern Day Marine intro materializes. Not on the calendar — opportunistic.
- **X Thread 02 (Marshall Fire anniversary):** target 2026-12-30. Five-year anniversary. Pre-load on 2026-12-28 to schedule.

## Summary KPI deltas the calendar moves

| Axis (per `valuation/engine.py`) | Today | After 2-week sprint | After quarter |
|---|---|---|---|
| `repo_public` | False | True | True |
| `public_announcements` | 0 | 2 | ~6–8 |
| `simulator_runs_total` | 5 | 15+ | 50+ |
| `partner_outreach_count` | 0 | 4 | 7+ |
| `signed_loa_count` | 0 | 0 (in flight) | 1 (CBFPD, gated) |
| `part_107_certified` | False | False | True (end of May) |
| `laanc_pre_auth` | False | True | True |
| `flight_hours_total` | 0 | 0 | 5–10 (best case) |
| `trained_ml_model` | False | False | True (end of June) |
| `foundry_dev_tier_accepted` | False | TBD | True (target) |
| Mid-band consensus valuation | $1.38M | $1.5M | $4–6M (with one LOA + flight + model card) |

## What this calendar deliberately does not include

- **No real Anduril or Red Cat outreach in the 2-week sprint.** Both are gated on the operator having flight hours and an LOA to point at. Premature.
- **No press / journalist outreach.** Separate kit; write later.
- **No fundraise.** Separate process; write a deck and a data room first.
- **No Discord / Matrix invite link in LinkedIn 05.** The community-tooling stand-up is itself a Week 2/3 task.
- **No tactical-variant CONOPS for Kratos.** That is a 2027 thing if at all.

The most important thing on this calendar is the very first row: **2026-05-04 Mon, send Email 01 (CBFPD).** Same cost as a stamp, plus-$3M to mid-band on signed LOA.
