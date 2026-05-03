"""Registry of public fuel-load + wildfire-risk data sources.

All entries are public-domain federal data (17 USC 105) or
Colorado-state open-data with permissive terms. No login-walled
or proprietary feeds.

Each `FuelLoadSource` carries:
  - `url`: canonical landing page or direct dataset URL
  - `license`: short token; see LICENSE_TOKENS below
  - `citation`: human-readable attribution to drop into reports
  - `fetch_strategy`: how `fetch.py` should pull this source
  - `freshness_days`: cache lifetime; older artifacts are re-fetched
  - `notes`: operator-facing instructions, esp. for manual-only sources
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

LICENSE_TOKENS = (
    "public_domain_federal",  # 17 USC 105 — federal works, no copyright
    "co_state_open_data",     # Colorado open-data terms; attribution required
    "cc0_1_0",                # CC0 1.0 Universal Public Domain Dedication
)


FetchStrategy = Literal["geojson_download", "raster_pull", "manual_only"]


@dataclass(frozen=True)
class FuelLoadSource:
    """One registered data source.

    `fetch_strategy` is advisory — `fetch.py` interprets it. Manual-only
    sources raise `FetchUnavailable` on `fetch_to_cache` with the `notes`
    field as the human-readable instruction.
    """

    name: str
    url: str
    license: str
    citation: str
    fetch_strategy: FetchStrategy
    freshness_days: int
    notes: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

REGISTERED_SOURCES: tuple[FuelLoadSource, ...] = (
    FuelLoadSource(
        name="usfs_ids",
        url="https://www.fs.usda.gov/science-technology/data-tools-products/fhp-mapping-reporting/detection-surveys",
        license="public_domain_federal",
        citation=(
            "USDA Forest Service, Forest Health Protection. Insect and "
            "Disease Detection Survey (IDS). Annual aerial-detection survey "
            "polygons. Public domain (17 USC 105)."
        ),
        fetch_strategy="geojson_download",
        freshness_days=365,
        notes=(
            "GeoJSON / Shapefile / GDB downloads available from the USFS "
            "FSGeodata Clearinghouse (https://data.fs.usda.gov/geodata/edw/datasets.php) "
            "and the ArcGIS Hub feature service "
            "(https://data-usfs.hub.arcgis.com/datasets/7ef417e53eaf4307a8d3d2c751e82026). "
            "Filter to GMUG National Forest, host = 'mountain pine beetle' or "
            "'spruce beetle', survey_year >= 2022."
        ),
    ),
    FuelLoadSource(
        name="csfs_forest_health_report",
        url="https://csfs.colostate.edu/forest-management/forest-health-report-2024/insects-and-diseases/",
        license="co_state_open_data",
        citation=(
            "Colorado State Forest Service, Colorado State University. "
            "2024 Forest Health Report — Insects and Diseases. Public access "
            "with attribution required."
        ),
        fetch_strategy="manual_only",
        freshness_days=365,
        notes=(
            "Annual PDF report; structured tables for beetle-kill acreage by "
            "county (Gunnison, Hinsdale, Saguache). Manual-only because the "
            "report is published as a PDF + HTML page, not a clean machine-"
            "readable feed. To use: download the PDF + the species pages, "
            "extract the per-county acreage tables, and feed them as the "
            "`csfs_summary` field on the classifier."
        ),
    ),
    FuelLoadSource(
        name="usfs_fia",
        url="https://research.fs.usda.gov/programs/fia",
        license="public_domain_federal",
        citation=(
            "USDA Forest Service. Forest Inventory and Analysis (FIA) "
            "DataMart. Public ground-survey plot data. Public domain (17 USC 105)."
        ),
        fetch_strategy="manual_only",
        freshness_days=730,
        notes=(
            "FIA plot data is point-sample only and the plot coordinates "
            "are FUZZED to protect landowner privacy (per 16 USC 1642(e)). "
            "Treat FIA-derived canopy_pct as a regional approximation, NOT "
            "a per-zone ground truth. To use: download the CO state CSV "
            "from https://research.fs.usda.gov/programs/fia/datamart and "
            "compute the regional median canopy_pct."
        ),
    ),
    FuelLoadSource(
        name="nifc_fire_perimeters",
        url="https://data-nifc.opendata.arcgis.com/datasets/nifc::interagencyfireperimeterhistory-all-years-view/about",
        license="public_domain_federal",
        citation=(
            "National Interagency Fire Center (NIFC). InterAgency Fire "
            "Perimeter History — All Years View. Maintained by the Wildland "
            "Fire Management Research, Development & Application program data team. "
            "Public domain."
        ),
        fetch_strategy="geojson_download",
        freshness_days=180,
        notes=(
            "Authoritative historic fire-perimeter polygons. Filter by "
            "geometry intersect against AOR bounding box; weight more recent "
            "fires higher (the `most_recent_fire_year` evidence field). "
            "Direct GeoJSON via the ArcGIS Hub /query?f=geojson endpoint."
        ),
    ),
    FuelLoadSource(
        name="mtbs_burn_severity",
        url="https://www.mtbs.gov/direct-download",
        license="cc0_1_0",
        citation=(
            "Monitoring Trends in Burn Severity (MTBS). Joint USDA Forest "
            "Service + USGS Earth Resources Observation and Science (EROS) "
            "Center program. Released under CC0 1.0 Universal Public Domain "
            "Dedication."
        ),
        fetch_strategy="raster_pull",
        freshness_days=365,
        notes=(
            "Burn-severity rasters (dNBR-derived). MTBS covers fires >=1,000 "
            "acres in the western US from 1984 onward. Raster pull is "
            "expensive — fetch only the bounding-box subset for the AOR. "
            "Direct GeoTIFF download per fire-id from "
            "https://www.mtbs.gov/direct-download."
        ),
    ),
    FuelLoadSource(
        name="co_wrap",
        url="https://co-pub.coloradoforestatlas.org/",
        license="co_state_open_data",
        citation=(
            "Colorado State Forest Service / Colorado State University. "
            "Colorado Wildfire Risk Assessment (CO-WRA) and Colorado "
            "Wildfire Risk Public Viewer (CO-WRAP). 2022 update. "
            "Open-data with attribution required."
        ),
        fetch_strategy="manual_only",
        freshness_days=365,
        notes=(
            "CO-WRAP exposes the wildfire-risk score via the Colorado Forest "
            "Atlas Wildfire Risk Reduction Planner — query by polygon and "
            "extract the `risk_index` and `burn_probability` raster values. "
            "Manual-only because the public viewer doesn't expose a clean "
            "GeoJSON tier — operator pulls the per-zone PDF report from "
            "co-pub.coloradoforestatlas.org and feeds the `risk_index` (0-5 "
            "scale, multiplied by 20 to map to our 0-100 risk_score) into "
            "the classifier as `co_wrap_risk_score`."
        ),
    ),
    FuelLoadSource(
        name="noaa_hrrr_smoke",
        url="https://rapidrefresh.noaa.gov/hrrr/HRRRsmoke/",
        license="public_domain_federal",
        citation=(
            "NOAA Earth System Research Laboratory. HRRR-Smoke "
            "(High-Resolution Rapid Refresh — Smoke) experimental forecast. "
            "Public domain (17 USC 105). Run every 6 hours; "
            "vertically integrated smoke + near-surface PM2.5."
        ),
        fetch_strategy="manual_only",
        freshness_days=1,
        notes=(
            "Run-time fire-weather model output. NOT used by the static "
            "fuel-load classifier — too volatile to commit into zone "
            "metadata. Documented here so the operator's run-time "
            "decision-support layer can pull it. Use `wildfire-watch` "
            "supervisor to fetch the latest run + extract the AOR cell."
        ),
    ),
)


def get_source(name: str) -> FuelLoadSource:
    """Look up a source by name. Raises KeyError if unregistered."""
    for src in REGISTERED_SOURCES:
        if src.name == name:
            return src
    raise KeyError(f"no registered fuel-load source named {name!r}")


__all__ = [
    "FuelLoadSource",
    "FetchStrategy",
    "LICENSE_TOKENS",
    "REGISTERED_SOURCES",
    "get_source",
]
