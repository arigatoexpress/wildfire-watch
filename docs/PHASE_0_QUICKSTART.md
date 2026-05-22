# wildfire-watch — Phase 0 Quickstart

> Looking for the step-by-step **operator runbook** for the SD-card
> flow? See [`PHASE_0_RUNBOOK.md`](PHASE_0_RUNBOOK.md). This document
> is the conceptual quickstart; the runbook is what you follow at the
> Mac mini after each flight.

The point of Phase 0 is to **prove the end-to-end pipeline works on the
hardware you already own** — Mavic Mini 1/2 + Mac mini + Raspberry Pis
(rari1, rari2). Total new hardware budget: $0. Iterate from here once
the Jetson + thermal camera arrive.

What Phase 0 does NOT do:

- No on-board AI on the drone — the Mavic Mini has no developer hooks. You
  fly manually, land, and run a post-flight script.
- No thermal camera — RGB-only. The fusion gate in `infer.py` is
  intentionally bypassed; signals never recommend `loiter_and_capture` or
  `notify_fire_dept`. At most they recommend `notify_operator`.
- No fine-tuned fire model — Phase 0 uses YOLOv8n pretrained on COCO
  (which has no fire/smoke class) plus a colour/brightness heuristic
  placeholder. Phase 1 replaces this with the FASDD/FLAME fine-tune.

Despite all that, you get: GPS-stamped detections, schema v1 signals,
the Sapphire bridge ingest path, and a Pi telemetry channel — every
piece the eventual MVP needs, exercised today.

## 1. Fly the Mavic Mini (manual scout pattern, ~5 min)

1. Pre-flight: check the FAA TFR list (https://tfr.faa.gov) and confirm
   the area is clear. Phase 0 has no automated geofence refusal-to-arm.
2. Power on, set the camera to record video at 1080p / 30fps OR rapid-fire
   photos at ~1 Hz.
3. **Make sure DJI Fly is set to write SRT subtitle files.**
   Settings → Camera → Video Caption (some firmwares: Subtitle) → ON.
   Without SRT files we cannot geo-locate detections.
4. Fly a serpentine pattern over the target area at 60-100 m AGL,
   keeping the gimbal at ~20-30 degrees forward-down. Manual flight; the
   Mavic Mini does not support uploaded missions.
5. Land. Power off.

## 2. Import to the Mac mini

Pull the SD card or use DJI Fly's USB sync. Drop everything into a
date-stamped folder:

    mkdir -p ~/wildfire-watch-flights/2026-05-01
    cp -i /Volumes/DJI*/DCIM/100MEDIA/* ~/wildfire-watch-flights/2026-05-01/

You should see paired files like:

    DJI_0001.MP4
    DJI_0001.SRT          <-- per-frame GPS, attitude, time
    DJI_0002.JPG

## 3. Run the post-flight detector

    cd ~/Code/wildfire-watch
    python3 ml/fire_detection/mavic_post_flight.py \
        ~/wildfire-watch-flights/2026-05-01 \
        --drone_id wfw-mavic01 \
        --zone_id phase0-monterey-east \
        --pipe-to-sapphire

What this does:

- Walks the folder for *.MP4 and *.JPG.
- Parses each `.SRT` to build a frame -> (lat, lon, rel_alt) lookup.
- Samples ~1 frame/second from videos, every photo once.
- Runs YOLOv8n (COCO) + a colour/brightness heuristic. **COCO has no
  fire class** — the heuristic is the placeholder. Documented in the
  script header.
- For every candidate frame, builds a `wildfire_signal` v1 (signal_type
  `smoke` or `fire`, signal_subtype `phase_0/heuristic_color_temp`).
- Pipes each signal into `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py`
  with `action=ingest`. The bridge validates against the schema, appends
  to `~/Code/Sapphire/data/wildfire_signals.jsonl`, and emits a
  `wildfire.signal.detected` event_bus envelope.

If `ultralytics` is not installed, pass `--no-yolo` to run the heuristic
alone:

    python3 ml/fire_detection/mavic_post_flight.py \
        ~/wildfire-watch-flights/2026-05-01 \
        --no-yolo

If you have no flight footage yet, exercise the pipeline against the
shipped synthetic-replay scenario:

    python3 ml/fire_detection/demo.py --pipe-to-sapphire

## 4. View results

- **Sapphire dashboard** at `http://mac.local:8080` (basic auth
  user `sapphire`). Watch the SSE event stream for `wildfire.signal.detected`.
- **Raw JSONL** at `~/Code/Sapphire/data/wildfire_signals.jsonl`. One
  signal per line, schema v1.
- **Local script output** prints each emit + bridge response to stdout
  as JSONL.

The hermes wildfire-alert Telegram skill is **not yet shipped** — it is
operator-supervised and is being landed in a separate PR. Until then
detections do not page anyone; they only land in the dashboard + JSONL.

## 5. Optional — Pi telemetry collector

Keep the Pi -> Mac path alive between flights so the bridge sees a
heartbeat even on no-fly days.

On rari1 or rari2:

    ssh rari@100.120.191.1   # rari1
    # or
    ssh rari@100.87.225.89   # rari2

Drop a config:

    mkdir -p ~/.wildfire-watch
    cat > ~/.wildfire-watch/pi_config.json <<JSON
    {
      "pi_id": "wfw-pi01",
      "zone_id": "phase0-rari1-baseline",
      "lat": 36.4906,
      "lon": -121.1825,
      "alt_agl_m": 0.0,
      "log_dir": "/var/log/wildfire-watch"
    }
    JSON

Smoke-test once:

    python3 ground_station/pi_telemetry_collector.py --once --dry-run

Run forever (heartbeat every 60s, batch POST every 5min):

    python3 ground_station/pi_telemetry_collector.py \
        --bridge-url http://100.67.171.79:18081/wildfire/ingest

The collector uses **stdlib only** — no pip installs needed on the Pi.
On the Mac side, the bridge URL must be the wildfire-bridge HTTP
endpoint; if you only have the stdin-JSON bridge, run the script with
`--dry-run` and pipe its output through the bridge yourself.

## 6. What's next (Phase 1 preview)

| Feature | Phase 0 (today) | Phase 1 (when hardware arrives) |
|---|---|---|
| AI | COCO YOLOv8n + colour heuristic, post-flight | FASDD/FLAME fine-tune on Jetson, on-board |
| Thermal | None | PureThermal 3 / FLIR, fusion gate active |
| Geofence refuse-to-arm | Manual | `geofence_check.py` polls TFR + winds |
| Telegram alerts | Disabled | `hermes-agent` wildfire-alert skill |
| Multi-drone consensus | Single airframe | Peer confirmation in signal `consensus` field |
| Auto-loiter | Disabled (Mavic Mini doesn't support it) | MAVLink `COMMAND_LONG` from Jetson |

## Honest limitations

1. **No thermal corroboration.** Phase 0 cannot tell smoke from a grey rock
   or fire from a sunset. False positives are the expected mode.
2. **Post-flight latency.** Real fires need minute-scale alerting; Phase 0
   is "after-the-flight". Acceptable only because the operator is in the
   loop on every flight.
3. **No autonomous behaviour.** No mission upload, no auto-loiter, no
   refuse-to-arm. The RPIC is the safety system.
