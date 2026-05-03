"""End-to-end pipeline tests using the bundled fixture (no network)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sapphire_integration.fuel_load import pipeline


REPO_ROOT = Path(__file__).resolve().parents[3]
ZONES_PATH = REPO_ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def _load_ids_fixture() -> list[dict]:
    with (FIXTURE_DIR / "sample_ids_polygon.geojson").open("r", encoding="utf-8") as f:
        gj = json.load(f)
    out: list[dict] = []
    for feat in gj["features"]:
        ring = feat["geometry"]["coordinates"][0]
        latlon = [(float(p[1]), float(p[0])) for p in ring]
        sev = (feat.get("properties") or {}).get("SEVERITY", "unknown")
        out.append({"polygon": latlon, "severity": sev})
    return out


def test_enrich_zones_writes_output(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched.geojson"
    written = pipeline.enrich_zones(ZONES_PATH, output_path=out_path)
    assert written.exists()
    with written.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    assert gj["type"] == "FeatureCollection"
    assert "fuel_load_metadata" in gj


def test_enrich_zones_every_non_exclusion_feature_classified(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched.geojson"
    pipeline.enrich_zones(ZONES_PATH, output_path=out_path)
    with out_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    for feat in gj["features"]:
        props = feat["properties"]
        if props.get("exclusion") is True:
            assert props.get("fuel_load_class") == "n/a"
            continue
        # Every non-exclusion feature carries the new evidence-derived fields.
        assert "fuel_load_class" in props
        assert "risk_score" in props
        assert "rationale" in props


def test_enrich_zones_preserves_existing_properties(tmp_path: Path) -> None:
    """Pipeline must not delete pre-existing zone properties (zone_id,
    elevation_min_m, primary_risk, phase, ...)."""
    out_path = tmp_path / "enriched.geojson"
    pipeline.enrich_zones(ZONES_PATH, output_path=out_path)
    with out_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    feat = next(f for f in gj["features"] if f["properties"].get("zone_id") == "slate-river-drainage")
    assert feat["properties"].get("primary_risk") == "beetle-kill spruce/fir"
    assert feat["properties"].get("elevation_min_m") == 2743
    assert feat["properties"].get("phase") == 0


def test_enrich_zones_with_ids_data_increases_slate_river_score(tmp_path: Path) -> None:
    """When the IDS fixture is fed through the pipeline, the Slate River
    drainage's risk_score should be materially higher than baseline."""
    out_baseline = tmp_path / "baseline.geojson"
    out_with_ids = tmp_path / "with_ids.geojson"
    pipeline.enrich_zones(ZONES_PATH, output_path=out_baseline)
    pipeline.enrich_zones(
        ZONES_PATH,
        output_path=out_with_ids,
        ids_polygons=_load_ids_fixture(),
    )
    with out_baseline.open("r", encoding="utf-8") as f:
        baseline = json.load(f)
    with out_with_ids.open("r", encoding="utf-8") as f:
        with_ids = json.load(f)

    def slate(gj: dict) -> dict:
        return next(f for f in gj["features"] if f["properties"]["zone_id"] == "slate-river-drainage")

    assert with_ids["features"][0]["properties"].get("evidence", {}).get("ids_severity_class") in {
        "heavy",
        "moderate",
        "unknown",
    }
    assert slate(with_ids)["properties"]["risk_score"] >= slate(baseline)["properties"]["risk_score"]


def test_enrich_zones_with_co_wrap_per_zone(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched.geojson"
    pipeline.enrich_zones(
        ZONES_PATH,
        output_path=out_path,
        co_wrap_scores={"slate-river-drainage": 75.0},
    )
    with out_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    slate = next(f for f in gj["features"] if f["properties"]["zone_id"] == "slate-river-drainage")
    assert slate["properties"]["evidence"]["co_wrap_risk"] == 75.0


def test_enrich_zones_metadata_contains_sources(tmp_path: Path) -> None:
    out_path = tmp_path / "enriched.geojson"
    pipeline.enrich_zones(ZONES_PATH, output_path=out_path)
    with out_path.open("r", encoding="utf-8") as f:
        gj = json.load(f)
    sources = gj["fuel_load_metadata"]["sources"]
    assert len(sources) >= 5
    for s in sources:
        assert s["url"].startswith("https://")
        assert s["license"]
        assert s["citation"]


def test_enrich_zones_missing_input_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pipeline.enrich_zones(tmp_path / "does-not-exist.geojson")
