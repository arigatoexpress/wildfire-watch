"""CLI entry-point.

Usage:

::

    python -m ml.fire_detection.synth.cli generate \
        --output ~/wildfire-watch-data/synth-v0/ \
        --n-train 200 --n-val 50 --n-test 50

    python -m ml.fire_detection.synth.cli preview --output preview.png

    python -m ml.fire_detection.synth.cli stats <dataset_dir>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import DEFAULT_W
from .pipeline import DEFAULT_BACKDROPS_DIR, generate_dataset


def _cmd_generate(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    backdrops = Path(args.backdrops).expanduser() if args.backdrops else DEFAULT_BACKDROPS_DIR
    print(f"[synth] generating dataset under {output}", flush=True)
    manifest = generate_dataset(
        output,
        n_train=args.n_train,
        n_val=args.n_val,
        n_test=args.n_test,
        seed=args.seed,
        backdrops_dir=backdrops,
        image_size=(args.imgsz, args.imgsz),
        augmentation_level=args.aug_level,
    )
    print(f"[synth] wrote {manifest['n_total']} samples in {manifest['elapsed_seconds']}s")
    print(f"[synth] data.yaml: {manifest['data_yaml']}")
    print(f"[synth] manifest: {Path(manifest['output_dir']) / 'manifest.json'}")
    return 0


def _cmd_preview(args: argparse.Namespace) -> int:
    # Lazy-import generator inside the command so the CLI can at least print
    # --help without PIL installed.
    from .generator import generate_sample  # noqa: PLC0415

    backdrops_dir = Path(args.backdrops).expanduser() if args.backdrops else DEFAULT_BACKDROPS_DIR
    bds = sorted(p for p in backdrops_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    backdrop = bds[args.backdrop_idx % len(bds)] if bds else None
    image, labels = generate_sample(
        backdrop,
        seed=args.seed,
        has_fire=not args.no_fire,
        has_smoke=not args.no_smoke,
        augmentation_level=args.aug_level,
        image_size=(args.imgsz, args.imgsz),
    )
    out = Path(args.output).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"[synth] wrote preview {out} with {len(labels)} labels")
    for label in labels:
        print(
            f"  cls={int(label['class_id'])} "
            f"({label['x_center']:.3f},{label['y_center']:.3f}) "
            f"{label['width']:.3f}x{label['height']:.3f}"
        )
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    dataset_dir = Path(args.dataset_dir).expanduser()
    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        print(f"[synth] no manifest.json under {dataset_dir}", file=sys.stderr)
        return 2
    manifest = json.loads(manifest_path.read_text())
    print(f"[synth] dataset: {dataset_dir}")
    print(f"  generator_version : {manifest.get('generator_version')}")
    print(f"  seed              : {manifest.get('seed')}")
    print(f"  image_size        : {manifest.get('image_size')}")
    print(f"  total samples     : {manifest.get('n_total')}")
    print(f"  total labels      : {manifest.get('total_labels')}")
    print(f"  backdrop count    : {manifest.get('backdrop_count')}")
    for subset, stats in manifest.get("per_subset_stats", {}).items():
        print(
            f"  [{subset:5}] samples={stats['samples']} "
            f"fire={stats['fire_labels']} smoke={stats['smoke_labels']} "
            f"negatives={stats['negatives']}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ml.fire_detection.synth.cli",
        description="Synthetic fire/smoke training-dataset generator.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pg = sub.add_parser("generate", help="generate a full YOLO-format dataset")
    pg.add_argument("--output", required=True, type=str, help="output dataset directory")
    pg.add_argument("--n-train", type=int, default=200)
    pg.add_argument("--n-val", type=int, default=50)
    pg.add_argument("--n-test", type=int, default=50)
    pg.add_argument("--seed", type=int, default=42)
    pg.add_argument("--imgsz", type=int, default=DEFAULT_W)
    pg.add_argument("--aug-level", type=float, default=0.6)
    pg.add_argument("--backdrops", type=str, default=None, help="override backdrop directory")
    pg.set_defaults(func=_cmd_generate)

    pp = sub.add_parser("preview", help="generate a single example for inspection")
    pp.add_argument("--output", required=True, type=str, help="preview image path (.png)")
    pp.add_argument("--seed", type=int, default=42)
    pp.add_argument("--imgsz", type=int, default=DEFAULT_W)
    pp.add_argument("--aug-level", type=float, default=0.5)
    pp.add_argument("--no-fire", action="store_true")
    pp.add_argument("--no-smoke", action="store_true")
    pp.add_argument("--backdrop-idx", type=int, default=0)
    pp.add_argument("--backdrops", type=str, default=None)
    pp.set_defaults(func=_cmd_preview)

    ps = sub.add_parser("stats", help="print dataset stats from manifest.json")
    ps.add_argument("dataset_dir", type=str)
    ps.set_defaults(func=_cmd_stats)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
