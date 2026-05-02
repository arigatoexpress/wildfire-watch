# Foundry — wildfire-watch ontology layer

Per `docs/intel/foundry-research-2026-05-01.md`, Foundry is the **ontology + AIP demo layer**, not the system of record. The system of record is PostGIS (`../postgis/`). Foundry pulls from Postgres on a 15-minute schedule via the existing Sapphire `lib/foundry/sync.py` daemon, exactly the same pattern used for trading signals.

## Files

| Path | Purpose |
|---|---|
| `ontology.py` | 6 ontology object types as Python dataclasses + serializers (`to_foundry_json`, `from_foundry_json`) + adapters from v1 wildfire_signals + GeoJSON features. |
| `tests/test_ontology.py` | 13 tests: round-trip serialization, adapter correctness, schema-version pin. |

## Ontology object types

| Foundry name | Python class | Primary key | Mirrors |
|---|---|---|---|
| `wfw.Drone` | `Drone` | `drone_id` (regex `^wfw-[a-z0-9]{4,16}$`) | airframe + RPIC + insurance + maintenance |
| `wfw.Zone` | `Zone` | `zone_id` | GeoJSON polygon + fuel-load class + elevation band; `is_exclusion=True` for wilderness etc. |
| `wfw.FireDepartmentUnit` | `FireDepartmentUnit` | `unit_id` | partner agencies; `engagement_status` tracks LOA progression |
| `wfw.FlightLog` | `FlightLog` | `flight_id` (UUIDv4) | one flight session — sim or real |
| `wfw.BatteryCycle` | `BatteryCycle` | `cycle_id` (UUIDv4) | airworthiness + maintenance |
| `wfw.WildfireSignal` | `WildfireSignal` | `signal_id` (UUIDv4 from drone) | the v1 schema as a Foundry object; `raw_payload` carries the full v1 JSON for forward-compat |

Reuses Sapphire's existing `Alert` and `Incident` ontology objects (defined in `~/Code/Sapphire/docs/foundry-ontology-schema.md`) for downstream rollups.

## Why a Python copy of the ontology?

1. **Source of truth.** wildfire-watch is the upstream of the schema; Foundry pulls from us, not the reverse. If Developer Tier access is denied or revoked, the Python module + the PostGIS adapter still gives us a working ontology layer.
2. **Round-trip testable.** Every serialization is JSON-clean and reversible. The 13 tests guarantee.
3. **Foundry-agnostic interface.** The object shape is defined here. The Foundry ontology is Just Another Sink — like PostGIS, like the v1 JSONL, like the dashboard SSE stream.
4. **Lazy import the Foundry SDK.** This module has zero dependencies. The actual Foundry network calls live in `~/Code/Sapphire/lib/foundry/client.py`, which is bearer-authenticated and OAuth-capable but lazy-imported inside the daemon.

## Status (2026-05-02)

- Schema defined ✓
- Tests passing ✓ (13/13)
- Foundry-side bindings: **TBD** — gated on Developer Tier approval per outreach kit Email 5.
- Live ingest from PostGIS: **TBD** — needs `~/Code/Sapphire/services/foundry_sync/` configured for the wildfire ontology.

## Example

```python
from sapphire_integration.foundry import (
    wildfire_signal_from_v1,
    to_foundry_json,
)

# v1 JSON payload from the wildfire bridge
v1 = {
    "schema_version": "1.0.0",
    "signal_id": "...",
    "drone_id": "wfw-unit01",
    "zone_id": "slate-river-drainage",
    "timestamp": "2026-05-02T22:00:00+00:00",
    "coords": {"lat": 38.9105, "lon": -107.0010, "alt_agl_m": 80.0},
    "signal_type": "smoke",
    "confidence": 0.91,
    "evidence": {"frame_uris": ["gs://bucket/frame.jpg"]},
    "risk_score": 78.0,
    "recommended_action": "notify_operator",
}

obj = wildfire_signal_from_v1(v1)
foundry_payload = to_foundry_json(obj)
# {"type":"wfw.WildfireSignal","primaryKey":"...","properties":{...}}
```
