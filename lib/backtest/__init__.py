"""Counterfactual replay of historic wildfires through the wildfire-watch fleet.

For each known historic fire (from `sapphire_integration.historical_fires`),
the backtest engine asks: "If a 3-drone wildfire-watch fleet had been
patrolling this AOR on this day, when would we have detected it?"

Outputs a per-fire `BacktestResult` containing the counterfactual
detection time, Δ-vs-historical-discovery, and the implied operational
benefit (acres saved at first-period fire-spread rate).

Pure stdlib. Deterministic given (fire, fleet_config, seed).
"""

from .engine import (
    BacktestResult,
    DetectionRoll,
    FleetConfig,
    backtest_fire,
    backtest_set,
    summarize,
)

__all__ = [
    "BacktestResult",
    "DetectionRoll",
    "FleetConfig",
    "backtest_fire",
    "backtest_set",
    "summarize",
]
