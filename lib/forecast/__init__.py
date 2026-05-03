"""Forward-projection scout-target ranker for wildfire-watch.

Given:
- The historic-fire backtest output (`lib.backtest`)
- The AOR zones (`missions/zones/gunnison_crested_butte_corridor.geojson`)
- Optional fuel-load enrichment (planned: `sapphire_integration.fuel_load`)

Produces:
- A ranked list of scout-target zones for the upcoming fire season,
  with priority scores + rationale + recommended patrol cadence.

Output is what the operator brings to the fire chief: "Based on 8 historic
fires in this corridor and our backtest, here are the 5 zones I want
patrolled at 12-minute revisit through August."
"""

from .ranker import ScoutTarget, rank_zones, summarize

__all__ = ["ScoutTarget", "rank_zones", "summarize"]
