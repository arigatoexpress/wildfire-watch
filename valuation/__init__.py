"""wildfire-watch intrinsic-value calculator + KPI dashboard.

Continuously updates a defensible valuation band as KPIs change.
Four methods: comparable_multiples, venture_method, dcf_lite, asset_floor.
The CLI snapshots a band per commit; the web panel renders the live band.
"""

__all__ = [
    "kpis",
    "comps",
    "methods",
    "engine",
    "recorder",
]
