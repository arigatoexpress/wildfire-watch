"""Recorder tests — SRT round-trips back through mavic_post_flight.parse_srt."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "ml" / "fire_detection"))

from mavic_post_flight import parse_srt  # noqa: E402

from sim.mission import load_mission  # noqa: E402
from sim.recorder import Recorder, _build_srt_block, _format_srt_timestamp  # noqa: E402
from sim.runner import RunnerConfig, SimulationRunner, TickRecord  # noqa: E402
from sim.scenario import ScenarioEngine, load_scenario  # noqa: E402

SIM_ROOT = Path(__file__).resolve().parent.parent
MISSION_PATH = SIM_ROOT / "missions" / "monterey_pinnacles_east_1km2.yaml"


def test_srt_timestamp_format():
    assert _format_srt_timestamp(0.0) == "00:00:00,000"
    assert _format_srt_timestamp(1.0) == "00:00:01,000"
    assert _format_srt_timestamp(61.5) == "00:01:01,500"
    assert _format_srt_timestamp(3661.234) == "01:01:01,234"


def test_one_block_round_trips():
    rec = TickRecord(
        ts_iso="2026-05-01T12:34:56Z",
        sim_time_s=0.0,
        lat=36.4906,
        lon=-121.1825,
        alt_agl_m=80.0,
        alt_msl_m=400.0,
        heading_deg=90.0,
        speed_mps=8.0,
        battery_pct=99.0,
        gate_state="closed",
        rgb_score=0.05,
        thermal_delta_c=0.5,
    )
    block = _build_srt_block(1, 0.0, 1.0, rec)
    fixes = parse_srt(block)
    assert len(fixes) == 1
    fix = fixes[0]
    assert abs(fix.lat - 36.4906) < 1e-6
    assert abs(fix.lon - (-121.1825)) < 1e-6
    assert abs(fix.rel_alt_m - 80.0) < 1e-3
    assert fix.abs_alt_m is not None
    assert abs(fix.abs_alt_m - 400.0) < 1e-3


def test_full_run_writes_parseable_srt(tmp_path: Path):
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "single_smoke_plume.yaml")
    with Recorder(tmp_path, scenario.name, run_id="SIM-TEST") as rec:
        runner = SimulationRunner(
            mission=mission,
            scenario_engine=ScenarioEngine(scenario),
            config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
            on_signal=rec.on_signal,
            on_tick=rec.on_tick,
        )
        result = runner.run(max_sim_seconds=600.0)
        rec.close({"ticks": result.ticks})
    # All four files exist.
    assert rec.flight_log_path.exists()
    assert rec.srt_path.exists()
    assert rec.signals_path.exists()
    assert rec.manifest_path.exists()
    # SRT round-trips through mavic_post_flight.parse_srt.
    text = rec.srt_path.read_text(encoding="utf-8")
    fixes = parse_srt(text)
    assert len(fixes) > 5
    # And first fix is at home.
    assert abs(fixes[0].lat - mission.home.lat) < 0.001
    assert abs(fixes[0].lon - mission.home.lon) < 0.001
    # Signals JSONL has at least one row, each is a valid JSON dict.
    sig_lines = rec.signals_path.read_text(encoding="utf-8").splitlines()
    assert len(sig_lines) >= 1
    for line in sig_lines:
        sig = json.loads(line)
        assert sig["schema_version"] == "1.0.0"
    # flight_log.jsonl has rows for every tick.
    fl_lines = rec.flight_log_path.read_text(encoding="utf-8").splitlines()
    assert len(fl_lines) == result.ticks


def test_short_run_produces_at_least_one_srt_cue(tmp_path: Path):
    """Even a 10-second sim should write at least 10 SRT cues."""
    mission = load_mission(MISSION_PATH)
    scenario = load_scenario(SIM_ROOT / "scenarios" / "clean_patrol.yaml")
    with Recorder(tmp_path, scenario.name, run_id="SIM-SHORT") as rec:
        runner = SimulationRunner(
            mission=mission,
            scenario_engine=ScenarioEngine(scenario),
            config=RunnerConfig(drone_id="wfw-test01", tick_hz=10.0),
            on_tick=rec.on_tick,
        )
        runner.run(max_sim_seconds=10.0)
        rec.close({})
    text = rec.srt_path.read_text(encoding="utf-8")
    fixes = parse_srt(text)
    # 10s @ 1 cue/s -> ~10 cues.
    assert len(fixes) >= 8
