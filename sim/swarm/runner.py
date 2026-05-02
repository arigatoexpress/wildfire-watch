"""SwarmRunner — composes Fleet + ConsensusVoter + MeshCommsModel.

Per-tick sequence at 10 Hz:

  1. Fleet.step(dt) advances all drones; collects raw signals.
  2. For every raw signal, the emitter publishes through MeshCommsModel
     to all peers.
  3. MeshCommsModel returns the deliveries that have arrived this tick;
     each delivery is fed to ConsensusVoter.
  4. ConsensusVoter may return a CONFIRMED consensus_signal_v1; if so,
     it goes to the recorder.
  5. Raw signals also go to the recorder.signals.jsonl (tagged with
     emitter id) for forensics.
  6. comms decisions go to recorder.comms.jsonl.

The voter operates on the *delivered* peer-side view, NOT on the raw
emit stream. That's the whole point: if comms drops a packet, the
receiver never votes. If comms is partitioned, the two halves of the
fleet can't reach k together. This makes consensus realistic, not just
a centralized rubber stamp.

ALSO: each drone always self-confirms its own emit (it doesn't need to
hear it back from the mesh). So a drone's emits always count toward its
own consensus tally.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from ..mission import Mission, Waypoint
from ..scenario import Scenario, ScenarioEngine
from .comms import CommsConfig, CommsLogEntry, MeshCommsModel
from .consensus import ConsensusConfig, ConsensusVoter
from .coverage_planner import (
    SubZone,
    lattice_waypoints_for_subzone,
    plan_coverage,
)
from .fleet import DroneTickRecord, Fleet, FleetTickResult

logger = logging.getLogger("sim.swarm.runner")

DEFAULT_TICK_HZ = 10.0


@dataclass
class SwarmRunnerConfig:
    n_drones: int = 3
    k_consensus: int = 2
    r_spatial_m: float = 75.0
    t_window_s: float = 60.0
    tick_hz: float = DEFAULT_TICK_HZ
    seed: int = 0
    drone_id_prefix: str = "wfw-sim"
    start_wallclock: datetime | None = None
    speed_multiplier: float = 0.0
    # If set, override comms config (otherwise CommsConfig defaults +
    # seed are used).
    comms_config: CommsConfig | None = None


@dataclass
class SwarmRunResult:
    ticks: int
    sim_seconds: float
    raw_signals: int
    consensus_signals: int
    drones_dead_battery: int
    per_drone_signals: dict[str, int] = field(default_factory=dict)
    sub_zones: list[SubZone] = field(default_factory=list)


class SwarmRunner:
    """Drives a fleet through a mission with shared scenario + consensus."""

    def __init__(
        self,
        *,
        mission: Mission,
        scenario: Scenario,
        config: SwarmRunnerConfig,
        on_drone_tick: Callable[[DroneTickRecord], None] | None = None,
        on_raw_signal: Callable[[str, dict[str, Any]], None] | None = None,
        on_consensus: Callable[[dict[str, Any]], None] | None = None,
        on_comms: Callable[[list[CommsLogEntry]], None] | None = None,
    ):
        self.mission = mission
        self.scenario = scenario
        self.config = config
        self.on_drone_tick = on_drone_tick or (lambda _r: None)
        self.on_raw_signal = on_raw_signal or (lambda _did, _s: None)
        self.on_consensus = on_consensus or (lambda _s: None)
        self.on_comms = on_comms or (lambda _e: None)

        # 1) Plan coverage. We use the geofence inclusion from the
        # mission as the inclusion boundary; if it's empty, we synthesize
        # one from the waypoint bbox. Hard exclusions are forwarded so
        # cells that overlap a wilderness no-fly are shrunk or dropped.
        polygon = list(mission.geofence.inclusion) or list(mission.geofence_polygon)
        if not polygon:
            lats = [w.lat for w in mission.waypoints]
            lons = [w.lon for w in mission.waypoints]
            polygon = [
                (min(lats), min(lons)),
                (min(lats), max(lons)),
                (max(lats), max(lons)),
                (max(lats), min(lons)),
            ]
        hard_exclusions: list[list[tuple[float, float]]] = [
            list(e.polygon) for e in mission.hard_exclusions()
        ]
        self.sub_zones = plan_coverage(
            polygon, config.n_drones, exclusions=hard_exclusions
        )

        # 2) Build per-drone sub-waypoints. Each drone gets a 4-corner
        # box inside its cell so it traverses + revisits the area.
        drone_ids: list[str] = []
        sub_waypoint_lists: list[list[Waypoint]] = []
        scenario_engines: list[ScenarioEngine] = []
        for i, zone in enumerate(self.sub_zones):
            drone_id = f"{config.drone_id_prefix}{i+1:02d}"
            drone_ids.append(drone_id)
            corners = lattice_waypoints_for_subzone(zone, n_waypoints=4)
            wps = [
                Waypoint(
                    lat=lat,
                    lon=lon,
                    alt_agl_m=mission.flight_params.altitude_agl_m,
                    action="capture",
                )
                for (lat, lon) in corners
            ]
            sub_waypoint_lists.append(wps)
            # Each drone gets its own ScenarioEngine instance so the
            # detection state is independent (events fire per-drone if
            # the scenario applies to that drone — see "drones" filter
            # below).
            scenario_engines.append(
                ScenarioEngine(
                    _filter_scenario_for_drone(scenario, drone_id, drone_ids[0])
                )
            )

        self.drone_ids = drone_ids

        # 3) Build the Fleet.
        self.fleet = Fleet(
            mission=mission,
            drone_ids=drone_ids,
            sub_waypoint_lists=sub_waypoint_lists,
            scenario_engines=scenario_engines,
            start_wallclock=(
                config.start_wallclock
                or datetime.now(UTC).replace(microsecond=0)
            ),
        )

        # 4) Comms model.
        comms_cfg = config.comms_config or CommsConfig(seed=config.seed)
        self.comms = MeshCommsModel(drone_ids=drone_ids, config=comms_cfg)

        # 5) Per-drone consensus voters. Each drone runs its OWN
        # voter against ITS local view (own emits + delivered peer
        # signals). This makes consensus realistic: full comms loss
        # leaves each drone's voter with only its own emit, which can
        # never reach k=2 from a single source. The first drone whose
        # local voter fires emits the canonical consensus signal; later
        # confirmations from other drones are deduplicated.
        self.voters: dict[str, ConsensusVoter] = {
            did: ConsensusVoter(
                ConsensusConfig(
                    k=config.k_consensus,
                    r_spatial_m=config.r_spatial_m,
                    t_window_s=config.t_window_s,
                )
            )
            for did in drone_ids
        }
        # Dedup map: (cluster target rounded) -> already-emitted bool.
        # Two drones whose local voters fire on the SAME target should
        # only produce one consensus_signal_v1; the runner picks the
        # first emit.
        self._emitted_targets: set[tuple[float, float]] = set()

        self._raw_signal_count = 0
        self._consensus_signal_count = 0
        self._per_drone_signals: dict[str, int] = {did: 0 for did in drone_ids}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, *, max_sim_seconds: float = 600.0) -> SwarmRunResult:
        dt = 1.0 / self.config.tick_hz
        max_ticks = int(max_sim_seconds * self.config.tick_hz) + 1
        ticks = 0
        while ticks < max_ticks:
            self._tick(dt)
            ticks += 1
            if self.fleet.all_finished():
                break
            if self.fleet.any_battery_dead():
                logger.warning("at least one drone battery exhausted; stopping")
                break
        return SwarmRunResult(
            ticks=ticks,
            sim_seconds=self.fleet.sim_time_s,
            raw_signals=self._raw_signal_count,
            consensus_signals=self._consensus_signal_count,
            drones_dead_battery=sum(
                1 for a in self.fleet.agents if a.state.battery_pct <= 0.0
            ),
            per_drone_signals=dict(self._per_drone_signals),
            sub_zones=list(self.sub_zones),
        )

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def _tick(self, dt: float) -> None:
        # 1) Fleet step.
        result: FleetTickResult = self.fleet.step(dt)
        for rec in result.drone_records:
            self.on_drone_tick(rec)

        now_s = self.fleet.sim_time_s

        # 2) Each new emit:
        #    a) self-confirms in the EMITTER's own voter (always),
        #    b) publishes to the mesh for peers (with loss + latency),
        #    c) is logged to the recorder as a raw single-drone emit.
        for emitter_id, sig in result.new_signals:
            self._raw_signal_count += 1
            self._per_drone_signals[emitter_id] = (
                self._per_drone_signals.get(emitter_id, 0) + 1
            )
            self.on_raw_signal(emitter_id, sig)

            # Emitter's local voter sees own emit immediately.
            consensus = self.voters[emitter_id].submit(
                sig, emitter_drone_id=emitter_id, sim_time_s=now_s
            )
            self._maybe_publish_consensus(consensus)

            # Publish for peers (subject to comms loss / latency / partition).
            comms_entries = self.comms.publish(
                sender_id=emitter_id, payload=sig, sent_at_s=now_s
            )
            self.on_comms(comms_entries)

        # 3) Drain any due deliveries from previous ticks; each delivery
        # feeds the RECEIVER's local voter.
        due = self.comms.deliveries_due(now_s=now_s)
        for delivery in due:
            voter = self.voters[delivery.receiver_id]
            consensus = voter.submit(
                delivery.payload,
                emitter_drone_id=delivery.sender_id,
                sim_time_s=now_s,
            )
            self._maybe_publish_consensus(consensus)

    def _maybe_publish_consensus(self, consensus: dict | None) -> None:
        """Dedup + publish a consensus signal. Two drones' local voters
        firing on the same target should only emit ONCE."""
        if consensus is None:
            return
        # Dedup by rounded target coords (5-decimal precision = ~1 m).
        tgt = consensus.get("target_coords") or {}
        key = (round(tgt.get("lat", 0.0), 5), round(tgt.get("lon", 0.0), 5))
        if key in self._emitted_targets:
            return
        self._emitted_targets.add(key)
        self._consensus_signal_count += 1
        self.on_consensus(consensus)


def _filter_scenario_for_drone(
    scenario: Scenario, drone_id: str, primary_drone_id: str
) -> Scenario:
    """Return a scenario whose events apply ONLY to `drone_id`.

    Each event in a swarm scenario YAML may carry an optional `drones`
    list (the drone_ids it applies to). If absent, the event is treated
    as fleet-wide AND only applies to the primary drone (`drone_id_prefix`
    + 01) to avoid the same event firing simultaneously on every drone.

    This keeps the single-drone scenario YAML format backward-compatible
    while letting swarm scenarios target specific drones.
    """
    from copy import deepcopy

    out_events = []
    for ev in scenario.events:
        targets = ev.payload.get("drones") if isinstance(ev.payload, dict) else None
        if targets is None:
            # Fleet-wide event: apply only to the primary drone (avoids
            # 3x amplification of a single physical event).
            if drone_id != primary_drone_id:
                continue
            out_events.append(deepcopy(ev))
        else:
            if drone_id in targets:
                out_events.append(deepcopy(ev))
    return Scenario(
        name=scenario.name, description=scenario.description, events=out_events
    )
