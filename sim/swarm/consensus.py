"""k-of-N spatial+temporal+type consensus voter.

A ConsensusVoter ingests `wildfire_signal` v1 dicts as they're emitted
by individual drones, groups them by spatial+temporal proximity, and
emits a CONFIRMED `consensus_signal_v1` event when at least k DISTINCT
drones have reported a target within R meters and T seconds of each
other, with compatible signal types.

Compatible signal types (a fire is also a smoke; both are also a thermal
anomaly):
    fire ⊃ smoke ⊃ thermal_anomaly

The voter takes the strictest matching type when emitting consensus.

When consensus fires, the v1 signal payload is augmented:
  - consensus.peer_drone_ids: list of drone_ids that contributed
  - consensus.peer_confirmations: count of confirmations
  - consensus.confirmed_at: ISO timestamp of the k-th vote
  - recommended_action: ESCALATED one tier
  - risk_score: bumped by min(20, 100 - current)
  - signal_subtype: set to 'sim/consensus_confirmed'
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from ..kinematics import haversine_m

logger = logging.getLogger("sim.swarm.consensus")

DEFAULT_R_SPATIAL_M = 75.0
DEFAULT_T_WINDOW_S = 60.0
DEFAULT_K = 2

# Type compatibility ladder. Lower index = stricter / higher-severity.
# Two signals are type-compatible if they share at least one ladder rung.
_TYPE_LADDER = ("fire", "smoke", "thermal_anomaly")
_TYPE_RANK = {t: i for i, t in enumerate(_TYPE_LADDER)}


def _types_compatible(a: str, b: str) -> bool:
    """Both types must appear on the ladder."""
    return a in _TYPE_RANK and b in _TYPE_RANK


def _strictest_type(types: list[str]) -> str:
    """Return the strictest (lowest-rank) type seen. Falls back to
    'thermal_anomaly' if the list is empty or unknown."""
    ranked = [_TYPE_RANK[t] for t in types if t in _TYPE_RANK]
    if not ranked:
        return "thermal_anomaly"
    return _TYPE_LADDER[min(ranked)]


# Recommended-action escalation ladder. Each step is "more aggressive".
# Order chosen so the canonical single-drone outputs (notify_operator,
# loiter_and_capture) escalate cleanly to dispatch-class actions
# (notify_fire_dept, auto_dispatch_response). The example in the spec
# is notify_operator -> notify_fire_dept, which is one tier here.
_ACTION_LADDER = (
    "log_only",
    "notify_operator",
    "notify_fire_dept",
    "loiter_and_capture",
    "auto_dispatch_response",
)
_ACTION_RANK = {a: i for i, a in enumerate(_ACTION_LADDER)}


def _escalate_action(current: str) -> str:
    """Return the next action level up, capped at the ladder top."""
    rank = _ACTION_RANK.get(current, 0)
    next_rank = min(rank + 1, len(_ACTION_LADDER) - 1)
    return _ACTION_LADDER[next_rank]


@dataclass
class _SignalRecord:
    """One drone's emitted signal, queued for consensus consideration."""

    drone_id: str
    sim_time_s: float
    target_lat: float
    target_lon: float
    signal_type: str
    raw_signal: dict[str, Any]


@dataclass
class _Cluster:
    """Working group of compatible signals that may form a consensus."""

    target_lat: float
    target_lon: float
    earliest_t: float
    latest_t: float
    signal_type: str  # strictest seen so far
    drone_ids: set[str] = field(default_factory=set)
    members: list[_SignalRecord] = field(default_factory=list)
    consensus_emitted: bool = False


@dataclass
class ConsensusConfig:
    k: int = DEFAULT_K
    r_spatial_m: float = DEFAULT_R_SPATIAL_M
    t_window_s: float = DEFAULT_T_WINDOW_S


def _signal_target_coords(sig: dict[str, Any]) -> tuple[float, float]:
    """Pull the best (lat, lon) for the *target* of a signal.

    Prefer target_coords (the inferred fire location), fall back to the
    drone's current coords (some emits don't include a target_coords).
    """
    tgt = sig.get("target_coords")
    if tgt and tgt.get("lat") is not None and tgt.get("lon") is not None:
        return float(tgt["lat"]), float(tgt["lon"])
    coords = sig.get("coords") or {}
    return float(coords.get("lat", 0.0)), float(coords.get("lon", 0.0))


class ConsensusVoter:
    """k-of-N voter operating on a stream of single-drone signals."""

    def __init__(self, config: ConsensusConfig | None = None):
        self.config = config or ConsensusConfig()
        self._clusters: list[_Cluster] = []
        self._consensus_emits: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(
        self,
        signal: dict[str, Any],
        *,
        emitter_drone_id: str,
        sim_time_s: float,
    ) -> dict[str, Any] | None:
        """Submit a single-drone signal. Returns a consensus signal if
        this submission tipped a cluster over the k-threshold, else None.
        """
        target_lat, target_lon = _signal_target_coords(signal)
        signal_type = str(signal.get("signal_type", "thermal_anomaly"))
        rec = _SignalRecord(
            drone_id=emitter_drone_id,
            sim_time_s=sim_time_s,
            target_lat=target_lat,
            target_lon=target_lon,
            signal_type=signal_type,
            raw_signal=signal,
        )

        # Drop stale clusters (outside the temporal window from now).
        self._evict_stale(sim_time_s)

        cluster = self._find_or_create_cluster(rec)
        cluster.drone_ids.add(rec.drone_id)
        cluster.members.append(rec)
        cluster.latest_t = max(cluster.latest_t, rec.sim_time_s)
        cluster.earliest_t = min(cluster.earliest_t, rec.sim_time_s)
        # Update strictest type if this signal is more severe.
        if _TYPE_RANK.get(rec.signal_type, 99) < _TYPE_RANK.get(cluster.signal_type, 99):
            cluster.signal_type = rec.signal_type

        if (
            not cluster.consensus_emitted
            and len(cluster.drone_ids) >= self.config.k
        ):
            cluster.consensus_emitted = True
            consensus_sig = self._build_consensus_signal(cluster, rec)
            self._consensus_emits += 1
            return consensus_sig
        return None

    @property
    def consensus_emitted_count(self) -> int:
        return self._consensus_emits

    @property
    def cluster_count(self) -> int:
        return len(self._clusters)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evict_stale(self, now_s: float) -> None:
        """Drop clusters whose latest member is older than t_window_s."""
        cutoff = now_s - self.config.t_window_s
        self._clusters = [c for c in self._clusters if c.latest_t >= cutoff]

    def _find_or_create_cluster(self, rec: _SignalRecord) -> _Cluster:
        for c in self._clusters:
            if not _types_compatible(c.signal_type, rec.signal_type):
                continue
            if abs(rec.sim_time_s - c.latest_t) > self.config.t_window_s:
                continue
            d = haversine_m(c.target_lat, c.target_lon, rec.target_lat, rec.target_lon)
            if d <= self.config.r_spatial_m:
                return c
        new = _Cluster(
            target_lat=rec.target_lat,
            target_lon=rec.target_lon,
            earliest_t=rec.sim_time_s,
            latest_t=rec.sim_time_s,
            signal_type=rec.signal_type,
        )
        self._clusters.append(new)
        return new

    def _build_consensus_signal(
        self, cluster: _Cluster, triggering: _SignalRecord
    ) -> dict[str, Any]:
        """Produce a consensus_signal_v1 dict by augmenting the
        triggering single-drone signal with consensus fields.

        Choose the highest-confidence member as the canonical body so
        operators see the strongest evidence first; layer on consensus
        metadata.
        """
        # Pick the most-confident member to use as the canonical body.
        best = max(
            cluster.members,
            key=lambda r: float(r.raw_signal.get("confidence", 0.0)),
        )
        base = dict(best.raw_signal)  # shallow copy; we don't mutate inner dicts
        base = _deep_copy_signal(base)

        # Fresh signal_id for the consensus emission.
        base["signal_id"] = str(uuid.uuid4())
        base["signal_subtype"] = "sim/consensus_confirmed"

        # Tighten the canonical type to the strictest one observed.
        base["signal_type"] = cluster.signal_type

        # Bump risk_score and escalate recommended_action.
        current_risk = float(base.get("risk_score", 0.0))
        base["risk_score"] = round(current_risk + min(20.0, 100.0 - current_risk), 2)
        base["recommended_action"] = _escalate_action(
            str(base.get("recommended_action", "notify_operator"))
        )

        # Stamp the consensus block. The peer set INCLUDES the emitter of
        # the canonical body so operators see "who confirmed this".
        peer_ids = sorted(cluster.drone_ids)
        base["consensus"] = {
            "peer_drone_ids": peer_ids,
            "peer_confirmations": len(peer_ids),
            "confirmed_at_sim_time_s": round(triggering.sim_time_s, 3),
            "spatial_radius_m": self.config.r_spatial_m,
            "temporal_window_s": self.config.t_window_s,
            "k_required": self.config.k,
        }
        return base


def _deep_copy_signal(sig: dict[str, Any]) -> dict[str, Any]:
    """Lightweight deep copy good enough for json-serializable signal
    dicts. Avoids depending on copy.deepcopy when we only need 1-level
    of nested dicts/lists.
    """
    out: dict[str, Any] = {}
    for k, v in sig.items():
        if isinstance(v, dict):
            out[k] = {kk: (list(vv) if isinstance(vv, list) else vv) for kk, vv in v.items()}
        elif isinstance(v, list):
            out[k] = list(v)
        else:
            out[k] = v
    return out
