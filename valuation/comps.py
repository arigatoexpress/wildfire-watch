"""Comparable transactions loader.

Reads valuation/data/comps_2026.yaml into a list of typed records.
The YAML format is documented in valuation/data/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_COMPS = DATA_DIR / "comps_2026.yaml"


@dataclass
class Comp:
    target: str
    acquirer: str | None
    date: str
    amount_usd: float
    revenue_estimate_usd: float | None
    multiple: float | None
    archetype: str
    source: str
    notes: str = ""


def load_comps(path: Path | str | None = None) -> list[Comp]:
    """Load and validate comps from YAML.

    Skips entries that are missing required fields rather than crashing,
    so a partial / dirty file still produces a usable comp set.
    """
    p = Path(path) if path else DEFAULT_COMPS
    if not p.exists():
        return []
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    except Exception:
        return []
    out: list[Comp] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        target = entry.get("target")
        archetype = entry.get("archetype")
        amount = entry.get("amount_usd")
        if not target or not archetype or not isinstance(amount, (int, float)):
            continue
        out.append(
            Comp(
                target=str(target),
                acquirer=entry.get("acquirer"),
                date=str(entry.get("date", "")),
                amount_usd=float(amount),
                revenue_estimate_usd=(
                    float(entry["revenue_estimate_usd"])
                    if entry.get("revenue_estimate_usd") is not None
                    else None
                ),
                multiple=(
                    float(entry["multiple"])
                    if entry.get("multiple") is not None
                    else None
                ),
                archetype=str(archetype),
                source=str(entry.get("source", "")),
                notes=str(entry.get("notes", "")),
            )
        )
    return out


def by_archetype(comps: list[Comp], archetype: str) -> list[Comp]:
    return [c for c in comps if c.archetype == archetype]


def multiples_for(comps: list[Comp]) -> list[float]:
    """Return the non-null multiples in the comp set, sorted ascending."""
    out = sorted(c.multiple for c in comps if c.multiple is not None)
    return out


def archetype_summary(comps: list[Comp]) -> dict[str, dict[str, Any]]:
    """For each archetype, return count + low/mid/high multiple."""
    out: dict[str, dict[str, Any]] = {}
    arches = sorted({c.archetype for c in comps})
    for arche in arches:
        subset = by_archetype(comps, arche)
        mults = multiples_for(subset)
        if mults:
            low = mults[0]
            high = mults[-1]
            mid = mults[len(mults) // 2]
        else:
            low = mid = high = 0.0
        out[arche] = {
            "count": len(subset),
            "multiple_low": low,
            "multiple_mid": mid,
            "multiple_high": high,
        }
    return out
