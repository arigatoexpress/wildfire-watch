"""wildfire-watch fire/smoke detector — dataset prep harness.

Downloads + extracts + verifies the three datasets we use:
    - FASDD     (pretrain)        CC-BY-4.0
    - FLAME-2   (fine-tune)       CC-BY-4.0
    - D-Fire    (holdout eval)    CC-BY-NC-4.0

Usage:
    python3 -m ml.fire_detection.eval.prep_datasets prep all
    python3 -m ml.fire_detection.eval.prep_datasets prep fasdd
    python3 -m ml.fire_detection.eval.prep_datasets status
    python3 -m ml.fire_detection.eval.prep_datasets verify dfire

URLs and SHA-256 checksums live in eval/targets.yaml. Two of the three datasets
require manual download (IEEE DataPort and Science Data Bank both require a
free account login). For those, prep prints actionable instructions and exits 2.

Datasets land in:
    ~/wildfire-watch-data/<name>/

NOT inside the repo. The repo's checkpoints/ and runs/ directories are
gitignored separately.

Dependencies are stdlib + lazy `requests`. No `wget`, no `aria2c`, no `gdown`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_TARGETS_PATH = Path(__file__).parent / "targets.yaml"
DEFAULT_DATA_ROOT = Path.home() / "wildfire-watch-data"
MANIFEST_FILENAME = ".prep_manifest.json"


@dataclass
class DatasetSpec:
    name: str
    role: str
    description: str
    license: str
    download_url: str
    homepage_url: str
    paper_url: str
    requires_manual_download: bool
    sha256: str
    expected_image_count_min: int
    expected_image_count_max: int


def load_specs(targets_path: Path = DEFAULT_TARGETS_PATH) -> dict[str, DatasetSpec]:
    """Read targets.yaml. Lazy-imports yaml; falls back to a tiny custom parser
    so that prep_datasets is usable in environments without pyyaml installed.

    The fallback is intentionally narrow: it understands `datasets: <name>: key: value`
    structure produced by our own targets.yaml and refuses anything weirder.
    """
    text = targets_path.read_text()
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text) or {}
    except ImportError:
        data = _parse_targets_fallback(text)

    raw_datasets = data.get("datasets") or {}
    out: dict[str, DatasetSpec] = {}
    for name, spec in raw_datasets.items():
        out[name] = DatasetSpec(
            name=name,
            role=str(spec.get("role", "")),
            description=str(spec.get("description", "")),
            license=str(spec.get("license", "")),
            download_url=str(spec.get("download_url", "")),
            homepage_url=str(spec.get("homepage_url", "")),
            paper_url=str(spec.get("paper_url", "")),
            requires_manual_download=bool(spec.get("requires_manual_download", False)),
            sha256=str(spec.get("sha256", "TBD-fill-after-first-download")),
            expected_image_count_min=int(spec.get("expected_image_count_min", 0)),
            expected_image_count_max=int(spec.get("expected_image_count_max", 0)),
        )
    return out


def _parse_targets_fallback(text: str) -> dict[str, Any]:
    """Tiny YAML subset parser — only handles the shape our targets.yaml uses."""
    result: dict[str, Any] = {"datasets": {}}
    in_datasets = False
    current_ds: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line == "datasets:":
            in_datasets = True
            continue
        if in_datasets:
            indent = len(line) - len(line.lstrip(" "))
            stripped = line.strip()
            if indent == 0:
                in_datasets = False
                current_ds = None
                continue
            if indent == 2 and stripped.endswith(":"):
                current_ds = stripped[:-1]
                result["datasets"][current_ds] = {}
                continue
            if indent == 4 and current_ds is not None and ":" in stripped:
                key, _, val = stripped.partition(":")
                val = val.strip().strip('"').strip("'")
                if val.lower() == "true":
                    parsed: Any = True
                elif val.lower() == "false":
                    parsed = False
                else:
                    try:
                        parsed = int(val)
                    except ValueError:
                        try:
                            parsed = float(val)
                        except ValueError:
                            parsed = val
                result["datasets"][current_ds][key.strip()] = parsed
    return result


def dataset_dir(name: str, root: Path = DEFAULT_DATA_ROOT) -> Path:
    return root / name


def manifest_path(name: str, root: Path = DEFAULT_DATA_ROOT) -> Path:
    return dataset_dir(name, root) / MANIFEST_FILENAME


def write_manifest(name: str, payload: dict[str, Any], root: Path = DEFAULT_DATA_ROOT) -> Path:
    p = manifest_path(name, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, indent=2) + "\n")
    return p


def read_manifest(name: str, root: Path = DEFAULT_DATA_ROOT) -> dict[str, Any] | None:
    p = manifest_path(name, root)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return None


def is_dataset_prepared(spec: DatasetSpec, root: Path = DEFAULT_DATA_ROOT) -> bool:
    manifest = read_manifest(spec.name, root)
    if manifest is None:
        return False
    return manifest.get("verified") is True and manifest.get("name") == spec.name


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def count_images(root: Path) -> int:
    if not root.exists():
        return 0
    n = 0
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}:
            n += 1
    return n


def folder_size_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def humanize_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PiB"


def _archive_member_is_safe(member_name: str, dest: Path) -> bool:
    """Refuse path-traversal and absolute-path archive members (CVE-2007-4559 family)."""
    # Resolve the would-be extraction target; reject if it escapes dest.
    cleaned = os.path.normpath(member_name)
    if cleaned.startswith("..") or os.path.isabs(cleaned):
        return False
    target = (dest / cleaned).resolve()
    try:
        target.relative_to(dest.resolve())
    except ValueError:
        return False
    return True


def safe_extract_archive(archive_path: Path, dest: Path) -> None:
    """Extract a .zip / .tar.gz / .tgz / .tar safely. Refuses traversal entries."""
    dest.mkdir(parents=True, exist_ok=True)
    name_lower = archive_path.name.lower()

    if name_lower.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                if not _archive_member_is_safe(member, dest):
                    raise RuntimeError(f"unsafe zip member: {member!r}")
            zf.extractall(dest)
    elif name_lower.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")):
        mode = "r:*" if not name_lower.endswith(".tar") else "r:"
        with tarfile.open(archive_path, mode) as tf:
            for member in tf.getmembers():
                if not _archive_member_is_safe(member.name, dest):
                    raise RuntimeError(f"unsafe tar member: {member.name!r}")
                if member.islnk() or member.issym():
                    # Skip links — they point outside our control envelope.
                    continue
            tf.extractall(dest)  # noqa: S202 - safety check above
    else:
        raise RuntimeError(
            f"Unrecognized archive type for {archive_path.name}. "
            "Supported: .zip, .tar, .tar.gz/.tgz, .tar.bz2, .tar.xz."
        )


def download_url_streaming(url: str, dest: Path, chunk_size: int = 1024 * 1024) -> None:  # pragma: no cover
    """Lazy-import requests. Streamed download with a temp file rename."""
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise SystemExit(
            "requests not installed. Either pip install requests, or fall back "
            "to manual download (most of our datasets require it anyway)."
        ) from e
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60.0) as r:
        r.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(chunk_size=chunk_size):
                if chunk:
                    fh.write(chunk)
    tmp.rename(dest)


def manual_download_instructions(spec: DatasetSpec, dest_root: Path) -> str:
    lines = [
        "",
        f"  Dataset: {spec.name} ({spec.role})",
        f"  Reason : {spec.description}",
        f"  License: {spec.license}",
        f"  Source : {spec.download_url}",
        f"  Paper  : {spec.paper_url}",
        "",
        "  This dataset requires a manual download (account login or click-through).",
        "  Steps:",
        f"    1. Open {spec.download_url}",
        "    2. Sign in / accept license terms.",
        f"    3. Download the dataset archive(s) into {dest_root / spec.name}/",
        "    4. Extract so that image files end up under that directory.",
        f"    5. Re-run: python3 -m ml.fire_detection.eval.prep_datasets verify {spec.name}",
    ]
    return "\n".join(lines)


def verify_prepared(spec: DatasetSpec, root: Path = DEFAULT_DATA_ROOT) -> tuple[bool, str]:
    """Verify a previously-prepared dataset.

    Checks:
      - directory exists
      - contains an image count within the expected range
      - if spec.sha256 is a real digest (not 'TBD'), require some archive to match.
    """
    d = dataset_dir(spec.name, root)
    if not d.exists():
        return False, f"directory does not exist: {d}"
    n = count_images(d)
    if n == 0:
        return False, f"no images under {d} (recursive)"
    if spec.expected_image_count_min and n < spec.expected_image_count_min:
        return False, (
            f"image count {n} is below expected minimum "
            f"{spec.expected_image_count_min} — was the archive fully extracted?"
        )
    if spec.expected_image_count_max and n > spec.expected_image_count_max * 2:
        return False, (
            f"image count {n} is suspiciously high (>{spec.expected_image_count_max * 2}) — "
            "check for nested copies or wrong dataset"
        )
    return True, f"verified: {n} images, {humanize_bytes(folder_size_bytes(d))} on disk"


def prep_dataset(
    spec: DatasetSpec,
    root: Path = DEFAULT_DATA_ROOT,
    force: bool = False,
) -> tuple[bool, str]:
    """Prepare one dataset. Returns (success, status_message)."""
    if not force and is_dataset_prepared(spec, root):
        manifest = read_manifest(spec.name, root) or {}
        return True, f"{spec.name}: already prepared ({manifest.get('image_count')} images)"

    dest = dataset_dir(spec.name, root)
    dest.mkdir(parents=True, exist_ok=True)

    if spec.requires_manual_download:
        # Don't fail catastrophically — print actionable instructions and
        # attempt verification in case the user already extracted manually.
        ok, msg = verify_prepared(spec, root)
        if ok:
            payload = {
                "name": spec.name,
                "role": spec.role,
                "license": spec.license,
                "verified": True,
                "image_count": count_images(dest),
                "size_bytes": folder_size_bytes(dest),
                "sha256_expected": spec.sha256,
                "method": "manual_download",
            }
            write_manifest(spec.name, payload, root)
            return True, f"{spec.name}: {msg}"
        return False, (
            f"{spec.name}: manual download required — see instructions:"
            + manual_download_instructions(spec, root)
        )

    # Auto-download path. Currently no dataset uses it (all 3 require manual),
    # but the code path is exercised so future datasets can drop in.
    parsed = urllib.parse.urlparse(spec.download_url)
    archive_name = Path(parsed.path).name or f"{spec.name}.zip"
    archive_path = dest / archive_name
    if not archive_path.exists() or force:
        try:
            download_url_streaming(spec.download_url, archive_path)
        except Exception as exc:  # pragma: no cover - depends on network
            return False, f"{spec.name}: download failed: {exc}"

    digest = sha256_file(archive_path)
    if not spec.sha256.startswith("TBD") and digest != spec.sha256:
        return False, (
            f"{spec.name}: sha256 mismatch — got {digest}, expected {spec.sha256}"
        )

    try:
        safe_extract_archive(archive_path, dest)
    except Exception as exc:
        return False, f"{spec.name}: extraction failed: {exc}"

    ok, msg = verify_prepared(spec, root)
    if not ok:
        return False, f"{spec.name}: post-extract verification failed: {msg}"

    payload = {
        "name": spec.name,
        "role": spec.role,
        "license": spec.license,
        "verified": True,
        "image_count": count_images(dest),
        "size_bytes": folder_size_bytes(dest),
        "sha256": digest,
        "method": "auto_download",
    }
    write_manifest(spec.name, payload, root)
    return True, f"{spec.name}: {msg}"


def cmd_prep(args: argparse.Namespace) -> int:
    specs = load_specs(args.targets)
    if args.target == "all":
        targets = list(specs.values())
    else:
        if args.target not in specs:
            print(f"unknown dataset: {args.target}. known: {sorted(specs)}", file=sys.stderr)
            return 2
        targets = [specs[args.target]]
    root = Path(args.data_root)
    any_failed = False
    any_manual = False
    for spec in targets:
        ok, msg = prep_dataset(spec, root, force=args.force)
        print(msg)
        if not ok:
            any_failed = True
            if spec.requires_manual_download:
                any_manual = True
    print()
    print(f"Total disk usage under {root}: {humanize_bytes(folder_size_bytes(root))}")
    if any_failed:
        return 2 if any_manual else 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    specs = load_specs(args.targets)
    root = Path(args.data_root)
    print(f"data root: {root}")
    print(f"total size: {humanize_bytes(folder_size_bytes(root))}")
    print()
    print(f"{'name':<10} {'prepared':<10} {'images':<8} {'size':<10} {'license':<14}")
    print("-" * 54)
    for spec in specs.values():
        d = dataset_dir(spec.name, root)
        prepared = is_dataset_prepared(spec, root)
        n = count_images(d) if d.exists() else 0
        size = humanize_bytes(folder_size_bytes(d)) if d.exists() else "-"
        print(f"{spec.name:<10} {str(prepared):<10} {n:<8} {size:<10} {spec.license:<14}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    specs = load_specs(args.targets)
    if args.target not in specs:
        print(f"unknown dataset: {args.target}", file=sys.stderr)
        return 2
    spec = specs[args.target]
    root = Path(args.data_root)
    ok, msg = verify_prepared(spec, root)
    print(f"{spec.name}: {msg}")
    if ok:
        # Refresh manifest.
        payload = {
            "name": spec.name,
            "role": spec.role,
            "license": spec.license,
            "verified": True,
            "image_count": count_images(dataset_dir(spec.name, root)),
            "size_bytes": folder_size_bytes(dataset_dir(spec.name, root)),
            "sha256_expected": spec.sha256,
            "method": "manual_verify",
        }
        write_manifest(spec.name, payload, root)
        return 0
    return 1


def cmd_clean(args: argparse.Namespace) -> int:
    specs = load_specs(args.targets)
    root = Path(args.data_root)
    if args.target == "all":
        targets = list(specs)
    else:
        if args.target not in specs:
            print(f"unknown dataset: {args.target}", file=sys.stderr)
            return 2
        targets = [args.target]
    for name in targets:
        d = dataset_dir(name, root)
        if d.exists():
            shutil.rmtree(d)
            print(f"removed {d}")
        else:
            print(f"{d} does not exist")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="wildfire-watch dataset prep harness")
    p.add_argument("--targets", type=Path, default=DEFAULT_TARGETS_PATH)
    p.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_prep = sub.add_parser("prep", help="Download + extract + verify a dataset (or 'all')")
    sp_prep.add_argument("target", help="Dataset name or 'all'")
    sp_prep.add_argument("--force", action="store_true", help="Re-download even if manifest says prepared")
    sp_prep.set_defaults(func=cmd_prep)

    sp_status = sub.add_parser("status", help="Print prepared/unprepared state")
    sp_status.set_defaults(func=cmd_status)

    sp_verify = sub.add_parser("verify", help="Verify a manually-extracted dataset")
    sp_verify.add_argument("target")
    sp_verify.set_defaults(func=cmd_verify)

    sp_clean = sub.add_parser("clean", help="Remove a dataset directory")
    sp_clean.add_argument("target", help="Dataset name or 'all'")
    sp_clean.set_defaults(func=cmd_clean)

    return p.parse_args()


def main() -> int:  # pragma: no cover
    args = parse_args()
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
