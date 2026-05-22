# Phase 0 Operator Runbook

Step-by-step for the **Mavic Mini SD-card flow**. Pre-flight gate
to live signals on the dashboard, with troubleshooting for every
failure mode the test suite has caught.

This is the runbook the operator follows on the Mac mini after
landing the drone. Read it once before the first flight, print
the *Quick steps* section, and keep it next to the laptop.

For the *why* behind each step (Phase 0 trade-offs, fusion-gate
bypass, etc.), see [`PHASE_0_QUICKSTART.md`](PHASE_0_QUICKSTART.md).

---

## Quick steps (laminate this)

1. Power on the Mac mini.
2. Plug the Mavic Mini's SD card into the mini's card reader.
3. Open Terminal and run:
   ```bash
   cd ~/Code/wildfire-watch
   /usr/local/bin/python3 scripts/phase0_e2e.py \
       --video    /Volumes/MAVIC/DCIM/100MEDIA/DJI_0001.MP4 \
       --log      /Volumes/MAVIC/DCIM/100MEDIA/DJI_0001.SRT \
       --endpoint http://127.0.0.1:18080/ingest \
       --drone-id wfw-mavic01 \
       --zone-id  gunnison-corridor \
       --fake-server
   ```
   (Replace the SD-card paths with your actual filenames; DJI's
   numbering rolls forward each flight.)
4. Open `http://localhost:5000/` in a browser to watch live signals.
5. If the fusion gate trips, expect a Telegram alert (or HTTP webhook
   fan-out) and a fresh row at `https://wildfire.sapphirealpha.xyz/`.

The harness exits non-zero if anything went wrong; the dashboard
will show a stale `last_seen` if the SD card was empty or the script
silently produced zero signals.

---

## Pre-flight checklist (every flight)

- [ ] **TFR check** — `https://tfr.faa.gov` for any active TFR
      overlapping the Gunnison-Crested Butte corridor. Phase 0 has no
      automated TFR refusal-to-arm; this is on the operator.
- [ ] **Wilderness boundaries** — confirm the planned flight path does
      not cross West Elk / Maroon Bells-Snowmass / Raggeds. These are
      hard no-fly per 36 CFR 261.16.
- [ ] **DJI Fly settings** — Camera → Video Caption (Subtitle) is
      **ON**. Without the SRT, GPS coordinates are lost and the flight
      becomes single-point-of-failure on the EXIF tags only.
- [ ] **Battery** — Mavic Mini at >40% remaining (Gunnison is at
      7,700+ ft; battery duration drops 25-35% above 9,000 ft. Plan
      for 70% nominal endurance).
- [ ] **SD card free space** — at least 4 GB clear before flight.
- [ ] **Mac mini** — ssh, dashboard, and Sapphire bridge all running.
      `ps -ef | grep -E '(wildfire|sapphire)'` should show all three.

---

## Step-by-step (operator flow)

### 1. Power on the Mac mini

The mini auto-resumes its launchd services. After login, confirm:

```bash
launchctl list | grep -E '(wildfire|sapphire)'
curl -s http://127.0.0.1:8080/healthz/   # sapphire dashboard
curl -s http://127.0.0.1:5000/healthz/   # wildfire-watch local
```

If any heartbeat is missing, run `~/Code/wildfire-watch/scripts/check_services.sh`
and follow the printed remediation.

### 2. Drop the SD card

The Mavic Mini SD card mounts as `/Volumes/MAVIC` (or whatever you
named it). DJI Fly writes:

- `DJI_0001.MP4` — the flight video
- `DJI_0001.SRT` — the GPS subtitle stream (if Video Caption was on)
- (sometimes) `DJI_0001.LRF` — low-res preview, ignored by Phase 0

If you see only `.MP4` and no `.SRT`, **stop**: the flight has no GPS
and Phase 0 cannot place the detection. Re-fly with Video Caption ON.

### 3. Run the post-flight harness

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 scripts/phase0_e2e.py \
    --video    /Volumes/MAVIC/DCIM/100MEDIA/DJI_0001.MP4 \
    --log      /Volumes/MAVIC/DCIM/100MEDIA/DJI_0001.SRT \
    --endpoint http://127.0.0.1:18080/ingest \
    --drone-id wfw-mavic01 \
    --zone-id  gunnison-corridor \
    --fake-server
```

Flags:

- `--video` — path to the .MP4 from the SD card.
- `--log` — path to the .SRT (DJI Fly subtitle) or .CSV (Airdata /
  DatCon export). Both are auto-detected by `MavicFlightLog`.
- `--endpoint` — where to POST the wildfire_signal envelopes. The
  fake-server flag spins up an in-process echo server on :18080 for
  smoke-testing the seams. To ship signals into Sapphire, point this
  at `http://127.0.0.1:18081/ingest/wildfire` instead.
- `--drone-id` — must match the regex `^wfw-[a-z0-9]{4,16}$`.
- `--zone-id` — any string; used by the dashboard zone filter.

The harness is HMAC-signed by default; receivers verify
`X-Wildfire-Signature` (HMAC-SHA256) over `timestamp + "." + body`.

### 4. Watch live signals

- **Local**: `http://localhost:5000/` (the wildfire-watch admin
  dashboard). Live signal map, KPI strip, sensor health pill, signal
  table.
- **Production**: `https://wildfire.sapphirealpha.xyz/` (Cloud Run,
  `wildfire-frontend`). The sensor pill in the nav goes orange when
  any sensor is `stale` and red when any is `down`.

If the harness ran but no signals show on the dashboard, check that
`data/wildfire_signals.jsonl` is being written (`ls -lt data/` and look
for the most recent mtime).

### 5. Fusion-gate trip behaviour

When `should_emit()` returns True AND `risk_score >= 70` AND
`signal_type ∈ {fire, smoke, thermal_anomaly}`, the alert router
fires:

- **Webhook** — POST to `ALERT_WEBHOOK_URL` with HMAC signature.
- **Telegram** — message to `TELEGRAM_CHAT_ID` if `TELEGRAM_TOKEN`
  is set.

Alerts are idempotent at `signal_id` granularity (ledger at
`~/.wildfire/alerts.jsonl`); a duplicate from a swarm vote or a
restart-replay does not double-page.

### 6. GCS evidence retry queue

If GCS is unreachable mid-flight (Mac mini WiFi flap, expired
service-account credentials), every detection frame lands in
`~/.wildfire/retry-evidence/`. **The next time you run the harness
or the live inference loop, the queue drains automatically before
new traffic.**

To check queue depth:

```bash
ls ~/.wildfire/retry-evidence/ | wc -l
```

To force a drain manually without flying:

```bash
/usr/local/bin/python3 -c \
  "from ml.fire_detection.evidence import drain_evidence_queue; \
   print(drain_evidence_queue())"
```

The webhook retry queue (`~/.wildfire/retry/`) follows the same
pattern — drains on next boot, manual drain via
`drain_retry_queue(endpoint, secret)`.

---

## Environment variables

These are read by both `infer.py` (live loop) and `phase0_e2e.py`
(post-flight). Set them in `~/.zshrc` or in a launchd plist for the
Mac mini.

| Variable | Default | Purpose |
|---|---|---|
| `WILDFIRE_WEBHOOK_SECRET` | (required) | HMAC secret for signal POSTs. Refuses to start with `REPLACE_ME`. |
| `EVIDENCE_BUCKET` | `wildfire-watch-evidence` | GCS bucket for detection frames. |
| `GOOGLE_APPLICATION_CREDENTIALS` | (ADC) | Service-account key path. Optional; ADC is preferred. |
| `ALERT_WEBHOOK_URL` | (none) | Where to POST fusion-gate-trip alerts. |
| `ALERT_WEBHOOK_SECRET` | falls back to `WILDFIRE_WEBHOOK_SECRET` | HMAC secret for the alert POST. |
| `TELEGRAM_TOKEN` | (none) | Bot API token. Off when unset. |
| `TELEGRAM_CHAT_ID` | (none) | Operator chat ID. |
| `SENSOR_STALE_MIN` | `30` | Minutes since last heartbeat before a sensor flips to `stale`. |
| `SENSOR_DOWN_MIN` | `120` | Minutes since last heartbeat before a sensor flips to `down`. |
| `SENSOR_HEALTH_POLL_SEC` | `300` | Background watcher poll interval (5 min). |

---

## Troubleshooting

### "WILDFIRE_WEBHOOK_SECRET env var must be set"

`_resolve_secret()` refuses to ship signed-with-`REPLACE_ME` traffic
into prod. Set the secret in your shell profile or in the launchd
plist for the inference service.

### Dashboard shows zero signals after the harness ran

1. `ls -lt data/wildfire_signals.jsonl` — was the sink written?
2. `tail -3 data/wildfire_signals.jsonl` — does it parse as valid JSONL?
3. The dashboard reads from the JSONL file path configured by
   `WFW_SIGNALS_PATH`; verify it points at the same file the harness
   wrote.

### Sensor pill says "down (1 down)"

A heartbeat hasn't arrived in `SENSOR_DOWN_MIN` minutes. Check:

1. The Pi's `pi_telemetry_collector` is still running (`ssh rari1 pgrep -fa pi_telemetry`).
2. The Pi can reach the signal endpoint (`curl -s http://mac-mini:18081/healthz`).
3. The webhook retry queue isn't backlogged on the Pi (`ls ~/.wildfire/retry/`).

### Evidence queue isn't draining

`drain_evidence_queue` stops on the **first** failure so a long-stale
buffered frame doesn't bury fresh ones. Symptoms:

- `ls ~/.wildfire/retry-evidence/ | wc -l` stays > 0 across multiple
  runs of the harness.
- Logs say "evidence: still failing on …".

Causes (most common first):

1. **No ADC credentials** — `gcloud auth application-default login` on
   the Mac mini.
2. **Bucket doesn't exist** — `gsutil ls gs://wildfire-watch-evidence`.
3. **Wrong project** — confirm the active gcloud config is
   `tho-ai-agent`.

### Alert didn't fire on a real fusion-gate trip

1. `tail -3 ~/.wildfire/alerts.jsonl` — was the signal_id already
   recorded? (Idempotence: the same signal_id only pages once.)
2. Are `TELEGRAM_TOKEN` + `TELEGRAM_CHAT_ID` actually exported to the
   process running infer.py? `launchctl print` for the launchd job, or
   `cat /proc/<pid>/environ | tr '\0' '\n'` if a child process.
3. Check the alert's `risk_score`. The default floor is 70.0; below
   that, the gate skips even on a `fire` signal. Tune via the
   `risk_threshold` kwarg to `maybe_alert` or set the producer to
   ship `fusion_gate_passed=True` explicitly.

---

## Hardware-blocked items (Phase 1)

These pieces of `infer.py` still carry `TODO()` markers because Phase
0 hardware can't exercise them:

- **MIPI-CSI camera capture** — Mavic Mini has no developer hooks; we
  rely on post-flight SD-card processing. Real capture wiring needs
  the Holybro X500 V2 + Arducam IMX477 from Phase 1.
- **Thermal camera (PureThermal 3)** — no thermal in Phase 0. The
  fusion gate's 5°C delta-T floor is bypassed; signals never claim
  `signal_type=fire` based on thermal alone.
- **TensorRT engine** — Mac mini doesn't have a CUDA GPU. Phase 0
  uses YOLOv8n on CPU via ultralytics. Engine compile lives on the
  Jetson Orin Nano in Phase 1.
- **MAVLink GPS** — Mavic Mini has no MAVLink stream. We pull GPS
  from the SRT subtitle stream via `mavic_log.py`.

Closing each of these is a Phase 1 deliverable, gated on the BOM
purchase.

---

See also:

- [`docs/PHASE_0_QUICKSTART.md`](PHASE_0_QUICKSTART.md) — the
  conceptual walkthrough.
- [`docs/30-ml-stack.md`](30-ml-stack.md) — fusion-gate design notes.
- [`docs/40-faa-compliance.md`](40-faa-compliance.md) — TFR + LAANC + Remote ID.
- [`README.md`](../README.md) — repo overview.
