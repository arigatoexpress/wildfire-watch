# sapphire_integration/fuel_load

Public-data ingestion + evidence-derived priority weighting for the
wildfire-watch AOR zones.

## Why

The hand-set `fuel_load_class` strings on
`missions/zones/gunnison_crested_butte_corridor.geojson` had no evidence
backing. This package replaces them with a numeric `risk_score` (0-100)
derived from public-domain federal + Colorado-state-open data, plus a
class boundary that is publishable and reproducible.

## Sources

All sources are public domain (17 USC 105) or Colorado-state-open with
attribution required. Full registry in `sources.py`.

| Source | URL | License |
|---|---|---|
| USFS Insect & Disease Detection Survey | https://www.fs.usda.gov/science-technology/data-tools-products/fhp-mapping-reporting/detection-surveys | public_domain_federal |
| Colorado State Forest Service Annual Forest Health Report | https://csfs.colostate.edu/forest-management/forest-health-report-2024/insects-and-diseases/ | co_state_open_data |
| USFS Forest Inventory and Analysis (FIA) | https://research.fs.usda.gov/programs/fia | public_domain_federal |
| NIFC Interagency Fire Perimeter History | https://data-nifc.opendata.arcgis.com/datasets/nifc::interagencyfireperimeterhistory-all-years-view/about | public_domain_federal |
| MTBS Burn Severity | https://www.mtbs.gov/direct-download | cc0_1_0 |
| CO-WRAP / Colorado Wildfire Risk Public Viewer | https://co-pub.coloradoforestatlas.org/ | co_state_open_data |
| NOAA HRRR-Smoke (run-time, not used by classifier) | https://rapidrefresh.noaa.gov/hrrr/HRRRsmoke/ | public_domain_federal |

## Class boundaries

```
risk_score < 25         -> "low"
25 <= risk_score < 50   -> "moderate"
50 <= risk_score < 70   -> "moderate-high"
70 <= risk_score < 85   -> "high"
risk_score >= 85        -> "extreme"
```

## Risk score formula

Weighted blend of available evidence components. Missing components have
their weight redistributed pro-rata across the present components.

| Component | Source | Weight |
|---|---|---:|
| IDS overlap pct (severity-weighted) | USFS IDS | 0.35 |
| Historical-fire density (5km buffer) | NIFC IFPH | 0.20 |
| CO-WRAP risk score | Colorado State Forest Service | 0.25 |
| FIA canopy cover % | USFS FIA | 0.10 |
| Distance-to-WUI proxy | computed in-package from AOR.md anchors | 0.10 |

The WUI distance proxy uses fixed anchors at Crested Butte
(38.8697, -106.9878), Mt. Crested Butte (38.8975, -106.9647), and
Gunnison (38.5458, -106.9253). Within 1 km of any anchor the sub-score
is 100; beyond 10 km it's 0; linear in between.

## Pipeline

```
fetch.py            # HTTPS-only fetcher + on-disk cache (~/.cache/wildfire-watch/fuel_load/)
classifier.py       # zone polygon + datasets -> {fuel_load_class, risk_score, evidence, rationale}
pipeline.py         # FeatureCollection -> enriched FeatureCollection
cli.py              # `python -m sapphire_integration.fuel_load.cli ...`
```

## CLI

```bash
# List registered sources + their licenses + citations
python -m sapphire_integration.fuel_load.cli sources

# Fetch a network-available source into the cache
python -m sapphire_integration.fuel_load.cli fetch usfs_ids
python -m sapphire_integration.fuel_load.cli fetch nifc_fire_perimeters --force

# Enrich the canonical AOR zones GeoJSON
python -m sapphire_integration.fuel_load.cli enrich \
    missions/zones/gunnison_crested_butte_corridor.geojson \
    --out missions/zones/gunnison_crested_butte_corridor.enriched.geojson

# Optionally feed per-zone CO-WRAP + FIA values (manual sources):
python -m sapphire_integration.fuel_load.cli enrich \
    missions/zones/gunnison_crested_butte_corridor.geojson \
    --co-wrap-json data/cowrap_scores.json \
    --fia-json data/fia_canopy.json

# Classify one ad-hoc polygon
python -m sapphire_integration.fuel_load.cli classify-zone \
    --polygon '[[38.9035,-107.0060],[38.9165,-107.0060],[38.9165,-106.9940],[38.9035,-106.9940]]'
```

## Constraints

- Stdlib + lazy `requests` + `pyyaml` only. No GDAL, shapely, fiona.
- Polygon math reuses `sim/geofence.py`.
- HTTPS-only — `fetch.py` refuses non-HTTPS URLs.
- No network in tests; the bundled fixture is synthetic IDS data.

## Known gaps

- **CO-WRAP and FIA are manual-only.** CO-WRAP publishes a public
  viewer, not a clean GeoJSON tier; FIA plot coordinates are fuzzed by
  law (16 USC 1642(e)). Operator pulls these fields manually and
  feeds them via `--co-wrap-json` / `--fia-json`.
- **WUI proxy is the AOR.md anchor list, not a true LANDFIRE WUI
  raster.** Acceptable for Phase 0; revisit when WUI raster ingestion
  is wired up.
- **The IDS overlap math is a 30x30 sample-grid Monte Carlo on the
  zone bounding box.** Sub-meter accuracy on AOR-scale polygons; not
  appropriate above ~70 deg latitude.
