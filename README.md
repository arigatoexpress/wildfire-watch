# wildfire-watch

[![tests](https://img.shields.io/badge/tests-538%20passing-brightgreen)](#status)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)
[![status](https://img.shields.io/badge/status-pre--flight-orange)](#status)
[![CI](https://github.com/arigatoexpress/wildfire-watch/actions/workflows/ci.yml/badge.svg)](https://github.com/arigatoexpress/wildfire-watch/actions/workflows/ci.yml)

**A county-scale autonomous drone fleet that detects wildfires before human spotters can.**

The first 30 minutes decide whether a fire stays under an acre or burns 1,000 structures. Satellites and 911 calls miss that window in the wildland-urban interface; this project is designed to fill the gap.

## What this does

A pre-flight Python monorepo spanning synthetic-data ML pipelines, a kinematic flight simulator, swarm consensus, and TAK/CoT interoperability. The target AOR is Gunnison Valley + Crested Butte, Colorado.

**Status: simulation and software only. Zero flight hours. No trained production ML model.**

## Quick start

```bash
# Install
pip install -e ".[dev]"

# Run full test suite (under 10 seconds)
python3 -m pytest -q

# Fly one drone with a synthetic plume
python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5

# View the flight in browser
python3 -m sim.web.server   # http://127.0.0.1:8088

# Valuation snapshot
python3 -m valuation.cli snapshot
```

## Architecture

```
ml/fire_detection/      Synthetic data, YOLOv8 training, inference gate
sim/                    Kinematic flight simulator + swarm + perception
frontend/               Admin dashboard (Flask) — Cloud Run target
valuation/              Intrinsic-value engine + KPI dashboard
sapphire_integration/   Schema, TAK/CoT emitter, Foundry adapter
ground_station/         Raspberry Pi telemetry collectors
hardware/               Phased BOM with Blue-UAS-substitutable parts
missions/zones/         AOR zones with wilderness exclusions
```

## Key features

- **Kinematic flight simulator** — deterministic seeding, JSONL logs, browser viewer
- **Multi-drone swarm + k-of-N consensus** — lossy-comms model, fused risk scoring
- **GNSS-denied navigation primitive** — VO + TRN + IMU fusion with spoof detection
- **TAK / Cursor-on-Target emitter** — 8 type-code mappings over TCP/UDP/TLS/multicast
- **Continuous valuation engine** — 4-method valuation band (comp, venture, DCF-lite, asset-floor)
- **Blue-UAS-substitutable BOM** — 3D-printable airframe, open parts list

## Tech stack

- Python 3.11+ (stdlib-first in `sim/`)
- Flask 3.x, Leaflet, Chart.js for frontend
- Ultralytics YOLOv8 (lazy-loaded), OpenCV (lazy-loaded)

## Hardware tiers

| Phase | Cost | Mission |
|---|---|---|
| **Phase 0** | $0 | DJI Mavic Mini + simulator-only autonomy |
| **Phase 0.5** | $215 | + RTL-SDR, sensors, LoRa mesh, edge YOLOv8 |
| **Phase 1** | $2,613 | Holybro X500 + Jetson Orin Nano + RGB/LWIR fusion |

## Governance notes

- **Simulation-only** — no real flight operations without FAA authorization
- **Wilderness geofences** — West Elk, Maroon Bells-Snowmass, Raggeds are no-fly per 36 CFR 261.16
- **NDAA compliance path** — DJI is a Phase 0 stopgap; Holybro/Cube/Jetson is the target stack
- No active fire penetration; detection and notification only

## Agent collaborators

See [AGENTS.md](AGENTS.md) for monorepo architecture, safety boundaries, test requirements, and deployment procedures.

## License

[Apache-2.0](LICENSE)
