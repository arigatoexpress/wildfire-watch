"""Historic-fire ingestion for wildfire-watch.

Pulls from public NIFC + MTBS data sources. Used by the backtest engine
(`lib.backtest`) to replay historic fires through our drone fleet as
counterfactuals — the data hook for the fire-chief demo.
"""

from .nifc import (
    HistoricFire,
    fetch_gunnison_county,
    fetch_state,
    load_cached,
)
from .sources import HISTORIC_SOURCES, HistoricFireSource

__all__ = [
    "HistoricFire",
    "HistoricFireSource",
    "HISTORIC_SOURCES",
    "fetch_gunnison_county",
    "fetch_state",
    "load_cached",
]
