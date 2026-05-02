"""Unit tests for the Mavic Mini flight-log GPS source.

Pure stdlib — synthesises CSVs in tmp_path and verifies parsing across
the four known dialects (DJI Fly, Airdata, DatCon, generic).

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/tests/test_mavic_log.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the parent ml/fire_detection importable when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.fire_detection.sources.mavic_log import (  # noqa: E402
    GpsFix,
    MavicFlightLog,
    parse_mavic_csv,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


GENERIC_CSV = """ts,lat,lon,alt_agl_m
0.00,38.8200,-106.9870,0.0
1.00,38.8201,-106.9869,5.0
2.00,38.8202,-106.9868,10.0
3.00,38.8203,-106.9867,12.0
"""

# DJI Fly app — note the unit-bracket suffixes that `_normalize` strips.
DJI_FLY_CSV = """OSD.flyTime [s],OSD.latitude,OSD.longitude,OSD.height [m],OSD.altitude [m]
0,38.8200,-106.9870,0.0,2750.0
0.5,38.8201,-106.9869,5.0,2755.0
1.0,38.8202,-106.9868,10.0,2760.0
"""

# Airdata.com — milliseconds, with a no-fix preamble row.
AIRDATA_CSV = """time(millisecond),latitude,longitude,height_above_takeoff(meters)
0,0.0,0.0,0.0
500,38.8201,-106.9869,5.0
1000,38.8202,-106.9868,10.0
"""

# DatCon / CsvView — uses colons in the column names.
DATCON_CSV = """Clock:offsetTime,GPS:Lat,GPS:Long,General:relativeHeight,General:absoluteAltitude
0,38.8200,-106.9870,0.0,2750.0
1,38.8201,-106.9869,5.0,2755.0
2,38.8202,-106.9868,10.0,2760.0
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# parse_mavic_csv — dialect coverage
# ---------------------------------------------------------------------------


def test_parse_generic_csv(tmp_path: Path) -> None:
    fixes = parse_mavic_csv(_write(tmp_path, "f.csv", GENERIC_CSV))
    assert len(fixes) == 4
    assert fixes[0] == GpsFix(0.0, 38.8200, -106.9870, 0.0, None)
    assert fixes[-1].t_offset_s == 3.0
    assert fixes[-1].alt_agl_m == 12.0


def test_parse_dji_fly_csv(tmp_path: Path) -> None:
    fixes = parse_mavic_csv(_write(tmp_path, "DJIFlight.csv", DJI_FLY_CSV))
    assert len(fixes) == 3
    # MSL altitude must come through when the DJI dialect provides it.
    assert fixes[0].alt_msl_m == 2750.0
    assert fixes[-1].alt_msl_m == 2760.0
    # to_coords includes alt_msl_m only when present.
    coords = fixes[0].to_coords()
    assert coords["lat"] == 38.8200
    assert coords["alt_agl_m"] == 0.0
    assert coords["alt_msl_m"] == 2750.0


def test_parse_airdata_csv_converts_ms_to_s(tmp_path: Path) -> None:
    fixes = parse_mavic_csv(_write(tmp_path, "airdata.csv", AIRDATA_CSV))
    # No-fix (lat=0,lon=0) row dropped, leaving two real fixes.
    assert len(fixes) == 2
    assert fixes[0].t_offset_s == pytest.approx(0.5)
    assert fixes[1].t_offset_s == pytest.approx(1.0)


def test_parse_datcon_csv(tmp_path: Path) -> None:
    fixes = parse_mavic_csv(_write(tmp_path, "datcon.csv", DATCON_CSV))
    assert len(fixes) == 3
    assert fixes[0].alt_msl_m == 2750.0


# ---------------------------------------------------------------------------
# parse_mavic_csv — robustness
# ---------------------------------------------------------------------------


def test_parse_drops_no_fix_rows(tmp_path: Path) -> None:
    body = "ts,lat,lon,alt_agl_m\n0.0,0.0,0.0,0.0\n1.0,38.0,-106.0,5.0\n"
    fixes = parse_mavic_csv(_write(tmp_path, "f.csv", body))
    assert len(fixes) == 1
    assert fixes[0].lat == 38.0


def test_parse_drops_unparseable_rows(tmp_path: Path) -> None:
    body = "ts,lat,lon,alt_agl_m\nbad,38.0,-106.0,5.0\n2.0,nope,-106.0,5.0\n3.0,38.1,-106.1,7.0\n"
    fixes = parse_mavic_csv(_write(tmp_path, "f.csv", body))
    assert len(fixes) == 1
    assert fixes[0].t_offset_s == 3.0


def test_parse_sorts_by_time(tmp_path: Path) -> None:
    body = "ts,lat,lon,alt_agl_m\n5.0,38.5,-106.0,5.0\n1.0,38.1,-106.0,5.0\n3.0,38.3,-106.0,5.0\n"
    fixes = parse_mavic_csv(_write(tmp_path, "f.csv", body))
    assert [f.t_offset_s for f in fixes] == [1.0, 3.0, 5.0]


def test_parse_strips_utf8_bom(tmp_path: Path) -> None:
    """DJI Fly's iOS export includes a BOM. csv.DictReader must handle it."""
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbf" + GENERIC_CSV.encode("utf-8"))
    fixes = parse_mavic_csv(p)
    assert len(fixes) == 4


def test_parse_unknown_dialect_raises(tmp_path: Path) -> None:
    body = "alpha,beta,gamma\n1,2,3\n"
    with pytest.raises(ValueError, match="unrecognised flight-log CSV"):
        parse_mavic_csv(_write(tmp_path, "f.csv", body))


def test_parse_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        parse_mavic_csv(tmp_path / "missing.csv")


def test_parse_empty_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.csv"
    p.write_text("")
    with pytest.raises(ValueError):
        parse_mavic_csv(p)


# ---------------------------------------------------------------------------
# MavicFlightLog — random-access + iteration
# ---------------------------------------------------------------------------


def test_flight_log_len_and_iter(tmp_path: Path) -> None:
    log = MavicFlightLog(_write(tmp_path, "f.csv", GENERIC_CSV))
    assert len(log) == 4
    assert [f.t_offset_s for f in log] == [0.0, 1.0, 2.0, 3.0]


def test_flight_log_at_returns_latest_at_or_before(tmp_path: Path) -> None:
    log = MavicFlightLog(_write(tmp_path, "f.csv", GENERIC_CSV))
    assert log.at(-1.0) is None, "before first sample -> None"
    assert log.at(0.0).t_offset_s == 0.0
    assert log.at(0.5).t_offset_s == 0.0
    assert log.at(1.99).t_offset_s == 1.0
    assert log.at(2.0).t_offset_s == 2.0
    assert log.at(99.0).t_offset_s == 3.0, "after last sample -> last fix"


def test_flight_log_to_coords_compatible_with_build_signal(tmp_path: Path) -> None:
    """The whole point of this module: the GpsFix.to_coords() output drops
    straight into infer.build_signal(coords=...)."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from infer import build_signal  # noqa: E402

    log = MavicFlightLog(_write(tmp_path, "f.csv", DJI_FLY_CSV))
    fix = log.at(1.0)
    assert fix is not None

    sig = build_signal(
        drone_id="wfw-mavic01",
        zone_id="gunnison-corridor",
        coords=fix.to_coords(),
        target_coords=None,
        signal_type="smoke",
        confidence=0.91,
        rgb_yolo_score=0.93,
        thermal_delta_c=18.5,
        frame_uris=["gs://test/frame.jpg"],
        risk_score=78.0,
        recommended_action="notify_operator",
    )
    assert sig["coords"]["lat"] == 38.8202
    assert sig["coords"]["alt_agl_m"] == 10.0
    assert sig["coords"]["alt_msl_m"] == 2760.0


def test_flight_log_fixes_returns_defensive_copy(tmp_path: Path) -> None:
    log = MavicFlightLog(_write(tmp_path, "f.csv", GENERIC_CSV))
    fixes = log.fixes()
    fixes.clear()
    assert len(log) == 4, "mutating the returned list must not affect the log"
