# wildfire-watch — Agent Guide

> **Read this file before modifying any code.**  
> This repo is a county-scale autonomous drone fleet for wildfire detection and ecological data.  
> It is pre-1.0, fast-moving, and safety-critical. When in doubt, ask.

---

## 1. Project Overview

**wildfire-watch** closes the 0–30 minute wildfire-detection gap in the wildland-urban interface (WUI).  
It is a Python monorepo that spans synthetic-data ML pipelines, a kinematic flight simulator, a swarm-consensus engine, a Flask frontend, a continuous valuation engine, and a bridge to the Sapphire intelligence stack.

**AOR:** Gunnison Valley + Crested Butte corridor, Gunnison County, Colorado.  
**Hardware tiers:** Phase 0 (DJI Mavic Mini), Phase 0.5 (sensors + LoRa), Phase 1 (Holybro X500 + Jetson Orin Nano Super).  
See [`AOR.md`](AOR.md) and [`CLAUDE.md`](CLAUDE.md) for operational context.

---

## 2. Monorepo Architecture

```
wildfire-watch
├── ml/                     # Machine learning
│   └── fire_detection/     # Synthetic data, training, inference, registry
├── sim/                    # Kinematic flight simulator + swarm
│   ├── perception/         # GNSS-denied nav (VO, TRN, IMU, fusion)
│   ├── swarm/              # Fleet + k-of-N consensus + comms model
│   ├── web/                # Browser viewer (Flask + Leaflet + SSE)
│   └── demo/               # Renderer / demo tools
├── frontend/               # Admin dashboard (Flask) — Cloud Run target
├── valuation/              # Intrinsic-value engine + KPI dashboard
├── sapphire_integration/   # Schema, TAK/CoT emitter, Foundry ontology
├── ground_station/         # Pi telemetry collectors
├── lib/                    # Shared backtest / forecast utilities
├── hardware/               # BOM (phased)
├── missions/               # AOR zones + mission YAMLs
├── docs/                   # Strategy, intel, simulation ladder
└── tests/                  # Cross-module integration tests
```

### 2.1 Package Descriptions

| Package | Tech Stack | Purpose |
|---|---|---|
| `ml/fire_detection` | Python 3.11+, PIL, NumPy, Ultralytics (lazy), OpenCV (lazy) | Synthetic fire/smoke dataset generator, YOLOv8 training loop, inference gate. |
| `sim` | **stdlib only** — no NumPy, SciPy, SimPy | Deterministic kinematic simulator, swarm consensus, GNSS-denied nav primitive. |
| `frontend` | Flask 3.x, Gunicorn, vanilla JS, Leaflet, Chart.js | Admin dashboard deployed to Cloud Run. |
| `valuation` | stdlib + PyYAML | Continuous intrinsic-value band (4 methods) + KPI CLI/dashboard. |
| `sapphire_integration` | Python, `requests`, `jsonschema` | `wildfire_signal` v1 schema, TAK/CoT XML emitter, Foundry ontology adapter. |
| `ground_station` | Python | Raspberry Pi heartbeat + system-event emitter. |
| `lib` | Python | Reusable backtest + forecast utilities. |

---

## 3. Development Commands

### 3.1 Install

```bash
# Light dev install (simulator + tests + lint — no heavy CV stack)
pip install -e ".[dev]"

# Full install (includes ultralytics, opencv, numpy, gcs, mavlink)
pip install -e ".[all]"

# ML-only install (Mac mini / Jetson)
pip install -e ".[ml]"
```

### 3.2 Test

```bash
# Full suite (538 tests, < 10 s on a modern laptop)
python3 -m pytest -q

# With coverage
python3 -m pytest -q --cov=sim --cov=sapphire_integration --cov=valuation --cov=ml

# Integration tests only
python3 -m pytest tests/integration -q -s

# Specific module
python3 -m pytest sim/swarm/tests -q
```

### 3.3 Lint

```bash
# Strict gate — syntax errors + undefined names (MUST pass)
ruff check --select E9,F63,F7,F82 .

# Advisory full rule set (should be clean, but non-blocking in CI)
ruff check .
ruff check . --fix
```

### 3.4 Build / Run

```bash
# Docker image for the admin frontend
docker build -f frontend/Dockerfile -t gcr.io/tho-ai-agent/wildfire-frontend .

# Run simulator + browser viewer
python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5
python3 -m sim.web.server   # http://127.0.0.1:8088

# Valuation snapshot
python3 -m valuation.cli snapshot
```

---

## 4. CI/CD Conventions

Workflow file: `.github/workflows/ci.yml`

### 4.1 Jobs

| Job | Trigger | Purpose |
|---|---|---|
| `lint` | push, PR | `ruff` strict gate + advisory output. |
| `test` | push, PR | pytest on Python 3.11 and 3.12 with coverage. |
| `integration` | push, PR | Cross-module end-to-end tests. |
| `schema-validate` | push, PR | JSON Schema 2020-12 metaschema validation. |
| `bom-validate` | push, PR | `hardware/bom.csv` sanity checks. |
| `valuation-snapshot` | push, PR | Emits valuation JSON artifact. |
| `deploy` | **push to `main` only** | Builds & pushes Docker image via Workload Identity Federation. |
| `ml-pipeline` | **push to `main` or `workflow_dispatch`** | Synthetic dataset generation + minimal training smoke test. |

### 4.2 Concurrency

A fresh push to a branch cancels in-flight runs for that branch (`cancel-in-progress: true`).

### 4.3 Commit Style

Prefer [Conventional Commits](https://www.conventionalcommits.org/):

- `feat(scope): ...`
- `fix(scope): ...`
- `docs(scope): ...`
- `style(scope): ...` (formatting, no logic change)
- `ci(scope): ...`
- `test(scope): ...`

---

## 5. Safety Boundaries — What Agents Must NOT Change

1. **Schema versioning**  
   Do NOT modify `sapphire_integration/wildfire_signal_schema.json` without bumping `schema_version` and updating every downstream consumer (infer.py, bridge, TAK emitter, tests, examples).

2. **Signal-building single source of truth**  
   Do NOT reimplement `ml/fire_detection/infer.build_signal()` or `infer.should_emit()`.  
   All emitters (simulator, swarm, post-flight, TAK) must compose against these functions.

3. **Simulator purity**  
   Do NOT add NumPy, SciPy, or SimPy to `sim/`. The simulator is deliberately stdlib-only for portability and fast cold-start.

4. **Wilderness geofences**  
   Do NOT remove or weaken the West Elk / Maroon Bells-Snowmass / Raggeds exclusion polygons. Wilderness boundaries are non-negotiable per 36 CFR 261.16.

5. **Dependency pinning policy**  
   Do NOT add hard `==` pins to `pyproject.toml` runtime dependencies. Use lower bounds (`>=`) so Phase 0 (Mac) and Phase 1 (Pi / Jetson) can resolve wheels without fights. Lockfiles belong in CI, not `pyproject.toml`.

6. **Branch discipline**  
   Do NOT push directly to `main`. Open a feature branch (`feat/*`, `fix/*`, `docs/*`) and merge via PR after CI passes.

7. **History**  
   Do NOT rewrite published history (`git rebase -i`, `git push --force`) without explicit confirmation.

8. **Code style**  
   No emoji in source files. stdlib-first where possible.

---

## 6. Deployment Procedures

### 6.1 Frontend (Cloud Run)

The admin frontend is containerised in `frontend/Dockerfile`.

**Manual (local):**
```bash
docker build -f frontend/Dockerfile -t gcr.io/tho-ai-agent/wildfire-frontend .
docker push gcr.io/tho-ai-agent/wildfire-frontend:latest
gcloud run deploy wildfire-frontend \
  --image gcr.io/tho-ai-agent/wildfire-frontend:latest \
  --region us-central1 --project tho-ai-agent --allow-unauthenticated
```

**CI (automated on `main`):**
The `deploy` job in `.github/workflows/ci.yml` authenticates via Google Cloud Workload Identity Federation, builds the image, and pushes to `gcr.io/tho-ai-agent/wildfire-frontend`.

> **Required setup** (operator one-time):  
> 1. Create a Workload Identity Pool + Provider in GCP (`tho-ai-agent`).  
> 2. Create a service account with `roles/storage.admin` and `roles/run.developer`.  
> 3. Bind the GitHub repo (`arigatoexpress/wildfire-watch`) to the provider.  
> 4. Fill in the `workload_identity_provider` and `service_account` values in `ci.yml`.

### 6.2 ML Training Pipeline

The `ml-pipeline` job runs on every `main` push:

1. Installs `.[dev,ml]`.
2. Generates a small synthetic dataset (`/tmp/synth-dataset`) — cached between runs.
3. Validates the manifest.
4. Runs a 1-epoch CPU smoke-test training loop to ensure the pipeline is intact.

To trigger manually:
```bash
gh workflow run ci.yml --ref main
```

---

## 7. Testing Requirements

- **538 tests** must pass before any merge to `main`.
- **Coverage** is reported per-job but not gated (advisory).
- **Integration tests** (`tests/integration/`) validate cross-module contracts.
- **Schema validation** is a hard gate — a malformed `wildfire_signal_schema.json` blocks CI.
- **BOM validation** is a hard gate — `hardware/bom.csv` must parse and contain required columns.
- **New features** must include tests. Prefer deterministic tests (use `--seed` in simulator scenarios).

---

## 8. Cross-References

- [`CLAUDE.md`](CLAUDE.md) — AI pair-programming context, gotchas, module map.
- [`AOR.md`](AOR.md) — Operational area, airspace, partner fire departments.
- [`SECURITY.md`](SECURITY.md) — Reporting vulnerabilities, scope, SLA.
- [`README.md`](README.md) — Human-facing quickstart, architecture diagram, roadmap.
- [`docs/SIMULATION_LADDER.md`](docs/SIMULATION_LADDER.md) — Tier 1 → Tier 4 simulation roadmap.
