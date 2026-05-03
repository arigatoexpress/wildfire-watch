# Secrets inventory

Every secret the project uses. If a new secret appears in code, it goes here on the same PR. If a secret is in this list, **it is never in the repository** — only its name and metadata.

## Conventions

- **Storage** is the canonical location. The Sapphire-host pattern is `~/.sapphire/secrets.env` mode 0600 (see [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md)). For wildfire-watch on the same machine we mirror that pattern at `~/.wildfire-watch/secrets.env` mode 0600. CI uses GitHub Actions secrets.
- **Rotation cadence** is a target. Anything HIGH-severity should be rotated more aggressively if there is any suspicion of compromise.
- **Access** is the minimum-privilege list. Adding a new entry requires the maintainer's explicit sign-off.

---

## Operational secrets (in use today)

### S-1 `WILDFIRE_WEBHOOK_SECRET`

The shared HMAC-SHA256 secret signing the alert webhook envelope.

| Property | Value |
|---|---|
| Used by | `ml/fire_detection/alerts.py:_sign_body` (signer); receiver-side bridge (verifier) |
| Format | random 32+ bytes, base64-encoded; minimum 256 bits of entropy |
| Storage | operator-side `~/.wildfire-watch/secrets.env` (mode 0600), GitHub Actions secret for CI integration tests |
| Rotation cadence | 90 days, or immediately on suspected compromise |
| Severity if disclosed | HIGH — attacker can forge a valid webhook envelope |
| Access | operator (read/write); CI (read in integration job only) |
| Rotation procedure | (1) generate new secret on operator machine; (2) deploy to receiver-side first; (3) deploy to drone-side; (4) confirm next signal verifies; (5) revoke old secret |

### S-2 `TELEGRAM_TOKEN`

Bot token for the operator-only Telegram alerts. Optional — the alert pipeline silently no-ops if unset.

| Property | Value |
|---|---|
| Used by | `ml/fire_detection/alerts.py:post_telegram` |
| Format | Telegram BotFather token (`<int>:<base64-ish>`) |
| Storage | `~/.wildfire-watch/secrets.env` (operator only) |
| Rotation cadence | 180 days; immediately on suspected compromise |
| Severity if disclosed | MEDIUM — attacker can post messages as the bot; cannot forge signals |
| Access | operator only |
| Rotation procedure | revoke via BotFather, generate new, update env |

### S-3 `TELEGRAM_CHAT_ID`

The chat ID the bot pages. Not sensitive on its own (it does not authenticate the bot), but disclosure tells an attacker WHERE pages go.

| Property | Value |
|---|---|
| Used by | `ml/fire_detection/alerts.py:post_telegram` |
| Format | numeric Telegram chat ID |
| Storage | `~/.wildfire-watch/secrets.env` |
| Rotation cadence | n/a (rotate by changing chat) |
| Severity if disclosed | LOW |
| Access | operator |

### S-4 `ADMIN_TOKEN`

Bearer for the dashboard at `frontend/app.py`.

| Property | Value |
|---|---|
| Used by | `frontend/app.py:requires_admin` |
| Format | random 32+ bytes, base64-encoded |
| Storage | `~/.wildfire-watch/secrets.env` (operator); future per-named-collaborator scheme on Phase 1 |
| Rotation cadence | 90 days |
| Severity if disclosed | HIGH — full read access to live signals and dashboards |
| Access | operator and any FD partner who has been granted dashboard access (Phase 1) |
| Rotation procedure | regenerate, deploy to dashboard env, distribute new token via TLS-only channel |

### S-5 GCS bucket signed-URL signer

The service-account JSON key that signs URLs for `gs://wildfire-watch-evidence/...`. Used by `ml/fire_detection/evidence.py`.

| Property | Value |
|---|---|
| Used by | `ml/fire_detection/evidence.py:upload_evidence` (uses `google-cloud-storage` library; the library reads `GOOGLE_APPLICATION_CREDENTIALS`) |
| Format | service-account JSON file |
| Storage | `~/.wildfire-watch/wfw-evidence-uploader.json` (mode 0600); never in repo |
| Rotation cadence | 90 days; immediately on suspected compromise; rotate on operator-machine change |
| Severity if disclosed | HIGH — attacker can read every evidence frame, generate signed URLs to unrelated parties, fill the bucket (DoS via bill) |
| Access | operator only |
| Rotation procedure | (1) create new key in GCP IAM; (2) update `GOOGLE_APPLICATION_CREDENTIALS`; (3) confirm next upload signs ok; (4) delete old key from IAM |

---

## Operational secrets (FUTURE — Phase 0.5 / Phase 1)

### S-6 ATAK / TAK Server client cert + key + CA pin

Mutual TLS to a partner FD's TAK Server. Today the code path exists (`sapphire_integration/tak/tak_server_client.py:_send_tls`) but the cert files are not yet provisioned.

| Property | Value |
|---|---|
| Used by | `sapphire_integration/tak/tak_server_client.py:_send_tls` (`tls_cafile`, `tls_certfile`, `tls_keyfile` constructor args) |
| Format | PEM x509 cert + PEM RSA key + PEM CA |
| Storage | per-partner-FD: `~/.wildfire-watch/tak/{fd_name}/{client.pem,client.key,ca.pem}` (mode 0600 on key) |
| Rotation cadence | per partner FD's policy; default 365 days |
| Severity if disclosed | HIGH — attacker can post to FD TAK as us, including forged signal pages |
| Access | operator + named drone airframes (Phase 1) |
| Rotation procedure | partner-FD-driven: their CA reissues the client cert, we deploy |

### S-7 Per-drone Ed25519 signing key (Phase 1)

For non-repudiation of signal envelopes (threat model section 5.3).

| Property | Value |
|---|---|
| Used by | `ml/fire_detection/infer.build_signal()` (FUTURE; Phase 1) |
| Format | Ed25519 private key |
| Storage | per-airframe HSM (TPM on the Jetson, or Cube Orange+ secure element) |
| Rotation cadence | per-airframe lifecycle; new key on airframe replacement |
| Severity if disclosed | HIGH — attacker can forge a non-repudiable signal claiming to be from this airframe |
| Access | the airframe only; key never leaves device |

### S-8 Sapphire <-> wildfire-watch shared secret

If we move the bridge from a subprocess fork to an HTTP shim (the future-direction noted in `CLAUDE.md`), we'll need a shared secret. Today: not used.

| Property | Value |
|---|---|
| Used by | (FUTURE) HTTP bridge between wildfire-watch and Sapphire |
| Format | TBD; HMAC pattern recommended |
| Storage | `~/.wildfire-watch/secrets.env` AND `~/.sapphire/secrets.env`; same value in both files |
| Rotation cadence | 90 days |
| Severity if disclosed | HIGH |
| Access | operator |

---

## CI / GitHub-side secrets

### S-9 GitHub Actions secrets

GitHub Actions secrets are scoped per repository. Currently the workflow at `.github/workflows/ci.yml` does NOT consume any secrets — every step runs against checked-in fixtures and synthetic data. This is intentional: the public CI surface should not need any secret to pass.

If any future job needs a secret (e.g. an integration test against a real GCS bucket), it goes through GitHub Actions secrets and is documented here on the same PR.

---

## Anti-patterns to avoid

- **Never commit a `.env` file.** The `.gitignore` includes `.env*` patterns; verify before each commit.
- **Never log a secret.** `_sign_body` in `alerts.py` is parameterised on `secret`; no logging path includes that argument. Verify on any change.
- **Never embed a secret in a webhook URL.** A query-parameter token is operational data and ends up in server logs and referrer headers.
- **Never commit the HMAC signature itself** — it leaks information about the underlying secret in combination with replays.
- **Never share a secret over Slack / iMessage.** Use a TLS-only channel (encrypted email, signed PDF, or 1Password sharing).
- **Never reuse a secret across environments.** Dev, integration, prod each get their own.

---

## Cross-references

- [`data_classification.md`](./data_classification.md) — Sensitive tier handling.
- [`incident_response.md`](./incident_response.md) — secret-rotation runbook on suspected compromise.
- [`threat_model_2026-05-02.md`](./threat_model_2026-05-02.md) — section 1.10 (operator credentials as asset A-10).
- Sapphire pattern: [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md) — `~/.sapphire/secrets.env` mode 0600.
