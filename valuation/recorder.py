"""Snapshot recorder: append valuation runs to data/valuation_history.jsonl.

The history file is gitignored (see valuation/.gitignore). Each line is
a self-contained JSON record so it can be parsed with `jq` or replayed
in a chart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HISTORY_PATH = Path(__file__).resolve().parent / "data" / "valuation_history.jsonl"


def append_snapshot(snapshot: dict[str, Any], path: Path | None = None) -> Path:
    """Append a snapshot to the history file. Creates parent dir if needed."""
    p = path or HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, default=str) + "\n")
    return p


def read_history(path: Path | None = None, *, last_n: int | None = None) -> list[dict[str, Any]]:
    """Read all snapshot records, optionally truncated to last_n."""
    p = path or HISTORY_PATH
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if last_n is not None:
        out = out[-last_n:]
    return out


def find_snapshot_by_sha(sha: str, path: Path | None = None) -> dict[str, Any] | None:
    """Return the snapshot whose commit_sha starts with `sha`, or None."""
    for rec in read_history(path):
        cs = rec.get("commit_sha", "")
        if cs and (cs == sha or cs.startswith(sha)):
            return rec
    return None
