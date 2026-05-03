"""Public fuel-load + wildfire-risk data ingestion for wildfire-watch.

This package replaces the hand-set `fuel_load_class` strings on the AOR
zone GeoJSON features with evidence-derived classifications backed by
public-domain federal + Colorado-state-open data:

  - USFS Insect & Disease Detection Survey (IDS)
  - Colorado State Forest Service Annual Forest Health Report (CSFS)
  - USFS Forest Inventory and Analysis (FIA)
  - NIFC Interagency Fire Perimeter History
  - MTBS (Monitoring Trends in Burn Severity)
  - CO-WRAP / Colorado Wildfire Risk Public Viewer
  - NOAA HRRR-Smoke (run-time only — not used by classifier yet)

Public-API:
  - sources: registered FuelLoadSource entries (see sources.py)
  - classify_zone: turn zone polygon + datasets into fuel_load_class + risk_score
  - enrich_zones: pipeline to write an enriched GeoJSON

See README.md for the full source attribution + classifier formula.
"""

from __future__ import annotations

from .classifier import classify_zone
from .pipeline import enrich_zones
from .sources import FuelLoadSource, REGISTERED_SOURCES, get_source

__all__ = [
    "FuelLoadSource",
    "REGISTERED_SOURCES",
    "classify_zone",
    "enrich_zones",
    "get_source",
]
