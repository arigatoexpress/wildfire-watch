---
to: AIP Bootcamp Wildfire program lead, Palantir / PVM (TBD — confirm contact via PVM blog at blog.pvmit.com or partners@palantir.com)
subject: Drone-mesh ontology source for Foundry / AIP wildfire — Foundry Developer Tier request
priority: medium
intent: partnership-explore
gated_on: Foundry Developer Tier acceptance (free, capacity-capped); a working ontology import of our 6-object schema; first patrol hours so the ontology has real signal data underneath it
---

Hi,

PG&E running PSPS planning on Foundry, and the AIP Bootcamp wildfire curriculum that PVM has been hosting, are the two things that pulled me toward this email. I am building a small civilian-wildfire research project that maps cleanly onto an AIP-native ontology, and I would like to apply for a Foundry Developer Tier slot to wire the integration up properly.

The project is wildfire-watch (https://github.com/arigatoexpress/wildfire-watch). Open source, Apache-2.0, AOR is the Gunnison Valley plus Crested Butte corridor in Colorado. The architecture is deliberately upstream of Foundry, not competitive with it: drones produce structured signals, a JSON-schema-validated wire format (`wildfire_signal v1`) carries them, a downstream consumer (today, Sapphire's `signal_logger:18081` and a TAK / Cursor-on-Target emitter; tomorrow, an AIP ontology) reasons against them.

The 6-object ontology design from the Foundry research doc in the repo:

- **Zone** — patrol polygon, includes wilderness exclusions and partner-FD AOR.
- **Patrol** — a single drone flight, with route, scenario, and outcome.
- **Signal** — a `wildfire_signal v1` event (smoke, fire, thermal anomaly, wildlife, anomaly, system event), with confidence, risk score, recommended action, and frame URIs.
- **Asset** — drone hardware identity, firmware version, sensor configuration, BOM lineage (NDAA / Blue UAS substitutability tagged per-line).
- **Confirmation** — k-of-N swarm consensus event, joining ≥k Signals from distinct Assets within a spatial / temporal window.
- **Dispatch** — operator decision, `notify_operator` / `notify_fire_dept` / `loiter_and_capture` / `rtl`, with audit trail back to the Confirmation.

That ontology composes naturally on top of an existing PG&E or CAL FIRE Foundry instance — drone telemetry becomes a new ontology source rather than a parallel platform.

Specific asks, both low-friction:

1. A Foundry Developer Tier slot. I understand the tier is free and capacity-capped. I have working integration plumbing in the related Sapphire monorepo (`lib/foundry/`, `services/foundry_sync/`) and would use the Developer Tier to wire wildfire-watch's signals into a real Foundry instance and publish a public ontology demo.

2. A 30-minute conversation with whoever leads the AIP Bootcamp for Wildfire — I would like their honest read on whether wildfire-watch is something the next Bootcamp could include as a reference integration partner, or whether the timing is wrong for that. Either answer is useful.

Honest state: 240 tests passing, ~13,700 lines of Python, kinematic simulator + browser viewer + swarm consensus + GNSS-denied perception + TAK/CoT emitter all working. Zero flight hours, no signed customer, no trained ML model (FASDD → FLAME-2 fine-tune is a Phase 1 deliverable). The strategic posture in the repo's `docs/strategy/` directory is candid about where this is in the lifecycle.

I am not asking for a commercial deal. The honest read is that Palantir's pattern with projects this early is partnership and ontology distribution rather than acquisition, and I would rather match that pattern than misread it.

No rush. If the right path is the public partner program form rather than this email, point me there.

— TBD (operator name)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch
