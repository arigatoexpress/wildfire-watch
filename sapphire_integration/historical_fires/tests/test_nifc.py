"""Tests for the NIFC historic-fire ingester. Offline only."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from sapphire_integration.historical_fires import nifc, sources  # noqa: E402


def test_sources_registry_non_empty() -> None:
    assert len(sources.HISTORIC_SOURCES) >= 5
    for s in sources.HISTORIC_SOURCES:
        assert s.url.startswith("https://")
        assert s.license
        assert s.citation


def test_get_returns_known_source() -> None:
    s = sources.get("nifc_wfigs_perimeters")
    assert s is not None
    assert s.fetch_strategy == "arcgis_rest"


def test_get_returns_none_for_unknown() -> None:
    assert sources.get("nonexistent") is None


def test_fixture_loads_three_fires() -> None:
    fires = nifc.load_fixture()
    assert len(fires) == 3
    years = sorted(f.year for f in fires)
    assert years == [2018, 2020, 2022]


def test_fixture_fires_have_required_fields() -> None:
    fires = nifc.load_fixture()
    for f in fires:
        assert f.fire_id
        assert f.name
        assert f.year > 0
        assert f.acres_burned > 0
        assert f.polygon_geojson["type"] == "Polygon"
        assert -180 <= f.centroid_lon <= 180
        assert -90 <= f.centroid_lat <= 90
        assert f.state == "US-CO"
        assert f.county == "Gunnison"


def test_normalize_handles_epoch_milliseconds() -> None:
    feature = {
        "type": "Feature",
        "properties": {
            "OBJECTID": 999,
            "IncidentName": "Test",
            "FireDiscoveryDateTime": 1530710400000,  # 2018-07-04 16:00:00 UTC ms
            "GISAcres": 100.0,
            "FireCause": "Lightning",
            "POOState": "US-CO",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-107.0, 38.9], [-107.0, 38.91],
                             [-106.99, 38.91], [-106.99, 38.9], [-107.0, 38.9]]],
        },
    }
    f = nifc._normalize_nifc_feature(feature, "test")
    assert f is not None
    assert f.year == 2018
    assert f.start_date is not None
    assert f.start_date.startswith("2018-07-04")


def test_normalize_skips_features_without_polygon() -> None:
    feature = {"type": "Feature", "properties": {"IncidentName": "Bad"}, "geometry": None}
    assert nifc._normalize_nifc_feature(feature, "test") is None


def test_polygon_centroid_inside_polygon() -> None:
    poly = {
        "type": "Polygon",
        "coordinates": [[
            [-107.0, 38.9], [-107.0, 38.91],
            [-106.99, 38.91], [-106.99, 38.9],
            [-107.0, 38.9],
        ]],
    }
    lat, lon = nifc._polygon_centroid(poly)
    assert 38.89 < lat < 38.92
    assert -107.01 < lon < -106.98


def test_to_jsonl_round_trip(tmp_path: Path) -> None:
    fires = nifc.load_fixture()
    out = tmp_path / "fires.jsonl"
    n = nifc.to_jsonl(fires, out)
    assert n == 3
    text = out.read_text(encoding="utf-8")
    assert text.count("\n") == 3
    rows = [json.loads(line) for line in text.strip().split("\n")]
    assert len(rows) == 3
    assert all("fire_id" in r for r in rows)


def test_cache_key_deterministic() -> None:
    a = nifc._cache_key("foo", {"state": "CO"})
    b = nifc._cache_key("foo", {"state": "CO"})
    c = nifc._cache_key("foo", {"state": "MT"})
    assert a == b
    assert a != c


def test_load_cached_handles_missing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nifc, "CACHE_BASE", tmp_path / "nonexistent")
    assert nifc.load_cached("nifc_wfigs_perimeters") == []


def test_load_cached_reads_geojson(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(nifc, "CACHE_BASE", tmp_path)
    src_dir = tmp_path / "test_source"
    src_dir.mkdir(parents=True)
    fc = {"type": "FeatureCollection", "features": nifc.fixture_features()}
    (src_dir / "abc.geojson").write_text(json.dumps(fc), encoding="utf-8")

    fires = nifc.load_cached("test_source")
    assert len(fires) == 3
    assert {f.year for f in fires} == {2018, 2020, 2022}


def test_gunnison_bbox_well_formed() -> None:
    bbox = nifc.GUNNISON_COUNTY_BBOX
    assert bbox["min_lat"] < bbox["max_lat"]
    assert bbox["min_lon"] < bbox["max_lon"]
    # Bbox is inside Colorado
    assert 36.0 < bbox["min_lat"] < 41.5
    assert -110.0 < bbox["min_lon"] < -102.0


def test_corridor_bbox_inside_county_bbox() -> None:
    cb = nifc.CRESTED_BUTTE_CORRIDOR_BBOX
    co = nifc.GUNNISON_COUNTY_BBOX
    assert co["min_lat"] <= cb["min_lat"]
    assert co["max_lat"] >= cb["max_lat"]
    assert co["min_lon"] <= cb["min_lon"]
    assert co["max_lon"] >= cb["max_lon"]


def test_fetch_state_raises_on_non_arcgis() -> None:
    with pytest.raises(NotImplementedError):
        nifc.fetch_state(source_name="mtbs_burned_areas")


def test_fetch_state_raises_on_unknown_source() -> None:
    with pytest.raises(ValueError):
        nifc.fetch_state(source_name="not-a-real-source")
