"""Tiny Flask dashboard for the valuation engine.

Run:
    python -m valuation.web        # serves http://localhost:8090

Single-page panel, no build step. Chart.js loads from CDN.
"""

from __future__ import annotations

import json
from typing import Any

from .comps import load_comps
from .engine import compute_valuation
from .kpis import collect_all, kpi_snapshot_dict
from .recorder import read_history


def _fmt_usd(n: float | int) -> str:
    n = float(n)
    if abs(n) >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}k"
    return f"${n:.0f}"


HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>wildfire-watch — intrinsic value</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; margin: 0; padding: 24px; background: #0f1115; color: #eaeaea; }
  h1 { font-size: 18px; margin: 0 0 8px; font-weight: 600; }
  h2 { font-size: 14px; margin: 24px 0 8px; font-weight: 600; color: #a0a0b0; text-transform: uppercase; letter-spacing: 0.05em; }
  .band { font-size: 32px; font-weight: 600; color: #4cd964; margin: 8px 0 4px; }
  .band-detail { color: #a0a0b0; font-size: 13px; }
  .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
  .card { background: #1a1d24; border: 1px solid #2a2d35; border-radius: 6px; padding: 12px; }
  .card h3 { font-size: 11px; color: #a0a0b0; margin: 0 0 6px; text-transform: uppercase; letter-spacing: 0.05em; }
  .kpi { display: flex; justify-content: space-between; font-size: 13px; padding: 2px 0; border-bottom: 1px solid #23262e; }
  .kpi:last-child { border-bottom: none; }
  .kpi-name { color: #ccc; }
  .kpi-val { color: #fff; font-variant-numeric: tabular-nums; font-weight: 500; }
  .acq { display: flex; align-items: center; padding: 6px 0; }
  .acq-name { width: 100px; font-weight: 500; }
  .acq-bar { flex: 1; height: 8px; background: #23262e; border-radius: 4px; overflow: hidden; margin: 0 8px; }
  .acq-bar-fill { height: 100%; background: linear-gradient(90deg, #4cd964 0%, #2ea44f 100%); }
  .acq-score { width: 50px; text-align: right; font-variant-numeric: tabular-nums; }
  .action { background: #1a1d24; border-left: 3px solid #f9a825; padding: 8px 12px; margin: 6px 0; border-radius: 0 4px 4px 0; font-size: 13px; line-height: 1.5; }
  .action.blocker { border-left-color: #ff3b30; }
  .meta { color: #888; font-size: 11px; margin-bottom: 16px; }
  canvas { background: #1a1d24; border-radius: 6px; padding: 8px; }
</style>
</head>
<body>
<h1>wildfire-watch — intrinsic value</h1>
<div class="meta">as of __AS_OF__ &middot; commit __SHA__</div>

<div class="band">__BAND__</div>
<div class="band-detail">low __LOW__ &middot; mid __MID__ &middot; high __HIGH__</div>

<h2>Acquirer fit</h2>
<div>
__ACQUIRERS__
</div>

<h2>Methods</h2>
<div class="grid">
__METHODS__
</div>

<h2>KPIs</h2>
<div class="grid">
__KPIS__
</div>

<h2>What's the next $1M move</h2>
<div>
__ACTIONS__
</div>

<h2>Mid-band over time</h2>
<canvas id="historyChart" height="80"></canvas>
<script>
const histData = __HIST_JSON__;
if (histData.length > 1) {
  const labels = histData.map(d => (d.as_of || '').slice(0, 10));
  const mids = histData.map(d => (d.consensus_band || {}).mid || 0);
  new Chart(document.getElementById('historyChart'), {
    type: 'line',
    data: { labels, datasets: [{ label: 'mid-band USD', data: mids, borderColor: '#4cd964', backgroundColor: 'rgba(76,217,100,0.1)', fill: true, tension: 0.2 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { ticks: { color: '#888' }, grid: { color: '#23262e' } }, y: { ticks: { color: '#888' }, grid: { color: '#23262e' } } } }
  });
} else {
  document.getElementById('historyChart').replaceWith(
    Object.assign(document.createElement('div'), { textContent: 'Need 2+ snapshots to chart.', style: 'color: #888; font-size: 13px;' })
  );
}
</script>
</body>
</html>
"""


def render_page(snapshot: dict[str, Any], history: list[dict[str, Any]]) -> str:
    band = snapshot["consensus_band"]
    kpis = collect_all()

    by_cat: dict[str, list] = {}
    for kpi in kpis.values():
        by_cat.setdefault(kpi.category, []).append(kpi)

    kpi_html_parts: list[str] = []
    for cat in ("engineering", "product", "strategic", "compliance"):
        if cat not in by_cat:
            continue
        rows = "".join(
            f'<div class="kpi"><span class="kpi-name">{k.name}</span>'
            f'<span class="kpi-val">{k.value}</span></div>'
            for k in by_cat[cat]
        )
        kpi_html_parts.append(
            f'<div class="card"><h3>{cat}</h3>{rows}</div>'
        )

    method_html_parts: list[str] = []
    for name, m in snapshot["methods"].items():
        method_html_parts.append(
            f'<div class="card"><h3>{name}</h3>'
            f'<div class="kpi"><span class="kpi-name">low</span>'
            f'<span class="kpi-val">{_fmt_usd(m["low"])}</span></div>'
            f'<div class="kpi"><span class="kpi-name">mid</span>'
            f'<span class="kpi-val">{_fmt_usd(m["mid"])}</span></div>'
            f'<div class="kpi"><span class="kpi-name">high</span>'
            f'<span class="kpi-val">{_fmt_usd(m["high"])}</span></div>'
            f'<div style="font-size: 11px; color: #888; margin-top: 6px;">{m["rationale"]}</div>'
            f'</div>'
        )

    acq_parts: list[str] = []
    max_score = max((r["score"] for r in snapshot["primary_acquirer_ranking"]), default=1.0)
    if max_score <= 0:
        max_score = 1.0
    for r in snapshot["primary_acquirer_ranking"]:
        pct = int(100 * r["score"] / max_score)
        acq_parts.append(
            f'<div class="acq">'
            f'<div class="acq-name">{r["name"]}</div>'
            f'<div class="acq-bar"><div class="acq-bar-fill" style="width: {pct}%"></div></div>'
            f'<div class="acq-score">{r["score"]:.3f}</div>'
            f'</div>'
        )

    action_parts: list[str] = []
    for action in snapshot["what_to_do_next"]:
        cls = "action blocker" if action.startswith("BLOCKER") else "action"
        action_parts.append(f'<div class="{cls}">{action}</div>')

    return (
        HTML
        .replace("__AS_OF__", str(snapshot.get("as_of", ""))[:19])
        .replace("__SHA__", str(snapshot.get("commit_sha", "(no commit)"))[:12])
        .replace(
            "__BAND__",
            f"{_fmt_usd(band['low'])} – {_fmt_usd(band['high'])}",
        )
        .replace("__LOW__", _fmt_usd(band["low"]))
        .replace("__MID__", _fmt_usd(band["mid"]))
        .replace("__HIGH__", _fmt_usd(band["high"]))
        .replace("__KPIS__", "\n".join(kpi_html_parts))
        .replace("__METHODS__", "\n".join(method_html_parts))
        .replace("__ACQUIRERS__", "\n".join(acq_parts))
        .replace("__ACTIONS__", "\n".join(action_parts))
        .replace("__HIST_JSON__", json.dumps(history, default=str))
    )


def create_app():
    """Lazy-imports Flask so importing valuation/web.py is cheap."""
    from flask import Flask, Response

    app = Flask(__name__)

    @app.get("/")
    def index() -> Response:
        kpi_dict = kpi_snapshot_dict()
        comps = load_comps()
        snapshot = compute_valuation(kpi_dict, comps)
        history = read_history(last_n=50)
        return Response(render_page(snapshot, history), mimetype="text/html")

    @app.get("/kpi")
    def kpi_panel() -> Response:
        # Same page; route alias matches the spec ("a /kpi panel").
        return index()

    @app.get("/api/snapshot.json")
    def snapshot_json() -> Response:
        kpi_dict = kpi_snapshot_dict()
        comps = load_comps()
        snapshot = compute_valuation(kpi_dict, comps)
        return Response(
            json.dumps(snapshot, default=str, indent=2),
            mimetype="application/json",
        )

    return app


def main() -> int:
    app = create_app()
    app.run(host="127.0.0.1", port=8090, debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
