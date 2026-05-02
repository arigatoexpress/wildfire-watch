"""Smoke tests for the valuation CLI."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from valuation import cli, recorder


@pytest.fixture(autouse=True)
def isolate_history(monkeypatch, tmp_path):
    """Redirect HISTORY_PATH so tests don't pollute the real file."""
    fake_history = tmp_path / "valuation_history.jsonl"
    monkeypatch.setattr(recorder, "HISTORY_PATH", fake_history)
    yield


def test_snapshot_json_returns_valid_json():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["snapshot", "--json"])
    assert rc == 0
    out = buf.getvalue()
    obj = json.loads(out)
    assert "consensus_band" in obj
    assert "methods" in obj


def test_snapshot_print_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["snapshot", "--print"])
    assert rc == 0
    text = buf.getvalue()
    assert "intrinsic valuation" in text
    assert "BAND:" in text


def test_kpi_command_runs():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["kpi"])
    assert rc == 0
    text = buf.getvalue()
    # Expect at least one of each category.
    assert "ENGINEERING" in text
    assert "PRODUCT" in text
    assert "STRATEGIC" in text
    assert "COMPLIANCE" in text


def test_history_empty_message():
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main(["history", "--last", "5"])
    assert rc == 0
    assert "No history" in buf.getvalue()


def test_compare_missing_returns_nonzero(capsys):
    rc = cli.main(["compare", "deadbeef", "cafef00d"])
    assert rc == 1
