# wildfire-watch sim viewer

Browser-based visualizer for flights produced by the `~/Code/wildfire-watch/sim/`
kinematic simulator.

- Leaflet 2D map (planned route + flown polyline + drone marker + signal pins + geofence)
- Live fusion-gate charts (Chart.js): rgb_score, thermal_delta_c, persistence
- SSE replay at configurable speed
- Post-flight analysis panel (path length, area covered, signal stats, gate hit-rate)

Vanilla JS + Leaflet + Chart.js loaded from a CDN. **No npm, no webpack, no React.**

## Run

```sh
cd ~/Code/wildfire-watch
python3 -m sim.web.server
# open http://127.0.0.1:8088
```

By default the server scans `~/wildfire-watch-flights/` for real flights produced
by the sim. Until SIM-A produces one, the **bundled fixture** at
`sim/web/fixtures/sample_flight/` is selected automatically.

CLI options:

```sh
python3 -m sim.web.server --port 8088 --host 127.0.0.1 \
    --flights-root ~/wildfire-watch-flights
```

Environment variables:

- `WFW_PORT` (default `8088`)
- `WFW_HOST` (default `127.0.0.1`)

## Endpoints

| Path | Notes |
|------|-------|
| `GET /` | the SPA |
| `GET /api/healthz` | liveness |
| `GET /api/flights` | list of available flights (fixture first, then real flights newest-first) |
| `GET /api/flights/<id>/manifest` | mission/scenario manifest |
| `GET /api/flights/<id>/flight_log` | first 5000 rows of flight_log.jsonl (paginatable via `?since=<ts>&limit=N`) |
| `GET /api/flights/<id>/signals` | all emitted wildfire_signal events |
| `GET /api/flights/<id>/analysis` | post-flight summary (see `analysis.py:summarize`) |
| `GET /api/flights/<id>/replay?speed=10` | text/event-stream of flight_log rows |

The bundled fixture's id is `fixture:sample_flight`. Real flights use their
directory name (e.g. `SIM-2026-05-01T17-30-00_demo_patrol`).

## Analysis

`analysis.py` is **CLI-runnable without flask**:

```sh
python3 -m sim.web.analysis sim/web/fixtures/sample_flight
```

`area_covered_km2` is the lat/lon **bounding-box area** of the flown polyline.
This is a fast, deterministic upper bound; if SIM-A wants a tighter estimate
later (convex hull or buffered swept-path), swap the implementation in
`bounding_box_km2`.

## Tests

```sh
cd ~/Code/wildfire-watch
python3 -m pytest sim/web/tests/ -q
```

## Layout

```
sim/web/
├── README.md
├── server.py             Flask app
├── analysis.py           post-flight metrics, CLI-runnable
├── templates/index.html  SPA
├── static/
│   ├── app.js            vanilla state machine + event handlers
│   ├── styles.css
│   └── img/drone-icon.svg
├── fixtures/sample_flight/   pre-canned 211-row flight, 1 signal
└── tests/                Flask test client + analysis math
```
