"""Source registry shape + license fields."""

from __future__ import annotations

import re

import pytest

from sapphire_integration.fuel_load import sources


def test_at_least_five_sources_registered() -> None:
    assert len(sources.REGISTERED_SOURCES) >= 5


def test_every_source_has_required_fields() -> None:
    for s in sources.REGISTERED_SOURCES:
        assert s.name, "source name must be non-empty"
        assert s.url, f"{s.name}: url must be non-empty"
        assert s.license, f"{s.name}: license must be non-empty"
        assert s.citation, f"{s.name}: citation must be non-empty"
        assert s.fetch_strategy in (
            "geojson_download",
            "raster_pull",
            "manual_only",
        ), f"{s.name}: unknown fetch_strategy {s.fetch_strategy!r}"
        assert s.freshness_days >= 0


def test_every_url_is_https() -> None:
    pat = re.compile(r"^https://", re.IGNORECASE)
    for s in sources.REGISTERED_SOURCES:
        assert pat.match(s.url), f"{s.name}: url must start with https://, got {s.url!r}"


def test_licenses_are_recognized_tokens() -> None:
    for s in sources.REGISTERED_SOURCES:
        assert s.license in sources.LICENSE_TOKENS, (
            f"{s.name}: license {s.license!r} not in LICENSE_TOKENS"
        )


def test_source_names_unique() -> None:
    names = [s.name for s in sources.REGISTERED_SOURCES]
    assert len(names) == len(set(names))


def test_get_source_lookup() -> None:
    s = sources.get_source("usfs_ids")
    assert s.name == "usfs_ids"
    with pytest.raises(KeyError):
        sources.get_source("nonexistent")


def test_required_sources_present() -> None:
    """The 5 sources called out in the task spec are all registered."""
    names = {s.name for s in sources.REGISTERED_SOURCES}
    required = {
        "usfs_ids",
        "csfs_forest_health_report",
        "usfs_fia",
        "nifc_fire_perimeters",
        "mtbs_burn_severity",
    }
    missing = required - names
    assert not missing, f"missing required sources: {missing}"
