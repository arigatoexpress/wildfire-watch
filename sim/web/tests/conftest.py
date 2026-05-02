"""Test fixtures shared across sim/web/tests/."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the repo root is on sys.path so ``import sim.web.server`` works
# whether pytest is invoked from the repo root or from sim/web.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


@pytest.fixture
def fixture_dir() -> Path:
    """Path to the bundled sample_flight fixture."""
    return Path(__file__).resolve().parents[1] / "fixtures" / "sample_flight"


@pytest.fixture
def app(tmp_path, fixture_dir):
    """Flask app pointed at an empty flights-root + the bundled fixture."""
    from sim.web.server import create_app

    flask_app = create_app(flights_root=tmp_path, fixture_dir=fixture_dir)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
