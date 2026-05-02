"""wildfire-watch — Mavic Mini post-flight detector (Phase 0).

Phase 0 reality check: the DJI Mavic Mini 1/2 is a ~249 g consumer drone
with no on-board AI hooks. The user flies it manually, lands, drops the SD
card into a folder on the Mac mini, and runs this script. This is a
post-flight pipeline, not a live one.

Pipeline:
  1. Walk a flight folder for *.MP4 / *.JPG.
  2. For each media file, parse the sibling *.SRT subtitle to build a
     timestamp -> (lat, lon, rel_alt) lookup.
  3. Sample frames (videos: every ~1s; photos: once) and run YOLOv8n
     (COCO-pretrained) for a coarse "person/car/truck/bird" pass to
     have *something* working today; on top of that, apply a colour /
     brightness heuristic to flag candidate smoke and fire pixels.
     COCO has no "fire" or "smoke" class — that is what Phase 1's
     FASDD/FLAME fine-tune is for. The heuristic exists so the
     end-to-end pipeline can be exercised today.
  4. For each candidate detection, emit a wildfire_signal v1 via
     `build_signal()` from `infer.py` (signal_type=smoke, with the
     `signal_subtype="phase_0/heuristic_color_temp"` annotation).
  5. Optional --pipe-to-sapphire: forwards each signal to
     ~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py
     (action=ingest), exactly the same surface as ml/fire_detection/demo.py.

Usage:
    python3 ml/fire_detection/mavic_post_flight.py FLIGHT_DIR
    python3 ml/fire_detection/mavic_post_flight.py FLIGHT_DIR --pipe-to-sapphire
    python3 ml/fire_detection/mavic_post_flight.py FLIGHT_DIR --no-yolo  # heuristic only

Constraints honoured:
  - ultralytics + opencv are LAZY-imported. `--help` and the test suite
    work in a stock venv with only stdlib + Pillow.
  - Schema v1 conformance via `build_signal()` from infer.py — no
    schema duplication.
  - No emoji in code.

DJI SRT subtitle format (DJI Fly app, Mavic Mini 2 firmware as of 2024-2025):

    1
    00:00:00,000 --> 00:00:00,033
    <font size="28">SrtCnt : 1, DiffTime : 33ms
    2025-04-30 12:34:56.789
    [iso : 100] [shutter : 1/1000.0] [fnum : 280] [ev : 0] [color_md : default]
    [focal_len : 24.00] [latitude: 36.4906] [longitude: -121.1825]
    [rel_alt: 80.000 abs_alt: 350.000] </font>

Older firmwares use a slightly different schema (HOME/GPS/BAROMETER
key=value blocks); we tolerate both.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).parent))
from infer import build_signal  # noqa: E402

logger = logging.getLogger("wildfire_watch.mavic_post_flight")

VIDEO_EXTS = {".mp4", ".mov"}
PHOTO_EXTS = {".jpg", ".jpeg"}
SAPPHIRE_BRIDGE = (
    Path.home()
    / "Code"
    / "Sapphire"
    / "plugins"
    / "claw-sapphire"
    / "tools"
    / "wildfire.py"
)

# Default frame sample rate for videos (Hz). Mavic Mini records at 30/60 fps;
# we don't need every frame to flag a persistent smoke plume.
DEFAULT_VIDEO_SAMPLE_HZ = 1.0

# Heuristic thresholds. These are deliberately loose — Phase 0 is "prove
# the pipeline works"; Phase 1 replaces this with the FASDD fine-tune.
SMOKE_GREY_MIN = 90        # min mean RGB for smoke candidate
SMOKE_GREY_MAX = 200       # max mean RGB
SMOKE_CHANNEL_SPREAD = 25  # max |R-G|, |G-B|, |R-B| (smoke is near-grey)
SMOKE_MIN_AREA_FRAC = 0.005  # min fraction of frame that must be "smoke"
FIRE_RED_DOMINANCE = 60    # R - max(G,B) for fire-pixel
FIRE_MIN_AREA_FRAC = 0.001


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GpsFix:
    """A single timestamped GPS fix from the SRT track."""
    t_offset_s: float       # seconds from clip start
    wallclock: datetime | None  # absolute wallclock if SRT had it
    lat: float
    lon: float
    rel_alt_m: float
    abs_alt_m: float | None

    def coords(self) -> dict[str, float]:
        c: dict[str, float] = {
            "lat": self.lat,
            "lon": self.lon,
            "alt_agl_m": self.rel_alt_m,
        }
        if self.abs_alt_m is not None:
            c["alt_msl_m"] = self.abs_alt_m
        return c


_TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_LAT_RE = re.compile(r"latitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
_LON_RE = re.compile(r"longitude\s*[:=]\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
# rel_alt may appear as "rel_alt: 80.000" or "rel_alt=80.000"
_REL_ALT_RE = re.compile(r"rel_alt\s*[:=]\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
_ABS_ALT_RE = re.compile(r"abs_alt\s*[:=]\s*([-+]?\d+(?:\.\d+)?)", re.IGNORECASE)
# Older firmware: GPS(lat,lon,alt) one-liner
_OLDER_GPS_RE = re.compile(
    r"GPS\s*\(\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*,\s*([-+]?\d+(?:\.\d+)?)\s*\)"
)
_WALLCLOCK_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:[.,](\d+))?"
)


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(text: str) -> list[GpsFix]:
    """Parse a DJI .SRT subtitle file into a list of GpsFix.

    Tolerant of both the modern Mavic Mini 2 / Mavic 3 schema (bracketed
    key:value pairs) and older firmware schemas (GPS(lat,lon,alt) lines).
    Cues with no extractable lat/lon are skipped.
    """
    fixes: list[GpsFix] = []
    # Split on blank-line cue separators. Cues use the standard SRT shape:
    # idx \n hh:mm:ss,mmm --> hh:mm:ss,mmm \n payload...
    blocks = re.split(r"\r?\n\r?\n", text.strip())
    for block in blocks:
        if not block.strip():
            continue
        ts_match = _TS_RE.search(block)
        if not ts_match:
            continue
        start_s = _to_seconds(*ts_match.group(1, 2, 3, 4))
        end_s = _to_seconds(*ts_match.group(5, 6, 7, 8))
        midpoint = (start_s + end_s) / 2.0

        lat: float | None = None
        lon: float | None = None
        rel_alt: float = 0.0
        abs_alt: float | None = None

        m = _LAT_RE.search(block)
        if m:
            lat = float(m.group(1))
        m = _LON_RE.search(block)
        if m:
            lon = float(m.group(1))
        m = _REL_ALT_RE.search(block)
        if m:
            rel_alt = float(m.group(1))
        m = _ABS_ALT_RE.search(block)
        if m:
            abs_alt = float(m.group(1))

        if lat is None or lon is None:
            m = _OLDER_GPS_RE.search(block)
            if m:
                lat = float(m.group(1))
                lon = float(m.group(2))
                if abs_alt is None:
                    abs_alt = float(m.group(3))

        if lat is None or lon is None:
            continue  # cue had a timestamp but no GPS — skip

        wallclock: datetime | None = None
        wm = _WALLCLOCK_RE.search(block)
        if wm:
            try:
                date_part, time_part = wm.group(1), wm.group(2)
                frac = wm.group(3) or "0"
                # pad to microseconds
                frac = (frac + "000000")[:6]
                wallclock = datetime.fromisoformat(f"{date_part}T{time_part}.{frac}").replace(
                    tzinfo=UTC
                )
            except ValueError:
                wallclock = None

        fixes.append(
            GpsFix(
                t_offset_s=midpoint,
                wallclock=wallclock,
                lat=lat,
                lon=lon,
                rel_alt_m=rel_alt,
                abs_alt_m=abs_alt,
            )
        )
    return fixes


def lookup_fix(fixes: list[GpsFix], t_offset_s: float) -> GpsFix | None:
    """Pick the closest GpsFix to t_offset_s. None if no fixes."""
    if not fixes:
        return None
    return min(fixes, key=lambda f: abs(f.t_offset_s - t_offset_s))


# ---------------------------------------------------------------------------
# Heuristic detector — placeholder for the FASDD/FLAME fine-tune in Phase 1.
# ---------------------------------------------------------------------------


@dataclass
class HeuristicResult:
    is_candidate: bool
    signal_type: str  # "smoke" | "fire" | "none"
    score: float      # pseudo-confidence in [0, 1]
    smoke_area_frac: float
    fire_area_frac: float
    notes: str


def heuristic_score_pil(image) -> HeuristicResult:
    """Rough colour/brightness check on a PIL Image. Phase 0 placeholder.

    - Smoke: a contiguous-ish chunk of near-grey pixels (channels close to
      each other, mid brightness).
    - Fire: pixels where red dominates green and blue.

    Returns a HeuristicResult. This is intentionally dumb. It exists so
    the end-to-end pipeline can fire signals on real flight footage today.
    Replace with the FASDD-pretrained YOLO once Phase 1 lands.
    """
    img = image.convert("RGB")
    # Downsample for speed — we don't need megapixel resolution for a
    # colour-frequency heuristic.
    img.thumbnail((320, 320))
    raw = img.tobytes()  # H*W*3 bytes, RGBRGBRGB...
    total = (len(raw) // 3) or 1
    pixels = (
        (raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)
    )

    smoke_pixels = 0
    fire_pixels = 0
    for r, g, b in pixels:
        max_chan = max(r, g, b)
        min_chan = min(r, g, b)
        spread = max_chan - min_chan
        mean = (r + g + b) / 3
        if SMOKE_GREY_MIN <= mean <= SMOKE_GREY_MAX and spread <= SMOKE_CHANNEL_SPREAD:
            smoke_pixels += 1
        if (r - max(g, b)) >= FIRE_RED_DOMINANCE and r > 150:
            fire_pixels += 1

    smoke_frac = smoke_pixels / total
    fire_frac = fire_pixels / total

    if fire_frac >= FIRE_MIN_AREA_FRAC:
        score = min(1.0, 0.5 + fire_frac * 5.0)
        return HeuristicResult(
            is_candidate=True,
            signal_type="fire",
            score=score,
            smoke_area_frac=smoke_frac,
            fire_area_frac=fire_frac,
            notes="red-channel-dominance heuristic; Phase 0 placeholder",
        )
    if smoke_frac >= SMOKE_MIN_AREA_FRAC:
        score = min(1.0, 0.4 + smoke_frac * 2.0)
        return HeuristicResult(
            is_candidate=True,
            signal_type="smoke",
            score=score,
            smoke_area_frac=smoke_frac,
            fire_area_frac=fire_frac,
            notes="grey-spread heuristic; Phase 0 placeholder",
        )
    return HeuristicResult(
        is_candidate=False,
        signal_type="none",
        score=0.0,
        smoke_area_frac=smoke_frac,
        fire_area_frac=fire_frac,
        notes="below thresholds",
    )


def yolo_corroborate(image, model) -> tuple[float, str]:
    """Optional COCO-YOLO pass. Returns (score, top_class).

    COCO has no fire/smoke class; this is a corroboration signal only.
    Detecting "person" or "car" in an aerial frame raises the priority
    of any heuristic positive (population at risk). If ultralytics is
    not installed, callers skip this.
    """
    try:
        results = model.predict(image, verbose=False, imgsz=640)
    except Exception as exc:  # noqa: BLE001 — we want to fall through cleanly
        logger.warning("YOLO predict failed: %s", exc)
        return (0.0, "")
    if not results:
        return (0.0, "")
    res = results[0]
    if res.boxes is None or len(res.boxes) == 0:
        return (0.0, "")
    # ultralytics Results: boxes.conf is a tensor; pull max confidence safely.
    try:
        confs = res.boxes.conf.tolist()
        cls_ids = res.boxes.cls.tolist()
        names = res.names
    except AttributeError:
        return (0.0, "")
    if not confs:
        return (0.0, "")
    idx_max = max(range(len(confs)), key=lambda i: confs[i])
    return (float(confs[idx_max]), str(names.get(int(cls_ids[idx_max]), "?")))


# ---------------------------------------------------------------------------
# Frame iteration. opencv is LAZY-imported so --help works without it.
# ---------------------------------------------------------------------------


def iter_video_samples(video_path: Path, sample_hz: float) -> Iterator[tuple[float, "object"]]:
    """Yield (t_offset_s, PIL.Image) tuples sampled at sample_hz from a video.

    Lazy-imports cv2 and PIL. If cv2 is missing, raises ImportError with a
    clear message — caller can choose to skip videos.
    """
    import cv2  # noqa: PLC0415
    from PIL import Image  # noqa: PLC0415

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise OSError(f"could not open video: {video_path}")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(fps / sample_hz)))
        idx = 0
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            if idx % step == 0:
                t_offset_s = idx / fps
                # cv2 is BGR; PIL expects RGB.
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                yield (t_offset_s, Image.fromarray(frame_rgb))
            idx += 1
    finally:
        cap.release()


def load_photo(photo_path: Path):
    """Open a photo as a PIL Image. Lazy-imports PIL."""
    from PIL import Image  # noqa: PLC0415
    return Image.open(photo_path)


# ---------------------------------------------------------------------------
# Sapphire bridge piping (mirrors demo.py)
# ---------------------------------------------------------------------------


def pipe_to_sapphire_bridge(signal: dict) -> dict:
    if not SAPPHIRE_BRIDGE.exists():
        return {"ok": False, "error": f"bridge not found: {SAPPHIRE_BRIDGE}"}
    payload = json.dumps({"action": "ingest", "signal": signal})
    proc = subprocess.run(
        ["python3", str(SAPPHIRE_BRIDGE)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        return {"ok": False, "stderr": proc.stderr.strip()}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "raw": proc.stdout}


# ---------------------------------------------------------------------------
# Detection -> signal
# ---------------------------------------------------------------------------


def detection_to_signal(
    *,
    drone_id: str,
    zone_id: str,
    media_path: Path,
    frame_idx: int,
    t_offset_s: float,
    fix: GpsFix | None,
    heuristic: HeuristicResult,
    yolo_score: float,
    yolo_class: str,
) -> dict:
    """Build a wildfire_signal v1 from a Phase 0 detection."""
    if fix is not None:
        coords = fix.coords()
    else:
        coords = {"lat": 0.0, "lon": 0.0, "alt_agl_m": 0.0}

    # Phase 0 has no thermal camera — we synthesise a thermal_delta_c of 0.
    # The fusion gate in infer.py would reject this; that is intentional.
    # We still emit so downstream sees the candidate, but recommended_action
    # is at most notify_operator, never auto-loiter.
    confidence = max(heuristic.score, yolo_score * 0.5)
    risk_score = round(confidence * 60.0, 2)  # cap at 60 since no thermal corroboration
    if confidence >= 0.8:
        recommended = "notify_operator"
    else:
        recommended = "log_only"

    frame_uri = f"file://{media_path.resolve()}#frame_{frame_idx}_t={t_offset_s:.2f}s"
    signal = build_signal(
        drone_id=drone_id,
        zone_id=zone_id,
        coords=coords,
        target_coords=None,
        signal_type=heuristic.signal_type if heuristic.signal_type != "none" else "anomaly",
        confidence=round(confidence, 3),
        rgb_yolo_score=round(yolo_score, 3),
        thermal_delta_c=0.0,
        frame_uris=[frame_uri],
        risk_score=risk_score,
        recommended_action=recommended,
    )
    # Tag this signal as Phase 0 / heuristic so downstream can filter.
    signal["signal_subtype"] = "phase_0/heuristic_color_temp"
    # Note: yolo_class is COCO (person/car/bird/...). It does NOT mean fire.
    # We attach it for triage but never let it gate the signal_type.
    if yolo_class:
        signal["evidence"]["model_outputs"]["rgb_yolo_class"] = yolo_class
    if fix is None:
        signal["geofence_status"] = {
            "in_authorized_zone": False,
            "tfr_active": False,
            "remote_id_active": False,
        }
    return signal


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch Mavic Mini post-flight detector.")
    p.add_argument("flight_dir", help="Folder of Mavic Mini media (.MP4 / .JPG with optional .SRT siblings).")
    p.add_argument("--drone_id", default="wfw-mavic01")
    p.add_argument("--zone_id", default="phase0-mavic-survey")
    p.add_argument("--sample_hz", type=float, default=DEFAULT_VIDEO_SAMPLE_HZ,
                   help="Frames per second sampled from each video.")
    p.add_argument("--no-yolo", action="store_true",
                   help="Skip COCO-YOLO corroboration (heuristic only). Useful when ultralytics is not installed.")
    p.add_argument("--pipe-to-sapphire", action="store_true",
                   help="Forward each emitted signal to ~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py.")
    return p.parse_args()


def find_media(flight_dir: Path) -> list[Path]:
    media: list[Path] = []
    for child in sorted(flight_dir.iterdir()):
        if child.is_file() and child.suffix.lower() in (VIDEO_EXTS | PHOTO_EXTS):
            media.append(child)
    return media


def sibling_srt(media_path: Path) -> Path | None:
    """Return the .SRT alongside this media file, if any.

    DJI Fly emits FILE.MP4 + FILE.SRT (same stem). Photos rarely have one,
    but if a single-frame .SRT exists we honour it.
    """
    candidates = [
        media_path.with_suffix(".SRT"),
        media_path.with_suffix(".srt"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def process_media(
    media_path: Path,
    args: argparse.Namespace,
    yolo_model,
) -> Iterator[dict]:
    """Yield wildfire_signals for one media file."""
    srt_path = sibling_srt(media_path)
    fixes: list[GpsFix] = []
    if srt_path is not None:
        try:
            fixes = parse_srt(srt_path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            logger.warning("could not read SRT %s: %s", srt_path, exc)
    else:
        logger.warning(
            "no SRT alongside %s — emitting signals with coords zero'd",
            media_path.name,
        )

    suffix = media_path.suffix.lower()
    if suffix in VIDEO_EXTS:
        try:
            samples = iter_video_samples(media_path, args.sample_hz)
        except ImportError:
            logger.error("opencv not installed — skipping video %s", media_path.name)
            return
        for frame_idx, (t_offset_s, image) in enumerate(samples):
            heuristic = heuristic_score_pil(image)
            yolo_score = 0.0
            yolo_class = ""
            if yolo_model is not None and heuristic.is_candidate:
                yolo_score, yolo_class = yolo_corroborate(image, yolo_model)
            if not heuristic.is_candidate:
                continue
            fix = lookup_fix(fixes, t_offset_s)
            yield detection_to_signal(
                drone_id=args.drone_id,
                zone_id=args.zone_id,
                media_path=media_path,
                frame_idx=frame_idx,
                t_offset_s=t_offset_s,
                fix=fix,
                heuristic=heuristic,
                yolo_score=yolo_score,
                yolo_class=yolo_class,
            )
    elif suffix in PHOTO_EXTS:
        try:
            image = load_photo(media_path)
        except OSError as exc:
            logger.error("could not open photo %s: %s", media_path.name, exc)
            return
        heuristic = heuristic_score_pil(image)
        yolo_score = 0.0
        yolo_class = ""
        if yolo_model is not None and heuristic.is_candidate:
            yolo_score, yolo_class = yolo_corroborate(image, yolo_model)
        if not heuristic.is_candidate:
            return
        # Photos: use the first GpsFix, if any.
        fix = fixes[0] if fixes else None
        yield detection_to_signal(
            drone_id=args.drone_id,
            zone_id=args.zone_id,
            media_path=media_path,
            frame_idx=0,
            t_offset_s=0.0,
            fix=fix,
            heuristic=heuristic,
            yolo_score=yolo_score,
            yolo_class=yolo_class,
        )


def load_yolo_model(disabled: bool):
    """Return a YOLOv8n COCO model, or None if disabled / unavailable."""
    if disabled:
        return None
    try:
        from ultralytics import YOLO  # noqa: PLC0415
    except ImportError:
        logger.warning("ultralytics not installed — running heuristic-only.")
        return None
    try:
        return YOLO("yolov8n.pt")
    except Exception as exc:  # noqa: BLE001 — model download / version mismatch
        logger.warning("failed to load yolov8n.pt: %s — running heuristic-only.", exc)
        return None


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    flight_dir = Path(args.flight_dir).expanduser().resolve()
    if not flight_dir.is_dir():
        logger.error("not a directory: %s", flight_dir)
        return 2

    media = find_media(flight_dir)
    if not media:
        logger.error("no .MP4 / .JPG found in %s", flight_dir)
        return 1
    logger.info("found %d media files in %s", len(media), flight_dir)

    yolo_model = load_yolo_model(disabled=args.no_yolo)

    emit_count = 0
    for media_path in media:
        logger.info("processing %s", media_path.name)
        for signal in process_media(media_path, args, yolo_model):
            emit_count += 1
            if args.pipe_to_sapphire:
                response = pipe_to_sapphire_bridge(signal)
                sys.stdout.write(json.dumps({"emit": signal, "bridge": response}) + "\n")
            else:
                sys.stdout.write(json.dumps(signal) + "\n")
            sys.stdout.flush()

    sys.stderr.write(f"\nemitted {emit_count} signals from {len(media)} media files\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
