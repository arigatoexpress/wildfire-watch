"""CLI for the wildfire-watch TAK / CoT emitter.

Subcommands:

    emit          Convert a wildfire_signal JSON file to CoT and dispatch.
    geofence      Convert a GeoJSON polygon to a CoT u-d-c-c drawing event.
    self-position Build a CoT self-position event for a drone.
    types         List the CoT type-code mapping.

Examples:

    python -m sapphire_integration.tak.cli emit signal.json
    python -m sapphire_integration.tak.cli emit signal.json \
        --server tcp://atak.crestedbutte.local:8087
    python -m sapphire_integration.tak.cli emit signal.json --out /dev/stdout
    python -m sapphire_integration.tak.cli geofence \
        missions/zones/gunnison_crested_butte_corridor.geojson \
        --out fence.xml
    python -m sapphire_integration.tak.cli self-position \
        wfw-unit01 38.910 -107.000 80
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m sapphire_integration.tak.cli",
        description="wildfire-watch TAK / Cursor-on-Target emitter.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # emit
    sp_emit = sub.add_parser("emit", help="Emit a CoT event from a wildfire_signal JSON.")
    sp_emit.add_argument("signal_path", help="Path to a wildfire_signal v1 JSON file (use '-' for stdin).")
    sp_emit.add_argument("--server", default=None,
                         help="TAK URL: tcp://host:port | tls://host:port | udp://host:port | mcast://239.2.3.1:6969")
    sp_emit.add_argument("--out", default=None,
                         help="Where to write the XML: a file path, '-' for stdout, or '/dev/stdout'.")
    sp_emit.add_argument("--tls-cafile", default=None)
    sp_emit.add_argument("--tls-certfile", default=None)
    sp_emit.add_argument("--tls-keyfile", default=None)
    sp_emit.add_argument("--timeout", type=float, default=5.0,
                         help="Socket timeout in seconds (default 5.0).")

    # geofence
    sp_fence = sub.add_parser("geofence",
                              help="Convert a GeoJSON polygon to a CoT u-d-c-c drawing event.")
    sp_fence.add_argument("geojson_path",
                          help="Path to a GeoJSON file (FeatureCollection / Feature / Polygon geometry).")
    sp_fence.add_argument("--name", default="wfw-geofence",
                          help="Callsign / drawing name (default 'wfw-geofence').")
    sp_fence.add_argument("--out", default="-",
                          help="Where to write the XML (default stdout).")

    # self-position
    sp_pos = sub.add_parser("self-position",
                            help="Build a CoT self-position event for a drone.")
    sp_pos.add_argument("drone_id")
    sp_pos.add_argument("lat", type=float)
    sp_pos.add_argument("lon", type=float)
    sp_pos.add_argument("alt_msl_m", type=float, nargs="?", default=0.0)
    sp_pos.add_argument("--out", default="-",
                        help="Where to write the XML (default stdout).")
    sp_pos.add_argument("--multicast", action="store_true",
                        help="Also send to TAK SA multicast 239.2.3.1:6969.")

    # types
    sp_types = sub.add_parser("types", help="Print the CoT type-code mapping.")
    sp_types.set_defaults(_unused=None)  # silence type checkers

    return p


def _load_signal(path: str) -> dict[str, Any]:
    if path == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_geojson_polygon(path: str) -> list[tuple[float, float]]:
    """Return a list of (lat, lon) tuples from the first polygon found."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    geom: dict[str, Any]
    if raw.get("type") == "FeatureCollection":
        if not raw.get("features"):
            raise ValueError(f"GeoJSON {path!r} has no features")
        geom = raw["features"][0]["geometry"]
    elif raw.get("type") == "Feature":
        geom = raw["geometry"]
    else:
        geom = raw

    gtype = geom.get("type")
    if gtype == "Polygon":
        ring = geom["coordinates"][0]
    elif gtype == "MultiPolygon":
        ring = geom["coordinates"][0][0]
    else:
        raise ValueError(f"unsupported geometry type {gtype!r} in {path!r}")

    # GeoJSON is [lon, lat] order; CoT is (lat, lon).
    return [(float(p[1]), float(p[0])) for p in ring]


def _cmd_emit(args: argparse.Namespace) -> int:
    from .atak_emitter import emit  # noqa: PLC0415

    signal = _load_signal(args.signal_path)
    try:
        xml = emit(
            signal,
            server=args.server,
            out=args.out,
            tls_cafile=args.tls_cafile,
            tls_certfile=args.tls_certfile,
            tls_keyfile=args.tls_keyfile,
            timeout_seconds=args.timeout,
        )
    except OSError as exc:
        sys.stderr.write(f"transport error: {exc}\n")
        return 2

    if args.out is None and args.server is None:
        sys.stdout.write(xml)
        sys.stdout.write("\n")
    return 0


def _cmd_geofence(args: argparse.Namespace) -> int:
    from .atak_emitter import _write_out  # noqa: PLC0415
    from .cot_event import build_geofence_polygon  # noqa: PLC0415

    poly = _load_geojson_polygon(args.geojson_path)
    xml = build_geofence_polygon(poly, name=args.name)
    _write_out(xml, args.out)
    return 0


def _cmd_self_position(args: argparse.Namespace) -> int:
    from .atak_emitter import _write_out  # noqa: PLC0415
    from .cot_event import build_drone_self_position  # noqa: PLC0415

    xml = build_drone_self_position(
        args.drone_id, args.lat, args.lon, args.alt_msl_m,
    )
    _write_out(xml, args.out)
    if args.multicast:
        from .tak_server_client import send_self_position_multicast  # noqa: PLC0415

        try:
            send_self_position_multicast(xml)
        except OSError as exc:
            sys.stderr.write(f"multicast transport error: {exc}\n")
            return 2
    return 0


def _cmd_types(_args: argparse.Namespace) -> int:
    from . import cot_types  # noqa: PLC0415

    print("# wildfire_signal.signal_type -> CoT type code")
    for st, code in cot_types.SIGNAL_TYPE_TO_COT_TYPE.items():
        desc = cot_types.describe_cot_type(code)
        print(f"  {st:18s} -> {code:14s}  ({desc})")
    print()
    print(f"# drone self-position: {cot_types.DRONE_SELF_POSITION_COT_TYPE}  "
          f"({cot_types.describe_cot_type(cot_types.DRONE_SELF_POSITION_COT_TYPE)})")
    print(f"# geofence polygon:    {cot_types.GEOFENCE_POLYGON_COT_TYPE}  "
          f"({cot_types.describe_cot_type(cot_types.GEOFENCE_POLYGON_COT_TYPE)})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "emit":
        return _cmd_emit(args)
    if args.cmd == "geofence":
        return _cmd_geofence(args)
    if args.cmd == "self-position":
        return _cmd_self_position(args)
    if args.cmd == "types":
        return _cmd_types(args)
    parser.error(f"unknown command {args.cmd!r}")
    return 2  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
