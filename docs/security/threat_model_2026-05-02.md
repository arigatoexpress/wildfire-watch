# wildfire-watch STRIDE threat model

**Date:** 2026-05-02
**Version:** 1.0 (first formal threat model)
**Scope:** the `arigatoexpress/wildfire-watch` repo at the commit this document lands on, plus the bridge contract to `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` (PR #551, MERGED 2026-05-02).
**Methodology:** STRIDE per surface (Microsoft, [STRIDE](https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats)).

This is the master document. Per-surface STRIDE tables live under [`stride/`](./stride/). Read this first; then drill into a surface.

---

## 1. Assets

The things we are protecting, in priority order:

| ID | Asset | Why it matters |
|---|---|---|
| A-1 | **Signal-pipeline integrity** — every `wildfire_signal` JSON object emitted by the system | A forged or tampered signal can either trigger a false fire-department page (cry wolf) or suppress a real one. Both kill the partnership. |
| A-2 | **Partner FD trust** | The FD is the customer. If they ever stop trusting our pages, we are out of business; "trust" is in the threat model directly because it is the asset most easily destroyed and hardest to rebuild. |
| A-3 | **AOR coordinates + flight plans** | The Gunnison-Crested Butte AOR (`AOR.md`, `missions/zones/gunnison_crested_butte_corridor.geojson`) is public at zone resolution but **specific evidence-frame coords + per-mission waypoints are operational**. They reveal where a private property owner reports anomalies, which is sensitive to that property owner. |
| A-4 | **Evidence frames + thermal imagery** | Evidence frames at GCS URIs (pattern `gs://wildfire-watch-evidence/{zone_id}/{date}/{signal_id}/frame_*.{jpg,png,tiff}`) can include private property, person identifiable subjects, or wildlife (deer/elk during rut). Disclosure can violate Colorado Revised Statute 33-14.5 if it shows wildlife harassment. |
| A-5 | **RPIC pilot identity** + insurance refs | Pilot license number (Part 107 cert), insurance policy reference, signed LOA documents — sensitive PII with downstream regulatory exposure. |
| A-6 | **Drone in flight** — physical asset, ~$3.4k Phase 1 system | The drone itself can be jammed, spoofed, hijacked, or crashed. Loss of airframe is a $3.4k event; loss of an airframe **into a wildfire scene** is a public-safety event. |
| A-7 | **Sapphire bridge contract** | The subprocess fork into `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` is privileged: it writes to Sapphire's signal log and emits `wildfire.signal.detected` event-bus envelopes. Trust boundary lives at this hop. |
| A-8 | **Model artifacts** at `ml/fire_detection/runs/v0.0.1/` | A substituted model can suppress real fires (denial of detection) or generate plausibly-classified false positives. The model is the single most valuable supply-chain target. |
| A-9 | **Repository integrity** — code, schema, hardware BOM | Tampering with the schema, the HMAC validator, or the BOM is the simplest way to compromise everything downstream. |
| A-10 | **Operator-only credentials** — `ADMIN_TOKEN` for the dashboard, `WILDFIRE_WEBHOOK_SECRET`, GCS signing key | Loss of these unlocks the bridge or the dashboard from anywhere. |

---

## 2. Trust boundaries

A trust boundary is a place where a request crosses from an untrusted to a (more) trusted domain. Each boundary needs an authenticator, an authoriser, and an integrity check.

```
   [drone / RPIC]                           untrusted-physical
        |
        | MAVLink / serial / Wi-Fi (Phase 0); Helix Mesh Rider (Phase 1)
        v
   [ground station / RPIC laptop]           trusted-on-prem
        |
        | local file sink (data/wildfire_signals.jsonl)
        | + HMAC-signed webhook POST  ----------------------+
        v                                                   |
   [sapphire bridge subprocess]             trusted-on-prem |
        |                                                   |
        | event-bus envelope                                |
        v                                                   |
   [sapphire data/wildfire_signals.jsonl]   trusted-on-prem |
                                                            |
   [partner FD endpoint] <--- TAK CoT (TLS) <---------------+
                                            untrusted-network-with-pinned-cert
   [public dashboard / web viewer]          untrusted-network
```

Boundaries (in order, with the enforcing code path):

| ID | Boundary | Authenticator | Implementing code |
|---|---|---|---|
| B-1 | drone -> ground station | RPIC physical custody (Phase 0); MAVLink + airframe-paired keys (Phase 1, FUTURE) | none today; see Phase 1 plan in `BLUE-UAS-LINEAGE.md` Sec. 5 |
| B-2 | ground station -> alert webhook | HMAC-SHA256 over `timestamp + "." + body` | `ml/fire_detection/alerts.py:_sign_body` (PR #2, MERGED) |
| B-3 | ground station -> sapphire bridge | OS-level subprocess; file-system permissions on `~/Code/Sapphire/data/wildfire_signals.jsonl` | `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` (PR #551, MERGED) |
| B-4 | sapphire bridge -> idempotency | per-signal UUIDv4 in `signal_id` | schema requires `signal_id` (uuid format); bridge dedupes by it |
| B-5 | bridge -> partner FD over TAK | TLS mutual auth with cafile + certfile + keyfile | `sapphire_integration/tak/tak_server_client.py:_send_tls` (TLS code path implemented; CA pinning callback documented but not yet wired) |
| B-6 | dashboard browser -> dashboard backend | `ADMIN_TOKEN` env var checked by `frontend/app.py:requires_admin` | `frontend/app.py:requires_admin` |
| B-7 | evidence frame at GCS bucket -> partner FD viewer | GCS signed URL with `signed_url_expires_in` seconds | `ml/fire_detection/evidence.py:upload_evidence` (PR #7, MERGED) |
| B-8 | repo `main` -> CI -> deployment | GitHub branch protection + ruff + pytest + jsonschema metaschema | `.github/workflows/ci.yml` |

---

## 3. Threat actors

We model 7 plausible actors. Capability scaled `LOW / MED / HIGH`; intent scaled to wildfire-watch outcomes.

| ID | Actor | Capability | Intent | Most-likely surface |
|---|---|---|---|---|
| TA-1 | **Script kiddie / opportunist** | LOW — scans GitHub for exposed `.env`, leaked API keys, default-cred dashboards | Low — bragging rights, crypto-mining a Pi | Dashboard `ADMIN_TOKEN`, leaked GCS HMAC key in commit history, `frontend/app.py` exposed publicly |
| TA-2 | **Business competitor** | MED — funded, can hire a contractor; no zero-days but solid OSINT | Med — discredit our signal accuracy in front of CBFPD/GCFPD; copy our model | Forge a wildfire_signal that pages CBFPD on a calm day; download model artifacts |
| TA-3 | **Supply-chain attacker** | HIGH — can submit a typo-squat package to PyPI, file a malicious GitHub Action update, ship a counterfeit chip | Med — broad, low-targeted; we are collateral on a wider campaign | `pyproject.toml` deps; GitHub Action versions; `ultralytics` (heavy CV stack); model weights in `ml/fire_detection/runs/v*/` |
| TA-4 | **GPS spoofer** | MED — $300 RTL-SDR + GNSS-Sim software is publicly available; physical proximity required | Low — usually opportunistic vandalism, occasionally targeted (poaching, illegal harvest hiding from drone overflight) | Drone GPS during patrol; spoofed `coords` field in emitted signal |
| TA-5 | **ITAR-restricted-data harvester** | MED-HIGH — nation-state-aligned actor scraping repos for defense-adjacent tech | High — collect Phase 1 BOM details, model architecture, sensor-fusion algorithms | Repo + model artifacts + `BLUE-UAS-LINEAGE.md` itself (which they already have, by design) |
| TA-6 | **Disgruntled volunteer / pilot** | LOW-MED — has legitimate creds at some point, knows our processes | Med — false-page CBFPD; leak partner contact list; dox the operator | Dashboard `ADMIN_TOKEN`, `~/.sapphire/secrets.env` if they had operator-laptop access; partner FD contact data |
| TA-7 | **Privacy advocate / litigant** | LOW — no offensive capability; FOIA, civil discovery, public-records requests | Med — extract evidence frames showing private property; force a Colorado Revised Statute 33-14.5 wildlife-harassment case | Evidence-frame retention; partner FD-side disclosure; FOIA against state wildlife agency |

---

## 4. Per-surface STRIDE index

Each surface is tabulated in a per-file analysis under [`stride/`](./stride/). The table below summarises **the single most-critical threat per surface** so the operator can scan-read priorities.

| # | Surface | Top threat | Severity | Status |
|---|---|---|---|---|
| 01 | [Drone telemetry](./stride/01_drone_telemetry.md) | GPS spoofing (S) places a real signal at a false location, paging FD on a wrong coordinate | HIGH | Detector implemented (`sim/perception/jamming.py`), production gating FUTURE |
| 02 | [Signal-emit pipeline](./stride/02_signal_emit_pipeline.md) | Schema-version downgrade attack (T) bypasses fields added in `v1.0.0` | HIGH | `schema_version` is `const: "1.0.0"` in JSON Schema; bridge rejects on mismatch FUTURE |
| 03 | [TAK CoT emitter](./stride/03_tak_emitter.md) | Multicast amplification (D) when the operator misconfigures `mcast://` to a routable group | MEDIUM | Documented; `_send_udp_multicast` sets `IP_MULTICAST_TTL=2` to cap blast radius |
| 04 | [Sapphire bridge](./stride/04_sapphire_bridge.md) | Subprocess argv injection (E) if a maliciously crafted signal field is shell-interpolated | HIGH | Bridge invoked with `subprocess.run([...], shell=False)`; argv is structured. **Repo grep verified.** |
| 05 | [Web viewer / dashboard](./stride/05_web_viewer.md) | XSS via signal `signal_subtype` rendered into the dashboard timeline (I) | HIGH | Jinja2 autoescape on; explicit `\|safe` filter audit FUTURE |
| 06 | [PostGIS persistence](./stride/06_postgis_persistence.md) | SQL injection via parameter interpolation (T/I) in `ingest.py` | HIGH | psycopg uses parametrised queries; **repo grep verified** no f-string `INSERT` |
| 07 | [Ground station](./stride/07_ground_station.md) | Untrusted Mavic SD card mounted on the operator's Mac (T/E) — autorun / filesystem CVEs | MEDIUM | macOS Gatekeeper + `mavic_post_flight.py` parses files as data only; no exec |

---

## 5. Cross-cutting threats

Threats that span multiple surfaces and are not naturally scoped to one STRIDE row.

### 5.1 Supply chain (TA-3)

- The `pyproject.toml` runtime deps are 4 packages (`pyyaml`, `flask`, `requests`, `jsonschema`). The `[ml]` extra adds `ultralytics`, `opencv-python-headless`, `numpy`, `Pillow` — a much larger surface. The `[mavlink]` extra adds `pymavlink`, `pyserial`. The `[gcs]` extra adds `google-cloud-storage`.
- **Mitigations in place:**
  - Direct deps only (no transitive-only direct usage).
  - CI installs from `pyproject.toml` (no separate `requirements.txt` to drift).
  - SBOM regenerated on every release at [`../sbom/wildfire_watch_v0_0_1_sbom.cdx.json`](../sbom/wildfire_watch_v0_0_1_sbom.cdx.json).
- **Mitigations FUTURE:**
  - Pin to hash via `pip-compile --generate-hashes` (Phase 0.5).
  - Sign the model artifact with sigstore (Phase 0.5).
  - Dependabot alerts enabled at the org level (Phase 0).

### 5.2 Geofence escape (TA-1, TA-6)

A drone autonomously crossing into West Elk Wilderness violates 36 CFR 261.16 and produces an evidence frame whose coordinates are inside a hard no-fly zone. This is both a public-safety and a regulatory event. The mitigation lives in `sim/mission.py` (geofence inclusion + Phase 0.5 exclusion polygons) plus `geofence_status.in_authorized_zone` in the schema. Today's geofence model supports inclusion only; **exclusion-polygon support is required by Phase 0.5** and is the same change required to honour `AOR.md` open question 3 (wilderness-edge drift).

### 5.3 Repudiation as a class

We need every signal to be non-repudiable: the drone cannot later claim it did not emit. The current chain is:
- `signal_id` UUIDv4 generated on the drone at emit time.
- `drone_id` regex-validated by the schema.
- `timestamp` ISO 8601 UTC, GPS-disciplined.
- HMAC-SHA256 signature on the alert webhook ([`alerts.py:_sign_body`](../../ml/fire_detection/alerts.py)).
- Bridge writes to an append-only JSONL with idempotency on `signal_id`.

What is missing for true non-repudiation:
- **Signed signal envelopes** — today the HMAC protects the *channel* between drone and webhook. A drone can still deny emitting a particular signal if its key is shared. **FUTURE: per-drone Ed25519 keypair, signed signal payload.** (Phase 1.)
- **Append-only ledger with hash chain** — JSONL is append-only by convention but not by enforcement. **FUTURE: rolling hash-chain or merkle root.** (Phase 1+.)

### 5.4 Privacy of evidence frames (TA-7)

Evidence frames can contain identifiable persons or private property. Today they sit at `gs://wildfire-watch-evidence/...` behind a GCS signed URL with `signed_url_expires_in`. Two gaps:
- **No retention schedule** — frames live forever. Privacy laws (CCPA, GDPR if a partner is EU-affiliated) require retention rationale. `data_classification.md` carries the policy; the implementation is a Phase 0.5 cron.
- **No on-frame PII redaction** — license plates, faces. The detector does not blur. **FUTURE: a redaction pass before upload** (Phase 1).

### 5.5 RF / GNSS environment

The Gunnison AOR sees genuine multi-path GPS error and the simulator already models GPS spoofing (`sim/perception/jamming.py`). What it does not model:
- **Adversarial RF jamming of telemetry uplink** (the SiK V3 915 MHz radio in Phase 1, the Wi-Fi link in Phase 0). A jammer sees the link drop; the drone behaviour on link loss matters (RTL? Loiter? Continue?). **FUTURE: deliberate link-loss test, with `recommended_action=rtl` as the default.**
- **Adversarial Remote ID spoofing** — pingRID broadcasts our drone's identity in cleartext to the FAA-mandated standard. An adversary cannot stop the broadcast but **can** broadcast a forged Remote ID claiming to be us. This is an ecosystem-level problem; document and accept.

---

## 6. Risk register (top 10 unmitigated)

Every row is a real possible threat the codebase faces today; no invented findings.

| # | Risk | Severity | Surface | Owner action |
|---|---|---|---|---|
| 1 | **Schema-downgrade attack on the Sapphire bridge subprocess** — a malicious signal omitting `schema_version` or sending an older const value could bypass field-level checks added in v1.0.0 | HIGH | 02, 04 | Add explicit `schema_version == "1.0.0"` enforcement on bridge ingest BEFORE jsonschema validation. The bridge currently relies on `jsonschema` + the `const` constraint to reject; verify the bridge actually fails closed if `schema_version` is missing entirely (jsonschema does enforce required, but explicit defense-in-depth wanted). |
| 2 | **Per-drone HMAC key reuse** — `WILDFIRE_WEBHOOK_SECRET` is one secret for the whole fleet | HIGH | 01, 02 | Move to per-drone keys (Phase 1, requires fleet ops). Until then, document rotation cadence (90 days) and emit on rotation. |
| 3 | **No geofence exclusion-polygon support** — wilderness boundaries enforced by docs only, not by code | HIGH | 01, 07 | Phase 0.5 follow-up. Same change closes AOR.md open question 3. |
| 4 | **GCS evidence retention is unbounded** — privacy + cost exposure | MEDIUM | 02, 07 | 90-day retention policy via GCS lifecycle rule (Phase 0). |
| 5 | **No per-drone rate-limit on signal ingest** — a single misbehaving drone (jammed sensor, infinite-loop bug, hijacked) can flood the bridge | MEDIUM | 02, 04 | Token-bucket on `drone_id` in the bridge (Phase 0.5). |
| 6 | **TLS cert pinning documented but not implemented** — `tak_server_client.py` does cert-of-CA verification but not pin-to-fingerprint | MEDIUM | 03 | Implement at the moment we point at the first real partner FD's TAK Server. |
| 7 | **No SBOM signing** — the SBOM at `docs/sbom/...cdx.json` is unsigned | MEDIUM | cross-cutting | Sign with sigstore on tag (Phase 0.5). |
| 8 | **Mavic SD-card mount on operator Mac** — opportunistic FS exploit, no sandbox | MEDIUM | 07 | macOS Gatekeeper + a documented `read-only` mount in PHASE_0_RUNBOOK.md is the practical mitigation; sandbox in a VM (Phase 1). |
| 9 | **Dashboard `ADMIN_TOKEN` is a single shared bearer** — no per-user audit trail | MEDIUM | 05 | Phase 1: replace with OIDC + a real IdP. |
| 10 | **No abuse-of-service runbook for partner FDs** — if CBFPD/GCFPD report receiving a forged page, today there is no documented kill-switch | MEDIUM | cross-cutting | Add to [`incident_response.md`](./incident_response.md) — done in this PR. |

---

## 7. Out-of-scope (intentionally)

Items outside this threat model. They are real concerns but are owned elsewhere or are deferred.

- **Sapphire's overall posture.** Owned by Sapphire; see [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md) (private). We assume Sapphire's `~/.sapphire/secrets.env` is mode 0600 per its own threat model.
- **Hermes-agent operator skill.** The future `wildfire-alert` skill (separate PR to `NousResearch/hermes-agent`) is a separate threat surface.
- **The Mavic Mini's own firmware.** DJI is a covered foreign entity per Sec. 1822; Phase 0 is hobbyist-only. Phase 0 -> Phase 1 transition closes this surface (per `BLUE-UAS-LINEAGE.md` Sec. 7 row 7).
- **Insurance and liability.** Tracked separately as `AOR.md` open question 1.

---

## 8. Maintenance

- This document is dated. On material revision, copy to a new dated filename and link from [`./README.md`](./README.md). Old versions stay in tree.
- The list of trust boundaries is reviewed every time a new code path crosses one (new integration, new dep, new external endpoint).
- The risk register is reviewed on every closed-out HIGH or CRITICAL issue.
