# wildfire-watch as a Foundry ontology source for AIP

**Date:** 2026-05-02
**For:** Palantir AIP Bootcamp wildfire lead / Foundry partner engineering
**Pair-with email:** `docs/outreach/emails/05_palantir_aip_bootcamp.md`
**Repo:** https://github.com/arigatoexpress/wildfire-watch (Apache-2.0)

---

## Cover line

wildfire-watch is the upstream drone-mesh ontology source for a wildfire
AIP workflow — six already-defined object types, JSON-schema-validated
signal payloads, and a pre-wired ingestion path into Foundry — designed to
sit cleanly alongside the existing PG&E PSPS Foundry instance, not to
compete with it.

## Their platform / our integration

We integrate with three named Foundry / AIP surfaces:

1. **Foundry Ontology** — the object-graph layer. wildfire-watch ships six
   object types as Python dataclasses today
   (`sapphire_integration/foundry/ontology.py`) with a serializer that
   produces the `{type, primaryKey, properties}` envelope shape that
   Foundry's ingest API accepts. The repo is the upstream of truth — the
   intent is for Foundry to pull from us, not the inverse.
   ([Foundry Ontology](https://www.palantir.com/explore/platforms/foundry/ontology/))
2. **AIP Logic** — the no-code orchestration layer. AIP Logic blocks would
   reason against `wfw.WildfireSignal` and `wfw.Confirmation` objects and
   trigger downstream actions (notify dispatch, request loiter, escalate
   to IC). Our `recommended_action` enum (`log_only`, `notify_operator`,
   `notify_fire_dept`, `loiter_and_capture`, `rtl`) is the hand-off point.
   ([AIP Logic overview](https://www.palantir.com/docs/foundry/logic/overview))
3. **Foundry Compute Modules** (GA Feb 2026) — the container surface for
   running custom code. The wildfire-watch `ml/fire_detection/infer.py`
   inference loop is exactly the kind of long-running, language-agnostic
   container Compute Modules are designed for. We bring the model + the
   gate logic; Foundry hosts and scales it.
   ([Compute Modules announcement, Feb 2026](https://www.palantir.com/docs/foundry/announcements/2026-02))

We do **not** integrate with Skykit (a hardened edge form-factor — not the
right fit for our drone-side compute) or MetaConstellation (satellite
tasking — orthogonal to our mission). PG&E's existing Foundry instance for
PSPS is the architectural reference; we're asking how to slot wildfire
signals into that pattern.

## What we deliver

- **`sapphire_integration/foundry/ontology.py`** — six dataclass-defined
  object types, primary keys defined, GeoJSON-typed geometry, license fields,
  Blue UAS substitutability tag. Round-trips through `to_foundry_json` /
  `from_foundry_json`. Schema version pinned to 1.0.0.
  - `wfw.Drone` — airframe + RPIC + insurance + maintenance + Blue UAS
    status. PK: `drone_id` (regex `^wfw-[a-z0-9]{4,16}$`).
  - `wfw.Zone` — patrol polygon, GeoJSON geometry, fuel-load class,
    elevation envelope, exclusion flag, regulatory basis (e.g., 36 CFR
    261.16 for wilderness). PK: `zone_id`.
  - `wfw.FireDepartmentUnit` — partner FD with AOR polygon, contact info,
    engagement status (`not_contacted` → `loa_signed` →
    `operational_partner`). PK: `unit_id`.
  - `wfw.FlightLog` — drone + mission + telemetry + counts. PK:
    `flight_id`.
  - `wfw.BatteryCycle` — chemistry, capacity, voltage envelope, coldest
    temperature observed (high-altitude winter ops gotcha). PK:
    `cycle_id`.
  - `wfw.WildfireSignal` — the v1 wildfire_signal as a Foundry object.
    Mirrors `sapphire_integration/wildfire_signal_schema.json` v1.0.0.
    PK: `signal_id` (UUIDv4).
- **`sapphire_integration/wildfire_signal_schema.json`** — the wire-format
  source of truth. Required fields: signal_id, drone_id, zone_id,
  timestamp, coords (lat/lon/alt_agl_m), signal_type
  (smoke|fire|thermal_anomaly|wildlife|anomaly|system_event), confidence
  [0..1], evidence.frame_uris (≥1), risk_score [0..100],
  recommended_action, schema_version. Validated by JSON Schema Draft 2020-12.
- **`ml/fire_detection/infer.py`** — the canonical
  `build_signal()` and `should_emit()` functions. The fusion gate is a
  conjunction: RGB score ≥ threshold AND thermal delta ≥ 5 °C AND
  persistence ≥ 5 frames AND geofence OK AND wind consistent. Exactly the
  kind of multi-input rule that AIP Logic chains-of-thought are designed
  to express, codified.
- **`sim/swarm/`** — the swarm consensus voter that produces the
  `wfw.Confirmation` object. k-of-N spatial+temporal consensus over a
  lossy-comms model.
- A two-line ingestion path into Sapphire's existing
  `lib/foundry/ingestion.py` daemon. Same pattern is reusable for a real
  Foundry tenant once Developer Tier is granted.

## Technical interface

| Foundry surface | wildfire-watch source | Wire form |
|---|---|---|
| Object Type registration | `sapphire_integration/foundry/ontology.py` | TypeScript type stubs generated from the Python dataclasses (TBD — needs Foundry Ontology Manager access) |
| Object ingestion | `to_foundry_json(obj)` | `{"type": "wfw.WildfireSignal", "primaryKey": "<uuid>", "properties": {...}}` |
| Compute Module entrypoint | `ml/fire_detection/infer.py::build_signal()` | Container invoked per frame; returns `wildfire_signal v1` JSON |
| AIP Logic block input | `wfw.WildfireSignal` and `wfw.Confirmation` objects | Property-level access to confidence, risk_score, recommended_action |
| AIP Logic block output | Notification action → existing TAK / Telegram fan-out via `sapphire_integration/tak/` and Sapphire hermes | Side effect; Foundry write-back to `wfw.Dispatch` (TBD object — defined in design doc, not yet in `ontology.py`) |
| Geometry storage | GeoJSON FeatureCollection per zone, embedded in `wfw.Zone.polygon_geojson` | Foundry geometry property type (PostGIS-backed) |

The TypeScript Ontology Manager bindings are TBD pending Developer Tier
access. The Python module is the source of truth and the serializer is
implemented; the TS shim is the missing piece.

## Proof points (today)

- 6-object ontology defined and round-tripping through JSON. Tests in
  `sapphire_integration/foundry/tests/`.
- 240+ tests passing in under 7 seconds. `python3 -m pytest -q`.
- v1 signal schema validates with `jsonschema` against canonical signal
  examples in `sapphire_integration/tak/examples/`.
- AIP Bootcamp wildfire curriculum precedent: PVM has run the AIP Bootcamp
  for Wildfire Management. wildfire-watch is the missing drone-mesh source
  layer for that curriculum.
  ([PVM AIP Bootcamp Wildfire](https://blog.pvmit.com/pvm-blog/aip-bootcamp-wildfire))
- PG&E PSPS Foundry deployment is the public production reference;
  reportedly 65% reduction in reportable ignitions.
  ([Palantir / PG&E impact](https://www.palantir.com/impact/pacific-gas-and-electric/))
- Operator already runs a sister Foundry-bridge stack in the Sapphire
  monorepo (`lib/foundry/`, `services/foundry_sync/`); the integration
  pattern is exercised, not novel.

## Roadmap (4 quarters from Developer Tier acceptance)

- **Q1 — Developer Tier + ontology import.** Six object types registered
  in a Foundry tenant. End-to-end: simulator → `wfw.WildfireSignal` →
  ontology → AIP Logic block → notification action. Public ontology demo.
- **Q2 — Phase 1 flight + Compute Module.** Live wildfire_signal events
  from real Phase 1 hardware (Holybro X500 V2 + Cube Orange+ + Jetson
  Orin Nano Super) into Foundry. v0.1.0 fire/smoke model packaged as a
  Compute Module.
- **Q3 — AIP Bootcamp presentation.** wildfire-watch as a reference
  integration partner at the next AIP Bootcamp for Wildfire — drone mesh
  source feeding an AIP Logic incident-response workflow.
- **Q4 — Joint customer.** A Colorado FD, an IOU partner (PG&E or Xcel /
  Tri-State on the Colorado side), or the GMUG district running a Foundry
  + wildfire-watch instance with measurable detection-time delta vs.
  ALERTColorado.

## The ask

1. A **Foundry Developer Tier slot.** Free, capacity-capped, intended for
   exactly this use case. We use it to (a) register the six object types,
   (b) wire the Compute Module, (c) build a public AIP Logic demo.
2. **30 minutes with the AIP Bootcamp wildfire program lead.** Their read
   on whether wildfire-watch belongs at the next Bootcamp as a presenting
   integration partner — or whether the timing is wrong. Either answer is
   useful.

If the right path is the public partner program intake form, point us
there.

## References

- [Foundry Ontology](https://www.palantir.com/explore/platforms/foundry/ontology/)
- [AIP Logic overview](https://www.palantir.com/docs/foundry/logic/overview)
- [Foundry Compute Modules (Feb 2026 GA)](https://www.palantir.com/docs/foundry/announcements/2026-02)
- [AIP overview](https://www.palantir.com/docs/foundry/aip/overview)
- [AIP Community Registry (GitHub)](https://github.com/palantir/aip-community-registry)
- [PVM AIP Bootcamp Wildfire](https://blog.pvmit.com/pvm-blog/aip-bootcamp-wildfire)
- [Palantir / PG&E PSPS impact](https://www.palantir.com/impact/pacific-gas-and-electric/)
- [Palantir Skykit](https://www.palantir.com/offerings/skykit/)
- wildfire-watch internal: `sapphire_integration/foundry/ontology.py`,
  `sapphire_integration/wildfire_signal_schema.json`,
  `docs/intel/foundry-research-2026-05-01.md`,
  `docs/strategy/ACQUIRER_FIT-2026-05-02.md`
