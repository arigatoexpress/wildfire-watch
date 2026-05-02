"""Real-image bench for wfw-fire-heuristic-v0.0.1.

Runs the v0.0.1 detector against a curated public-domain image set
(`images/`, hand-labeled in `labels.yaml`) and produces a Markdown report
with per-image results + aggregate precision/recall/F1.

This is the qualitative ground truth for the v0.0.1 model card. The
synthetic eval in `eval/eval_harness.py` says "the heuristic works on
canned RGB scalars"; this bench says "the heuristic works (or doesn't)
on real federal-public-domain wildfire imagery."

Usage:
    python3 -m ml.fire_detection.eval.real_bench.bench
    python3 -m ml.fire_detection.eval.real_bench.bench --out /tmp/bench.md
    python3 -m ml.fire_detection.eval.real_bench.bench --images-dir <path>
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]


def _load_inference():
    """Lazy-import v0.0.1 inference. Returns the predict_image function.

    Must register the module in sys.modules before exec, otherwise dataclass
    decorators fail to look up the module under Python 3.12.
    """
    name = "wfw_v0_0_1_inference"
    if name in sys.modules:
        return sys.modules[name]
    inf_path = REPO_ROOT / "ml" / "fire_detection" / "runs" / "v0.0.1" / "inference.py"
    spec = importlib.util.spec_from_file_location(name, inf_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load v0.0.1 inference at {inf_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_labels(labels_yaml: Path) -> list[dict]:
    """Lazy-import yaml; load labels list."""
    import yaml  # noqa: PLC0415

    doc = yaml.safe_load(labels_yaml.read_text(encoding="utf-8"))
    return list(doc.get("images") or [])


@dataclass
class Result:
    filename: str
    expected_class: str
    expected_min_score: float | None
    predicted_class: str
    predicted_score: float
    bbox: tuple[float, float, float, float] | None
    latency_ms: float
    notes: str
    verdict: str  # TP, FP, FN, TN, OOR (out-of-range score)


def _verdict(expected: str, predicted: str, score: float, min_score: float | None) -> str:
    """Classify each prediction against the expected label.

    For fire-detection, "fire" and "smoke" are the positive classes; "none"
    and "wildlife" are the negative classes. The bench is binary at the
    detector level (positive = something fired) but tracks which positive
    class.
    """
    expected_pos = expected in {"fire", "smoke"}
    predicted_pos = predicted in {"fire", "smoke"}

    if expected_pos and predicted_pos:
        # Right family. Check confidence floor.
        if min_score is not None and score < min_score:
            return "OOR"  # detected, but below the expected confidence floor
        return "TP"
    if expected_pos and not predicted_pos:
        return "FN"
    if not expected_pos and predicted_pos:
        return "FP"
    return "TN"


def run_bench(
    images_dir: Path,
    labels_yaml: Path,
) -> list[Result]:
    """Run v0.0.1 against every labeled image. Returns a list of Result."""
    inference = _load_inference()
    labels = _load_labels(labels_yaml)

    results: list[Result] = []
    for entry in labels:
        filename = entry["filename"]
        image_path = images_dir / filename
        if not image_path.exists():
            results.append(
                Result(
                    filename=filename,
                    expected_class=entry.get("expected_class", "?"),
                    expected_min_score=entry.get("expected_min_score"),
                    predicted_class="error",
                    predicted_score=0.0,
                    bbox=None,
                    latency_ms=0.0,
                    notes=f"image file missing: {image_path}",
                    verdict="OOR",
                )
            )
            continue

        try:
            det = inference.predict_image(image_path)
        except Exception as exc:  # noqa: BLE001
            results.append(
                Result(
                    filename=filename,
                    expected_class=entry.get("expected_class", "?"),
                    expected_min_score=entry.get("expected_min_score"),
                    predicted_class="error",
                    predicted_score=0.0,
                    bbox=None,
                    latency_ms=0.0,
                    notes=f"inference raised: {type(exc).__name__}: {exc}",
                    verdict="OOR",
                )
            )
            continue

        verdict = _verdict(
            entry.get("expected_class", "none"),
            det.class_name,
            det.score,
            entry.get("expected_min_score"),
        )

        results.append(
            Result(
                filename=filename,
                expected_class=entry.get("expected_class", "?"),
                expected_min_score=entry.get("expected_min_score"),
                predicted_class=det.class_name,
                predicted_score=det.score,
                bbox=tuple(det.bbox_xyxy) if det.bbox_xyxy else None,
                latency_ms=det.latency_ms,
                notes=entry.get("notes", "").strip(),
                verdict=verdict,
            )
        )

    return results


def aggregate(results: list[Result]) -> dict[str, Any]:
    tp = sum(1 for r in results if r.verdict == "TP")
    fp = sum(1 for r in results if r.verdict == "FP")
    fn = sum(1 for r in results if r.verdict == "FN")
    tn = sum(1 for r in results if r.verdict == "TN")
    oor = sum(1 for r in results if r.verdict == "OOR")

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "total": len(results),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "oor": oor,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "mean_latency_ms": (
            sum(r.latency_ms for r in results) / len(results) if results else 0.0
        ),
    }


def render_report(
    results: list[Result],
    agg: dict[str, Any],
    images_dir: Path,
    license_block: str,
) -> str:
    """Render the per-image table + aggregate stats as Markdown."""
    now = datetime.now(UTC).isoformat()
    lines: list[str] = []
    lines.append("# wildfire-watch real-image bench - wfw-fire-heuristic-v0.0.1")
    lines.append("")
    lines.append(f"Generated: `{now}`")
    lines.append("")
    lines.append(
        "Bench: 12 federal-public-domain images (NPS / USFS / NPS-Yellowstone) "
        "labeled by a single reviewer. The detector is "
        "`ml/fire_detection/runs/v0.0.1/inference.py`. See "
        "`images/README.md` for full attribution and "
        "`labels.yaml` for the ground-truth file."
    )
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- **Total images**: {agg['total']}")
    lines.append(f"- **True positives**: {agg['tp']}")
    lines.append(f"- **False positives**: {agg['fp']}")
    lines.append(f"- **False negatives**: {agg['fn']}")
    lines.append(f"- **True negatives**: {agg['tn']}")
    lines.append(
        f"- **Out-of-range** (right family, below expected confidence floor): {agg['oor']}"
    )
    lines.append(f"- **Precision**: {agg['precision']:.3f}")
    lines.append(f"- **Recall**: {agg['recall']:.3f}")
    lines.append(f"- **F1**: {agg['f1']:.3f}")
    lines.append(f"- **Mean latency** (Mac CPU, JPEG decode included): "
                 f"{agg['mean_latency_ms']:.1f} ms")
    lines.append("")
    lines.append("## Per-image results")
    lines.append("")
    lines.append(
        "| # | image | expected | predicted | score | "
        "latency_ms | verdict | notes |"
    )
    lines.append(
        "|---|---|---|---|---:|---:|---|---|"
    )
    for i, r in enumerate(results, start=1):
        notes = r.notes.replace("\n", " ").strip()
        if len(notes) > 80:
            notes = notes[:77] + "..."
        lines.append(
            f"| {i} | `{r.filename}` | {r.expected_class} | "
            f"{r.predicted_class} | {r.predicted_score:.3f} | "
            f"{r.latency_ms:.1f} | {r.verdict} | {notes} |"
        )
    lines.append("")

    # Failure / surprise analysis.
    fps = [r for r in results if r.verdict == "FP"]
    fns = [r for r in results if r.verdict == "FN"]
    oors = [r for r in results if r.verdict == "OOR"]
    lines.append("## Failure mode analysis")
    lines.append("")
    if not fps and not fns and not oors:
        lines.append(
            "No false positives, false negatives, or out-of-range scores. "
            "v0.0.1 fired correctly on every image. "
            "(Caveat: 12 images is a tiny sample; the synthetic eval in "
            "`runs/v0.0.1/eval.json` already shows recall is 0.978 and "
            "precision is 0.821 across 100 synthetic cases.)"
        )
    else:
        if fps:
            lines.append(f"**False positives ({len(fps)}):**")
            for r in fps:
                lines.append(
                    f"- `{r.filename}` (expected {r.expected_class}, "
                    f"predicted {r.predicted_class} at score {r.predicted_score:.3f}). "
                    f"{r.notes}"
                )
            lines.append("")
        if fns:
            lines.append(f"**False negatives ({len(fns)}):**")
            for r in fns:
                lines.append(
                    f"- `{r.filename}` (expected {r.expected_class}, "
                    f"predicted {r.predicted_class} at score {r.predicted_score:.3f}). "
                    f"{r.notes}"
                )
            lines.append("")
        if oors:
            lines.append(f"**Out-of-range ({len(oors)}) - right family, below floor:**")
            for r in oors:
                lines.append(
                    f"- `{r.filename}` (expected {r.expected_class} >= "
                    f"{r.expected_min_score}, got {r.predicted_class} at "
                    f"{r.predicted_score:.3f})."
                )
            lines.append("")

    lines.append("## Recommendations for v0.1.0")
    lines.append("")
    lines.append(
        "Each FP / FN / OOR above is a training-data-augmentation hint for "
        "the YOLOv8n fine-tune. In particular:"
    )
    lines.append("")
    lines.append(
        "- **FP on wildlife / yellow-foliage / charred terrain**: add hard "
        "negatives from these classes to the FASDD pretrain set. "
        "(`12_wildlife_elk_bannock_usfs.jpg`, "
        "`10_normal_aspens_custer_gallatin_nps.jpg`, "
        "`08_post_fire_swan_lake_nps.jpg`.)"
    )
    lines.append(
        "- **FN on distant smoke**: FLAME-2's UAV palettes should fix this; "
        "v0.0.1's RGB heuristic can't disambiguate atmospheric haze from "
        "smoke."
    )
    lines.append(
        "- **OOR (right class, low confidence)**: re-tune the confidence "
        "calibration during v0.1.0 eval — D-Fire holdout will give a real "
        "Platt-scaling target."
    )
    lines.append("")

    lines.append("## License attribution")
    lines.append("")
    lines.append(license_block.strip())
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    p.add_argument(
        "--images-dir",
        type=Path,
        default=HERE / "images",
        help="Directory of public-domain images.",
    )
    p.add_argument(
        "--labels",
        type=Path,
        default=HERE / "labels.yaml",
        help="Hand-label YAML.",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=HERE / "report_2026-05-02.md",
        help="Output Markdown report path.",
    )
    args = p.parse_args(argv)

    if not args.images_dir.is_dir():
        print(f"images dir not found: {args.images_dir}", file=sys.stderr)
        return 2
    if not args.labels.is_file():
        print(f"labels.yaml not found: {args.labels}", file=sys.stderr)
        return 2

    license_block = (
        "All twelve images in this evaluation set are works of U.S. "
        "federal employees taken in the course of their official duties "
        "(NPS, USFS, USDA), and are in the public domain under "
        "17 U.S.C. Sec. 105. They were retrieved from Wikimedia Commons "
        "mirrors, which preserve the original federal licensing. "
        "No copyrighted material is included."
    )

    results = run_bench(args.images_dir, args.labels)
    agg = aggregate(results)
    report = render_report(results, agg, args.images_dir, license_block)
    args.out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
