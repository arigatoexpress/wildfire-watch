# AGENTS.md — wildfire-watch

## What this repo does

County-scale autonomous wildfire detection platform. Pre-flight Python monorepo with synthetic-data ML, kinematic flight simulator, swarm consensus, GNSS-denied nav, and TAK/CoT interoperability. AOR: Gunnison Valley + Crested Butte, Colorado.

## Key directories and files

| Path | Role |
|---|---|
| `ml/fire_detection/` | Synthetic data, YOLOv8 training, inference gate |
| `sim/` | Kinematic flight simulator (stdlib only) |
| `sim/perception/` | GNSS-denied nav (VO, TRN, IMU, fusion) |
| `sim/swarm/` | Fleet + k-of-N consensus + comms model |
| `sim/web/` | Browser viewer (Flask + Leaflet + SSE) |
| `frontend/` | Admin dashboard — Cloud Run target |
| `valuation/` | Intrinsic-value engine + KPI dashboard |
| `sapphire_integration/` | `wildfire_signal` v1 schema, TAK/CoT emitter |
| `ground_station/` | Pi telemetry collectors |
| `hardware/bom.csv` | Phased BOM |
| `missions/zones/` | AOR zones + mission YAMLs |
| `AOR.md` | Operational area, airspace, partner fire departments |

## How to run tests / dev server

```bash
# Install
pip install -e ".[dev]"

# Tests (538 tests, < 10 s)
python3 -m pytest -q

# Simulator + viewer
python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5
python3 -m sim.web.server   # :8088

# Lint
ruff check --select E9,F63,F7,F82 .
```

## Safety boundaries

1. **Schema versioning** — bump `schema_version` and update all consumers if you change `sapphire_integration/wildfire_signal_schema.json`
2. **Signal-building SSoT** — do NOT reimplement `ml/fire_detection/infer.build_signal()` or `should_emit()`
3. **Simulator purity** — do NOT add NumPy, SciPy, or SimPy to `sim/`
4. **Wilderness geofences** — do NOT remove or weaken West Elk / Maroon Bells-Snowmass / Raggeds exclusions
5. **Dependency pinning** — use lower bounds (`>=`) in `pyproject.toml`, not hard `==` pins
6. **Do NOT** push directly to `main`. Open feature branches and merge via PR
7. **No emoji in source files**

## Current status

- 538 tests passing; full suite under 10 seconds
- ~13,700 LOC Python; simulation + valuation stable
- Zero flight hours; detector is a placeholder colour heuristic
- FASDD → FLAME-2 fine-tune is Phase 1 work
