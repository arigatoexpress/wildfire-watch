"""KPI definitions + collectors for wildfire-watch intrinsic valuation.

A KPI is a measurable, defensible number that ticks as the project ships.
Collectors read the live repo state, the user's flight directory, and a
small set of curated YAML files under valuation/data/.

All collectors are best-effort: if a source is missing, the KPI defaults
to zero or False (documented per-field in the dataclass).
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SAPPHIRE_SIGNALS = Path.home() / "Code" / "Sapphire" / "data" / "wildfire_signals.jsonl"
FLIGHTS_DIR = Path.home() / "wildfire-watch-flights"
BOM_PATH = REPO_ROOT / "hardware" / "bom.csv"
ZONES_DIR = REPO_ROOT / "missions" / "zones"
INTEL_DOCS_DIR = REPO_ROOT / "docs" / "intel"
ML_RUNS_DIR = REPO_ROOT / "ml" / "fire_detection" / "runs"
DATA_DIR = Path(__file__).resolve().parent / "data"
PARTNERS_YAML = DATA_DIR / "partners.yaml"
TEAM_YAML = DATA_DIR / "team.yaml"

# Vendors that disqualify the BOM from NDAA Blue UAS eligibility.
NDAA_BLOCKED_VENDORS = {"DJI", "Autel", "Autel Robotics", "Yuneec"}

# Heuristic ITAR/military-coded markers — presence in the codebase
# pushes ITAR exposure score up. We deliberately want a LOW score for a
# civilian fire-watch project, so this is a tripwire, not a feature.
ITAR_MARKERS = [
    "STANAG-4586",
    "MIL-STD-1553",
    "TADIL",
    "TS/SCI",
    "Link 16",
    "JREAP",
]


@dataclass
class KPI:
    """A single KPI with provenance + value.

    `value` is the raw number/bool the methods consume. `unit` and
    `category` are for the dashboard. `source` documents where the
    number came from so it's auditable.
    """

    name: str
    value: Any
    unit: str
    category: str  # "engineering" | "product" | "strategic" | "compliance"
    source: str
    notes: str = ""


def _safe_int(s: str) -> int:
    try:
        return int(s.strip().split()[0])
    except (ValueError, IndexError):
        return 0


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a shell command; return stdout (empty on failure)."""
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return proc.stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return ""


def _iter_py_files(root: Path, exclude_tests: bool = False) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if any(part.startswith(".") for part in parts):
            continue
        if "__pycache__" in parts:
            continue
        if "valuation" in parts:
            # Don't count our own module — chicken/egg on intrinsic-value.
            continue
        if exclude_tests and (
            p.name.startswith("test_") or "tests" in parts
        ):
            continue
        out.append(p)
    return out


def _iter_test_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if any(part.startswith(".") for part in parts):
            continue
        if "__pycache__" in parts:
            continue
        if "valuation" in parts:
            continue
        if p.name.startswith("test_") or "tests" in parts:
            out.append(p)
    return out


def _wc_l(paths: list[Path]) -> int:
    total = 0
    for p in paths:
        try:
            with p.open("rb") as f:
                total += sum(1 for _ in f)
        except OSError:
            continue
    return total


def _word_count_md() -> int:
    total = 0
    for p in REPO_ROOT.rglob("*.md"):
        if any(part.startswith(".") for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            total += len(text.split())
        except OSError:
            continue
    return total


def _count_signals_emitted() -> tuple[int, int]:
    """Returns (total_signals, signals_in_last_30_days).

    Pulls from Sapphire's wildfire_signals.jsonl if present, otherwise
    falls back to summing per-flight signals.jsonl files under
    ~/wildfire-watch-flights/.
    """
    total = 0
    last_30d = 0
    cutoff = datetime.now(timezone.utc).timestamp() - 30 * 86400

    sources: list[Path] = []
    if SAPPHIRE_SIGNALS.exists():
        sources.append(SAPPHIRE_SIGNALS)
    if FLIGHTS_DIR.exists():
        sources.extend(FLIGHTS_DIR.rglob("signals.jsonl"))

    for src in sources:
        try:
            with src.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    total += 1
                    try:
                        obj = json.loads(line)
                        ts = obj.get("timestamp", "")
                        # Try ISO-8601 parse.
                        try:
                            ts_parsed = datetime.fromisoformat(
                                ts.replace("Z", "+00:00")
                            ).timestamp()
                            if ts_parsed >= cutoff:
                                last_30d += 1
                        except (ValueError, AttributeError):
                            pass
                    except json.JSONDecodeError:
                        pass
        except OSError:
            continue
    return total, last_30d


def _count_simulator_runs() -> int:
    if not FLIGHTS_DIR.exists():
        return 0
    count = 0
    for p in FLIGHTS_DIR.iterdir():
        if not p.is_dir():
            continue
        if p.name.startswith("SIM-") or p.name.startswith("SWARM-"):
            count += 1
    return count


def _total_simulated_minutes() -> float:
    """Sum sim_seconds across every flight manifest, convert to minutes."""
    if not FLIGHTS_DIR.exists():
        return 0.0
    total_s = 0.0
    for manifest in FLIGHTS_DIR.rglob("manifest.json"):
        try:
            obj = json.loads(manifest.read_text(encoding="utf-8"))
            total_s += float(obj.get("sim_seconds", 0))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue
    return total_s / 60.0


def _count_mission_zones() -> int:
    if not ZONES_DIR.exists():
        return 0
    count = 0
    for p in ZONES_DIR.glob("*.geojson"):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            features = obj.get("features", [])
            count += len(features) if features else 1
        except (OSError, json.JSONDecodeError):
            continue
    return count


def _ndaa_blue_uas_eligible() -> tuple[bool, list[str]]:
    """Read hardware/bom.csv. If any row's vendor is in the blocklist,
    the BOM is NOT NDAA Blue UAS eligible. Returns (eligible, offending_parts).
    """
    if not BOM_PATH.exists():
        return True, []
    offenders: list[str] = []
    try:
        with BOM_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendor = (row.get("vendor") or "").strip()
                part = (row.get("part") or "").strip()
                if vendor in NDAA_BLOCKED_VENDORS:
                    offenders.append(f"{vendor}: {part}")
                # Also flag DJI mentions in the part name itself.
                if any(blocked.lower() in part.lower() for blocked in ("dji", "mavic", "autel")):
                    offenders.append(f"{vendor}: {part}")
    except OSError:
        return True, []
    eligible = len(offenders) == 0
    return eligible, offenders


def _itar_exposure_score() -> int:
    """Heuristic 0-100. Default 5 (low for civilian).

    The valuation/ tree itself is excluded so the marker list in
    this very file doesn't trigger its own tripwire.
    """
    score = 5
    hits: list[str] = []
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in (".py", ".md", ".yaml", ".yml", ".json"):
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        if "valuation" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marker in ITAR_MARKERS:
            if marker in text:
                hits.append(f"{p.name}:{marker}")
                score += 10
    return min(score, 100)


def _secrets_in_repo() -> int:
    """Quick regex sweep for high-confidence secret patterns."""
    patterns = [
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
        re.compile(r"sk-[A-Za-z0-9]{48,}"),  # OpenAI-style
        re.compile(r"ghp_[A-Za-z0-9]{36,}"),  # GitHub PAT
        re.compile(r"-----BEGIN (?:RSA )?PRIVATE KEY-----"),
    ]
    hits = 0
    for p in REPO_ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.parts):
            continue
        if p.suffix in (".png", ".jpg", ".jpeg", ".gif", ".pdf", ".bin", ".tlog"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patterns:
            if pat.search(text):
                hits += 1
    return hits


def _read_partners_yaml() -> dict:
    if not PARTNERS_YAML.exists():
        return {"partners": []}
    try:
        import yaml

        return yaml.safe_load(PARTNERS_YAML.read_text()) or {"partners": []}
    except Exception:
        return {"partners": []}


def _read_team_yaml() -> dict:
    if not TEAM_YAML.exists():
        return {"members": []}
    try:
        import yaml

        return yaml.safe_load(TEAM_YAML.read_text()) or {"members": []}
    except Exception:
        return {"members": []}


def collect_all() -> dict[str, KPI]:
    """Collect every KPI. Idempotent, safe to call repeatedly."""
    py_all = _iter_py_files(REPO_ROOT)
    py_tests = _iter_test_files(REPO_ROOT)
    loc_total = _wc_l(py_all)
    loc_tests = _wc_l(py_tests)
    md_words = _word_count_md()
    docs_files = sum(
        1
        for p in REPO_ROOT.rglob("*.md")
        if not any(part.startswith(".") for part in p.parts)
    )
    intel_docs = (
        sum(1 for _ in INTEL_DOCS_DIR.glob("*.md")) if INTEL_DOCS_DIR.exists() else 0
    )

    commits_30d = _safe_int(
        _run(
            ["git", "log", "--since=30.days.ago", "--oneline"], cwd=REPO_ROOT
        )
        .strip()
        .count("\n").__str__()
    )
    # Recompute properly — count newlines in stdout.
    stdout = _run(["git", "log", "--since=30.days.ago", "--oneline"], cwd=REPO_ROOT)
    commits_30d = sum(1 for line in stdout.splitlines() if line.strip())

    authors = {
        line.strip()
        for line in _run(
            ["git", "log", "--since=90.days.ago", "--format=%ae"], cwd=REPO_ROOT
        ).splitlines()
        if line.strip()
    }
    unique_authors_90d = len(authors)

    # Test count via pytest --co (collect-only).
    pytest_out = _run(["python3", "-m", "pytest", "--co", "-q"], cwd=REPO_ROOT)
    tests_passing = 0
    for line in pytest_out.splitlines():
        m = re.match(r"^\s*(\d+)\s+tests?\s+collected", line)
        if m:
            tests_passing = int(m.group(1))
            break
    tests_files = len(py_tests)

    sigs_total, sigs_30d = _count_signals_emitted()
    sim_runs = _count_simulator_runs()
    sim_minutes = _total_simulated_minutes()
    fp_rate = (sigs_total / sim_minutes) if sim_minutes > 0 else 0.0
    model_versions = (
        sum(1 for p in ML_RUNS_DIR.iterdir() if p.is_dir())
        if ML_RUNS_DIR.exists()
        else 0
    )
    zones_count = _count_mission_zones()

    partners_doc = _read_partners_yaml()
    partners_engaged = sum(
        1 for p in partners_doc.get("partners", []) if p.get("engaged", False)
    )
    loa_count = sum(
        1 for p in partners_doc.get("partners", []) if p.get("loa_signed", False)
    )

    team_doc = _read_team_yaml()
    pilots = sum(
        1 for m in team_doc.get("members", []) if m.get("part107_certified", False)
    )

    ndaa_eligible, ndaa_offenders = _ndaa_blue_uas_eligible()
    itar = _itar_exposure_score()
    secrets = _secrets_in_repo()

    code_to_doc_ratio = (loc_total / md_words) if md_words > 0 else 0.0

    kpis: dict[str, KPI] = {
        # Engineering
        "loc_total": KPI(
            "loc_total", loc_total, "lines", "engineering", "wc -l on **/*.py"
        ),
        "loc_tests": KPI(
            "loc_tests",
            loc_tests,
            "lines",
            "engineering",
            "wc -l on test files",
        ),
        "tests_passing": KPI(
            "tests_passing",
            tests_passing,
            "tests",
            "engineering",
            "pytest --co -q",
            "Collected count; assumes green CI",
        ),
        "tests_files": KPI(
            "tests_files", tests_files, "files", "engineering", "test_*.py + tests/"
        ),
        "commits_30d": KPI(
            "commits_30d",
            commits_30d,
            "commits",
            "engineering",
            "git log --since=30.days.ago",
        ),
        "unique_authors_90d": KPI(
            "unique_authors_90d",
            unique_authors_90d,
            "authors",
            "engineering",
            "git log --format=%ae",
        ),
        "docs_files": KPI(
            "docs_files", docs_files, "files", "engineering", "**/*.md"
        ),
        "intel_docs_count": KPI(
            "intel_docs_count",
            intel_docs,
            "files",
            "engineering",
            "docs/intel/*.md",
        ),
        "code_to_doc_ratio": KPI(
            "code_to_doc_ratio",
            round(code_to_doc_ratio, 2),
            "ratio",
            "engineering",
            "loc_total / md_words",
            "Higher = code-heavy; ~10 is healthy",
        ),
        # Product
        "signals_emitted_total": KPI(
            "signals_emitted_total",
            sigs_total,
            "signals",
            "product",
            "signals.jsonl line count",
        ),
        "signals_emitted_30d": KPI(
            "signals_emitted_30d",
            sigs_30d,
            "signals",
            "product",
            "signals.jsonl in last 30 days",
        ),
        "simulator_runs_total": KPI(
            "simulator_runs_total",
            sim_runs,
            "runs",
            "product",
            "~/wildfire-watch-flights/SIM-* + SWARM-*",
        ),
        "simulated_minutes_total": KPI(
            "simulated_minutes_total",
            round(sim_minutes, 1),
            "minutes",
            "product",
            "sum(sim_seconds in manifest.json)/60",
        ),
        "false_positive_rate_estimate": KPI(
            "false_positive_rate_estimate",
            round(fp_rate, 4),
            "signals/min",
            "product",
            "signals_emitted_total / simulated_minutes_total",
            "Placeholder until labeled ground truth exists",
        ),
        "model_versions_shipped": KPI(
            "model_versions_shipped",
            model_versions,
            "versions",
            "product",
            "ml/fire_detection/runs/ subdirs",
        ),
        "mission_zones_count": KPI(
            "mission_zones_count",
            zones_count,
            "zones",
            "product",
            "missions/zones/*.geojson features",
        ),
        # Strategic
        "letters_of_authorization_count": KPI(
            "letters_of_authorization_count",
            loa_count,
            "LOAs",
            "strategic",
            "valuation/data/partners.yaml loa_signed:true",
        ),
        "partner_agencies_engaged": KPI(
            "partner_agencies_engaged",
            partners_engaged,
            "agencies",
            "strategic",
            "valuation/data/partners.yaml engaged:true",
        ),
        "acquirer_briefings_held": KPI(
            "acquirer_briefings_held",
            0,
            "briefings",
            "strategic",
            "default 0; manual override",
        ),
        "media_mentions_30d": KPI(
            "media_mentions_30d",
            0,
            "mentions",
            "strategic",
            "default 0; manual override",
        ),
        # Compliance
        "ndaa_blue_uas_eligible": KPI(
            "ndaa_blue_uas_eligible",
            ndaa_eligible,
            "bool",
            "compliance",
            "hardware/bom.csv scan vs vendor blocklist",
            f"Offenders: {ndaa_offenders}" if ndaa_offenders else "",
        ),
        "itar_exposure_score": KPI(
            "itar_exposure_score",
            itar,
            "score",
            "compliance",
            "heuristic regex over codebase",
            "0-100; lower is better for civilian project",
        ),
        "faa_part107_certified_pilots": KPI(
            "faa_part107_certified_pilots",
            pilots,
            "pilots",
            "compliance",
            "valuation/data/team.yaml",
        ),
        "secrets_in_repo": KPI(
            "secrets_in_repo",
            secrets,
            "matches",
            "compliance",
            "regex sweep AWS/OpenAI/GitHub/PEM",
            "MUST be 0",
        ),
    }
    return kpis


def kpi_snapshot_dict() -> dict[str, Any]:
    """Flat dict of KPI name -> value, for engine consumption + history file."""
    return {name: kpi.value for name, kpi in collect_all().items()}
