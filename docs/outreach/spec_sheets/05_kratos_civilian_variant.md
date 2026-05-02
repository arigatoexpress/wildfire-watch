# wildfire-watch as the proof for a Kratos civilian product line

**Date:** 2026-05-02
**For:** Kratos Defense — Unmanned Systems Division strategy
**Pair-with email:** `docs/outreach/emails/08_kratos_civilian_variant.md`
**Repo:** https://github.com/arigatoexpress/wildfire-watch (Apache-2.0)

---

## Cover line

This is a long-shot framing document, not a near-term pitch.
wildfire-watch is the working proof that the autonomous-patrol +
multimodal-perception stack underneath the XQ-58 / target-drone product
space transfers cleanly to a civilian wedge — and a possible argument for
opening a Kratos civilian / public-safety product line on the same IP base
Kratos already builds for tactical adversary-air and target drones.

## Their platform / our integration

We **do not** propose to integrate with the XQ-58 Valkyrie, the BQM-167
target drone, or any current Kratos Unmanned Systems Division airframe.
The form factors and CONOPS are wrong for a wildfire patrol-density
mission.

What we propose is a strategy conversation about a **hypothetical
civilian product line** that uses wildfire-watch as the existence proof:

1. **The autonomy + perception IP transfers across mission classes.** The
   wildfire-watch stack — multimodal edge fusion (RGB + LWIR + acoustic +
   behavioral wildlife), k-of-N swarm consensus over a lossy mesh,
   GNSS-denied vision-nav (VO + TRN + IMU + GPS-spoof discriminator),
   TAK / CoT interop — sits in a product layer above the airframe. It
   runs on a hobbyist Holybro X500 V2 today; it could run on a
   Kratos-engineered hybrid-VTOL or fixed-wing patrol airframe with no
   architectural changes.
2. **The civilian wedge earns dual-use trust.** The Korean Air–Anduril
   wildfire partnership announced in April 2026 and the XPRIZE Wildfire
   competition are public proof that the dual-use defense-tech path goes
   *through* a civilian wedge, not around it. Anduril, Palantir, and Ondas
   are all on the field. Kratos is not — and the lowest-friction way onto
   the field is a civilian product line built on transferable IP.
3. **The Marine MUX TACAIR contract (January 2026) puts Kratos in
   collaborative-combat-aircraft territory** with Northrop as prime —
   meaning the autonomy software is being built by the prime, not in-
   house. A civilian product line is the venue where Kratos could rebuild
   in-house autonomy + perception capability without competing with the
   Northrop Marine deal.
   ([Northrop / Kratos MUX TACAIR, Breaking Defense, Jan 2026](https://breakingdefense.com/2026/01/northrop-kratos-team-picked-for-marine-corps-drone-wingmen/))

We do **not** propose to compete with the XQ-58 program or to redirect
Kratos's existing R&D. We propose that the IP we are building today is
worth a 30-minute strategy conversation about whether a civilian product
line is a coherent expansion.

## What we deliver

A working civilian-wildfire reference platform that demonstrates each
piece of the underlying autonomy + perception IP independently:

- **Multimodal edge fusion** — `ml/fire_detection/infer.py`. Fusion gate
  combines RGB classifier, thermal delta, persistence count, geofence
  check, and wind consistency. v0.0.1 is a colour-heuristic placeholder;
  v0.1.0 is a YOLOv8n trained on FASDD → FLAME-2 (model card published).
  Generalizes beyond fire/smoke — same gate architecture works for any
  multimodal-corroboration mission (vehicle thermal + acoustic, anomaly +
  persistence, etc.).
- **k-of-N swarm consensus** — `sim/swarm/`. Each drone's own emit counts
  toward its own tally; peer signals only count after a lossy-comms model
  delivers them. Reference run: 3 drones, 1 km², k=2, mesh `loss_rate=0.0`
  → CONFIRMED smoke at risk_score 97.33; with `loss_rate=1.0` no
  consensus fires. The "strictest type wins" rule and the action
  escalation ladder (`notify_operator → loiter_and_capture → notify_fire_dept`)
  are the parts that generalize cleanly to a tactical CONOPS.
- **GNSS-denied vision-nav** — `sim/perception/`. VO + TRN + IMU +
  complementary fusion + GPS-spoof discriminator. 60-second outage at
  80 m AGL: 1.39 m mean / 2.15 m max position error. The Ukraine drone
  playbook (Bavovna AI, KrattWorks Ghost Dragon, OSCAR) is the public
  evidence base; our reference cites it explicitly.
  [`docs/intel/ukraine-drone-playbook-2026-05-01.md`,
  `sim/perception/README.md`].
- **TAK / Cursor-on-Target interop** — `sapphire_integration/tak/`.
  8 type-code mappings, MIL-STD-2525-derived, federated through ATAK /
  WinTAK / iTAK / FreeTAKServer. The same interop primitive a tactical
  variant would need.
- **Blue UAS lineage** — `BLUE-UAS-LINEAGE.md`. Phase-1 BOM substitution
  table; civilian-product line built on Cleared / Framework parts from
  day one. NDAA / Sec. 848 / Sec. 1822 diligence pre-done.

## Technical interface

There is no Kratos surface to integrate with today. The technical
deliverable from this conversation, if it leads anywhere, is a **paper
brief** on what a Kratos-civilian product line would look like:

| Question | Status |
|---|---|
| Airframe class | TBD — fixed-wing or hybrid-VTOL, longer endurance than Mavic class, smaller than Valkyrie. Possibly a derivative of an existing Kratos target-drone cell. |
| Onboard compute | Jetson-class FP16 inference reference; same as wildfire-watch Phase 1. |
| Mission profile | Public-safety patrol density (wildfire, search-and-rescue, perimeter monitoring of critical infrastructure). |
| Software stack | Port wildfire-watch's perception + consensus + TAK emitter; layer on top of whatever flight autonomy Kratos picks. |
| Procurement vehicle | DHS, FEMA, USDA Forest Service, state EM agencies — all federal-civilian, all subject to FAR 52.240-1 (Sec. 1822) and therefore Blue UAS-aligned. |
| Adjacent transfer | Same IP runs in a tactical adversary-air or "loitering eyes" decoy variant; civilian wedge is the dual-use entry, not the endpoint. |

The honest position: **none of this is a product spec yet.** It is a
hypothesis that would need to be tested against Kratos's actual
strategy / portfolio.

## Proof points (today)

- 240+ tests passing in under 7 seconds. `python3 -m pytest -q`.
- Swarm consensus reference run: `sim/swarm/runs/reference/`,
  risk_score=97.33 CONFIRMED smoke event. Documented in
  `sim/swarm/README.md`.
- GNSS-denied perception: 1.39 m / 2.15 m error envelope on a 60-second
  GPS outage at 80 m AGL. Documented in `sim/perception/README.md`.
- v0.0.1 fire/smoke detector model card (Mitchell et al. 2019 framework).
- TAK emitter with 50+ unit tests, 8 type-code mappings.
- `BLUE-UAS-LINEAGE.md` substitution table and 24-month Cleared roadmap.
- `docs/strategy/ACQUIRER_FIT-2026-05-02.md` Sec. 6 — explicitly
  identifies Kratos as the lowest-immediate-fit acquirer with the
  highest optionality conditional on a tactical patrol variant.
- ION Analytics has reported Kratos as a potential acquisition target —
  meaning the strategy window for adjacent-product expansion is plausibly
  open *now*, not in two years.
  ([ION Analytics — Kratos as acquisition target](https://ionanalytics.com/insights/mergermarket/kratos-defense-pegged-as-potential-acquisition-target-sector-advisors-say/))

## Roadmap (4 quarters from a strategy conversation)

This is intentionally lower-velocity than the other four spec sheets,
because the ask is exploratory:

- **Q1 — relationship build, no commitment.** A 30-minute conversation
  with USD strategy. wildfire-watch sends civilian-wedge milestones
  quarterly: first flight, first LOA, first MOU.
- **Q2 — Phase 1 flight + dual-use position paper.** Real flight hours
  on the wildfire-watch civilian platform. A short paper on what a
  hypothetical Kratos-civilian product line could look like, written as
  a discussion document, not a sales document.
- **Q3 — SOFIC / AUSA / Modern Day Marine encounter.** A 5-minute brief
  at one of the 2026 H2 conferences, at Kratos's invitation if
  appropriate.
- **Q4 — strategy decision.** Either (a) Kratos confirms it has no
  intention of opening a civilian product line, in which case
  wildfire-watch focuses on Anduril / Ondas / Red Cat and the relationship
  stays cordial; or (b) Kratos has interest, in which case we scope a
  joint feasibility study.

## The ask

A **30-minute strategy conversation, no commitment.** The conversation
is "is a civilian / public-safety product line a coherent product wedge
for Kratos USD, given the autonomy IP base wildfire-watch is building?"
The honest answer might be no, and that is a perfectly fine outcome —
the goal is to get the question answered cleanly rather than guess.

A SOFIC / AUSA / Modern Day Marine 5-minute brief slot, no booth, no
marketing — just so a few people inside USD know the project exists — is
a fully acceptable substitute.

## References

- [XQ-58 Valkyrie product page (Kratos)](https://www.kratosdefense.com/unmanned-systems/air/uncrewed-tactical-aircraft/xq-58a)
- [Northrop / Kratos picked for Marine MUX TACAIR (Breaking Defense, Jan 2026)](https://breakingdefense.com/2026/01/northrop-kratos-team-picked-for-marine-corps-drone-wingmen/)
- [Kratos demonstrates XQ-58A EW for USMC (UAS Magazine)](https://uasmagazine.com/articles/kratos-demonstrates-xq-58a-electronic-warfare-capabilities-for-united-states-marine-corps)
- [ION Analytics — Kratos as acquisition target](https://ionanalytics.com/insights/mergermarket/kratos-defense-pegged-as-potential-acquisition-target-sector-advisors-say/)
- [Anduril–Korean Air wildfire partnership (April 2026)](https://www.anduril.com/news/korean-air-and-anduril-explore-solutions-to-global-wildfire-response)
- [XPRIZE Wildfire finalists](https://www.xprize.org/news/meet-the-future-of-autonomous-wildfire-response-xprize-wildfire-announces-finalist-teams-advancing-in-11m-competition)
- wildfire-watch internal: `sim/swarm/README.md`,
  `sim/perception/README.md`, `sapphire_integration/tak/README.md`,
  `BLUE-UAS-LINEAGE.md`, `docs/strategy/ACQUIRER_FIT-2026-05-02.md` Sec. 6,
  `docs/intel/ukraine-drone-playbook-2026-05-01.md`
