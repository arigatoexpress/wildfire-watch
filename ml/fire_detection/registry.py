"""wildfire-watch fire/smoke detector model registry.

Scans ``ml/fire_detection/runs/`` for versioned model directories and exposes
them as typed entries. Each version directory is expected to contain at
minimum:

- ``manifest.json`` - metadata + provenance (model_id, version, type, license,
  code_sha, released_at, ...).
- ``eval.json`` - measured eval output (precision/recall/latency/...).

Version directories that don't have both files are skipped silently so a
half-prepared release in flight doesn't break the registry. (The KPI
collector counts entries that ``list_models()`` returns, which by design
means a malformed half-built version doesn't pump the
``model_versions_shipped`` number.)

Public API:

- :func:`list_models` - all valid entries on disk, sorted by version.
- :func:`get` - look up by model_id, version, or 'latest'.
- :func:`shipped_count` - integer count of valid entries; mirrors what
  ``valuation/kpis.py`` reports.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUNS_DIR = Path(__file__).resolve().parent / "runs"

_VERSION_DIR_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$")

# Permitted status values on ModelEntry. Any string can appear in manifest.json,
# but the registry normalizes unknown values to STATUS_UNKNOWN so dashboards
# can rely on the closed set.
STATUS_RELEASED = "RELEASED"
STATUS_TRAINING_READY = "TRAINING_READY"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"
ALLOWED_STATUSES = frozenset(
    {STATUS_RELEASED, STATUS_TRAINING_READY, STATUS_BLOCKED, STATUS_UNKNOWN}
)


@dataclass(frozen=True)
class ModelEntry:
    """One registered model version on disk.

    The ``status`` field is read from ``manifest.json["status"]`` and
    normalized into the closed set ``ALLOWED_STATUSES``. Older manifests
    that don't carry a status field default to ``STATUS_UNKNOWN`` so they
    don't crash the registry; dashboards should treat UNKNOWN as
    "manifest predates the status convention" rather than as a bug.

    Both RELEASED and TRAINING_READY count as "shipped" for the
    valuation engine's ``model_versions_shipped`` KPI: the manifest +
    recipe + entrypoint together are a shipped artifact, even when the
    trained weights are pending. BLOCKED entries are still counted —
    the operator should explicitly remove the run-dir to drop them
    from the registry.
    """

    model_id: str
    version: str
    path: Path
    released_at: str
    eval: dict[str, Any]
    manifest: dict[str, Any]
    status: str = STATUS_UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "version": self.version,
            "path": str(self.path),
            "released_at": self.released_at,
            "eval": self.eval,
            "manifest": self.manifest,
            "status": self.status,
        }


def _parse_version_tuple(version: str) -> tuple[int, int, int]:
    """Sortable tuple from a semver-ish 'x.y.z' or 'vx.y.z' string."""
    s = version.lstrip("v")
    # Strip pre-release / build metadata for sorting.
    s = s.split("-", 1)[0].split("+", 1)[0]
    parts = s.split(".")
    while len(parts) < 3:
        parts.append("0")
    out: list[int] = []
    for p in parts[:3]:
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return out[0], out[1], out[2]


def _is_version_dir(p: Path) -> bool:
    return p.is_dir() and bool(_VERSION_DIR_RE.match(p.name))


def _load_entry(p: Path) -> ModelEntry | None:
    """Load one version dir into an entry, or return None if invalid."""
    manifest_path = p / "manifest.json"
    eval_path = p / "eval.json"
    if not manifest_path.exists() or not eval_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        eval_blob = json.loads(eval_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(eval_blob, dict):
        return None

    model_id = str(manifest.get("model_id") or "")
    version = str(manifest.get("version") or p.name.lstrip("v"))
    released_at = str(manifest.get("released_at") or "")
    if not model_id or not version:
        return None

    raw_status = manifest.get("status")
    status = str(raw_status).upper() if raw_status else STATUS_UNKNOWN
    if status not in ALLOWED_STATUSES:
        status = STATUS_UNKNOWN

    return ModelEntry(
        model_id=model_id,
        version=version,
        path=p,
        released_at=released_at,
        eval=eval_blob,
        manifest=manifest,
        status=status,
    )


def list_models(runs_dir: Path | None = None) -> list[ModelEntry]:
    """Return all valid model entries on disk, sorted ascending by version."""
    root = runs_dir or RUNS_DIR
    if not root.exists():
        return []
    entries: list[ModelEntry] = []
    for child in sorted(root.iterdir()):
        if not _is_version_dir(child):
            continue
        entry = _load_entry(child)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda e: _parse_version_tuple(e.version))
    return entries


def get(model_id_or_version: str, runs_dir: Path | None = None) -> ModelEntry | None:
    """Look up an entry by model_id, version (with or without 'v'), or 'latest'.

    Examples::

        get("wfw-fire-heuristic-v0.0.1")
        get("0.0.1")
        get("v0.0.1")
        get("latest")  # highest version on disk
    """
    entries = list_models(runs_dir)
    if not entries:
        return None

    key = (model_id_or_version or "").strip()
    if not key:
        return None
    if key == "latest":
        return entries[-1]

    # Try exact model_id match first.
    for e in entries:
        if e.model_id == key:
            return e

    # Then version match (with or without leading 'v').
    norm = key.lstrip("v")
    for e in entries:
        if e.version == key or e.version == norm or e.version.lstrip("v") == norm:
            return e

    return None


def shipped_count(runs_dir: Path | None = None) -> int:
    """Number of valid (manifest+eval-bearing) model entries.

    Mirrors what ``valuation/kpis.py`` reports for the
    ``model_versions_shipped`` KPI. (The valuation collector counts raw
    subdirs; this function counts validated entries. They agree as long as
    each version dir has its manifest.json + eval.json.)

    Both ``RELEASED`` and ``TRAINING_READY`` entries are counted: the
    artifact (manifest + recipe + entrypoint) is shipped even when the
    trained weights are pending. ``BLOCKED`` entries are also counted
    until the operator removes the run-dir.
    """
    return len(list_models(runs_dir))


def count_by_status(runs_dir: Path | None = None) -> dict[str, int]:
    """Bucket the valid entries by their normalized ``status`` field.

    Useful for dashboards that need to distinguish "models with weights"
    from "training-ready recipes". Returns a dict with keys drawn from
    ``ALLOWED_STATUSES`` (entries with no manifests-status default to
    ``STATUS_UNKNOWN``).
    """
    counts: dict[str, int] = {s: 0 for s in ALLOWED_STATUSES}
    for entry in list_models(runs_dir):
        counts[entry.status] = counts.get(entry.status, 0) + 1
    return counts
