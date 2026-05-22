# Incident response runbook

A one-page playbook for the moment something has gone wrong. Read top-to-bottom on first incident; bookmark the section index thereafter.

## Section index

1. [Detection](#1-detection) — what tells us we have an incident
2. [Triage](#2-triage) — first 15 minutes
3. [Containment](#3-containment) — first hour
4. [Remediation](#4-remediation) — first day to first week
5. [Post-mortem](#5-post-mortem) — within 14 days
6. [Partner-FD specific](#6-partner-fd-specific) — when an FD reports the issue

---

## 1. Detection

Signals that an incident is in progress, in rough order of "you should already be paying attention":

| Signal | Source | Action threshold |
|---|---|---|
| Test failure spike on `main` | `.github/workflows/ci.yml` | 3+ consecutive failed runs without intervening human commits |
| `gitleaks` / secret-scan alert | GitHub default; or `gitleaks detect` locally | ANY positive finding |
| Dependabot CVE alert | GitHub | HIGH or CRITICAL |
| Unexpected wildfire signal in `data/wildfire_signals.jsonl` | manual or Sapphire `wildfire.signal.detected` event-bus subscriber | any signal whose `signal_id` you cannot trace to a flight |
| Partner FD reports a page they did not believe | the FD calling you | always |
| HMAC verification failure rate > 0 on alert webhook | `alerts.py` receiver-side logs (FUTURE: a per-failure metric) | any non-zero rate |
| Drone position anomaly | `geofence_status.in_authorized_zone == false` in the schema | always |
| GCS bucket egress spike | GCP billing / monitoring | > 10x baseline |
| `ADMIN_TOKEN` / dashboard auth failures | `frontend/app.py` request log | > 5 distinct source IPs in an hour |
| Unsolicited GitHub Security Advisory | inbox / repo `/security/advisories` | always |

The **partner-FD report** is the highest-trust signal. If they call, treat it as confirmed regardless of what the rest of the system says.

---

## 2. Triage

First 15 minutes from detection. Goal: classify, page, preserve evidence.

### 2.1 Classify

What kind of incident is this? Use the matrix:

| Class | Example | Severity |
|---|---|---|
| **Secret exposure** | webhook secret in a commit; GCS key in a public Slack | HIGH |
| **Data leak** | evidence frame URL leaked outside the scope of the partnership | MEDIUM (single frame) to HIGH (bulk) |
| **Forged signal** | `wildfire_signal` in the JSONL the operator did not generate | HIGH (no FD page sent) to CRITICAL (FD page sent) |
| **Drone in wrong place** | flight outside the geofence; flight inside wilderness; flight during TFR | CRITICAL — regulatory + safety |
| **Bridge / dashboard offline** | DoS, bad deploy, dependency upgrade broke prod | LOW (alone) to HIGH (during active fire weather) |
| **Code-execution exploit** | RCE in `frontend/app.py` or `mavic_post_flight.py` | CRITICAL |
| **Partner-FD-reported false page** | CBFPD / GCFPD calls about a page they did not believe | CRITICAL |

### 2.2 Page

Single operator today, so "paging" is a self-page:
- Stop whatever else you are doing.
- Open `~/Documents/wildfire-watch-private/incident-log.md` and start the running log (timestamp every action).
- If the partner FD is involved, **call them back within 15 minutes of the report** with an acknowledgement (not a fix; just acknowledgement).

For a future multi-operator scenario:
- The maintainer is the incident commander by default.
- Communications go through a dedicated channel (Slack `#wfw-incident-NNNN` or equivalent), not the general operator chat.

### 2.3 Preserve evidence

Before changing anything:
- `git status` — note the working-tree state.
- `git rev-parse HEAD` — the SHA at the moment of incident.
- Snapshot any relevant logs (`data/wildfire_signals.jsonl`, GCS access logs for the bucket, dashboard request log).
- If a forged signal is suspected, snapshot the `signal_id` and any cross-referenced FD page.
- Take a screenshot if there is a dashboard view that shows the incident state.

**Do NOT** `git reset` or delete suspicious data until evidence is preserved.

---

## 3. Containment

First hour. Goal: stop the bleeding.

### 3.1 Revoke the smallest scope of secret necessary

Per [`secrets_inventory.md`](./secrets_inventory.md):

| Suspected leak | Action |
|---|---|
| `WILDFIRE_WEBHOOK_SECRET` (S-1) | Generate a new secret; deploy receiver-side first; deploy drone-side; old secret refused on next signal |
| `TELEGRAM_TOKEN` (S-2) | Revoke via BotFather; generate new |
| `ADMIN_TOKEN` (S-4) | Regenerate; redeploy dashboard; force-refresh in operator browser |
| GCS service-account key (S-5) | Disable the key in GCP IAM Console; create new; rotate `GOOGLE_APPLICATION_CREDENTIALS` |
| TAK client cert (S-6, FUTURE) | Notify partner FD; their CA revokes; we deploy reissued cert |
| `git` history committed secret | (1) revoke as above; (2) `git filter-repo` or `git-filter-branch` the secret; (3) force-push (only with explicit operator authorisation per CLAUDE.md); (4) request GitHub cache purge |

### 3.2 Kill-switch the affected drone

If a specific drone is compromised, hijacked, jammed-into-bad-state, or simply behaving wrong:

- **Phase 0 (Mavic Mini):** RTL via the controller; on landing, power down; isolate SD card (mount read-only on a separate machine before any analysis).
- **Phase 1 (Holybro X500 V2 + Cube Orange+):** the same RTL pattern, plus disable the airframe's MAVLink uplink at the ground station.
- **Bridge / fleet-wide kill-switch:** today there is **no fleet kill-switch endpoint**. The mitigation is:
  - Stop the alert-webhook receiver (revoke or rotate `WILDFIRE_WEBHOOK_SECRET`; deploy receiver-side first so existing signals fail closed).
  - Stop the bridge subprocess: `pgrep -f wildfire.py | xargs kill`.
  - This is **risk register item #5** in the threat model — the kill-switch is FUTURE work.

### 3.3 Take the bridge offline (if necessary)

If the issue is upstream of the bridge (signal forgery, schema-version downgrade, RCE in the bridge):
- Set a sentinel file Sapphire knows about: `~/.sapphire/wildfire_pause` (parallel to `~/.sapphire/hyperliquid_trading_pause` per [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md) — risk-register item to wire this in).
- Or: kill the bridge subprocess and document the downtime.
- Inform partners that pages are paused. **Silent pause is worse than disclosed pause.**

### 3.4 Notify partners

- For HIGH or CRITICAL incidents involving forged pages or a real-world drone, notify the partner FD within 1 hour by phone (not email).
- Use the contact in `docs/50-fire-dept-partnership.md` (currently CA-flavored placeholder; update at first real partnership). For Gunnison / Crested Butte the canonical numbers are in `AOR.md`.

---

## 4. Remediation

First day to first week. Goal: ship a fix, document, restore service.

### 4.1 Fix in code

- Branch off `main`: `git checkout -b incident/<short-name>`.
- Write a regression test that reproduces the incident BEFORE the fix.
- Land the fix + test in one PR.
- Tag with a CVE if the issue is in our code (file via GitHub Security Advisories; GHSA -> CVE pipeline takes a few business days).

### 4.2 Restore service

- Once the fix has landed and CI is green, redeploy the affected component(s).
- Confirm with a test signal end-to-end (synthetic mission, fixture frame, expected JSONL row, expected webhook page).
- Lift the partner-FD pause; notify them by phone.

### 4.3 Communicate

- Ship a public advisory if the issue is exploitable elsewhere.
- Ship a partner-FD email summarising what happened, what we fixed, what we changed about our process. **No PII in this email.**
- Post-mortem template below.

---

## 5. Post-mortem

Within 14 days of incident close. Run a blameless post-mortem; the goal is to fix process, not blame people.

### Template

```markdown
# Incident NNNN: <one-line summary>

## Timeline
- Detection: <UTC timestamp>
- Triage start: <UTC timestamp>
- Containment complete: <UTC timestamp>
- Remediation deployed: <UTC timestamp>
- Service restored: <UTC timestamp>
- Post-mortem published: <UTC timestamp>

## Severity
HIGH / MEDIUM / etc.

## Impact
- Affected systems: ...
- Data exposed: ...
- Partners notified: ...
- Real-world drone events: ...

## Root cause
Describe the root cause(s). Use the "five whys" pattern. Cite the code path
that allowed it.

## What went well
- ...

## What did not go well
- ...

## Action items
| ID | Action | Owner | Due |
|---|---|---|---|
| ai-1 | ... | ... | YYYY-MM-DD |

## References
- Incident log: ~/Documents/wildfire-watch-private/incident-log-NNNN.md
- Fix PR: #...
- Advisory: GHSA-... (or "n/a")
```

Save the post-mortem at `~/Documents/wildfire-watch-private/post-mortem-NNNN.md`. **Do not commit it to the public repo unless every detail is Public-tier per [`data_classification.md`](./data_classification.md).** Cross-link from the threat model risk register.

---

## 6. Partner-FD specific

If a partner fire department is the reporter, the runbook is the same plus these adjustments:

1. **Acknowledge within 15 minutes by phone.** Not email. Not Slack. Phone.
2. **Pause the bridge by default.** Silent paging from us to them while we triage is worse than no pages.
3. **Hand off a single point of contact** to them — give them the maintainer's mobile number for the duration of the incident.
4. **Provide them with a written post-incident report within 14 days.** This is the same post-mortem template, with the public-tier facts only and PII redacted.
5. **Offer to brief their leadership in person** if the incident is HIGH or CRITICAL.
6. **Document the relationship impact** in the partnership log. The trust asset (A-2 in the threat model) is the thing being protected.

---

## Cross-references

- [`threat_model_2026-05-02.md`](./threat_model_2026-05-02.md) — every incident class maps to a risk register entry.
- [`secrets_inventory.md`](./secrets_inventory.md) — secret-rotation procedures.
- [`data_classification.md`](./data_classification.md) — what tier the leaked data is in determines partner-notification scope.
- Repo-root [`SECURITY.md`](../../SECURITY.md) — public-facing reporting channel; if the incident is reported via this channel, this runbook starts with their report.
