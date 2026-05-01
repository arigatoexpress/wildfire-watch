# Sapphire Integration

This directory bridges wildfire-watch drones into the operator's Sapphire
intelligence stack at `~/Code/Sapphire`.

## Why this exists

The operator already runs:

- **`signal_logger:18081`** (Mac, Tailscale-only) — JSONL persistence + Telegram
  fan-out via hermes-agent. Source: `services/alpha/src/signal_logger.py`.
- **dashboard:8080** — operator dashboard with auth.
- **rari1 / rari2** Tailscale Pi cluster — free GPU-less compute for ensemble
  cross-checks.
- **hermes-agent** Telegram bot — already paginated, already rate-limited, already
  on the operator's phone.

We don't rebuild any of that. We POST the signal and let Sapphire's existing fan-out do its job.

## Endpoint

Drone (or ground station on its behalf) POSTs JSON conforming to
[`wildfire_signal_schema.json`](wildfire_signal_schema.json) to:

```
POST http://100.67.171.79:18081/signal
Authorization: Bearer ${WEBHOOK_SECRET}
Content-Type: application/json
```

Constraints (inherited from Sapphire):
- **Tailscale-only** — `signal_logger` rejects non-`100.64.0.0/10` and non-localhost.
  Drone uplink path is: drone → LTE → ground station (Mac, on Tailscale) → signal_logger.
  The drone itself does **not** call `signal_logger` directly unless it has Tailscale (rare).
- **WEBHOOK_SECRET** required — shared secret in operator's `~/.zshenv`.

## Where signals land in Sapphire

- **JSONL**: `~/Code/Sapphire/data/wildfire_signals.jsonl` (recommended new file).
  We do **not** mix into `trading_signals.jsonl`; the analyzer logic differs.
- **Dashboard**: surface a wildfire tab at `/wildfire` reading from the new JSONL.
- **Telegram**: hermes-agent message format:
  ```
  [WFW] {signal_type} from {drone_id} in {zone_id}
  conf={confidence:.2f} risk={risk_score}/100
  {target_coords.lat},{target_coords.lon}
  evidence: {first frame_uri}
  recommended: {recommended_action}
  ```
- **Cloud Run**: `sapphire-479610` project — public ecology API consumes the
  `signal_type=wildlife` subset and republishes (no fire signals exposed publicly).

## Adapter (recommended sketch)

Until a Sapphire PR adds first-class wildfire support, the ground station runs a
small adapter:

```python
# ground_station/sapphire_adapter.py (stub, not yet shipped)
import os, httpx, json
from pathlib import Path

SAPPHIRE_URL = os.getenv("SAPPHIRE_SIGNAL_URL", "http://100.67.171.79:18081/signal")
SECRET = os.environ["WEBHOOK_SECRET"]

def forward(signal: dict) -> None:
    r = httpx.post(
        SAPPHIRE_URL,
        json=signal,
        headers={"Authorization": f"Bearer {SECRET}"},
        timeout=5.0,
    )
    r.raise_for_status()
    # Also persist locally for resilience
    Path("data/wildfire_signals.jsonl").open("a").write(json.dumps(signal) + "\n")
```

## Sapphire-side patch (downstream, separate PR to Sapphire repo)

We **do not** modify Sapphire from this repo. The Sapphire-side change is a
separate PR there that:

1. Adds a discriminator on `signal_type` ∈ {`smoke`, `fire`, `thermal_anomaly`,
   `wildlife`, `anomaly`, `system_event`} to route to `wildfire_signals.jsonl`.
2. Adds a hermes-agent template for the WFW format (above).
3. Adds a `/wildfire` dashboard tab — separate from the `/trading` tab.
4. Adds a Cloud Run function that mirrors `wildlife`-typed signals to a
   public-read GCS bucket for the ecology dataset.

Until that lands, the adapter writes locally and emits a stub Telegram via the
existing trading_signal channel with a `[WFW]` prefix — sufficient for MVP.

## Failure modes

- `signal_logger` down → adapter writes locally + retries on a 60-s backoff;
  drone-edge signal buffer holds 24 h.
- WEBHOOK_SECRET rotation → operator updates `.zshenv` and restarts the adapter
  service.
- Telegram outage → hermes already handles offline buffering.
