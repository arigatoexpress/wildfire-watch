# wildfire-watch admin frontend

Dedicated, dark-themed Flask operator console for the wildfire-watch
volunteer drone fleet. Reads validated signals from
`data/wildfire_signals.jsonl`, renders them on a Leaflet map over the
Gunnison-Crested Butte AOR, and exposes a small JSON API for the
client.

## What it shows

- **Live signal map** — markers colored by `risk_score` (green < 50,
  amber 50-74, red >= 75; heartbeats grey). AOR polygons from
  `missions/zones/gunnison_crested_butte_corridor.geojson` (West Elk
  Wilderness exclusion drawn dashed-red).
- **KPI strip** — 24h / 7d / all-time signal counts, highest-risk
  zone, last sensor heartbeat, on-disk webhook retry-queue depth.
- **Sensor health** — per-drone last-seen + signal counts. Online (<15
  min), stale (15-120 min), offline (older).
- **Recent signals table** — filterable by zone, signal type, minimum
  risk score.
- **How-to modal** — operator-facing primer on deploying a sensor,
  reading the dashboard, and what the AOR covers.

## Run locally

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m pip install flask
ADMIN_TOKEN=dev /usr/local/bin/python3 -m frontend.app --port 8090
# visit http://127.0.0.1:8090/?admin_token=dev
```

If `data/wildfire_signals.jsonl` is missing or empty, the dashboard
falls back to `frontend/fixtures/signals.jsonl` so the UI is testable
on day one.

Run tests:

```bash
/usr/local/bin/python3 -m pytest frontend/tests -q
```

## Auth (stub)

Every route except `/healthz/` is wrapped in `@requires_admin`. The
stub checks `X-Admin-Token` (or `?admin_token=` / `admin_token`
cookie) against the `ADMIN_TOKEN` env var. When `ADMIN_TOKEN` is unset
the gate is disabled — fine for local dev, never for prod.

Production will replace this with WebAuthn (separate lane, tracked in
project memory). The stub is sufficient for the first deploy.

## API

| Route | Description |
|---|---|
| `GET /healthz/` | service health, no auth |
| `GET /` | dashboard HTML |
| `GET /api/signals?zone=&signal_type=&min_risk=&limit=` | filtered signals |
| `GET /api/kpis` | aggregate counters |
| `GET /api/sensors` | per-drone health |
| `GET /api/aor` | AOR GeoJSON FeatureCollection |

## Deploy to Cloud Run

```bash
gcloud builds submit --config=frontend/cloudbuild.yaml \
  --project=tho-ai-agent \
  --substitutions=_REGION=us-central1,_SERVICE=wildfire-frontend

# Once green, map the public domain (one-time):
gcloud run domain-mappings create \
  --service=wildfire-frontend \
  --domain=wildfire.sapphirealpha.xyz \
  --region=us-central1 \
  --project=tho-ai-agent
```

The Dockerfile builds a slim Python 3.12 image, copies in
`frontend/` + `missions/`, and serves via gunicorn (2 workers x 4
threads). Memory limit 512Mi, max instances 3 — sufficient for a
read-heavy dashboard with O(thousands) signals in the JSONL.

## Layout

```
frontend/
  app.py                   # Flask factory + auth + aggregations
  fixtures/signals.jsonl   # 12-row demo dataset (used when sink empty)
  templates/index.html     # dashboard markup
  static/css/dashboard.css # dark theme matching Sapphire OS
  static/js/dashboard.js   # Leaflet + fetch + filter wiring
  tests/test_app.py        # Flask test_client smoke + unit tests
  Dockerfile               # Cloud Run image
  cloudbuild.yaml          # build + deploy pipeline
  README.md                # this file
```
