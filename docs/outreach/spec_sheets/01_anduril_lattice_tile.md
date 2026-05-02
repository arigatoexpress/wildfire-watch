# wildfire-watch as a Lattice tile

**Date:** 2026-05-02
**For:** Anduril Lattice partner-engineering / Mission Autonomy
**Pair-with email:** `docs/outreach/emails/04_anduril_lattice_intro.md`
**Repo:** https://github.com/arigatoexpress/wildfire-watch (Apache-2.0)

---

## Cover line

wildfire-watch is the small, civilian, NDAA-clean patrol-density tile that
publishes Lattice Entities and consumes Lattice Tasks for the wildfire
mission — so the Sentry / Ghost-X / Pulsar-tier assets only have to react to
confirmed signals, not to noise.

## Their platform / our integration

We integrate with five named Lattice surfaces, each documented at
[developer.anduril.com](https://developer.anduril.com):

1. **Lattice Mesh** — the decentralized data fabric. wildfire-watch
   ground-station publishes into Mesh; each consensus-confirmed
   `wildfire_signal` becomes a Lattice **Entity** with components for
   location, classification, provenance, and confidence.
   ([Lattice Mesh overview](https://www.anduril.com/lattice/lattice-mesh))
2. **Entities API** — the REST surface for `publishEntity`. An entity is
   "an interoperable data structure that powers the Lattice common
   operational picture (COP)" — components, not type hierarchy, define what
   it is. wildfire-watch already produces a JSON-schema-validated
   `wildfire_signal v1` with the exact fields a Lattice Entity needs (UUID,
   timestamp, location, classification, confidence, evidence URIs).
   ([Entities overview](https://developer.anduril.com/guides/entities/overview))
3. **Tasks API** — the model for "deliberate, sequential actions an
   operator can execute on a taskable agent." A wildfire-watch drone is a
   taskable agent: it accepts `loiter_and_capture`, `rtl`, and (future)
   `transit_to_zone` Tasks. Mapping is direct from our existing
   `recommended_action` enum.
   ([Tasks overview](https://developer.anduril.com/guides/tasks/overview))
4. **Lattice Sandboxes** — the partner-developer dev environment. Each
   Sandbox is a notional-data Lattice instance, max 12-hour lifetime, max 2
   concurrent per developer. Our request below is sized to that envelope.
   ([Lattice Sandboxes](https://developer.anduril.com/guides/getting-started/sandboxes))
5. **Lattice Partner Program** — the governance wrapper over the SDK.
   ([Lattice Partner Program](https://www.anduril.com/lattice/lattice-partner-program))

We do **not** integrate with Sentry hardware, Pulsar EW, or ALTIUS launched
effects. Those are the upper-stack assets we hand off to.

## What we deliver

The slice of wildfire-watch that lands inside Lattice today, all working in
the simulator, all under test:

- **`sapphire_integration/tak/`** — Cursor-on-Target XML emitter over TCP /
  UDP / TLS / multicast. CoT is the underlying TAK wire protocol, and TAK
  Server federates with Lattice. This is the lowest-friction
  drone-to-Lattice path that exists. 8 type-code mappings already shipped:
  `b-r-f-h-s` (smoke), `b-r-f-h-c` (fire), `b-r-f-h-h` (thermal anomaly),
  `a-n-G` (wildlife / neutral), `b-d` (anomaly), `b-m-p-s-m` (system
  event), `a-f-A-M-F-Q-r` (drone self-position), `u-d-c-c` (geofence
  polygon). ATAK auto-renders icons from these.
- **`sim/swarm/`** — N-drone fleet + k-of-N spatial+temporal consensus
  voter + lossy-comms model. **A swarm voter is a Lattice-tile-shaped
  primitive.** It produces a single `consensus_signal_v1` from k corroborating
  Entity candidates; that consensus event is what we'd publish to Lattice,
  not the noisy raw stream. Last reference run: 3 drones, 1 km² mission,
  k=2, `consensus_smoke` scenario → 1 CONFIRMED smoke at risk_score 97.33.
- **`sim/perception/`** — GNSS-denied vision-nav primitive (visual
  odometry + terrain-relative navigation + IMU + complementary fusion + GPS
  spoof discriminator). 60-second outage at 80 m AGL stayed within 1.39 m
  mean / 2.15 m max of truth. This is the precondition for any wildfire
  mission — smoke kills GPS lock and Gunnison canyons block half the
  constellation.
- **`sapphire_integration/foundry/ontology.py`** — 6-object data model
  (Drone, Zone, FireDepartmentUnit, FlightLog, BatteryCycle,
  WildfireSignal) that maps cleanly onto Lattice Entity components.
- **`BLUE-UAS-LINEAGE.md`** — every Phase-1 BOM line traced to its NDAA /
  Sec. 848 substitution path. Cube Orange+, Holybro X500 V2, Jetson Orin
  Nano Super, FLIR Lepton 3.5, Sony IMX477. Phase 0 prototyping uses a DJI
  Mavic Mini explicitly outside the federal-funded surface; Phase 1 is on
  Blue UAS-substitutable components from day one.

## Technical interface

| Lattice surface | wildfire-watch source | Wire form |
|---|---|---|
| `publishEntity` (REST POST) | `sapphire_integration/tak/cot_event.py` plus a thin Lattice adapter (TBD — needs Sandbox SDK access) | JSON Entity envelope; components: `Location` (WGS84), `MilView` (CoT type), `Provenance` (drone_id + sensor versions), `Tracked` (kinematic), `Signal` (custom — confidence, risk_score, recommended_action) |
| `createTask` (drone is taskable) | `ml/fire_detection/infer.py::should_emit()` consumes Tasks via a future Lattice listener; `recommended_action` enum already maps to Task verbs | Task with `agentId=drone_id`, `definition.action="LOITER" / "RETURN_TO_LAUNCH" / "TRANSIT"` |
| Mesh subscription | `sim/swarm/swarm_runner.py` ConsensusVoter reads peer Entities | Entity stream filter on `wfw-*` agent IDs within R=75 m, T=60 s windows |
| TAK federation | `sapphire_integration/tak/tak_server_client.py` | CoT XML over `tcp://` / `tls://` / `udp://` / `mcast://` |
| Sandbox notional data | `sim/web/server.py` produces SSE event stream | localhost:8088 → bridged into Sandbox |

The Lattice-adapter shim — translating `wildfire_signal v1` JSON into the
Entity envelope and POST-ing to `publishEntity` — is an ~80-line file we
have not written yet because we have not had Sandbox SDK access. **TBD —
needs Lattice Sandbox slot.**

## Proof points (today)

- 240+ tests passing in under 7 seconds. `python3 -m pytest -q`.
- TAK emitter has 50+ unit tests; canonical CoT XML examples for smoke,
  fire, drone self-position, AOR geofence in `sapphire_integration/tak/examples/`.
- Swarm consensus reference run: `consensus_smoke` scenario,
  risk_score=97.33, `recommended_action=notify_fire_dept`.
  `sim/swarm/runs/reference/`.
- GNSS-denied perception: 1.39 m mean / 2.15 m max position error over a
  60-second GPS outage at 80 m AGL.
- v0.0.1 fire/smoke detector model card published; YOLOv8n architecture,
  FASDD pretrain → FLAME-2 fine-tune plan, p95 latency target ≤25 ms on
  Jetson Orin Nano Super FP16. v0.0.1 is a colour-heuristic placeholder;
  v0.1.0 is the first trained model.
- `BLUE-UAS-LINEAGE.md` traces every Phase-1 BOM line to substitution
  status. Doodle Labs Helix Mesh Rider for the radio (the only radio that
  meets all Blue UAS Framework requirements per DIU sponsorship). Cube
  Orange+ already shipping in Cleared platforms (Freefly Astro/Max).

## Roadmap (4 quarters from Lattice Sandbox approval)

- **Q1 — open-source repo + LOA + Sandbox prototype.** wildfire-watch
  publishes signed Entity events into a Sandbox; CoT + Lattice-Entity dual
  emit, schema parity verified. Crested Butte FPD Letter of Authorization
  in hand. First Phase 0 flight in the Slate River drainage.
- **Q2 — Phase 1 hardware, real flight, v0.1.0 detector.** First trained
  fire/smoke model on Jetson Orin Nano Super, on a Holybro X500 V2 with
  Cube Orange+. Doodle Labs Helix Mesh Rider radio. 50+ patrol hours over
  the Gunnison fire-season tail. Real Entity events in Lattice from real
  hardware.
- **Q3 — joint pilot.** Lattice instance running for one Colorado FD or
  GMUG district; wildfire-watch publishing live; Sentry-tower or Ghost-X
  cross-confirmation if Anduril hardware is on-site. Public reference.
- **Q4 — joint customer.** Either (a) a multi-agency Colorado pilot
  generating $25-100k ARR with wildfire-watch as a Lattice-tile line item,
  or (b) integration into a Korean Air-Anduril wildfire deployment.

## The ask

A **Lattice Sandbox slot** under the Lattice SDK developer program, and an
intro to the Mission Autonomy public-safety / wildfire vertical lead.

Sandbox sized at the documented default — 1 environment, ≤12-hour
lifetime, notional data, no production deployment. We use it to (a) write
the wildfire_signal-to-Entity adapter, (b) verify our Tasks consumer, (c)
publish a public reference Entity stream into a partner-tier Sandbox.

If the right path is the Lattice Partner Program intake form rather than a
direct Sandbox grant, point us there.

## References

- [Lattice Partner Program](https://www.anduril.com/lattice/lattice-partner-program)
- [Lattice SDK overview](https://developer.anduril.com/guides/concepts/overview)
- [Lattice Sandboxes](https://developer.anduril.com/guides/getting-started/sandboxes)
- [Entities overview](https://developer.anduril.com/guides/entities/overview)
- [Tasks overview](https://developer.anduril.com/guides/tasks/overview)
- [Lattice Mesh](https://www.anduril.com/lattice/lattice-mesh)
- [Pulsar family](https://www.anduril.com/pulsar)
- [Anduril–Korean Air wildfire response (April 2026)](https://www.anduril.com/news/korean-air-and-anduril-explore-solutions-to-global-wildfire-response)
- wildfire-watch internal: `BLUE-UAS-LINEAGE.md`,
  `sapphire_integration/tak/README.md`, `sim/swarm/README.md`,
  `sim/perception/README.md`, `ml/fire_detection/MODEL_CARD.md`,
  `docs/strategy/ACQUIRER_FIT-2026-05-02.md`
