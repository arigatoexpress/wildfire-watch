# wildfire-watch as an Optimus mission payload

**Date:** 2026-05-02
**For:** Ondas Holdings / OAS / American Robotics — payload-program intake
**Pair-with email:** `docs/outreach/emails/06_ondas_optimus_payload_intro.md`
**Repo:** https://github.com/arigatoexpress/wildfire-watch (Apache-2.0)

---

## Cover line

wildfire-watch is the wildfire-detection mission payload + edge perception
stack for Optimus — a Blue UAS-aligned, civilian-public-safety wedge that
fits inside the documented "up to 9 mission payloads" envelope and gives
OAS a public-safety reference customer story for its 2026 revenue ramp.

## Their platform / our integration

We integrate with the Ondas / American Robotics **Optimus System** —
specifically:

1. **Optimus drone-in-a-box dock.** "Dock houses 11 onboard batteries and
   up to 9 mission payloads, enabling extended endurance without human
   intervention. Using an integrated mechanical arm, payloads can be
   autonomously exchanged between flights, allowing the system to shift
   mission profiles in real time." This is the architectural slot we fit
   into — wildfire-watch is one of the 9 payload modules.
   ([Ondas press release, 2026-01-28](https://ir.ondas.com/press-releases/detail/275/ondas-american-robotics-optimus-drone-approved-for-rapid))
2. **DCMA Blue UAS Cleared List.** Optimus was added 2026-01-28. We are
   substitutable to it — every Phase-1 BOM line in `BLUE-UAS-LINEAGE.md`
   traces to a Cleared / Framework / NDAA-eligible part.
3. **24/7 autonomous ops profile.** Optimus is a fixed-zone perimeter
   patrol system. Wildfire perimeter-patrol fits this profile exactly —
   recurrent flights over the same beetle-killed timber stand, dock at
   night, fly at first light.

We do **not** build a competing drone-in-a-box. We bring the perception +
fusion + consensus + ontology stack that runs on top of one. We do not
overlap with Ondas Networks (private dot16/5G) or with Sentrycs (counter-UAS).

## What we deliver

The wildfire-watch slice that ports onto an Optimus mission-payload bay,
all working in the simulator and under test today:

- **`ml/fire_detection/infer.py`** — fire/smoke YOLOv8n head plus the
  multimodal fusion gate `should_emit()`. Targets a Jetson Orin Nano
  Super 8 GB at FP16 TensorRT, p95 latency target ≤25 ms / ≥40 FPS at
  640×640. We do not assume Optimus's onboard compute SKU, but the
  wildfire-watch stack is hardware-agnostic by construction (see Sec. 6 of
  `BLUE-UAS-LINEAGE.md`).
- **`sapphire_integration/wildfire_signal_schema.json`** — the wire-format
  source of truth. Every emit composes against this. This is the artifact
  a payload-partner program would expect to see at the wire layer.
- **`sapphire_integration/tak/`** — Cursor-on-Target XML emitter over
  TCP / UDP / TLS / multicast. Optimus signals federate into ATAK,
  WinTAK, iTAK, FreeTAKServer, Lattice — same wire format. 8 type-code
  mappings shipped.
- **`sim/swarm/`** — the consensus voter that turns a stand of 3-9
  Optimus airframes covering adjacent zones into a single false-positive-
  suppressed alert stream. k-of-N spatial+temporal corroboration over a
  lossy mesh. Reference run: 3 drones, 1 km², k=2 → CONFIRMED smoke at
  risk_score 97.33.
- **`sim/perception/`** — GNSS-denied vision-nav primitive (VO + TRN +
  IMU + complementary filter + GPS-spoof discriminator). Smoke kills GPS
  lock; the perception primitive is what keeps an Optimus inside its
  geofence during a real fire.
- **`sapphire_integration/foundry/ontology.py`** — six-object data model
  (Drone, Zone, FireDepartmentUnit, FlightLog, BatteryCycle,
  WildfireSignal). This is the data layer Ondas can put in front of an
  agency customer (CAL FIRE, DFPC, PG&E) without writing the schema from
  scratch.
- **`BLUE-UAS-LINEAGE.md`** — every Phase-1 component traced to NDAA /
  Sec. 848 substitution status. Sec. 1822 / FAR 52.240-1 diligence
  pre-done.

## Technical interface

| Optimus surface | wildfire-watch source | Wire form |
|---|---|---|
| Mission payload mechanical bay | n/a — we run on whatever Optimus already supplies for sensor / compute payloads | TBD — needs Optimus payload-bay mechanical / electrical spec under NDA |
| Onboard compute | `ml/fire_detection/infer.py` packaged as a Linux container | x86_64 or arm64 with NVIDIA Jetson-class GPU (Orin Nano Super 8 GB reference); FP16 TensorRT for the fire/smoke head |
| Sensor ingest | `infer.py` consumes RGB + LWIR frames + ADS-B feed | RGB: V4L2 / GStreamer; LWIR: FLIR Lepton I2C / SPI; ADS-B: pingRX UART |
| Signal egress | `wildfire_signal v1` JSON | JSONL append + (a) HTTP POST to ground station, (b) CoT XML to TAK Server, (c) Lattice Entity publish if Optimus integrates Lattice |
| Dock-side aggregation | OAS dock control plane → wildfire-watch ground station | TCP / TLS to ground station; we provide the receiver |
| Fleet-level consensus | `sim/swarm/consensus_voter.py` runs on the dock or ground station, not on the airframe | Each drone publishes Signals; voter produces Confirmations |
| Recommended-action handoff | enum `recommended_action` mapped to Optimus mission re-tasking | TBD — needs Optimus mission API |

The Optimus payload bay mechanical / electrical specification is **TBD —
needs a payload-program NDA and the physical interface document.** Public
sources confirm the "up to 9 mission payloads" capacity but not the
payload-bay dimensions, weight envelope, or compute/sensor connector
specification. This is the single largest unknown for this spec sheet.

## Proof points (today)

- 240+ tests passing in under 7 seconds. `python3 -m pytest -q`.
- Wire-format JSON Schema validated against canonical examples; signal
  builder + fusion gate are the canonical entrypoints (`build_signal()`,
  `should_emit()`).
- `BLUE-UAS-LINEAGE.md` is the most directly relevant artifact for OAS:
  it's the diligence document that lets Ondas present an Optimus +
  wildfire-watch SKU to a federal customer without re-running
  Sec. 1822 component review on our half of the stack.
- Operator profile: runs Sapphire (5,275+ tests, 49 plugin tools, 4-tier
  compute mesh), TradingView orchestrator, hermes-agent Telegram, OpenBB
  intel pipeline. Capacity to ship and operate complex distributed
  systems is documented.
- Strategic posture in `docs/strategy/ACQUIRER_FIT-2026-05-02.md` is
  candid about price band ($5-10M acqui-hire today, $20-50M
  mission-payload + customer-pilot at 12-18 months, $50-150M full
  platform at 36 months).

## Roadmap (4 quarters from payload-partner intake acceptance)

- **Q1 — open-source repo + first LOA + payload spec.** Crested Butte FPD
  Letter of Authorization in hand. Optimus payload-bay spec under NDA.
  wildfire-watch container image targeted at the documented compute
  envelope.
- **Q2 — Phase 1 hardware, real flight, v0.1.0 detector.** First trained
  fire/smoke model on Jetson-class compute, on a Holybro X500 V2 (our
  Phase 1 reference) and (parallel) packaged for the Optimus payload bay.
  50+ patrol hours over the Gunnison fire-season tail. Real
  `wildfire_signal` events from real hardware.
- **Q3 — first joint pilot.** One Optimus dock + wildfire-watch payload
  deployed for a Colorado FD or DFPC partner. Public reference. CoT
  signals into the dispatcher's ATAK or WinTAK client. Detection-time
  delta vs. the local PTZ camera spotter network measured.
- **Q4 — first joint customer.** Either (a) a multi-agency Colorado pilot
  generating $25-100k ARR with Optimus + wildfire-watch as a SKU, or
  (b) co-pitch with American Robotics into a CAL FIRE / DFPC RFP.

## The ask

A **paid evaluation as an Optimus mission payload.** 90 days, scoped SOW,
one Optimus dock + one wildfire-watch payload integration, one Colorado
public-safety partner, one detection-time-delta measurement.

Pricing and SOW are open. We are not optimizing for revenue from the eval;
we are optimizing for a public reference of an Optimus + wildfire-watch
deployment that gives OAS the public-safety vertical reference for its
2026 revenue narrative.

If the right path is the American Robotics payload-partner intake form,
point us there.

## References

- [Ondas / Optimus Blue UAS approval (2026-01-28)](https://ir.ondas.com/press-releases/detail/275/ondas-american-robotics-optimus-drone-approved-for-rapid)
- [Ondas OAS Investor Day — 2026 revenue target $375M](https://www.stocktitan.net/news/ONDS/ondas-hosts-oas-investor-day-ups-2026-revenue-target-to-170-180-18lq1ollcueo.html)
- [American Robotics product page](https://www.ondas.com/american-robotics)
- [Ondas/Mistral defense + homeland-security partnership](https://www.american-robotics.com/post/ondas-and-mistral-sign-strategic-partnership-to-accelerate-u-s-defense-and-homeland-security-sales)
- [DCMA Blue UAS Cleared List](https://bluelist.dcma.mil)
- [Drone Girl — Blue UAS Cleared List 2026](https://www.thedronegirl.com/2026/03/19/blue-uas-cleared-list/)
- wildfire-watch internal: `BLUE-UAS-LINEAGE.md`,
  `sapphire_integration/wildfire_signal_schema.json`,
  `sapphire_integration/tak/README.md`, `sim/swarm/README.md`,
  `ml/fire_detection/MODEL_CARD.md`,
  `docs/strategy/ACQUIRER_FIT-2026-05-02.md`
