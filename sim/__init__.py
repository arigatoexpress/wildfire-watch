"""wildfire-watch flight simulator.

Pure-Python kinematic drone-flight simulator. Drives a virtual airframe
along a planned mission, emits Mavic-Mini-shaped telemetry + DJI-Fly
SRT subtitles, and produces wildfire_signal v1 events through the
fusion gate in ml/fire_detection/infer.py.

No NumPy, no SciPy, no SimPy, no PX4 — stdlib + pyyaml + requests only.
"""

__all__ = [
    "airframe",
    "kinematics",
    "mission",
    "recorder",
    "runner",
    "scenario",
]
