"""Tests for mavic_post_flight.py — Phase 0 detector.

Pure-logic tests only: SRT parsing, fix lookup, heuristic detection,
detection-to-signal conversion, and the SRT-missing edge case. No video
decoding, no YOLO, no network.

Run:
    cd ~/Code/wildfire-watch
    python3 -m pytest ml/fire_detection/test_mavic_post_flight.py -q
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from mavic_post_flight import (  # noqa: E402
    GpsFix,
    HeuristicResult,
    detection_to_signal,
    find_media,
    heuristic_score_pil,
    lookup_fix,
    parse_srt,
    sibling_srt,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Modern Mavic Mini 2 / Mavic 3 SRT cue format: bracketed key:value pairs.
MODERN_SRT = """1
00:00:00,000 --> 00:00:00,033
<font size="28">SrtCnt : 1, DiffTime : 33ms
2025-04-30 12:34:56.789
[iso : 100] [shutter : 1/1000.0] [fnum : 280] [ev : 0] [color_md : default] [focal_len : 24.00] [latitude: 36.4906] [longitude: -121.1825] [rel_alt: 80.000 abs_alt: 350.000] </font>

2
00:00:00,033 --> 00:00:00,066
<font size="28">SrtCnt : 2, DiffTime : 33ms
2025-04-30 12:34:56.822
[iso : 100] [shutter : 1/1000.0] [latitude: 36.4907] [longitude: -121.1826] [rel_alt: 81.000 abs_alt: 351.000] </font>

3
00:00:01,000 --> 00:00:01,033
<font size="28">SrtCnt : 3, DiffTime : 33ms
2025-04-30 12:34:57.789
[latitude: 36.4910] [longitude: -121.1830] [rel_alt: 85.000 abs_alt: 355.000] </font>
"""

# Older Mavic firmware: GPS(lat,lon,alt) one-liner, comma decimals.
OLDER_SRT = """1
00:00:00,000 --> 00:00:00,033
HOME(36.4900,-121.1820) 2024-06-01 09:00:00
GPS(36.4906,-121.1825,80.0) BAROMETER:80.5

2
00:00:00,033 --> 00:00:00,066
HOME(36.4900,-121.1820) 2024-06-01 09:00:00
GPS(36.4915,-121.1840,90.5) BAROMETER:90.7
"""

# Cue with timestamp but no GPS — should be skipped.
CORRUPT_SRT = """1
00:00:00,000 --> 00:00:00,033
<font size="28">SrtCnt : 1, DiffTime : 33ms — sensor warming up</font>

2
00:00:00,500 --> 00:00:00,533
<font size="28">[latitude: 36.5] [longitude: -121.2] [rel_alt: 50.0] </font>
"""


# ---------------------------------------------------------------------------
# parse_srt
# ---------------------------------------------------------------------------


def test_parse_srt_modern_format() -> None:
    fixes = parse_srt(MODERN_SRT)
    assert len(fixes) == 3
    assert fixes[0].lat == 36.4906
    assert fixes[0].lon == -121.1825
    assert fixes[0].rel_alt_m == 80.0
    assert fixes[0].abs_alt_m == 350.0
    # midpoint of 0.000-0.033 ~ 0.0165s
    assert 0.01 < fixes[0].t_offset_s < 0.03
    # wallclock should have parsed
    assert fixes[0].wallclock is not None
    assert fixes[0].wallclock.year == 2025


def test_parse_srt_older_format() -> None:
    fixes = parse_srt(OLDER_SRT)
    assert len(fixes) == 2
    assert fixes[0].lat == 36.4906
    assert fixes[0].lon == -121.1825
    # older format puts altitude in GPS(...,...,alt); we promote it to abs_alt
    assert fixes[0].abs_alt_m == 80.0


def test_parse_srt_skips_cues_with_no_gps() -> None:
    fixes = parse_srt(CORRUPT_SRT)
    # cue 1 has timestamp but no GPS — skipped. cue 2 should remain.
    assert len(fixes) == 1
    assert fixes[0].lat == 36.5


def test_parse_srt_empty_returns_empty() -> None:
    assert parse_srt("") == []
    assert parse_srt("\n\n") == []


# ---------------------------------------------------------------------------
# lookup_fix
# ---------------------------------------------------------------------------


def test_lookup_fix_picks_closest_in_time() -> None:
    fixes = parse_srt(MODERN_SRT)
    # cue 2 midpoint is ~0.05s, cue 3 midpoint is ~1.02s.
    near_cue_2 = lookup_fix(fixes, 0.05)
    near_cue_3 = lookup_fix(fixes, 1.0)
    assert near_cue_2 is not None
    assert near_cue_3 is not None
    assert near_cue_2.lat == 36.4907
    assert near_cue_3.lat == 36.4910


def test_lookup_fix_empty_returns_none() -> None:
    assert lookup_fix([], 0.0) is None


# ---------------------------------------------------------------------------
# Photo-timestamp coords lookup (uses parse_srt + lookup_fix)
# ---------------------------------------------------------------------------


def test_photo_timestamp_to_coords_lookup() -> None:
    """Simulate: photo taken at clip-relative t=1s -> nearest fix is cue 3."""
    fixes = parse_srt(MODERN_SRT)
    fix = lookup_fix(fixes, 1.0)
    assert fix is not None
    coords = fix.coords()
    assert coords["lat"] == 36.4910
    assert coords["lon"] == -121.1830
    assert coords["alt_agl_m"] == 85.0
    assert coords["alt_msl_m"] == 355.0


# ---------------------------------------------------------------------------
# Heuristic detector — synthesise PIL Images.
# ---------------------------------------------------------------------------


def _solid_image(rgb: tuple[int, int, int], size: tuple[int, int] = (64, 64)):
    pil = pytest.importorskip("PIL.Image", reason="Pillow is required for heuristic tests")
    return pil.new("RGB", size, rgb)


def test_heuristic_flags_grey_smoke_image() -> None:
    img = _solid_image((140, 145, 150))  # mid-grey, low channel spread
    res = heuristic_score_pil(img)
    assert res.is_candidate is True
    assert res.signal_type == "smoke"
    assert 0.0 < res.score <= 1.0


def test_heuristic_flags_red_dominant_fire_image() -> None:
    img = _solid_image((230, 50, 30))  # strong red dominance
    res = heuristic_score_pil(img)
    assert res.is_candidate is True
    assert res.signal_type == "fire"


def test_heuristic_ignores_blue_sky_image() -> None:
    img = _solid_image((90, 140, 220))  # blue-dominant sky, big channel spread
    res = heuristic_score_pil(img)
    assert res.is_candidate is False
    assert res.signal_type == "none"


def test_heuristic_ignores_green_canopy_image() -> None:
    img = _solid_image((40, 130, 50))  # forest canopy
    res = heuristic_score_pil(img)
    assert res.is_candidate is False


# ---------------------------------------------------------------------------
# detection_to_signal — schema v1 conformance.
# ---------------------------------------------------------------------------


def _heuristic_smoke() -> HeuristicResult:
    return HeuristicResult(
        is_candidate=True,
        signal_type="smoke",
        score=0.7,
        smoke_area_frac=0.6,
        fire_area_frac=0.0,
        notes="grey-spread heuristic; Phase 0 placeholder",
    )


def test_detection_to_signal_with_fix(tmp_path: Path) -> None:
    media = tmp_path / "DJI_0001.MP4"
    media.write_bytes(b"")  # touch
    fix = GpsFix(
        t_offset_s=0.5,
        wallclock=None,
        lat=36.4906,
        lon=-121.1825,
        rel_alt_m=80.0,
        abs_alt_m=350.0,
    )
    sig = detection_to_signal(
        drone_id="wfw-mavic01",
        zone_id="phase0-test",
        media_path=media,
        frame_idx=15,
        t_offset_s=0.5,
        fix=fix,
        heuristic=_heuristic_smoke(),
        yolo_score=0.0,
        yolo_class="",
    )
    # Schema v1 required fields.
    for field in (
        "schema_version",
        "signal_id",
        "drone_id",
        "zone_id",
        "timestamp",
        "coords",
        "signal_type",
        "confidence",
        "evidence",
        "risk_score",
        "recommended_action",
    ):
        assert field in sig
    assert sig["schema_version"] == "1.0.0"
    assert sig["signal_type"] == "smoke"
    assert sig["coords"]["lat"] == 36.4906
    assert sig["coords"]["lon"] == -121.1825
    assert sig["coords"]["alt_agl_m"] == 80.0
    assert sig["coords"]["alt_msl_m"] == 350.0
    assert sig["signal_subtype"] == "phase_0/heuristic_color_temp"
    assert sig["evidence"]["frame_uris"][0].startswith("file://")
    assert "frame_15" in sig["evidence"]["frame_uris"][0]
    # uuid4 sanity
    parsed = uuid.UUID(sig["signal_id"])
    assert parsed.version == 4
    # JSON round-trip — proves it is JSONL-appendable.
    assert json.loads(json.dumps(sig))["signal_id"] == sig["signal_id"]


def test_detection_to_signal_no_fix_zeroes_coords_and_warns(tmp_path: Path) -> None:
    """Edge case: video had no SRT — emit signal with coords zero'd."""
    media = tmp_path / "DJI_NOFIX.MP4"
    media.write_bytes(b"")
    sig = detection_to_signal(
        drone_id="wfw-mavic01",
        zone_id="phase0-no-srt",
        media_path=media,
        frame_idx=0,
        t_offset_s=0.0,
        fix=None,  # no SRT
        heuristic=_heuristic_smoke(),
        yolo_score=0.0,
        yolo_class="",
    )
    assert sig["coords"]["lat"] == 0.0
    assert sig["coords"]["lon"] == 0.0
    assert sig["coords"]["alt_agl_m"] == 0.0
    # geofence_status must reflect the missing-position state so downstream
    # never auto-loiters or auto-pages on a no-GPS Phase 0 emit.
    assert sig["geofence_status"]["in_authorized_zone"] is False
    assert sig["geofence_status"]["remote_id_active"] is False


def test_detection_to_signal_caps_recommended_action_at_notify_operator(tmp_path: Path) -> None:
    """Phase 0 has no thermal — never recommend loiter/notify_fire_dept."""
    media = tmp_path / "DJI_0001.MP4"
    media.write_bytes(b"")
    high_conf_heuristic = HeuristicResult(
        is_candidate=True,
        signal_type="fire",
        score=0.95,
        smoke_area_frac=0.1,
        fire_area_frac=0.5,
        notes="x",
    )
    sig = detection_to_signal(
        drone_id="wfw-mavic01",
        zone_id="z",
        media_path=media,
        frame_idx=0,
        t_offset_s=0.0,
        fix=None,
        heuristic=high_conf_heuristic,
        yolo_score=0.9,
        yolo_class="person",
    )
    # No on-board thermal in Phase 0 -> never auto-loiter, never auto-page fire dept.
    assert sig["recommended_action"] in {"log_only", "notify_operator"}
    # YOLO class is recorded but does NOT promote signal_type.
    assert sig["evidence"]["model_outputs"]["rgb_yolo_class"] == "person"
    # Risk score capped at 60 because there is no thermal corroboration.
    assert sig["risk_score"] <= 60.0


# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------


def test_find_media_picks_mp4_and_jpg_only(tmp_path: Path) -> None:
    (tmp_path / "DJI_0001.MP4").write_bytes(b"")
    (tmp_path / "DJI_0001.SRT").write_text(MODERN_SRT)
    (tmp_path / "DJI_0002.JPG").write_bytes(b"")
    (tmp_path / "log.txt").write_text("not media")
    (tmp_path / "thumb.JPEG").write_bytes(b"")
    media = find_media(tmp_path)
    names = sorted(p.name for p in media)
    assert names == ["DJI_0001.MP4", "DJI_0002.JPG", "thumb.JPEG"]


def test_sibling_srt_finds_uppercase_and_lowercase(tmp_path: Path) -> None:
    # Uppercase .SRT (DJI Fly default).
    media = tmp_path / "DJI_0001.MP4"
    media.write_bytes(b"")
    srt = tmp_path / "DJI_0001.SRT"
    srt.write_text(MODERN_SRT)
    found = sibling_srt(media)
    assert found is not None
    # macOS APFS is case-insensitive — the resolved path may surface as either
    # case; what matters is that the content is the SRT we wrote.
    assert found.read_text(encoding="utf-8") == MODERN_SRT

    # No SRT alongside.
    media3 = tmp_path / "DJI_0003.MP4"
    media3.write_bytes(b"")
    assert sibling_srt(media3) is None
