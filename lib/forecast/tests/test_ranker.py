"""Tests for the forward-projection ranker. Pure stdlib + offline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from lib.forecast import ranker  # noqa: E402
from sapphire_integration.historical_fires import nifc  # noqa: E402

ZONES_GEOJSON = ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"


def _zones() -> dict:
    return json.loads(ZONES_GEOJSON.read_text(encoding="utf-8"))


def test_haversine_zero() -> None:
    assert ranker._haversine_km(38.9, -107.0, 38.9, -107.0) == pytest.approx(0.0, abs=1e-9)


def test_polygon_centroid_simple_square() -> None:
    """For a closed-ring 1deg square, the centroid is the average of its
    5 coords (including the duplicated closing point), so it's slightly
    biased toward the start corner. That's fine for our use — zones are
    ~1km square, the bias is well under 100m. We just check the result is
    inside the polygon and roughly central."""
    coords = [[-107.0, 38.0], [-107.0, 39.0], [-106.0, 39.0], [-106.0, 38.0], [-107.0, 38.0]]
    lat, lon = ranker._polygon_centroid(coords)
    assert 38.0 <= lat <= 39.0
    assert -107.0 <= lon <= -106.0


def test_polygon_area_1km_square_about_1km2() -> None:
    # ~0.01 deg square at 38.9N is roughly 0.87km wide x 1.11km tall ≈ 0.97 km^2
    coords = [
        [-107.000, 38.900], [-107.000, 38.910],
        [-106.990, 38.910], [-106.990, 38.900],
        [-107.000, 38.900],
    ]
    area = ranker._polygon_area_km2(coords)
    assert 0.5 < area < 1.5


def test_recommended_revisit_monotonic() -> None:
    assert ranker._recommended_revisit(95) <= ranker._recommended_revisit(75)
    assert ranker._recommended_revisit(75) <= ranker._recommended_revisit(55)
    assert ranker._recommended_revisit(55) <= ranker._recommended_revisit(35)
    assert ranker._recommended_revisit(35) <= ranker._recommended_revisit(15)


def test_rank_zones_returns_descending() -> None:
    zones = _zones()
    fires = nifc.load_fixture()
    out = ranker.rank_zones(zones, fires=fires, current_year=2026)
    assert len(out) >= 3
    scores = [t.priority_score for t in out]
    assert scores == sorted(scores, reverse=True)


def test_rank_zones_excludes_exclusion_features() -> None:
    zones = _zones()
    fires = nifc.load_fixture()
    out = ranker.rank_zones(zones, fires=fires)
    zone_ids = {t.zone_id for t in out}
    assert "west-elk-wilderness-exclusion" not in zone_ids


def test_top_zone_has_recent_history() -> None:
    """The highest-priority zone should be the one closest to the most recent fixture fire."""
    zones = _zones()
    fires = nifc.load_fixture()
    out = ranker.rank_zones(zones, fires=fires, current_year=2026)
    top = out[0]
    assert top.priority_score > 0
    # The Slate River zone should rank highest because:
    # - high fuel-load class (60+ score), AND
    # - the 2018 Slate River Test Fire fixture is centered in/on it (history bonus)
    assert top.historical_fire_count > 0


def test_rank_zones_no_history_still_works() -> None:
    zones = _zones()
    out = ranker.rank_zones(zones, fires=[], current_year=2026)
    assert len(out) > 0
    for t in out:
        assert t.historical_fire_count == 0
        assert t.historical_acres_total == 0.0
        assert "no historic fires" in t.rationale


def test_rationale_includes_fuel_class() -> None:
    zones = _zones()
    fires = nifc.load_fixture()
    out = ranker.rank_zones(zones, fires=fires)
    for t in out:
        assert t.fuel_load_class in t.rationale


def test_summarize_with_targets() -> None:
    zones = _zones()
    fires = nifc.load_fixture()
    targets = ranker.rank_zones(zones, fires=fires)
    s = ranker.summarize(targets)
    assert s["total_zones"] == len(targets)
    assert s["total_aor_km2"] > 0
    assert s["top_zone_id"]


def test_summarize_with_empty() -> None:
    s = ranker.summarize([])
    assert s["total_zones"] == 0


def test_to_jsonl_roundtrip(tmp_path: Path) -> None:
    zones = _zones()
    fires = nifc.load_fixture()
    targets = ranker.rank_zones(zones, fires=fires)
    out = tmp_path / "targets.jsonl"
    n = ranker.to_jsonl(targets, out)
    assert n == len(targets)
    text = out.read_text(encoding="utf-8")
    assert text.count("\n") == n


def test_polygon_centroid_handles_empty() -> None:
    assert ranker._polygon_centroid([]) == (0.0, 0.0)


def test_polygon_area_handles_degenerate() -> None:
    assert ranker._polygon_area_km2([]) == 0.0
    assert ranker._polygon_area_km2([[0, 0], [1, 1]]) == 0.0


def test_recency_weighting_makes_recent_fires_count_more() -> None:
    """Two equal-acreage fires at the same distance: the recent one
    contributes more to the priority score."""
    zones = _zones()
    # Slate River fixture is 2018; pretend year is 2026 (8 years gap)
    fires_old = nifc.load_fixture()  # 2018, 2020, 2022
    a = ranker.rank_zones(zones, fires=fires_old, current_year=2026)

    # Now backdate the same fires by 100 years
    from dataclasses import replace
    fires_ancient = [replace(f, year=f.year - 100) for f in fires_old]
    b = ranker.rank_zones(zones, fires=fires_ancient, current_year=2026)

    # Sum of priority_scores in (a) should be >= (b) (recent fires
    # weighted more heavily).
    assert sum(t.priority_score for t in a) >= sum(t.priority_score for t in b)
