# wildfire-watch as the missing software layer for ARACHNID

**Date:** 2026-05-02
**For:** Red Cat Holdings — software / ARACHNID program management
**Pair-with email:** `docs/outreach/emails/07_red_cat_software_intro.md`
**Repo:** https://github.com/arigatoexpress/wildfire-watch (Apache-2.0)

---

## Cover line

wildfire-watch is the public-safety mission software + multi-modal
perception stack ARACHNID does not own internally — Jetson-class portable,
NDAA-clean, TAK / ATAK-native, and explicitly designed to slot into the
WEB / Palladyne / Palantir VNav partner pattern Red Cat already runs.

## Their platform / our integration

We integrate with three Red Cat components, all named in public sources:

1. **Black Widow / ARACHNID family** — the Army SRR-winning small-form
   ISR airframe. Black Widow features forward obstacle-avoidance and an
   integrated FLIR Prism AI software stack. ARACHNID is the family:
   Black Widow + FANG + Edge 130 + (sister) Teal 2.
   ([Black Widow product page (Advexure)](https://advexure.com/products/red-cat-black-widow-srr-drone-system),
   [ARACHNID introduction at AUSA 2024](https://ir.redcatholdings.com/news-events/press-releases/detail/156/red-cat-introduces-arachnid-family-of-small-isr-and-precision-strike-systems-at-ausa-2024))
2. **WEB control system + ATAK UAS Tool integration.** "WEB is uniquely
   designed to command and control the ARACHNID Family of Systems for
   defense and security operations. In development with Booz Allen
   Hamilton, Red Cat has implemented an industry-first UAS Tool interface,
   through ATAK." This is the C2 surface our TAK / CoT emitter publishes
   into. We do not rebuild WEB — we feed it.
   ([Red Cat C2 page](https://redcat.red/controllers/))
3. **Palladyne Pilot AI** — Red Cat's autonomy partner, demonstrated in
   the May 2025 cross-platform multi-drone autonomous flight test
   (Teal 2 + Black Widow). Onboard edge computing + constrained comms.
   wildfire-watch's swarm consensus voter and GNSS-denied perception
   primitive are explicitly composable with that Pilot AI runtime — they
   sit *above* the autonomy layer at the perception / mission-software
   tier.
   ([Palladyne–Red Cat cross-platform flight, May 2025](https://www.palladyneai.com/press-releases/palladyne-ai-and-red-cat-announce-successful-completion-of-cross-platform-collaborative-drone-flight/))

We do **not** rebuild Palladyne Pilot AI's flight autonomy or VNav's
GNSS-denied positioning — those are already partnered. We bring the layer
above: multimodal sensor fusion, k-of-N false-positive suppression, and
the ATAK / Lattice-federation TAK emitter Red Cat appears not to own
internally.

## What we deliver

The slice of wildfire-watch that ports onto an ARACHNID-class airframe
today:

- **`ml/fire_detection/infer.py`** — multimodal fusion gate. Conjunction:
  RGB score ≥ threshold AND thermal delta ≥ 5 °C AND persistence ≥ 5
  frames AND geofence OK AND wind consistent. Designed for Jetson Orin
  Nano Super 8 GB FP16 TensorRT, p95 ≤25 ms target. Camera-agnostic;
  swaps cleanly between FLIR Boson (Black Widow) and FLIR Lepton 3.5
  (wildfire-watch reference).
- **`sim/swarm/`** — k-of-N spatial+temporal consensus voter +
  lossy-comms model. False-positive suppression by independent
  corroboration within R=75 m / T=60 s. Reference run: 3 drones, 1 km²,
  k=2 → CONFIRMED smoke at risk_score 97.33. With `loss_rate=1.0` no
  consensus fires; with `loss_rate=0.0` every emit propagates instantly.
  This is the discriminator that lets a heterogeneous fleet (Black Widow
  + Teal 2 + Edge 130) emit one alert instead of three.
- **`sim/perception/`** — GNSS-denied vision-nav primitive. VO + TRN +
  IMU + complementary fusion + GPS-spoof discriminator. 60-second outage
  at 80 m AGL: 1.39 m mean / 2.15 m max position error. This sits
  alongside, not in place of, Palantir VNav — VNav is the navigation
  product; ours is the spoof-detection + cross-check primitive that runs
  per-tick.
- **`sapphire_integration/tak/`** — Cursor-on-Target XML emitter over
  TCP / UDP / TLS / multicast. ARACHNID signals out into ATAK / WinTAK /
  iTAK / FreeTAKServer / Lattice — same wire format. 8 type-code mappings
  shipped: smoke, fire, thermal anomaly, wildlife, anomaly, system event,
  drone self-position, geofence. Stale-window defaults baked per type
  (1 hour for fire, 15 min for thermal anomaly, 24 hours for system
  event). Cert-pinning hooks for TAK Server mutual-TLS already present.
- **`sapphire_integration/wildfire_signal_schema.json`** — wire-format
  source of truth. Public-safety wedge, but the schema is general:
  mission-mode-extensible if Red Cat wants to specialize for civilian
  vs. defense profiles.
- **`BLUE-UAS-LINEAGE.md`** — every Phase-1 BOM line traced to NDAA /
  Sec. 848 substitution. Material for Red Cat given the Fuzzy Panda
  Research supply-chain critique — adding wildfire-watch to ARACHNID's
  software stack *strengthens* the Sec. 1822 posture rather than weakening
  it.
- **`sapphire_integration/foundry/ontology.py`** — six-object data model
  that gives ARACHNID a Foundry-compatible ontology if Red Cat customers
  ask for it (e.g., the existing Palantir VNav relationship suggests
  Foundry is in the picture).

## Technical interface

| Red Cat surface | wildfire-watch source | Wire form |
|---|---|---|
| Onboard compute | `ml/fire_detection/infer.py` packaged as a container or systemd unit | TBD — Black Widow / ARACHNID onboard compute SKU not public; reference target is Jetson Orin Nano Super FP16 |
| Sensor ingest | `infer.py` consumes RGB + LWIR | RGB: V4L2 / GStreamer; LWIR: FLIR Boson via Teledyne SDK; thermal-delta gate is in our code |
| WEB / ATAK signal egress | `sapphire_integration/tak/atak_emitter.py` | CoT XML over `tcp://atak.local:8087` or `tls://...:8089` (mutual TLS); RemarkObject + `__group` element for callsign |
| Palladyne Pilot AI handoff | `sim/swarm/consensus_voter.py` runs at the WEB / dock layer; consumes per-airframe Signals from Pilot AI's edge-comms bus | TBD — Pilot AI software bus contract not public |
| GNSS-denied cross-check | `sim/perception/fusion.py` complementary filter | Sits per-tick under whatever VNav decides about position; emits `trusted=False` flag when GPS disagrees with VO+IMU by >3σ |
| Mission planning hook | `recommended_action` enum: `log_only` / `notify_operator` / `notify_fire_dept` / `loiter_and_capture` / `rtl` | Mapped to WEB mission-tool re-tasking commands (TBD — needs WEB API) |

The Black Widow / ARACHNID onboard-compute SKU and the Palladyne Pilot AI
software-bus contract are **TBD — public sources name the partners but
not the integration interfaces.** A 90-day paid eval is sized to scope
exactly those two unknowns.

## Proof points (today)

- 240+ tests passing in under 7 seconds. `python3 -m pytest -q`.
- TAK emitter has 50+ unit tests; canonical CoT XML examples for every
  signal type in `sapphire_integration/tak/examples/`. Sat-down with
  MIL-STD-2525 and FreeTAKServer reference; type-code dictionary in
  `sapphire_integration/tak/cot_types.py`.
- Swarm consensus reference run: `sim/swarm/runs/reference/` shows the
  full multi-drone scenario producing one CONFIRMED event from three raw
  emits. Documented in `sim/swarm/README.md`.
- GNSS-denied perception: 1.39 m / 2.15 m error envelope on a 60-second
  GPS outage at 80 m AGL.
- v0.0.1 fire/smoke detector model card (Mitchell et al. 2019 framework)
  with explicit precision-at-recall=0.80 ≥ 0.95 production target,
  intended-use scope, fusion-gate safety net, and Colorado-specific
  beetle-kill false-positive risk acknowledged.
  [`ml/fire_detection/MODEL_CARD.md`].
- `BLUE-UAS-LINEAGE.md` Sec. 4 substitution table and Sec. 8 path-to-
  Cleared roadmap are the artifacts that make a Red Cat acquisition net-
  positive on supply-chain posture.

## Roadmap (4 quarters from paid-eval acceptance)

- **Q1 — eval scoping + LOA + first port.** Black Widow / ARACHNID
  payload-API spec under NDA. wildfire-watch perception head ported to
  the Black Widow onboard compute target. Crested Butte FPD LOA in hand.
  Phase 0 flight on the Slate River drainage.
- **Q2 — Phase 1 hardware, real flight, v0.1.0 detector.** v0.1.0 trained
  fire/smoke model on Jetson Orin Nano Super FP16. Black Widow flying a
  wildfire patrol with the wildfire-watch perception head live. CoT
  events into the operator's WEB / ATAK client.
- **Q3 — public-safety reference + Palladyne integration.** A Red Cat +
  wildfire-watch integration tested alongside Palladyne Pilot AI in the
  multi-drone collaborative-flight regime. Public reference from one
  Colorado FD / DFPC partner.
- **Q4 — joint customer.** Either (a) a multi-agency Colorado pilot
  generating $25-100k ARR for Black Widow + wildfire-watch as a
  public-safety SKU, or (b) a software-stack acquisition conversation
  consistent with the price bands in
  `docs/strategy/ACQUIRER_FIT-2026-05-02.md` ($10-30M software stack at
  12-18 months).

## The ask

A **90-day paid evaluation** on a Black Widow or ARACHNID-class airframe.
We port the perception head, the swarm voter, and the TAK emitter to Red
Cat's onboard compute, run a wildfire-detection scenario, and ship Red
Cat back the integration artifacts (model, schema, TAK adapter) plus a
public reference. Pricing and SOW are open.

If a paid eval is too early, the lower-priority ask is a **30-minute
conversation with Black Widow / ARACHNID software product management** —
their honest read on whether the gap we think we see (mission software /
multi-modal perception layer between Pilot AI and WEB) is real, or one
Red Cat is already filling another way.

## References

- [Black Widow SRR product page (Advexure)](https://advexure.com/products/red-cat-black-widow-srr-drone-system)
- [ARACHNID family introduction (Red Cat IR, AUSA 2024)](https://ir.redcatholdings.com/news-events/press-releases/detail/156/red-cat-introduces-arachnid-family-of-small-isr-and-precision-strike-systems-at-ausa-2024)
- [Red Cat WEB / C2 page](https://redcat.red/controllers/)
- [Palladyne–Red Cat cross-platform multi-drone flight (May 2025)](https://www.palladyneai.com/press-releases/palladyne-ai-and-red-cat-announce-successful-completion-of-cross-platform-collaborative-drone-flight/)
- [Red Cat Army SRR production selection](https://ir.redcatholdings.com/news-events/press-releases/detail/160/red-cat-announces-production-selection-for-u-s-army-short-range-reconnaissance-program)
- [Fuzzy Panda Research — Red Cat critique](https://fuzzypandaresearch.com/rcat-army-contract-smaller-than-claimed/)
- [DSEI 2025 — Black Widow battlefield awareness](https://www.armyrecognition.com/news/army-news/2025/dsei-2025-how-the-black-widow-drone-shapes-the-future-of-us-army-battlefield-awareness)
- wildfire-watch internal: `BLUE-UAS-LINEAGE.md`,
  `sapphire_integration/tak/README.md`, `sim/swarm/README.md`,
  `sim/perception/README.md`, `ml/fire_detection/MODEL_CARD.md`,
  `docs/strategy/ACQUIRER_FIT-2026-05-02.md`
