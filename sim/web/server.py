"""Flask server for the wildfire-watch sim viewer.

Serves the SPA at ``/`` and a small read-only JSON/SSE API for flights
discovered under ``~/wildfire-watch-flights/`` plus the bundled fixture
at ``sim/web/fixtures/sample_flight``.

The bundled fixture is exposed as flight_id ``fixture:sample_flight`` and
is always present so the viewer is testable on day one — even before
SIM-A produces a real flight directory.

Run:

    python3 -m sim.web.server [--port 8088] [--flights-root ~/wildfire-watch-flights]
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from flask import Flask, Response, abort, jsonify, render_template, request, stream_with_context

from sim.web.analysis import read_jsonl, read_manifest, summarize

# ---------------------------------------------------------------------------
# Flight resolution
# ---------------------------------------------------------------------------

_FIXTURE_PREFIX = "fixture:"
_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_flight"
_DEFAULT_FLIGHTS_ROOT = Path.home() / "wildfire-watch-flights"


def _flights_root(app: Flask) -> Path:
    return Path(app.config.get("FLIGHTS_ROOT", _DEFAULT_FLIGHTS_ROOT))


def _fixture_dir(app: Flask) -> Path:
    return Path(app.config.get("FIXTURE_DIR", _FIXTURE_DIR))


def _resolve_flight_dir(app: Flask, flight_id: str) -> Path:
    """Map a flight_id from the URL to a real directory on disk.

    Raises 404 on traversal attempts or unknown ids.
    """
    if flight_id.startswith(_FIXTURE_PREFIX):
        name = flight_id[len(_FIXTURE_PREFIX):]
        if name != _fixture_dir(app).name:
            abort(404)
        return _fixture_dir(app)

    # Real flights live as direct children of FLIGHTS_ROOT. Reject anything
    # with a path separator or "..".
    if "/" in flight_id or ".." in flight_id or flight_id.startswith("."):
        abort(404)
    candidate = (_flights_root(app) / flight_id).resolve()
    root = _flights_root(app).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        abort(404)
    if not candidate.is_dir() or not (candidate / "manifest.json").exists():
        abort(404)
    return candidate


def _list_flights(app: Flask) -> List[Dict[str, Any]]:
    """Enumerate flights — bundled fixture first, then any real flights."""
    out: List[Dict[str, Any]] = []
    fixture = _fixture_dir(app)
    if fixture.exists():
        out.append(_flight_summary_card(f"{_FIXTURE_PREFIX}{fixture.name}", fixture))
    root = _flights_root(app)
    if root.is_dir():
        for child in sorted(root.iterdir(), reverse=True):
            if not child.is_dir():
                continue
            if not (child / "manifest.json").exists():
                continue
            out.append(_flight_summary_card(child.name, child))
    return out


def _flight_summary_card(flight_id: str, flight_dir: Path) -> Dict[str, Any]:
    manifest = read_manifest(flight_dir / "manifest.json")
    sig_count = 0
    sig_path = flight_dir / "signals.jsonl"
    if sig_path.exists():
        with sig_path.open("r", encoding="utf-8") as f:
            sig_count = sum(1 for line in f if line.strip())
    return {
        "flight_id": flight_id,
        "mission_name": manifest.get("mission_name") or flight_dir.name,
        "scenario_name": manifest.get("scenario_name") or "",
        "started_at": manifest.get("started_at"),
        "duration_s": manifest.get("duration_s"),
        "signals_count": sig_count,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(
    flights_root: Optional[Path] = None,
    fixture_dir: Optional[Path] = None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )
    if flights_root is not None:
        app.config["FLIGHTS_ROOT"] = Path(flights_root)
    if fixture_dir is not None:
        app.config["FIXTURE_DIR"] = Path(fixture_dir)

    # ---- routes ---------------------------------------------------------

    @app.get("/")
    def index() -> Any:
        return render_template("index.html")

    @app.get("/api/healthz")
    def healthz() -> Any:
        return jsonify({"ok": True})

    @app.get("/api/flights")
    def list_flights() -> Any:
        return jsonify(_list_flights(app))

    @app.get("/api/flights/<flight_id>/manifest")
    def flight_manifest(flight_id: str) -> Any:
        flight_dir = _resolve_flight_dir(app, flight_id)
        return jsonify(read_manifest(flight_dir / "manifest.json"))

    @app.get("/api/flights/<flight_id>/flight_log")
    def flight_log(flight_id: str) -> Any:
        flight_dir = _resolve_flight_dir(app, flight_id)
        since = request.args.get("since")
        try:
            limit = int(request.args.get("limit", "5000"))
        except ValueError:
            limit = 5000
        limit = max(1, min(limit, 50000))
        rows = read_jsonl(flight_dir / "flight_log.jsonl")
        if since:
            rows = [r for r in rows if r.get("ts", "") > since]
        return jsonify(rows[:limit])

    @app.get("/api/flights/<flight_id>/signals")
    def flight_signals(flight_id: str) -> Any:
        flight_dir = _resolve_flight_dir(app, flight_id)
        rows = read_jsonl(flight_dir / "signals.jsonl")
        return jsonify(rows)

    @app.get("/api/flights/<flight_id>/analysis")
    def flight_analysis(flight_id: str) -> Any:
        flight_dir = _resolve_flight_dir(app, flight_id)
        return jsonify(summarize(flight_dir))

    @app.get("/api/flights/<flight_id>/replay")
    def flight_replay(flight_id: str) -> Any:
        flight_dir = _resolve_flight_dir(app, flight_id)
        try:
            speed = float(request.args.get("speed", "1.0"))
        except ValueError:
            speed = 1.0
        speed = max(0.1, min(speed, 200.0))
        rows = read_jsonl(flight_dir / "flight_log.jsonl")

        def _gen() -> Iterable[bytes]:
            prev_t: Optional[datetime] = None
            for idx, row in enumerate(rows):
                # Compute sleep based on row timestamps, fall back to 0.1s/row.
                ts_str = row.get("ts")
                cur_t = _parse_ts(ts_str) if ts_str else None
                if prev_t is not None and cur_t is not None:
                    dt = (cur_t - prev_t).total_seconds() / speed
                    if dt > 0:
                        time.sleep(min(dt, 5.0))  # cap so a corrupt row can't stall forever
                else:
                    time.sleep(0.1 / speed)
                prev_t = cur_t
                payload = {"index": idx, "row": row}
                yield f"event: tick\ndata: {json.dumps(payload)}\n\n".encode("utf-8")
            yield b"event: end\ndata: {}\n\n"

        return Response(
            stream_with_context(_gen()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _parse_ts(ts: str) -> Optional[datetime]:
    """Parse 'YYYY-MM-DDTHH:MM:SSZ' (or ISO with offset). Return None on failure."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch sim viewer")
    p.add_argument("--port", type=int, default=int(os.environ.get("WFW_PORT", "8088")))
    p.add_argument("--host", default=os.environ.get("WFW_HOST", "127.0.0.1"))
    p.add_argument("--flights-root", default=str(_DEFAULT_FLIGHTS_ROOT))
    p.add_argument("--debug", action="store_true")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    app = create_app(flights_root=Path(args.flights_root).expanduser())
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
