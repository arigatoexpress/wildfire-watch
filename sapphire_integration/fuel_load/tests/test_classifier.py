"""Classifier tests — schema, weighted blend, boundary cases.

No network. The Slate River drainage zone is the canonical
high-evidence test case (heavy spruce beetle overlap from the bundled
fixture).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sapphire_integration.fuel_load import classifier as clf


REPO_ROOT = Path(__file__).resolve().parents[3]
ZONES_PATH = REPO_ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_zone_ring(zone_id: str) -> list[tuple[float, float]]:
    """Load the (lat, lon) outer ring for a named zone from the canonical
    AOR GeoJSON. Mirrors `pipeline._extract_ring_latlon`."""
    with ZONES_PATH.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        if (feat.get("properties") or {}).get("zone_id") == zone_id:
            outer = feat["geometry"]["coordinates"][0]
            return [(float(p[1]), float(p[0])) for p in outer]
    raise KeyError(f"no zone_id={zone_id!r} in {ZONES_PATH}")


def _load_ids_polygons_fixture() -> list[dict]:
    """Load the synthetic IDS fixture and convert to the classifier-shape."""
    with (FIXTURE_DIR / "sample_ids_polygon.geojson").open("r", encoding="utf-8") as f:
        gj = json.load(f)
    out: list[dict] = []
    for feat in gj["features"]:
        ring = feat["geometry"]["coordinates"][0]
        # GeoJSON [lon, lat] -> classifier (lat, lon).
        latlon = [(float(p[1]), float(p[0])) for p in ring]
        sev = (feat.get("properties") or {}).get("SEVERITY", "unknown")
        year = int((feat.get("properties") or {}).get("SURVEY_YEAR", 2024))
        out.append({"polygon": latlon, "severity": sev, "survey_year": year})
    return out


# ---------------------------------------------------------------------------
# Schema + dispatch
# ---------------------------------------------------------------------------

def test_classify_zone_schema_keys() -> None:
    """The result dict carries every documented field."""
    ring = _load_zone_ring("slate-river-drainage")
    out = clf.classify_zone(ring)
    assert {
        "fuel_load_class",
        "risk_score",
        "evidence",
        "rationale",
        "data_freshness_days_max",
    }.issubset(out.keys())
    ev = out["evidence"]
    assert {
        "ids_overlap_pct",
        "ids_severity_class",
        "historical_fires_in_buffer_5km",
        "most_recent_fire_year",
        "co_wrap_risk",
        "fia_canopy_pct",
        "wui_distance_km",
    }.issubset(ev.keys())


def test_classify_zone_returns_known_class_string() -> None:
    ring = _load_zone_ring("slate-river-drainage")
    out = clf.classify_zone(ring)
    assert out["fuel_load_class"] in {"low", "moderate", "moderate-high", "high", "extreme"}


def test_classify_zone_score_in_range() -> None:
    for zid in (
        "slate-river-drainage",
        "cement-creek-drainage",
        "east-river-corridor",
    ):
        ring = _load_zone_ring(zid)
        out = clf.classify_zone(ring)
        assert 0.0 <= out["risk_score"] <= 100.0, f"{zid}: out of range"


def test_classify_zone_rejects_degenerate_polygon() -> None:
    with pytest.raises(ValueError):
        clf.classify_zone([(38.0, -107.0), (38.1, -107.0)])


# ---------------------------------------------------------------------------
# Class boundary tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "score,expected",
    [
        (0.0, "low"),
        (24.0, "low"),
        (24.999, "low"),
        (25.0, "moderate"),
        (49.999, "moderate"),
        (50.0, "moderate-high"),
        (69.999, "moderate-high"),
        (70.0, "high"),
        (84.999, "high"),
        (85.0, "extreme"),
        (100.0, "extreme"),
    ],
)
def test_class_boundary(score: float, expected: str) -> None:
    assert clf._class_for_score(score) == expected


# ---------------------------------------------------------------------------
# IDS overlap
# ---------------------------------------------------------------------------

def test_slate_river_with_heavy_spruce_overlap_scores_higher() -> None:
    """The bundled IDS fixture covers most of slate-river-drainage with
    severity=heavy. The risk score should be materially higher than with
    no IDS evidence."""
    ring = _load_zone_ring("slate-river-drainage")
    no_ids = clf.classify_zone(ring)
    with_ids = clf.classify_zone(ring, ids_polygons=_load_ids_polygons_fixture())
    assert with_ids["risk_score"] > no_ids["risk_score"]
    assert with_ids["evidence"]["ids_overlap_pct"] > 50.0
    assert with_ids["evidence"]["ids_severity_class"] == "heavy"


def test_ids_overlap_pct_zero_when_polygon_disjoint() -> None:
    """A polygon far from any IDS poly produces 0% overlap."""
    far_ring = [
        (40.0, -120.0),
        (40.01, -120.0),
        (40.01, -119.99),
        (40.0, -119.99),
        (40.0, -120.0),
    ]
    out = clf.classify_zone(far_ring, ids_polygons=_load_ids_polygons_fixture())
    assert out["evidence"]["ids_overlap_pct"] == 0.0


# ---------------------------------------------------------------------------
# Pro-rata weight redistribution
# ---------------------------------------------------------------------------

def test_missing_components_redistribute_weight() -> None:
    """When CO-WRAP and FIA and IDS and historical fires are all missing,
    the score is driven entirely by the WUI proxy. With Slate River near
    Mt. Crested Butte the WUI sub-score should be high (~70+)."""
    ring = _load_zone_ring("slate-river-drainage")
    out = clf.classify_zone(ring)
    # Only WUI present → score equals the WUI sub-score.
    expected_wui = clf._wui_distance_to_subscore(out["evidence"]["wui_distance_km"])
    assert abs(out["risk_score"] - expected_wui) < 0.01


def test_weighted_blend_present_components_normalize_to_one() -> None:
    components = {
        "ids": 100.0,
        "historical_fires": None,
        "co_wrap": 0.0,
        "fia_canopy": None,
        "wui_distance": None,
    }
    # Only IDS=100 and CO-WRAP=0 present. Their original weights are
    # 0.35 + 0.25 = 0.60. After pro-rata renorm the IDS component is
    # 0.35/0.60 ≈ 58.3% and CO-WRAP is 0.25/0.60 ≈ 41.7%. Score ≈ 58.3.
    score = clf._weighted_blend(components)
    assert 58.0 < score < 58.5


# ---------------------------------------------------------------------------
# Historical fires
# ---------------------------------------------------------------------------

def test_historical_fires_recent_year_bumps_score() -> None:
    ring = _load_zone_ring("slate-river-drainage")
    centroid_lat = sum(p[0] for p in ring) / len(ring)
    centroid_lon = sum(p[1] for p in ring) / len(ring)
    # One synthetic fire perimeter overlapping the zone in the recent past.
    fires = [
        {
            "perimeter": [
                (centroid_lat - 0.005, centroid_lon - 0.005),
                (centroid_lat + 0.005, centroid_lon - 0.005),
                (centroid_lat + 0.005, centroid_lon + 0.005),
                (centroid_lat - 0.005, centroid_lon + 0.005),
                (centroid_lat - 0.005, centroid_lon - 0.005),
            ],
            "fire_year": 2023,
            "fire_name": "Synthetic Recent",
        },
    ]
    out = clf.classify_zone(ring, historical_fires=fires, reference_year=2026)
    assert out["evidence"]["historical_fires_in_buffer_5km"] == 1
    assert out["evidence"]["most_recent_fire_year"] == 2023


def test_historical_fires_old_year_no_bonus() -> None:
    ring = _load_zone_ring("slate-river-drainage")
    centroid_lat = sum(p[0] for p in ring) / len(ring)
    centroid_lon = sum(p[1] for p in ring) / len(ring)
    fires = [
        {
            "perimeter": [
                (centroid_lat - 0.005, centroid_lon - 0.005),
                (centroid_lat + 0.005, centroid_lon - 0.005),
                (centroid_lat + 0.005, centroid_lon + 0.005),
                (centroid_lat - 0.005, centroid_lon + 0.005),
                (centroid_lat - 0.005, centroid_lon - 0.005),
            ],
            "fire_year": 1960,
            "fire_name": "Synthetic Ancient",
        },
    ]
    out_old = clf.classify_zone(ring, historical_fires=fires, reference_year=2026)
    fires[0]["fire_year"] = 2023
    out_recent = clf.classify_zone(ring, historical_fires=fires, reference_year=2026)
    assert out_recent["risk_score"] > out_old["risk_score"]


# ---------------------------------------------------------------------------
# CO-WRAP + FIA + WUI
# ---------------------------------------------------------------------------

def test_co_wrap_score_clamped() -> None:
    ring = _load_zone_ring("slate-river-drainage")
    out = clf.classify_zone(ring, co_wrap_risk_score=999.0)
    assert out["evidence"]["co_wrap_risk"] == 100.0


def test_fia_canopy_drives_higher_score() -> None:
    ring = _load_zone_ring("east-river-corridor")
    low = clf.classify_zone(ring, fia_canopy_pct=10.0)
    high = clf.classify_zone(ring, fia_canopy_pct=80.0)
    assert high["risk_score"] > low["risk_score"]


def test_wui_distance_drives_score_for_close_zones() -> None:
    """A zone right on top of Crested Butte should produce a high WUI sub-score."""
    cb_lat, cb_lon = 38.8697, -106.9878
    ring = [
        (cb_lat - 0.001, cb_lon - 0.001),
        (cb_lat + 0.001, cb_lon - 0.001),
        (cb_lat + 0.001, cb_lon + 0.001),
        (cb_lat - 0.001, cb_lon + 0.001),
        (cb_lat - 0.001, cb_lon - 0.001),
    ]
    out = clf.classify_zone(ring)
    assert out["evidence"]["wui_distance_km"] < 1.0
    # WUI sub-score caps at 100 within WUI_FULL_DISTANCE_KM; pure-WUI score = 100.
    assert out["risk_score"] == 100.0


def test_rationale_mentions_drivers() -> None:
    ring = _load_zone_ring("slate-river-drainage")
    out = clf.classify_zone(
        ring,
        ids_polygons=_load_ids_polygons_fixture(),
        co_wrap_risk_score=80.0,
    )
    rationale = out["rationale"]
    assert "IDS" in rationale or "beetle" in rationale.lower()
    assert "CO-WRAP" in rationale
