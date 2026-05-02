"""Valuation CLI.

    python -m valuation.cli snapshot [--commit-sha <sha>] [--print|--json]
    python -m valuation.cli history --last 10
    python -m valuation.cli kpi
    python -m valuation.cli compare <sha-a> <sha-b>

Every `snapshot` run appends to valuation/data/valuation_history.jsonl.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from .comps import load_comps
from .engine import compute_valuation
from .kpis import collect_all, kpi_snapshot_dict
from .recorder import append_snapshot, find_snapshot_by_sha, read_history

REPO_ROOT = Path(__file__).resolve().parent.parent


def _current_commit_sha() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


def _fmt_usd(n: float | int) -> str:
    n = float(n)
    if abs(n) >= 1_000_000_000:
        return f"${n/1_000_000_000:.2f}B"
    if abs(n) >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if abs(n) >= 1_000:
        return f"${n/1_000:.1f}k"
    return f"${n:.0f}"


def _print_snapshot(snapshot: dict[str, Any]) -> None:
    band = snapshot["consensus_band"]
    print("=" * 70)
    print(f"wildfire-watch intrinsic valuation — {snapshot['as_of']}")
    if snapshot.get("commit_sha"):
        print(f"commit: {snapshot['commit_sha'][:12]}")
    print("=" * 70)
    print(
        f"BAND: {_fmt_usd(band['low'])} – {_fmt_usd(band['high'])}  "
        f"(mid {_fmt_usd(band['mid'])})"
    )
    print()
    print("Methods:")
    for name, m in snapshot["methods"].items():
        print(
            f"  {name:24s} {_fmt_usd(m['low']):>10s} – {_fmt_usd(m['high']):<10s} "
            f"(mid {_fmt_usd(m['mid'])})"
        )
        print(f"    {m['rationale']}")
    print()
    print("Acquirer ranking:")
    for r in snapshot["primary_acquirer_ranking"]:
        print(f"  {r['name']:10s} score={r['score']:.3f}  ({r['reason']})")
    print()
    print("What to do next:")
    for i, action in enumerate(snapshot["what_to_do_next"], start=1):
        print(f"  {i}. {action}")
    print()


def _cmd_snapshot(args: argparse.Namespace) -> int:
    kpi_dict = kpi_snapshot_dict()
    comps = load_comps()
    snapshot = compute_valuation(kpi_dict, comps)
    sha = args.commit_sha or _current_commit_sha()
    if sha:
        snapshot["commit_sha"] = sha
    append_snapshot(snapshot)
    if args.json:
        print(json.dumps(snapshot, indent=2, default=str))
    else:
        _print_snapshot(snapshot)
    return 0


def _cmd_kpi(_args: argparse.Namespace) -> int:
    kpis = collect_all()
    by_cat: dict[str, list] = {}
    for kpi in kpis.values():
        by_cat.setdefault(kpi.category, []).append(kpi)
    for cat in ("engineering", "product", "strategic", "compliance"):
        if cat not in by_cat:
            continue
        print(f"\n[{cat.upper()}]")
        for kpi in by_cat[cat]:
            note = f"  -- {kpi.notes}" if kpi.notes else ""
            print(f"  {kpi.name:38s} = {str(kpi.value):>15s}  ({kpi.unit}){note}")
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    records = read_history(last_n=args.last)
    if not records:
        print("No history yet. Run `snapshot` first.")
        return 0
    print(f"{'when':25s}  {'sha':12s}  {'low':>10s}  {'mid':>10s}  {'high':>10s}")
    for rec in records:
        when = str(rec.get("as_of", ""))[:24]
        sha = str(rec.get("commit_sha", ""))[:12]
        band = rec.get("consensus_band", {})
        print(
            f"{when:25s}  {sha:12s}  "
            f"{_fmt_usd(band.get('low', 0)):>10s}  "
            f"{_fmt_usd(band.get('mid', 0)):>10s}  "
            f"{_fmt_usd(band.get('high', 0)):>10s}"
        )
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    a = find_snapshot_by_sha(args.sha_a)
    b = find_snapshot_by_sha(args.sha_b)
    if a is None or b is None:
        missing = []
        if a is None:
            missing.append(args.sha_a)
        if b is None:
            missing.append(args.sha_b)
        print(f"Could not find snapshot(s) for: {', '.join(missing)}", file=sys.stderr)
        return 1
    band_a = a["consensus_band"]
    band_b = b["consensus_band"]
    print(f"A: {a.get('commit_sha','?')[:12]}  {a.get('as_of','')[:24]}")
    print(f"   {_fmt_usd(band_a['low'])} – {_fmt_usd(band_a['high'])} (mid {_fmt_usd(band_a['mid'])})")
    print(f"B: {b.get('commit_sha','?')[:12]}  {b.get('as_of','')[:24]}")
    print(f"   {_fmt_usd(band_b['low'])} – {_fmt_usd(band_b['high'])} (mid {_fmt_usd(band_b['mid'])})")
    print()
    delta_low = band_b["low"] - band_a["low"]
    delta_mid = band_b["mid"] - band_a["mid"]
    delta_high = band_b["high"] - band_a["high"]
    print(
        f"DELTA (B - A): low {_fmt_usd(delta_low)}, "
        f"mid {_fmt_usd(delta_mid)}, high {_fmt_usd(delta_high)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m valuation.cli",
        description="wildfire-watch intrinsic-value calculator.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_snap = sub.add_parser(
        "snapshot",
        help="Collect KPIs, compute valuation, append to history.",
    )
    p_snap.add_argument("--commit-sha", default=None)
    g = p_snap.add_mutually_exclusive_group()
    g.add_argument("--print", action="store_true", help="Pretty-print (default).")
    g.add_argument("--json", action="store_true", help="Full JSON dump.")

    sub.add_parser("kpi", help="Print KPIs only — no valuation.")

    p_hist = sub.add_parser("history", help="Show history of snapshots.")
    p_hist.add_argument("--last", type=int, default=10)

    p_cmp = sub.add_parser(
        "compare", help="Show valuation delta between two stored commit SHAs."
    )
    p_cmp.add_argument("sha_a")
    p_cmp.add_argument("sha_b")

    args = parser.parse_args(argv)
    if args.cmd == "snapshot":
        return _cmd_snapshot(args)
    if args.cmd == "kpi":
        return _cmd_kpi(args)
    if args.cmd == "history":
        return _cmd_history(args)
    if args.cmd == "compare":
        return _cmd_compare(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
