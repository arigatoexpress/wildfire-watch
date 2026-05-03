# Data classification

Four tiers. Every data class the project handles must fit into exactly one. If you cannot place a new data class, raise it to the maintainer; do not improvise.

## Tiers at a glance

| Tier | Examples | Storage | Transmission | Retention | Access |
|---|---|---|---|---|---|
| **Public** | BOM, model card, simulator, AOR zone GeoJSON at >= 1 km^2 resolution, this README | Repo, public docs site | Plain HTTP/HTTPS, no encryption required | Indefinite | Anyone |
| **Operational** | Flight logs, signals (location-specific), partner agency contact data, GCS evidence URIs | `data/`, GCS bucket, PostGIS | TLS-only; HMAC-signed where applicable | 90 days for evidence frames; 365 days for signal log; indefinite for FD-confirmed-fire signals | Maintainer + invited collaborators |
| **Sensitive** | RPIC pilot license, insurance policy refs, signed LOAs, partner-FD signed agreements | Encrypted at rest (LUKS/FileVault); never in repo | TLS-only; encrypted email or signed PDF | Per legal retention floor (typically 7 years for insurance) | Maintainer + named delegates only |
| **Restricted** | (none today) | (reserved) | (reserved) | (reserved) | (reserved) |

---

## Public

**Definition:** data the project intentionally publishes; disclosure carries no harm.

**Examples in this repo:**
- `hardware/bom.csv` — every part on the bill of materials, including vendor and SKU.
- `ml/fire_detection/runs/v0.0.1/model_card.md` — the model card for the registered v0.0.1 artifact.
- `sim/missions/*.yaml` — simulated mission definitions. (Note: real-mission-derived YAMLs that include private property coords are NOT public — they are Operational.)
- `missions/zones/gunnison_crested_butte_corridor.geojson` at the published resolution.
- `AOR.md`, `CLAUDE.md`, `BLUE-UAS-LINEAGE.md`.

**Storage requirements:**
- Repository (public branch).
- Optional: documentation hosting; arbitrary mirror.

**Transmission requirements:**
- TLS preferred for the operator's own pages but not required for protection.

**Retention:**
- Indefinite. Public artifacts may be archived; do not delete a published model artifact even after supersession.

**Access:**
- Anyone.

**Things that LOOK public but are NOT:**
- Specific evidence frames at GCS even if signed-URL access is widely shared. **A signed URL is operational, not public.**
- A mission YAML targeted at a specific private property's quarter section.

---

## Operational

**Definition:** data needed to run the system; disclosure does not compromise safety but does compromise the partnership trust (A-2) or operator productivity.

**Examples in this repo and the operator's machines:**
- `data/wildfire_signals.jsonl` (the canonical signal sink on the operator's machine).
- `~/Code/Sapphire/data/wildfire_signals.jsonl` (the bridge's destination).
- GCS evidence frames under `gs://wildfire-watch-evidence/`.
- Flight logs from the Mavic Mini (`mavic_post_flight.py` ingest path).
- `data/sensors/` — Pi heartbeat + state-change history.
- Partner FD contact data: phone numbers, dispatch emails, on-call rotation.
- Signed URLs to evidence frames.
- The HMAC alert webhook URL itself (knowing the URL doesn't grant access without the key, but it does invite probing).

**Storage requirements:**
- **At rest on the operator's machine:** filesystem permission 0640 minimum for files containing partner contact data; FileVault on macOS / LUKS on Linux for the laptop disk; never on a thumb drive without encryption.
- **In GCS:** bucket-level IAM `Storage Object Viewer` for partner FDs only; `Storage Object Admin` for the operator only. Bucket configured private (no `allUsers`).
- **In PostGIS:** local-only, no public network exposure (per `sapphire_integration/postgis/docker-compose.yml` defaults).

**Transmission requirements:**
- TLS for any HTTP transport.
- HMAC-SHA256 signatures on the alert webhook (`ml/fire_detection/alerts.py`).
- TLS mutual auth for the TAK CoT emitter when pointed at a partner FD's TAK Server (`sapphire_integration/tak/tak_server_client.py:_send_tls`).

**Retention:**
- **Evidence frames:** 90 days. After 90 days, signal-confirmed-as-no-fire frames are deleted; FD-confirmed-fire frames are retained indefinitely (training data, Operational tier preserved).
- **Signal log:** 365 days at full fidelity, then aggregated to monthly summary (counts, false-positive rate). Confirmed-fire signals never deleted.
- **Pi heartbeat / state history:** 30 days.
- **Partner FD contact data:** retained until the partnership ends or the contact updates; review yearly.

**Access:**
- Operator (read/write everything).
- Named collaborators (read; write only on a per-table basis).
- Partner FDs: read access to signals + evidence frames involving their jurisdiction only. **No partner-FD access today; this is the design target.**

**Cross-tier flow:**
- A signal whose `recommended_action == "notify_fire_dept"` and which fires the alert webhook is operational on emit. The CoT XML emitted to the partner FD's TAK Server is operational on the wire and operational at rest in their TAK Server.
- An evidence frame uploaded to GCS is operational at upload time. The signed URL passed to the FD is operational.

---

## Sensitive

**Definition:** data whose disclosure causes legal or contractual harm to a person or to the partnership.

**Examples:**
- RPIC Part 107 certificate number.
- UAS commercial liability insurance policy reference + carrier name + coverage limits.
- Signed LOA documents between wildfire-watch and a partner FD.
- Partner FD's incident-response playbook excerpts (if shared with us under NDA).
- Email threads with FD chiefs that contain PII.

**Storage requirements:**
- **NEVER in the repository, never in `data/`.** These belong in encrypted-at-rest local storage on the operator's machine (`~/Documents/wildfire-watch-private/`, FileVault enabled) or in a secrets manager.
- For Sapphire-pattern parity, these may live alongside `~/.sapphire/secrets.env` (mode 0600 per Sapphire's pattern; see [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md)).
- Cloud storage only with a customer-managed key (CMEK) and short retention.

**Transmission requirements:**
- TLS-only.
- For documents: encrypted email (S/MIME or PGP) preferred; failing that, an encrypted PDF with a separately-shared password.
- LOA documents: signed PDFs returned over TLS; no email body interpolation.

**Retention:**
- Insurance policy refs: 7 years (typical statute of repose for liability).
- LOA documents: duration of partnership + 3 years.
- RPIC cert: as long as it's the active cert; previous certs deleted on renewal.

**Access:**
- Operator only (read/write).
- Maintainer-named delegates with explicit signed authorisation per access (no standing access).
- Never shared with collaborators or contributors without a documented sign-off.

---

## Restricted

**Definition:** reserved tier for any future data class whose disclosure would constitute a serious legal, safety, or partnership breach beyond Sensitive.

**Today this tier is empty.**

Anticipated future content (Phase 1+):
- Live partner-FD ICS dispatch logs (if we ever get push-feeds from a partner CAD system).
- Federal-funded mission data subject to FAR 52.240-1 / Sec. 1822 supply-chain rules.
- Any data subject to ITAR (currently we hold none; `BLUE-UAS-LINEAGE.md` documents the line).

When we first ingest a Restricted data class, the storage / transmission / retention / access rules become a separate dated supplement to this file, signed off by the operator.

---

## Mapping data to code paths

A quick lookup for "where does this data class live in the code?"

| Data class | Tier | Code path |
|---|---|---|
| BOM rows | Public | `hardware/bom.csv` (CI parsed by `.github/workflows/ci.yml:bom-validate`) |
| Model artifact + card | Public | `ml/fire_detection/runs/v0.0.1/` |
| `wildfire_signal` schema | Public | `sapphire_integration/wildfire_signal_schema.json` (CI metaschema validated) |
| Mission YAMLs (sim) | Public (sim) / Operational (real-flight derivative) | `sim/missions/`, `missions/` |
| Signal JSONL sink | Operational | `data/wildfire_signals.jsonl` (operator) and `~/Code/Sapphire/data/wildfire_signals.jsonl` (bridge target) |
| GCS evidence frames | Operational | `gs://wildfire-watch-evidence/` (uploaded by `ml/fire_detection/evidence.py`) |
| HMAC webhook secret | Sensitive (the secret); Operational (the URL) | env `WILDFIRE_WEBHOOK_SECRET`, `WILDFIRE_WEBHOOK_URL` |
| Telegram bot token | Sensitive | env `TELEGRAM_TOKEN` |
| Dashboard admin token | Sensitive | env `ADMIN_TOKEN` |
| Partner FD contact (email/phone) | Operational | `docs/strategy/`, `docs/50-fire-dept-partnership.md` (currently CA-flavored placeholder; AOR.md flags this) |
| Pilot Part 107 cert / insurance | Sensitive | NEVER in repo; operator-side `~/Documents/wildfire-watch-private/` |
| Drone position telemetry | Operational | MAVLink stream + signal `coords` field |
| Drone-emit per-drone signing key | Sensitive (Phase 1, FUTURE) | not in repo; per-airframe KMS |

---

## Cross-references

- [`secrets_inventory.md`](./secrets_inventory.md) — the operational mechanics of every Sensitive secret.
- [`threat_model_2026-05-02.md`](./threat_model_2026-05-02.md) Section 1 (Assets) — the why behind these tiers.
- [`incident_response.md`](./incident_response.md) — what to do when a tier is breached.
- Sapphire pattern: [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md) defines the operator's `~/.sapphire/secrets.env` mode-0600 baseline; we mirror it for any Sensitive secret on the same machine.
