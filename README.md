# wildfire-watch

3D-printed, AI-enabled autonomous drones that patrol defined zones, photograph wildlife and ecology,
and feed real-time fire-risk intelligence to fire departments — minutes-to-hours before a
human spotter or satellite would catch a smoke plume.

## Vision

A mesh of low-cost (sub-$2.5k BOM) drones, each running on-board CV for smoke/flame and
wildlife detection, syncing telemetry to a Tailscale-meshed ground station, and pushing
risk-scored signals into the [Sapphire intelligence stack](https://github.com/arigatoexpress)
and downstream to fire-department TAK servers. Every flight produces a public-good
ecological dataset (wildlife sightings, fuel-load imagery) as a byproduct.

See [`docs/00-vision.md`](docs/00-vision.md) for the stakeholder pitch.

## Quick start (MVP — single drone, single zone)

```bash
# 1. Clone, install firmware deps
git clone <your-fork> && cd wildfire-watch

# 2. Print frame (links in hardware/bom.csv)
# 3. Flash ArduPilot Copter 4.6 to Cube Orange+ (firmware/README.md)
# 4. Flash Jetson Orin Nano Super with JetPack 6.2 (ml/fire_detection/README.md)
# 5. Define a zone
cp missions/zones.example.geojson missions/zones/my_zone.geojson

# 6. Train / pull fire-detection model
cd ml/fire_detection && python train.py --dataset fasdd --base yolov8n

# 7. Boot ground station
cd ground_station && docker compose up -d   # Mission Planner + TAK Server + MediaMTX

# 8. Wire signals into Sapphire (optional)
# Drone POSTs JSON to signal_logger:18081 — see sapphire_integration/README.md
```

## Repo layout

| Path | Purpose |
|---|---|
| `docs/` | Vision, architecture, BOM, ML, FAA, partnership, roadmap, ADRs |
| `hardware/` | CAD links, machine-readable BOM |
| `firmware/` | ArduPilot/PX4 config, parameter files, mission scripts |
| `ml/fire_detection/` | YOLOv8/v11 fire+smoke training + edge inference |
| `ml/wildlife_id/` | MegaDetector v6 + BirdNET integration |
| `ground_station/` | Mission Planner config, TAK server, MediaMTX video relay |
| `sapphire_integration/` | Signal schema + adapter to Sapphire `signal_logger:18081` |
| `missions/` | GeoJSON zone definitions |

## Status

MVP scaffolding only. No printed parts, no flight hours yet. See [`docs/60-roadmap.md`](docs/60-roadmap.md).

## License

Apache-2.0 — chosen over MIT for explicit patent grant; relevant given hardware,
firmware, and ML model contributions that may invite patent disputes from incumbent
drone manufacturers (DJI, Skydio). See [`LICENSE`](LICENSE).
