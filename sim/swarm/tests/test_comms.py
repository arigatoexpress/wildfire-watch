"""Tests for sim.swarm.comms."""

from __future__ import annotations

from sim.swarm.comms import CommsConfig, MeshCommsModel


def _payload(signal_id: str = "sig-1") -> dict:
    return {"signal_id": signal_id, "drone_id": "x"}


def test_no_loss_no_partition_every_peer_receives():
    model = MeshCommsModel(
        ["d1", "d2", "d3"], CommsConfig(loss_rate=0.0, seed=0)
    )
    entries = model.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    # 2 peers, both delivered.
    assert len(entries) == 2
    assert all(e.outcome == "delivered" for e in entries)


def test_full_loss_drops_everything():
    model = MeshCommsModel(
        ["d1", "d2", "d3"], CommsConfig(loss_rate=1.0, seed=0)
    )
    entries = model.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    assert len(entries) == 2
    assert all(e.outcome == "dropped_loss" for e in entries)


def test_no_self_delivery():
    """Sender should never receive its own publish."""
    model = MeshCommsModel(["d1", "d2"], CommsConfig(loss_rate=0.0, seed=0))
    entries = model.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    assert all(e.receiver_id != "d1" for e in entries)


def test_latency_within_configured_range():
    cfg = CommsConfig(loss_rate=0.0, latency_min_ms=30, latency_max_ms=120, seed=42)
    model = MeshCommsModel(["d1", "d2", "d3"], cfg)
    model.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    # Nothing should be due at t=0.0.
    due_now = model.deliveries_due(now_s=0.0)
    assert due_now == []
    # By t=0.2 every delivery should be due (max latency = 120 ms).
    due = model.deliveries_due(now_s=0.2)
    assert len(due) == 2


def test_partition_blocks_cross_group_messages():
    cfg = CommsConfig(
        loss_rate=0.0,
        partition_at_t_seconds=0.0,
        partition_recovery_at_t_seconds=None,
        partition_a=("d1",),
        partition_b=("d2", "d3"),
        seed=0,
    )
    model = MeshCommsModel(["d1", "d2", "d3"], cfg)
    entries = model.publish(sender_id="d1", payload=_payload(), sent_at_s=1.0)
    # d1 is in A; d2 and d3 are in B; both should be partitioned.
    assert all(e.outcome == "dropped_partition" for e in entries)


def test_partition_recovery_restores_delivery():
    cfg = CommsConfig(
        loss_rate=0.0,
        partition_at_t_seconds=0.0,
        partition_recovery_at_t_seconds=10.0,
        partition_a=("d1",),
        partition_b=("d2", "d3"),
        seed=0,
    )
    model = MeshCommsModel(["d1", "d2", "d3"], cfg)
    # Before recovery: dropped.
    pre = model.publish(sender_id="d1", payload=_payload("a"), sent_at_s=5.0)
    assert all(e.outcome == "dropped_partition" for e in pre)
    # After recovery: delivered.
    post = model.publish(sender_id="d1", payload=_payload("b"), sent_at_s=15.0)
    assert all(e.outcome == "delivered" for e in post)


def test_with_full_loss_no_consensus_is_possible():
    """Surface check: with loss_rate=1.0, no peer ever sees anything,
    so consensus across the mesh would never accumulate."""
    model = MeshCommsModel(
        ["d1", "d2", "d3"], CommsConfig(loss_rate=1.0, seed=0)
    )
    # Publish 100 signals; nothing should land in pending queue.
    for i in range(100):
        model.publish(
            sender_id="d1", payload=_payload(f"sig{i}"), sent_at_s=float(i)
        )
    due = model.deliveries_due(now_s=10_000.0)
    assert due == []


def test_log_records_outcomes():
    cfg = CommsConfig(loss_rate=0.5, seed=7)
    model = MeshCommsModel(["d1", "d2", "d3"], cfg)
    model.publish(sender_id="d1", payload=_payload("s1"), sent_at_s=0.0)
    log = model.log()
    # 2 peers, so 2 entries.
    assert len(log) == 2
    outcomes = {e.outcome for e in log}
    assert outcomes <= {"delivered", "dropped_loss", "dropped_partition"}


def test_deterministic_with_seed():
    """Two models with the same seed should make the same decisions."""
    a = MeshCommsModel(["d1", "d2", "d3"], CommsConfig(loss_rate=0.5, seed=99))
    b = MeshCommsModel(["d1", "d2", "d3"], CommsConfig(loss_rate=0.5, seed=99))
    ea = a.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    eb = b.publish(sender_id="d1", payload=_payload(), sent_at_s=0.0)
    assert [e.outcome for e in ea] == [e.outcome for e in eb]
