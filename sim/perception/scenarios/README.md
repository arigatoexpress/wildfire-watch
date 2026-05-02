# GNSS-denied scenarios

Each YAML here is a `JammingScenario` — a list of GPS-degradation events.
Load with `JammingScenario.load(path)` and pass to
`runner_extension.wrap_with_fused_nav(runner, jamming=...)`.

| File | What it tests |
|------|---------------|
| canyon_gps_outage.yaml | Single 60-second outage at T=30s. VO+IMU must carry. |
| smoke_plume_gps_loss.yaml | 25-second outage at T=90s while a smoke burst is active — VO is also degraded. Worst-case wildfire scenario. |
| deliberate_jam_burst.yaml | 10-second GPS spoof reporting a false position ~2km off. Spoof discriminator must reject. |
| altitude_dependent_loss.yaml | Two short outages bracketing a descent — models below-ridgeline GPS shadowing. |

Event types:

- `gps_outage` — `available=False` for `duration_s` seconds. Receiver
  reports nothing. VO+IMU+TRN take over.
- `gps_spoof` — receiver reports `payload.false_lat / false_lon` for
  `duration_s` seconds. Spoof discriminator (`jamming.py`) compares
  reported velocity vs VO+IMU velocity and flips `trusted=False` when
  they disagree by > 3 sigma.
