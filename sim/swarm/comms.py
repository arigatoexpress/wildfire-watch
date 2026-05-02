"""Mesh comms model: lossy peer-to-peer with latency + partitions.

Each drone publishes its emitted single-drone signal to the shared mesh.
The MeshCommsModel decides:

  - which peers actually receive the message (loss_rate),
  - when each peer receives it (latency draw, uniform over a range),
  - whether the receiver is in the same network partition as the sender
    (a partition_at_t_seconds may split the swarm into 2 groups).

This is a forensics-friendly model: every message is logged with
delivery decisions so the consensus trace can be reconstructed even if
consensus never fires (handy for debugging "why didn't this confirm?").

The model is deterministic given the same `seed`; tests rely on that.

What this is NOT:
  - It is NOT a queue / event simulator. It returns the deliveries that
    apply to a given (now, peer) lookup. The runner is the loop driver.
  - It does NOT model bandwidth / queuing congestion. Every message is
    a single envelope that arrives intact (or doesn't).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sim.swarm.comms")

DEFAULT_LOSS_RATE = 0.05
DEFAULT_LATENCY_MIN_MS = 30
DEFAULT_LATENCY_MAX_MS = 120


@dataclass
class CommsConfig:
    loss_rate: float = DEFAULT_LOSS_RATE
    latency_min_ms: int = DEFAULT_LATENCY_MIN_MS
    latency_max_ms: int = DEFAULT_LATENCY_MAX_MS
    partition_at_t_seconds: float | None = None
    partition_recovery_at_t_seconds: float | None = None
    # Optional: explicit partition assignment when partition is active.
    # Two-set assignment by drone_id; if None, model splits drones in
    # half (sorted by id).
    partition_a: tuple[str, ...] | None = None
    partition_b: tuple[str, ...] | None = None
    seed: int = 0


@dataclass
class _PendingDelivery:
    sender_id: str
    receiver_id: str
    deliver_at_s: float
    sent_at_s: float
    payload: dict[str, Any]


@dataclass
class CommsLogEntry:
    """One (sender, receiver, decision) record, for the comms.jsonl log."""

    sent_at_s: float
    delivered_at_s: float | None  # None if dropped or partitioned
    sender_id: str
    receiver_id: str
    outcome: str  # "delivered" | "dropped_loss" | "dropped_partition"
    signal_id: str | None
    latency_ms: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class MeshCommsModel:
    """Lossy peer-to-peer relay.

    Usage:
      model = MeshCommsModel(["d0", "d1", "d2"], CommsConfig(seed=0))
      model.publish(sender_id="d0", payload=signal, sent_at_s=t)
      for ev in model.deliveries_due(now_s=t):
          # ev = {receiver_id, sender_id, payload, ...}
    """

    def __init__(self, drone_ids: list[str], config: CommsConfig | None = None):
        self.drone_ids = list(drone_ids)
        self.config = config or CommsConfig()
        self._rng = random.Random(self.config.seed)
        self._pending: list[_PendingDelivery] = []
        self._log: list[CommsLogEntry] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def publish(
        self,
        *,
        sender_id: str,
        payload: dict[str, Any],
        sent_at_s: float,
    ) -> list[CommsLogEntry]:
        """Sender publishes `payload`; for each peer (excluding self),
        decide delivery. Returns the immediate decisions made (which may
        include drops). Successful deliveries are queued for retrieval
        via `deliveries_due` once their latency elapses.
        """
        entries: list[CommsLogEntry] = []
        signal_id = payload.get("signal_id")
        for receiver_id in self.drone_ids:
            if receiver_id == sender_id:
                continue
            entry = self._decide_delivery(
                sender_id=sender_id,
                receiver_id=receiver_id,
                signal_id=signal_id,
                sent_at_s=sent_at_s,
                payload=payload,
            )
            entries.append(entry)
            self._log.append(entry)
        return entries

    def deliveries_due(self, *, now_s: float) -> list[_PendingDelivery]:
        """Return + remove all queued deliveries whose deliver_at_s has
        elapsed. Caller passes them to the receiver drones / voter.
        """
        ready = [d for d in self._pending if d.deliver_at_s <= now_s]
        if ready:
            self._pending = [d for d in self._pending if d.deliver_at_s > now_s]
            # Stamp the log: find the matching log entry & set its
            # delivered_at_s to the actual now_s (covers the case where
            # the runner ticks faster than latency_min).
            for d in ready:
                self._mark_delivered(
                    sender_id=d.sender_id,
                    receiver_id=d.receiver_id,
                    signal_id=d.payload.get("signal_id"),
                    delivered_at_s=now_s,
                )
        return ready

    def log(self) -> list[CommsLogEntry]:
        """All recorded comms decisions (for forensics)."""
        return list(self._log)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _decide_delivery(
        self,
        *,
        sender_id: str,
        receiver_id: str,
        signal_id: str | None,
        sent_at_s: float,
        payload: dict[str, Any],
    ) -> CommsLogEntry:
        # 1) Partition check.
        if self._partitioned(sender_id, receiver_id, sent_at_s):
            return CommsLogEntry(
                sent_at_s=sent_at_s,
                delivered_at_s=None,
                sender_id=sender_id,
                receiver_id=receiver_id,
                outcome="dropped_partition",
                signal_id=signal_id,
            )
        # 2) Random loss draw.
        if self._rng.random() < self.config.loss_rate:
            return CommsLogEntry(
                sent_at_s=sent_at_s,
                delivered_at_s=None,
                sender_id=sender_id,
                receiver_id=receiver_id,
                outcome="dropped_loss",
                signal_id=signal_id,
            )
        # 3) Latency draw, queue.
        lat_ms = self._rng.uniform(
            self.config.latency_min_ms, self.config.latency_max_ms
        )
        deliver_at = sent_at_s + (lat_ms / 1000.0)
        self._pending.append(
            _PendingDelivery(
                sender_id=sender_id,
                receiver_id=receiver_id,
                deliver_at_s=deliver_at,
                sent_at_s=sent_at_s,
                payload=payload,
            )
        )
        return CommsLogEntry(
            sent_at_s=sent_at_s,
            delivered_at_s=deliver_at,  # provisional; corrected on retrieval
            sender_id=sender_id,
            receiver_id=receiver_id,
            outcome="delivered",
            signal_id=signal_id,
            latency_ms=round(lat_ms, 2),
        )

    def _partitioned(
        self, sender_id: str, receiver_id: str, t: float
    ) -> bool:
        """Return True iff a partition is active at `t` AND sender/receiver
        sit in different groups."""
        cfg = self.config
        if cfg.partition_at_t_seconds is None:
            return False
        if t < cfg.partition_at_t_seconds:
            return False
        if (
            cfg.partition_recovery_at_t_seconds is not None
            and t >= cfg.partition_recovery_at_t_seconds
        ):
            return False
        a, b = self._partition_groups()
        if sender_id in a and receiver_id in b:
            return True
        if sender_id in b and receiver_id in a:
            return True
        return False

    def _partition_groups(self) -> tuple[set[str], set[str]]:
        """Materialize partition groups, defaulting to a sorted half-split."""
        cfg = self.config
        if cfg.partition_a is not None and cfg.partition_b is not None:
            return set(cfg.partition_a), set(cfg.partition_b)
        sorted_ids = sorted(self.drone_ids)
        half = max(1, len(sorted_ids) // 2)
        return set(sorted_ids[:half]), set(sorted_ids[half:])

    def _mark_delivered(
        self,
        *,
        sender_id: str,
        receiver_id: str,
        signal_id: str | None,
        delivered_at_s: float,
    ) -> None:
        # Walk newest-first; stamp the most recent matching provisional entry.
        for entry in reversed(self._log):
            if (
                entry.sender_id == sender_id
                and entry.receiver_id == receiver_id
                and entry.signal_id == signal_id
                and entry.outcome == "delivered"
            ):
                entry.delivered_at_s = delivered_at_s
                return
