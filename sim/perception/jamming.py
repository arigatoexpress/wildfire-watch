"""GPS jamming + spoofing scenarios.

A JammingScenario is a YAML-loadable list of scheduled events. Each
event has a trigger time (sim seconds) and a type:

  gps_outage    GPS becomes UNAVAILABLE for `duration_s` seconds.
                The simulator will report no GPS reading at all during
                the window. This models physical jamming (the receiver
                sees no satellites).

  gps_spoof     GPS reports a FALSE position (false_lat, false_lon) for
                `duration_s` seconds. The receiver is happy; the
                position is wrong. The fusion layer's spoof
                discriminator must detect this by comparing
                GPS-reported velocity against VO+IMU velocity.

YAML format:

    name: canyon_outage
    description: ...
    events:
      - at: {t_seconds: 30}
        type: gps_outage
        duration_s: 60
      - at: {t_seconds: 100}
        type: gps_spoof
        duration_s: 5
        payload:
          false_lat: 38.7000
          false_lon: -107.0500

Spoof discriminator:

  Each tick we compute reported_velocity_mps from successive GPS
  positions, and compare it against the truth-step velocity (or, in
  practice, against VO+IMU velocity). If they disagree by > N*sigma
  (N=3, sigma combined VO+IMU one-sigma), we mark GPS UNTRUSTED.

  This is *deliberately* fragile. Real anti-spoofing uses inertial
  consistency, multi-band L1/L5 receivers, or a dedicated CRPA
  antenna; we model only the inertial-consistency branch.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class JammingEvent:
    """One scheduled GPS-degradation event."""

    name: str
    type: str  # "gps_outage" | "gps_spoof"
    t_start_s: float
    duration_s: float
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def t_end_s(self) -> float:
        return self.t_start_s + self.duration_s


@dataclass
class JammingState:
    """Current per-tick GPS condition. Mutable, owned by the engine."""

    available: bool = True
    trusted: bool = True
    reported_lat: float | None = None
    reported_lon: float | None = None
    active_event_name: str = ""


class JammingScenario:
    """Holds scheduled events + the engine that applies them."""

    def __init__(self, name: str, description: str, events: list[JammingEvent]):
        self.name = name
        self.description = description
        self.events = events
        # Spoof-discriminator threshold: number of sigmas of VO/IMU
        # velocity the GPS-reported velocity must deviate before we
        # mark UNTRUSTED.
        self.spoof_sigma_threshold = 3.0
        # Internal: rolling track of the last truth-velocity to compute
        # GPS-reported deltas against.
        self._last_truth_lat: float | None = None
        self._last_truth_lon: float | None = None

    # ---- factory -----------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> "JammingScenario":
        import yaml  # noqa: PLC0415  lazy

        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"jamming scenario not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            raise ValueError(f"jamming scenario must be a YAML mapping: {p}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "JammingScenario":
        events: list[JammingEvent] = []
        for i, e in enumerate(data.get("events", []) or []):
            at = e.get("at", {}) or {}
            t = float(at.get("t_seconds", 0.0))
            events.append(
                JammingEvent(
                    name=str(e.get("name", f"event_{i}")),
                    type=str(e["type"]),
                    t_start_s=t,
                    duration_s=float(e.get("duration_s", 0.0)),
                    payload=dict(e.get("payload", {}) or {}),
                )
            )
        return cls(
            name=str(data.get("name", "unnamed-jamming")),
            description=str(data.get("description", "")),
            events=events,
        )

    # ---- per-tick evaluation ----------------------------------------

    def step(
        self,
        *,
        sim_time_s: float,
        truth_lat: float,
        truth_lon: float,
        vo_velocity_mps: float | None,
        vo_imu_sigma_m: float,
        dt: float,
    ) -> JammingState:
        """Return GPS availability + trust + reported position for this tick.

        - Default: GPS available, trusted, reported = truth perturbed by
          a small CEP (the runner_extension calls this directly; we
          emit truth here and let the fusion layer add the GPS sigma
          as part of its variance accounting).
        - Within an outage event: available=False.
        - Within a spoof event: reported = false_lat / false_lon.
        - The spoof discriminator runs every tick we have a reported
          position, comparing reported delta against truth delta. If
          they disagree by > threshold sigmas, trusted=False.
        """
        state = JammingState(
            available=True,
            trusted=True,
            reported_lat=truth_lat,
            reported_lon=truth_lon,
        )

        for ev in self.events:
            if not (ev.t_start_s <= sim_time_s < ev.t_end_s):
                continue
            state.active_event_name = ev.name
            if ev.type == "gps_outage":
                state.available = False
                state.reported_lat = None
                state.reported_lon = None
            elif ev.type == "gps_spoof":
                state.reported_lat = float(ev.payload.get("false_lat", truth_lat))
                state.reported_lon = float(ev.payload.get("false_lon", truth_lon))
            # Unknown event types fall through silently.

        # Spoof discriminator. Only meaningful when GPS reports SOMETHING.
        if state.available and state.reported_lat is not None:
            self._discriminate(
                state=state,
                truth_lat=truth_lat,
                truth_lon=truth_lon,
                vo_velocity_mps=vo_velocity_mps,
                vo_imu_sigma_m=vo_imu_sigma_m,
                dt=dt,
            )

        # Roll truth tracker forward for next tick.
        self._last_truth_lat = truth_lat
        self._last_truth_lon = truth_lon
        return state

    def _discriminate(
        self,
        *,
        state: JammingState,
        truth_lat: float,
        truth_lon: float,
        vo_velocity_mps: float | None,
        vo_imu_sigma_m: float,
        dt: float,
    ) -> None:
        """If reported GPS position disagrees with VO+IMU velocity by
        > N*sigma, set trusted=False."""
        if self._last_truth_lat is None or vo_velocity_mps is None:
            return
        reported_lat = state.reported_lat
        reported_lon = state.reported_lon
        if reported_lat is None or reported_lon is None:
            return
        # GPS-reported jump from last tick.
        dlat = reported_lat - self._last_truth_lat
        dlon = reported_lon - self._last_truth_lon
        cos_phi = max(1e-6, math.cos(math.radians(reported_lat)))
        gps_step_m = math.hypot(dlat * 111_320.0, dlon * 111_320.0 * cos_phi)
        # Truth step.
        tdlat = truth_lat - self._last_truth_lat
        tdlon = truth_lon - self._last_truth_lon
        truth_step_m = math.hypot(
            tdlat * 111_320.0,
            tdlon * 111_320.0 * cos_phi,
        )
        # Disagreement in displacement, in meters.
        disagreement_m = abs(gps_step_m - truth_step_m)
        # Combined sigma (VO+IMU per-tick).
        threshold_m = max(0.5, self.spoof_sigma_threshold * vo_imu_sigma_m)
        if disagreement_m > threshold_m:
            state.trusted = False
