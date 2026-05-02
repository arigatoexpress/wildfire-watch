# hermes wildfire-alert skill — Integration Spec

The hermes-agent gateway (`ai.hermes.gateway` LaunchAgent on the Mac commander)
hosts the operator-facing Telegram bot for Sapphire OS. The
**`wildfire-alert` skill** is the pager that converts wildfire-watch drone
signals into operator-supervised Telegram alerts. This document specifies the
integration contract.

The skill itself lives outside this repo at:

```
~/.hermes/skills/sapphire/wildfire-alert/
```

It consumes events emitted by the Sapphire-side bridge tool at
`~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` (PR #551, merged
2026-05-02 to the `Sapphire` repo), which is fed by the schema in this directory
([`wildfire_signal_schema.json`](wildfire_signal_schema.json)).

## What this closes

The previous `sapphire_integration/README.md` documents how a wildfire_signal
v1 reaches Sapphire's `signal_logger:18081` and lands in
`~/Code/Sapphire/data/wildfire_signals.jsonl`. That covers ingestion and
persistence. **It does not handle alerting.** Until the `wildfire-alert` skill
ships, an `notify_fire_dept` recommended action would land on disk and silently
wait for a human to notice.

`wildfire-alert` closes the loop: signals on the Sapphire event bus become
operator-supervised Telegram messages with explicit reply tokens.

## Event-bus envelope (the contract)

The Sapphire bridge writes to `~/Code/Sapphire/data/events/bus.jsonl` — the
same JSONL stream used by `lead.ingested`, `kill_switch.activated`, etc.
Each line is one envelope:

```json
{
  "id": "local-<epoch>-<uuid8>",
  "type": "wildfire.signal.detected",
  "ts": "2026-05-02T14:23:00.000000+00:00",
  "source": "wildfire-bridge",
  "data": {
    "signal": {
      "schema_version": "1.0.0",
      "signal_id": "<uuidv4>",
      "drone_id": "wfw-unit01",
      "zone_id": "slate-river-drainage",
      "timestamp": "2026-05-02T14:23:00Z",
      "coords": {"lat": 38.9105, "lon": -107.0010, "alt_agl_m": 80, "...": "..."},
      "target_coords": {"lat": 38.9105, "lon": -107.0010, "...": "..."},
      "signal_type": "fire",
      "confidence": 0.91,
      "evidence": {"frame_uris": ["gs://..."], "thermal_frame_uris": [], "...": "..."},
      "environment": {"wind_dir_deg": 145, "...": "..."},
      "risk_score": 86,
      "recommended_action": "notify_fire_dept",
      "consensus": {"peer_drone_ids": ["wfw-sim02"], "peer_confirmations": 1}
    }
  }
}
```

The skill tolerates both `data.signal = {...}` (preferred) and `data = {...}`
inline. Use the wrapped form going forward.

## Recommended-action routing

The skill filters on `signal.recommended_action`:

| Action               | Skill behavior                                                     |
| -------------------- | ------------------------------------------------------------------ |
| `log_only`           | Silent. Marked seen so it doesn't re-fire on a re-tail.            |
| `rtl`                | Silent. Operator sees it in the next `--mode status` summary.      |
| `notify_operator`    | **Telegram alert** with `ESCALATE`/`SECOND`/`DOWNGRADE` reply tokens. |
| `loiter_and_capture` | **Telegram alert** with `RTL`/`ESCALATE` reply tokens.             |
| `notify_fire_dept`   | **Telegram alert** with **`PAGE FIRE`/`DOWNGRADE`/`SECOND`**.       |

## Operator-supervision contract (CRITICAL)

The skill **never dials, pages, or notifies any fire department directly.**

`recommended_action=notify_fire_dept` is a recommendation. The drone has
fused multimodal evidence (RGB + thermal + peer confirmation) and reached a
risk score above the auto-escalation threshold. But the call to dispatch a
fire crew is an operator decision, every time.

The Telegram message includes the dispatch number for the AOR:

- **CBFPD — Crested Butte Fire Protection District: (970) 349-5333**
- (Gunnison County FPD: (970) 641-0244 — verify before publishing)

The operator dials. The skill logs the operator's reply (`PAGE FIRE`,
`DOWNGRADE`, `SECOND`) back to the Sapphire bridge for audit, but it does
not trigger the call itself.

This is non-negotiable. The aviation/SAR liability exposure of an autonomous
agent placing a 911-adjacent call is unacceptable. The human stays in the
loop.

## Dedup-key strategy

Each emitted Telegram alert is keyed on `signal.signal_id` (the v1 schema
mandates a UUIDv4 generated drone-side at signal-emit time, idempotent for
the receiver). The seen-set lives at:

```
~/.hermes/state/wildfire_alert_seen.json
```

Format: `{ signal_id: first_alerted_ts }`, JSON, atomic write via tmp-file
rename. The skill checks the seen-set on every tail pass and within the
pass itself, so duplicate envelopes (e.g. from an at-least-once bus
re-emit) never produce a duplicate alert.

If `signal_id` is missing (schema violation — should never happen), the
fallback key is `drone_id|zone_id|timestamp`. This is logged to stderr so
the bridge can be debugged.

## Skill layout

```
~/.hermes/skills/sapphire/wildfire-alert/
├── SKILL.md                              # description, commands, when-to-use
├── prompt.md                             # LLM-facing instructions (reply handling, contract)
├── inputs.json                           # JSON schema of accepted inputs
├── config.yaml                           # tunable params (reference; script has stdlib defaults)
├── script.py                             # formatter + dedup + tail + self-test (stdlib-only)
└── com.sapphire.wildfire-alert.plist     # LaunchAgent template (NOT auto-installed)
```

Convention follows the existing `~/.hermes/skills/sapphire/system-health/`
and `~/.hermes/skills/sapphire/threat-intel/` skills.

## Modes

### A. Operator-pull (`--mode status`)

User in Telegram: `/wildfire` or `wildfire status today`. The skill shells
out to the Sapphire bridge with `{"action":"stats","since_hours":24}` and
formats the response:

```
WFW STATUS | last 24h
zone slate-river-drainage:  2 signals (1 fire, 1 smoke)  max_risk 86
zone cement-creek-drainage: 0 signals
total: 2 signals | 1 critical | 0 fire-dept-notify

most recent (T-12m):
  fire @ 38.9105, -107.0010  conf 0.91  risk 86  notify_operator
  drone wfw-unit01 zone slate-river-drainage
```

If the bridge is unreachable, the skill degrades to reading
`~/Code/Sapphire/data/wildfire_signals.jsonl` directly.

### B. Auto-alert (`--mode tail`)

The LaunchAgent (template only — see install steps below) polls the event
bus every 30 seconds, filters for `wildfire.signal.detected`, dedups, and
pipes formatted alerts into the hermes-agent Telegram channel.

Sample rendered alert for a `notify_fire_dept` signal:

```
[WFW-ALERT 2026-05-02T14:23Z]  notify_fire_dept

zone:      slate-river-drainage
signal:    fire (conf 0.91, risk 86)
location:  38.9105, -107.0010 (about 1.6 km NW of Mt CB)
target:    fire center 25m uncertainty bearing 90
drone:     wfw-unit01 (alt_agl 80m)
peers:     wfw-sim02 confirmed (consensus k=2)
evidence:  3 frames captured, 1 thermal, 30s clip
weather:   wind 145deg/8.5mps, RH 18%, FWI=42

ACTION: this is a fire-dept-notify recommendation.
        The drone has corroborating evidence (see signal detail above).
        To page CBFPD (970) 349-5333 NOW, reply: PAGE FIRE
        To downgrade and continue patrol, reply: DOWNGRADE
        To dispatch second drone for visual confirm, reply: SECOND
```

## LaunchAgent install (manual)

The plist template is in the skill directory but is **not auto-installed**.
To enable:

```bash
cp ~/.hermes/skills/sapphire/wildfire-alert/com.sapphire.wildfire-alert.plist \
   ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) \
   ~/Library/LaunchAgents/com.sapphire.wildfire-alert.plist
```

Verify it's running:

```bash
launchctl print gui/$(id -u)/com.sapphire.wildfire-alert
tail -f /tmp/wildfire-alert.out.log
```

Pause via Sapphire's standard routine-pause convention:

```bash
mkdir -p ~/.sapphire/routine_pause
touch ~/.sapphire/routine_pause/wildfire-alert
```

Uninstall:

```bash
launchctl bootout gui/$(id -u)/com.sapphire.wildfire-alert
rm ~/Library/LaunchAgents/com.sapphire.wildfire-alert.plist
```

The plist runs `script.py --mode tail` every 30s and pipes record-separated
alerts (`\x1e` between messages) into
`hermes_agent.cli telegram-send --channel operator --stdin`. If your hermes
gateway exposes a different ingest endpoint, edit the `ProgramArguments`
shell pipeline accordingly.

## Verify

```bash
ls -la ~/.hermes/skills/sapphire/wildfire-alert/
/usr/local/bin/python3 ~/.hermes/skills/sapphire/wildfire-alert/script.py --self-test
```

Expected output ends with `ALL ASSERTIONS PASSED`.

## Failure modes + limitations

1. **Bridge tool absent.** If `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py`
   doesn't exist (e.g. on a fresh Sapphire clone before PR #551), `--mode
   status` falls back to reading `wildfire_signals.jsonl` directly. `--mode
   tail` reads the bus directly and is unaffected.
2. **Bus rotation / truncation.** The skill reads the bus from byte-zero
   every pass. Dedup is bounded only by the seen-set. If `bus.jsonl` is
   rotated and a previously-alerted signal_id reappears in a fresh file,
   the skill correctly skips it. If the **seen-set** is wiped (e.g. by a
   home-directory restore), the alert can re-fire — this is the safer
   failure direction.
3. **No automatic 911 dial.** By design. See "Operator-supervision contract"
   above.

## Why this is in `sapphire_integration/` and not elsewhere

This README documents how `wildfire-watch` (this repo) integrates with the
external hermes-agent skill. The skill itself ships in `~/.hermes/`, which
is operator-private state and not under `wildfire-watch` version control.
This document is the contract that pins the event-envelope shape and the
operator-supervision boundary so future skill-side changes don't silently
break wildfire-watch's expectations.
