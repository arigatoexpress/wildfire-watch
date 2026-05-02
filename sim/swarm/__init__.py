"""wildfire-watch multi-drone swarm primitives.

Composition-only extension of the single-drone simulator. The single-drone
modules (sim.runner, sim.mission, sim.scenario, sim.airframe, sim.kinematics,
sim.recorder) are reused unchanged.

Public surface:
    Fleet              — N-drone container, lockstep tick.
    CoveragePlanner    — bbox-grid partition of an inclusion polygon.
    ConsensusVoter     — k-of-N spatial+temporal+type confirmation.
    MeshCommsModel     — lossy peer-to-peer with latency + partitions.
    SwarmRunner        — composes Fleet + Voter + Comms + Scenario.
    SwarmRecorder      — writes drones / signals / consensus / comms jsonl.
"""

__all__ = [
    "comms",
    "consensus",
    "coverage_planner",
    "fleet",
    "recorder",
    "runner",
]
