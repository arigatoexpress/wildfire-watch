"""Flask factory for the wildfire-watch admin dashboard.

Single-file factory keeps the surface easy to audit. The app reads
signals from ``data/wildfire_signals.jsonl`` (preferred) or, if that
sink is empty, falls back to the bundled fixture so the dashboard is
testable on day one.

Run locally::

    ADMIN_TOKEN=dev python3 -m frontend.app
    # then: open http://127.0.0.1:8090/  (browser passes header via
    # localStorage shim — see static/js/auth.js)

Health::

    curl http://127.0.0.1:8090/healthz/
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SIGNALS_PATH = REPO_ROOT / "data" / "wildfire_signals.jsonl"
FIXTURE_SIGNALS_PATH = Path(__file__).resolve().parent / "fixtures" / "signals.jsonl"
AOR_GEOJSON_PATH = (
    REPO_ROOT / "missions" / "zones" / "gunnison_crested_butte_corridor.geojson"
)
RETRY_QUEUE_DIR = REPO_ROOT / "data" / "webhook_retry"


# ---------------------------------------------------------------------------
# Auth scaffolding
# ---------------------------------------------------------------------------


def requires_admin(view: Callable) -> Callable:
    """Stub admin gate.

    Production replaces this with WebAuthn. For now it compares
    ``X-Admin-Token`` against ``ADMIN_TOKEN`` (or query param
    ``admin_token`` for browser convenience). When ``ADMIN_TOKEN`` is
    unset the gate is disabled — fine for local dev, never for prod.
    """

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        expected = os.environ.get("ADMIN_TOKEN")
        if not expected:
            return view(*args, **kwargs)
        provided = (
            request.headers.get("X-Admin-Token")
            or request.args.get("admin_token")
            or request.cookies.get("admin_token")
        )
        if provided != expected:
            return _json_error("admin token required", 401)
        return view(*args, **kwargs)

    return wrapper


def _json_error(msg: str, code: int) -> Tuple[Response, int]:
    return jsonify({"error": msg}), code


# ---------------------------------------------------------------------------
# Signal loading
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                # Skip malformed lines rather than crashing the dashboard.
                continue
    except OSError:
        return []
    return out


def _load_signals(app: Flask) -> List[Dict[str, Any]]:
    """Return signals from the configured JSONL path, fall back to fixture."""
    primary = Path(app.config["SIGNALS_PATH"])
    rows = _read_jsonl(primary)
    if rows:
        return rows
    fixture = Path(app.config["FIXTURE_PATH"])
    return _read_jsonl(fixture)


def _load_aor(app: Flask) -> Dict[str, Any]:
    path = Path(app.config["AOR_PATH"])
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"type": "FeatureCollection", "features": []}


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def _parse_ts(raw: Any) -> Optional[datetime]:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # Accept trailing Z; Python <3.11 chokes on "Z" suffix in some envs.
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        return datetime.fromisoformat(raw).astimezone(timezone.utc)
    except ValueError:
        return None


def _retry_queue_depth(app: Flask) -> int:
    path = Path(app.config["RETRY_DIR"])
    if not path.exists() or not path.is_dir():
        return 0
    try:
        return sum(1 for p in path.iterdir() if p.is_file())
    except OSError:
        return 0


def compute_kpis(signals: Iterable[Dict[str, Any]], retry_depth: int) -> Dict[str, Any]:
    """Aggregate KPIs from raw signals."""
    now = datetime.now(timezone.utc)
    cut_24h = now - timedelta(hours=24)
    cut_7d = now - timedelta(days=7)

    total = 0
    last_24h = 0
    last_7d = 0
    last_heartbeat: Optional[datetime] = None
    risk_by_zone: Counter[str] = Counter()
    risk_count_by_zone: Counter[str] = Counter()
    by_type: Counter[str] = Counter()

    for sig in signals:
        total += 1
        ts = _parse_ts(sig.get("timestamp"))
        if ts is not None:
            if ts >= cut_24h:
                last_24h += 1
            if ts >= cut_7d:
                last_7d += 1
        sig_type = sig.get("signal_type")
        if isinstance(sig_type, str):
            by_type[sig_type] += 1
            if sig_type == "system_event" and ts is not None:
                if last_heartbeat is None or ts > last_heartbeat:
                    last_heartbeat = ts
        zone = sig.get("zone_id")
        risk = sig.get("risk_score")
        if isinstance(zone, str) and isinstance(risk, (int, float)):
            risk_by_zone[zone] += float(risk)
            risk_count_by_zone[zone] += 1

    avg_risk_by_zone: Dict[str, float] = {
        z: risk_by_zone[z] / risk_count_by_zone[z]
        for z in risk_by_zone
        if risk_count_by_zone[z]
    }
    if avg_risk_by_zone:
        top_zone, top_risk = max(avg_risk_by_zone.items(), key=lambda kv: kv[1])
    else:
        top_zone, top_risk = None, None

    return {
        "total": total,
        "last_24h": last_24h,
        "last_7d": last_7d,
        "highest_risk_zone": top_zone,
        "highest_risk_value": round(top_risk, 1) if top_risk is not None else None,
        "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
        "retry_queue_depth": retry_depth,
        "by_type": dict(by_type),
    }


def compute_sensor_health(signals: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-drone last-seen + signal counts."""
    last_seen: Dict[str, datetime] = {}
    counts: Counter[str] = Counter()
    last_zone: Dict[str, str] = {}
    for sig in signals:
        drone = sig.get("drone_id")
        if not isinstance(drone, str):
            continue
        counts[drone] += 1
        ts = _parse_ts(sig.get("timestamp"))
        if ts is not None and (drone not in last_seen or ts > last_seen[drone]):
            last_seen[drone] = ts
            zone = sig.get("zone_id")
            if isinstance(zone, str):
                last_zone[drone] = zone
    now = datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    for drone, ts in last_seen.items():
        age_min = (now - ts).total_seconds() / 60.0
        if age_min < 15:
            status = "online"
        elif age_min < 120:
            status = "stale"
        else:
            status = "offline"
        out.append(
            {
                "drone_id": drone,
                "last_seen": ts.isoformat(),
                "last_seen_age_min": round(age_min, 1),
                "signal_count": counts[drone],
                "last_zone": last_zone.get(drone),
                "status": status,
            }
        )
    out.sort(key=lambda r: r["last_seen_age_min"])
    return out


def filter_signals(
    signals: Iterable[Dict[str, Any]],
    zone: Optional[str] = None,
    signal_type: Optional[str] = None,
    min_risk: Optional[float] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sig in signals:
        if zone and sig.get("zone_id") != zone:
            continue
        if signal_type and sig.get("signal_type") != signal_type:
            continue
        if min_risk is not None:
            risk = sig.get("risk_score")
            if not isinstance(risk, (int, float)) or float(risk) < min_risk:
                continue
        rows.append(sig)
    rows.sort(key=lambda s: s.get("timestamp") or "", reverse=True)
    return rows[:limit]


# ---------------------------------------------------------------------------
# Flask factory
# ---------------------------------------------------------------------------


def create_app(
    signals_path: Optional[Path] = None,
    fixture_path: Optional[Path] = None,
    aor_path: Optional[Path] = None,
    retry_dir: Optional[Path] = None,
) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).resolve().parent / "templates"),
        static_folder=str(Path(__file__).resolve().parent / "static"),
    )
    app.config["SIGNALS_PATH"] = str(
        signals_path or os.environ.get("WFW_SIGNALS_PATH") or DEFAULT_SIGNALS_PATH
    )
    app.config["FIXTURE_PATH"] = str(fixture_path or FIXTURE_SIGNALS_PATH)
    app.config["AOR_PATH"] = str(aor_path or AOR_GEOJSON_PATH)
    app.config["RETRY_DIR"] = str(retry_dir or RETRY_QUEUE_DIR)

    @app.route("/healthz/")
    def healthz() -> Any:  # pragma: no cover - trivial
        return jsonify({"ok": True, "service": "wildfire-watch-frontend"})

    @app.route("/")
    @requires_admin
    def index() -> Any:
        signals = _load_signals(app)
        kpis = compute_kpis(signals, _retry_queue_depth(app))
        return render_template(
            "index.html",
            kpis=kpis,
            signal_count=len(signals),
        )

    @app.route("/api/signals")
    @requires_admin
    def api_signals() -> Any:
        signals = _load_signals(app)
        zone = request.args.get("zone") or None
        sig_type = request.args.get("signal_type") or None
        min_risk_raw = request.args.get("min_risk")
        try:
            min_risk = float(min_risk_raw) if min_risk_raw else None
        except ValueError:
            min_risk = None
        try:
            limit = max(1, min(int(request.args.get("limit", "100")), 1000))
        except ValueError:
            limit = 100
        rows = filter_signals(
            signals,
            zone=zone,
            signal_type=sig_type,
            min_risk=min_risk,
            limit=limit,
        )
        return jsonify({"count": len(rows), "signals": rows})

    @app.route("/api/kpis")
    @requires_admin
    def api_kpis() -> Any:
        signals = _load_signals(app)
        return jsonify(compute_kpis(signals, _retry_queue_depth(app)))

    @app.route("/api/aor")
    @requires_admin
    def api_aor() -> Any:
        return jsonify(_load_aor(app))

    @app.route("/api/sensors")
    @requires_admin
    def api_sensors() -> Any:
        signals = _load_signals(app)
        return jsonify({"sensors": compute_sensor_health(signals)})

    @app.errorhandler(404)
    def not_found(_e: Any) -> Any:
        return _json_error("not found", 404)

    return app


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8090")))
    p.add_argument("--signals", default=None, help="Override signals JSONL path")
    return p.parse_args()


def main() -> int:  # pragma: no cover - smoke entry point
    args = _parse_args()
    signals_path = Path(args.signals).resolve() if args.signals else None
    app = create_app(signals_path=signals_path)
    app.run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
