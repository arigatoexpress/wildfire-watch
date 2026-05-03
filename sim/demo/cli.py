# Copyright 2026 wildfire-watch contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# See the LICENSE file in the repo root for the full text.
"""Command-line entry point for the demo recorder + renderer.

    python -m sim.demo.cli record [--seed 42] [--output sim/demo/canonical]
    python -m sim.demo.cli render <flight-dir> [--output report.html]
    python -m sim.demo.cli all                 # record + render
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .recorder import DEFAULT_SEED, record_canonical_flight
from .renderer import render_report

logger = logging.getLogger("sim.demo.cli")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CANONICAL = REPO_ROOT / "sim" / "demo" / "canonical"
DEFAULT_REPORT_NAME = "wildfire_watch_demo.html"


def _build_record_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("record", help="Record the canonical demo flight.")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument(
        "--output",
        default=str(DEFAULT_CANONICAL),
        help=f"Output dir (default: {DEFAULT_CANONICAL}).",
    )
    return p


def _build_render_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("render", help="Render a flight dir to a single HTML file.")
    p.add_argument("flight_dir", help="Path to a flight directory (contains manifest.json).")
    p.add_argument(
        "--output",
        default=None,
        help=(
            "Output HTML path. Default: <flight_dir>/wildfire_watch_demo.html "
            "if flight_dir is the canonical demo root, else next to flight_dir."
        ),
    )
    return p


def _build_all_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("all", help="record + render in one go.")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument(
        "--output",
        default=str(DEFAULT_CANONICAL),
        help=f"Output dir (default: {DEFAULT_CANONICAL}).",
    )
    p.add_argument(
        "--report",
        default=None,
        help=(
            "Output HTML path. Default: <output>/wildfire_watch_demo.html — the "
            "single-file artifact ready to email or embed in a README."
        ),
    )
    p.add_argument(
        "--flight",
        choices=("swarm", "single"),
        default="swarm",
        help="Which sub-flight to render (default swarm — has consensus signals).",
    )
    return p


def _resolve_flight_dir(arg: str) -> Path:
    """Accept either a direct flight dir, or a parent canonical dir.

    A parent canonical dir contains ``swarm/`` + ``single/`` from the
    recorder. We pick the swarm sub-run by default since it's the more
    illustrative one (consensus signals + multi-drone paths).
    """
    p = Path(arg).expanduser().resolve()
    if not p.is_dir():
        raise FileNotFoundError(f"flight dir not found: {p}")
    if (p / "manifest.json").exists() and (
        (p / "flight_log.jsonl").exists() or (p / "drones.jsonl").exists()
    ):
        return p
    swarm_runs = sorted((p / "swarm").glob("SWARM-*"))
    if swarm_runs:
        return swarm_runs[-1]
    single_runs = sorted((p / "single").glob("SIM-*"))
    if single_runs:
        return single_runs[-1]
    raise FileNotFoundError(f"no flight runs found under {p}")


def _resolve_run_in_canonical(canonical_dir: Path, kind: str) -> Path:
    if kind == "swarm":
        runs = sorted((canonical_dir / "swarm").glob("SWARM-*"))
    else:
        runs = sorted((canonical_dir / "single").glob("SIM-*"))
    if not runs:
        raise FileNotFoundError(
            f"no {kind} runs under {canonical_dir} — did you run `record` first?"
        )
    return runs[-1]


def _cmd_record(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    manifest = record_canonical_flight(seed=args.seed, output_dir=output)
    sys.stdout.write(json.dumps(manifest, indent=2, default=str) + "\n")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    flight_dir = _resolve_flight_dir(args.flight_dir)
    if args.output:
        output = Path(args.output).expanduser()
    else:
        output = flight_dir.parent / DEFAULT_REPORT_NAME
    render_report(flight_dir, output)
    sys.stdout.write(f"wrote {output}\n")
    return 0


def _cmd_all(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    record_canonical_flight(seed=args.seed, output_dir=output)
    flight_dir = _resolve_run_in_canonical(output, args.flight)
    if args.report:
        report_path = Path(args.report).expanduser()
    else:
        report_path = output / DEFAULT_REPORT_NAME
    render_report(flight_dir, report_path)
    sys.stdout.write(
        json.dumps(
            {
                "canonical_dir": str(output),
                "rendered_from": str(flight_dir),
                "report_html": str(report_path),
                "size_bytes": report_path.stat().st_size,
            },
            indent=2,
        )
        + "\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="python -m sim.demo.cli",
        description=(
            "Record the canonical wildfire-watch demo flight and render "
            "a single self-contained HTML report."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    _build_record_parser(sub)
    _build_render_parser(sub)
    _build_all_parser(sub)

    args = parser.parse_args(argv)
    if args.cmd == "record":
        return _cmd_record(args)
    if args.cmd == "render":
        return _cmd_render(args)
    if args.cmd == "all":
        return _cmd_all(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
