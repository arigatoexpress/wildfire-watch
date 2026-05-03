"""Public data sources for historic fire perimeters + incident reports.

Every source is public-domain federal (17 U.S.C. Sec. 105) or open-data
state. Citations + URLs are part of the contract — they end up in the
fire-chief demo pack.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FetchStrategy = Literal[
    "arcgis_rest",     # ArcGIS REST query API, public, no auth
    "geojson_download",  # direct GeoJSON file download
    "raster_download",   # raster (TIFF/COG) download
    "manual_only",     # human download required (auth-gated, captcha, etc.)
]


@dataclass(frozen=True)
class HistoricFireSource:
    """One public-data source for historic-fire data."""

    name: str
    url: str
    license: str
    citation: str
    fetch_strategy: FetchStrategy
    coverage: str             # geographic coverage description
    earliest_year: int
    latest_year: int | None   # None = present
    notes: str = ""


# Canonical source registry. Re-source quarterly.
HISTORIC_SOURCES: tuple[HistoricFireSource, ...] = (
    HistoricFireSource(
        name="nifc_wfigs_perimeters",
        url=(
            "https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/"
            "WFIGS_Interagency_Perimeters_Current/FeatureServer/0"
        ),
        license="public_domain_federal",
        citation=(
            "National Interagency Fire Center (NIFC), Wildland Fire "
            "Interagency Geospatial Services (WFIGS) Interagency Perimeters."
        ),
        fetch_strategy="arcgis_rest",
        coverage="United States (all federal + state-managed fires)",
        earliest_year=2014,
        latest_year=None,
        notes=(
            "The current/year-to-date layer. Updated daily during fire "
            "season. Use the historical layer for archived years."
        ),
    ),
    HistoricFireSource(
        name="nifc_wfigs_perimeters_archive",
        url=(
            "https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/"
            "WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0"
        ),
        license="public_domain_federal",
        citation=(
            "National Interagency Fire Center (NIFC), WFIGS Interagency "
            "Perimeters - Year to Date archive."
        ),
        fetch_strategy="arcgis_rest",
        coverage="United States, year-to-date perimeters",
        earliest_year=2014,
        latest_year=None,
        notes="YTD layer; rolls over each calendar year.",
    ),
    HistoricFireSource(
        name="mtbs_burned_areas",
        url="https://www.mtbs.gov/direct-download",
        license="public_domain_federal",
        citation=(
            "Monitoring Trends in Burn Severity (MTBS), USGS + USDA Forest "
            "Service. Eidenshink et al. 2007."
        ),
        fetch_strategy="geojson_download",
        coverage="United States, fires >= 1000 acres (West) or 500 acres (East)",
        earliest_year=1984,
        latest_year=2022,
        notes=(
            "Released annually with ~2-year lag. Authoritative for severity "
            "classification (low / mod / high). Companion ZIP downloads "
            "include burn-severity rasters."
        ),
    ),
    HistoricFireSource(
        name="nifc_irwin_incidents",
        url=(
            "https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/services/"
            "WFIGS_Incident_Locations_Current/FeatureServer/0"
        ),
        license="public_domain_federal",
        citation=(
            "NIFC IRWIN (Integrated Reporting of Wildland Fire Information). "
            "Incident point data, daily-updated during fire season."
        ),
        fetch_strategy="arcgis_rest",
        coverage="United States",
        earliest_year=2014,
        latest_year=None,
        notes=(
            "Point-feature service. Use IncidentName + ContainmentDateTime "
            "to time-align with perimeter polygons."
        ),
    ),
    HistoricFireSource(
        name="ics_209_situational_reports",
        url="https://famit.nwcg.gov/applications/SIT209",
        license="public_domain_federal",
        citation=(
            "ICS-209 Situation Reports, National Wildfire Coordinating Group "
            "(NWCG). Daily incident reports from incident commanders."
        ),
        fetch_strategy="manual_only",
        coverage="United States",
        earliest_year=1999,
        latest_year=None,
        notes=(
            "Login-gated bulk export; per-incident view is public. We pull "
            "manually for major Colorado fires when assembling the demo. "
            "Programmatic access is on the FAMIT roadmap."
        ),
    ),
    HistoricFireSource(
        name="colorado_dnr_fire_history",
        url=(
            "https://opendata.arcgis.com/api/v3/datasets/"
            "26ed6f9a6e4a4b3082f2c0a00fd7b95f_0/downloads/"
            "data?format=geojson&spatialRefId=4326"
        ),
        license="co_state_open_data",
        citation=(
            "Colorado Department of Natural Resources, "
            "Colorado Wildfire History."
        ),
        fetch_strategy="geojson_download",
        coverage="Colorado",
        earliest_year=2002,
        latest_year=None,
        notes=(
            "Colorado-state authoritative. Smaller than NIFC for federal "
            "lands but has finer resolution on state-managed parcels."
        ),
    ),
    HistoricFireSource(
        name="usgs_lcms",
        url="https://www.fs.usda.gov/research/products/dataandtools/lcms",
        license="public_domain_federal",
        citation=(
            "USGS / USFS Landscape Change Monitoring System (LCMS). "
            "Annual change detection including fire disturbance."
        ),
        fetch_strategy="raster_download",
        coverage="Conterminous US + Alaska",
        earliest_year=1985,
        latest_year=2023,
        notes=(
            "30m resolution rasters; we use as a check on MTBS perimeters "
            "and as a proxy for post-fire vegetation recovery state."
        ),
    ),
    HistoricFireSource(
        name="noaa_storm_events_lightning",
        url="https://www.ncdc.noaa.gov/stormevents/",
        license="public_domain_federal",
        citation=(
            "NOAA National Centers for Environmental Information (NCEI), "
            "Storm Events Database (lightning + wildfire categories)."
        ),
        fetch_strategy="geojson_download",
        coverage="United States",
        earliest_year=1950,
        latest_year=None,
        notes=(
            "Lightning-strike density is a leading indicator for ignition. "
            "Used as a forecast input rather than a backtest input."
        ),
    ),
)


def list_sources() -> list[dict]:
    """Return source metadata as plain dicts for CLI / JSON output."""
    return [
        {
            "name": s.name,
            "url": s.url,
            "license": s.license,
            "citation": s.citation,
            "fetch_strategy": s.fetch_strategy,
            "coverage": s.coverage,
            "earliest_year": s.earliest_year,
            "latest_year": s.latest_year,
            "notes": s.notes,
        }
        for s in HISTORIC_SOURCES
    ]


def get(name: str) -> HistoricFireSource | None:
    for s in HISTORIC_SOURCES:
        if s.name == name:
            return s
    return None
