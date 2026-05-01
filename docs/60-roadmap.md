# Roadmap

## MVP (months 0–3) — single drone, single zone, fire-only

**Goal**: One drone airborne over one defined zone, detecting smoke plumes
above a threshold confidence and pushing signals to Sapphire signal_logger.
No fire department in the loop yet. No wildlife head yet.

**Deliverables**:
- [ ] Frame printed + assembled (week 1-2)
- [ ] ArduPilot Copter 4.6 calibrated, basic LOITER + RTL working (week 3)
- [ ] Jetson Orin Nano Super flashed with JetPack 6.2, MAVLink bridge to Cube
      Orange+ working over UART (week 3)
- [ ] FASDD-pretrained YOLOv8n exported to TensorRT, running at >100 FPS on
      bench (week 4)
- [ ] Lepton 3.5 thermal capture pipeline working (week 4)
- [ ] First flight with live inference, no fire (week 5)
- [ ] Controlled-burn test: prescribed-burn footage from CAL FIRE archive +
      a small backyard burn-barrel test (with permits) for live-fire eval
      (week 6-7)
- [ ] Signal POST to Sapphire `signal_logger:18081` working end-to-end (week 8)
- [ ] One zone defined as GeoJSON, autonomous patrol working (week 10)
- [ ] 10 successful patrol flights, signal precision/recall reported (week 12)

**Success metric**: ≥0.90 precision and ≥0.70 recall on a held-out
controlled-burn evaluation set, with full ground-station signal flow working.

**Failure metric**: any unrecoverable fly-away, any flight in violation of
Part 107, any signal posted to a real fire department's TAK before pilot
agreement is signed.

## Phase 2 (months 3–9) — 3-drone mesh, wildlife, fire dept partnership

**Goal**: 3 drones operating as a mesh over one or two zones, MegaDetector v6
wildlife head live, BirdNET ecology audio capture during perch mode, and a
signed pilot MOU with one fire department (likely El Dorado County FPD or
CAL FIRE San Benito-Monterey unit per `50-fire-dept-partnership.md`).

**Deliverables**:
- [ ] Build 2 more units (units 2, 3); first should reproduce in <8 hours,
      validating the build doc.
- [ ] Multi-drone signal consensus (2-of-N quorum on rari1/rari2 cross-check)
- [ ] MegaDetector v6 Compact deployed, wildlife BB output going to dashboard
- [ ] BirdNET-Analyzer running on perch / hover mode, species log per flight
- [ ] TAK Server adapter writes CoT XML; tested against Free TAK Server in lab,
      then partner's COTAK
- [ ] Public Safety Shielded Operations Waiver (PSSOW) filed by partner agency
- [ ] Pilot MOU signed; first patrol flight under fire-dept authorization
- [ ] Public ecology API live on Cloud Run (`sapphire-479610`,
      `wildfire-watch-public` service)

**Success metric**: 50+ patrol hours over the fire season with at least one
true-positive signal that beat existing detection (ALERTWildfire / 911) by
≥5 minutes.

## Phase 3 (months 9–18) — multi-county, fire-dept dashboard, Sapphire-routed alerts

**Goal**: Multi-jurisdiction deployment, 5+ drones, dedicated fire-dept-facing
dashboard (separate from Sapphire operator dashboard), and integration of our
signals into a CAL FIRE statewide RDI evaluation.

**Deliverables**:
- [ ] Per-jurisdiction TAK adapter config; each district sees only their own
      signals
- [ ] Public-facing fire-dept dashboard at `wildfire-watch.[domain]` —
      auth via SSO with the agency's existing identity provider
- [ ] DNS-routed alert tiers: high-confidence signals page on-call IC; mid-conf
      go to ecology / research log; low-conf go to model retrain pool only
- [ ] Part 108 / Part 146 compliance plan filed with FAA (assuming rulemaking
      finalized by mid-2026)
- [ ] CAL FIRE RDI grant submitted ($150k–$500k range based on 2025 awards)
- [ ] First pre-ignition heat-anomaly detection demonstrated (Phase-3 R&D goal,
      not commitment)
- [ ] Open-source release of all firmware, ML models, and CAD on GitHub under
      Apache-2.0; ecology dataset on a research data repo (Zenodo / LILA BC)

**Success metric**: ≥3 partner agencies, ≥500 patrol hours/season, ≥10
publishable true-positive detections with quantified time-delta improvement.

## Out of scope (forever, or until very late phases)

- **Active fire suppression** (water/retardant drops). We are detection-only.
  Suppression aircraft is regulated, type-certified, expensive, and not what
  this product is.
- **Counter-UAS / surveillance of people**. Hard out. Privacy posture in
  `00-vision.md` is non-negotiable.
- **Sales of identifiable wildlife data**. Public-good only.
- **Acquisition of an incumbent (Skydio / Parrot / Autel) airframe**. Vertical
  integration on hardware is the moat.

## Risks (top 5, ranked)

1. **First fly-away or crash damaging property/person** — kills program. Hard
   geofence, conservative airspeed envelope, redundant IMUs, mandatory
   pre-flight checklist enforced by ground station refusal-to-arm.
2. **First false-positive that triggers fire-dept dispatch** — kills credibility
   and the partnership. 2-of-N consensus + edge confidence gating + manual
   verification gate before any TAK push during the first 50 hours of fly-time.
3. **FAA enforcement action** — kills program. Operations manual, RPIC
   currency log, and zero-tolerance on TFR violations.
4. **NDAA component drift** — kills public-safety procurement. Quarterly BOM
   audit against Section 848 list.
5. **Sapphire stack instability cascading to detection availability** —
   degrades trust. Drone-edge keeps a 24-hour signal buffer; ground station
   has stand-alone TAK push that doesn't depend on Sapphire reachability.

## Open questions for the operator

- **Which county / zone is the first target?** Sapphire memory doesn't
  pinpoint a location; this doc assumes California generically. Pick a zone
  before week 4 of MVP.
- **Solo operator or co-founder?** Phase 2 PSSOW + multi-drone ops are hard
  for one person. Start identifying a co-pilot or contract VO.
- **CAL FIRE RDI grant cadence?** Verify next funding cycle and align Phase 2
  delivery to grant deadlines.
