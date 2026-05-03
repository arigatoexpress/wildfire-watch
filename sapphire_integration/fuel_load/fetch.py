"""HTTPS fetcher with on-disk cache for fuel-load datasets.

Cache layout:
    ~/.cache/wildfire-watch/fuel_load/<source-name>/<filename>

Honors `FuelLoadSource.freshness_days`. Uses the stdlib `urllib`
fallback when `requests` is not installed (lazy import).

Manual-only sources raise `FetchUnavailable` so the caller can surface
the operator-facing instructions in `notes`. We never auto-fetch from a
manual-only source — the licensing posture (some CO-state data needs
attribution review, FIA needs careful interpretation, NOAA HRRR is
run-time-only) is an explicit operator decision.

Stdlib + lazy `requests` only. No GDAL, no fiona, no shapely.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .sources import FuelLoadSource


CACHE_ROOT_ENV = "WILDFIRE_WATCH_FUEL_LOAD_CACHE"
DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "wildfire-watch" / "fuel_load"


class FetchUnavailable(RuntimeError):
    """Raised when a source can't be auto-fetched (manual_only or network failure)."""


@dataclass(frozen=True)
class FetchResult:
    """One artifact stored on disk after a successful fetch."""

    source_name: str
    cache_path: Path
    sha256: str
    fetched_at_unix: float
    bytes_written: int


def cache_root() -> Path:
    """Return the cache directory, honoring the env-var override."""
    env = os.environ.get(CACHE_ROOT_ENV)
    if env:
        return Path(env).expanduser()
    return DEFAULT_CACHE_ROOT


def _cache_dir_for(source: FuelLoadSource) -> Path:
    return cache_root() / source.name


def _cache_meta_path(source: FuelLoadSource) -> Path:
    return _cache_dir_for(source) / "_meta.json"


def _cache_data_path(source: FuelLoadSource) -> Path:
    # The on-disk filename is opaque — we compute it from the URL hash so
    # that URL changes invalidate the cache automatically.
    suffix = ".geojson" if source.fetch_strategy == "geojson_download" else ".bin"
    h = hashlib.sha1(source.url.encode("utf-8")).hexdigest()[:12]
    return _cache_dir_for(source) / f"{source.name}_{h}{suffix}"


def is_cache_fresh(source: FuelLoadSource, *, now: Optional[float] = None) -> bool:
    """True iff the cache is present AND younger than `freshness_days`."""
    meta_path = _cache_meta_path(source)
    data_path = _cache_data_path(source)
    if not meta_path.exists() or not data_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    fetched_at = float(meta.get("fetched_at_unix", 0.0))
    if fetched_at <= 0.0:
        return False
    age_s = (now if now is not None else time.time()) - fetched_at
    max_age_s = source.freshness_days * 86400.0
    return age_s < max_age_s


def fetch_to_cache(
    source: FuelLoadSource,
    *,
    force: bool = False,
    timeout_s: float = 30.0,
) -> FetchResult:
    """Download `source` to the cache directory.

    Manual-only sources raise `FetchUnavailable` with the source's
    `notes` field as the human-readable instruction. Network failures
    also raise `FetchUnavailable`.

    Honors `freshness_days` — if the cache is fresh AND `force=False`,
    no network call is made and the cached artifact is returned.
    """
    if source.fetch_strategy == "manual_only":
        raise FetchUnavailable(
            f"{source.name}: manual-only source. Operator instructions:\n"
            f"  {source.notes}"
        )

    data_path = _cache_data_path(source)
    if not force and is_cache_fresh(source):
        meta = json.loads(_cache_meta_path(source).read_text(encoding="utf-8"))
        return FetchResult(
            source_name=source.name,
            cache_path=data_path,
            sha256=str(meta.get("sha256", "")),
            fetched_at_unix=float(meta.get("fetched_at_unix", 0.0)),
            bytes_written=int(meta.get("bytes_written", data_path.stat().st_size)),
        )

    body = _http_get(source.url, timeout_s=timeout_s)

    _cache_dir_for(source).mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(body)
    digest = hashlib.sha256(body).hexdigest()
    fetched_at = time.time()
    meta = {
        "source_name": source.name,
        "url": source.url,
        "sha256": digest,
        "fetched_at_unix": fetched_at,
        "bytes_written": len(body),
        "license": source.license,
        "citation": source.citation,
    }
    _cache_meta_path(source).write_text(
        json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8"
    )
    return FetchResult(
        source_name=source.name,
        cache_path=data_path,
        sha256=digest,
        fetched_at_unix=fetched_at,
        bytes_written=len(body),
    )


def _http_get(url: str, *, timeout_s: float = 30.0) -> bytes:
    """HTTPS GET. Prefers `requests` (better cert handling) but falls back
    to stdlib `urllib` so the unit-test suite + `--help` work in a clean
    venv. Raises `FetchUnavailable` on any network error.
    """
    if not url.lower().startswith("https://"):
        raise FetchUnavailable(
            f"refusing to fetch non-HTTPS URL: {url!r}"
        )
    # Lazy-import requests to keep the unit-test suite light.
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        return _http_get_stdlib(url, timeout_s=timeout_s)

    try:
        resp = requests.get(url, timeout=timeout_s, allow_redirects=True)
    except Exception as e:  # network / DNS / TLS errors
        raise FetchUnavailable(f"network error fetching {url}: {e}") from e
    if resp.status_code != 200:
        raise FetchUnavailable(
            f"HTTP {resp.status_code} fetching {url}"
        )
    return resp.content


def _http_get_stdlib(url: str, *, timeout_s: float = 30.0) -> bytes:
    """Stdlib fallback — used when `requests` isn't installed."""
    from urllib.error import URLError, HTTPError  # noqa: PLC0415
    from urllib.request import Request, urlopen  # noqa: PLC0415

    req = Request(url, headers={"User-Agent": "wildfire-watch/0.1 fuel_load"})
    try:
        with urlopen(req, timeout=timeout_s) as resp:  # nosec B310 — HTTPS-only enforced above
            if resp.status != 200:
                raise FetchUnavailable(f"HTTP {resp.status} fetching {url}")
            return resp.read()
    except (URLError, HTTPError, OSError) as e:
        raise FetchUnavailable(f"network error fetching {url}: {e}") from e


__all__ = [
    "FetchUnavailable",
    "FetchResult",
    "DEFAULT_CACHE_ROOT",
    "CACHE_ROOT_ENV",
    "cache_root",
    "fetch_to_cache",
    "is_cache_fresh",
]
