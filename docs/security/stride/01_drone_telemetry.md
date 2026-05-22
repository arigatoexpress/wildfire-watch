# STRIDE 01 — Drone telemetry

**Surface:** the on-drone GPS / IMU / video / MAVLink streams + the link back to the ground station.

**Phase 0 reality:** Mavic Mini 1 / 2, post-flight SD-card processing on the operator's Mac via `ml/fire_detection/mavic_post_flight.py`. No live telemetry uplink.

**Phase 1 target:** Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super + Doodle Labs Helix Mesh Rider (per [`BLUE-UAS-LINEAGE.md`](../../../BLUE-UAS-LINEAGE.md) Sec. 5). Live MAVLink + companion-compute Inference + signal emit on detection.

**Trust boundary:** B-1 (drone -> ground station) per [`../threat_model_2026-05-02.md`](../threat_model_2026-05-02.md) Section 2.

| STRIDE | Threat | Severity | Mitigation | Code path |
|---|---|---|---|---|
| **S** Spoofing | **GPS spoofing** — adversary broadcasts a false GNSS solution near the drone (RTL-SDR + GNSS-Sim, $300 hardware). Drone reports position inside the AOR while physically elsewhere. Signal `coords` field is wrong. FD pages a wrong location. | **HIGH** | (1) Inertial-consistency discriminator: VO+IMU velocity vs GPS-reported velocity; > N*sigma disagreement marks GPS UNTRUSTED. (2) Phase 1: multi-band L1/L5 receiver. (3) Phase 1: complementary filter fuses VO + TRN + IMU. | `sim/perception/jamming.py:JammingScenario._discriminate` (modelled); `sim/perception/fusion.py` (complementary filter); production gating FUTURE for Phase 1 |
| **S** Spoofing | **Drone-id spoofing** — an attacker emits signals with `drone_id=wfw-unit01` from off-fleet hardware. | HIGH | Schema regex pattern `^wfw-[a-z0-9]{4,16}$` enforces format. HMAC on the alert webhook (S-1) authenticates the channel. **FUTURE: per-drone Ed25519 signing key** (Phase 1, threat-model section 5.3). | `sapphire_integration/wildfire_signal_schema.json` (`drone_id.pattern`); `ml/fire_detection/alerts.py:_sign_body` (channel auth); per-drone keys FUTURE |
| **S** Spoofing | **Remote-ID spoofing** — adversary broadcasts a forged Remote ID claiming to be us. | LOW | Ecosystem-level problem. We document and accept; per `BLUE-UAS-LINEAGE.md` Sec. 7 the pingRID hardware is uAvionix and FAA-cooperating. | `hardware/bom.csv` row `remote_id`; documented in threat-model section 5.5 |
| **T** Tampering | **MITM on telemetry uplink** — adversary on the same RF medium injects MAVLink commands or alters telemetry. | HIGH | Phase 0: link is the operator's controller; physical custody. Phase 1: Doodle Labs Helix Mesh Rider provides AES-256 link encryption (per [`BLUE-UAS-LINEAGE.md`](../../../BLUE-UAS-LINEAGE.md) Sec. 5); MAVLink2 signing (FUTURE) for command-level auth. | Phase 1 link layer; MAVLink2 signing FUTURE |
| **T** Tampering | **Tampered signal at the webhook hop** — adversary alters body in transit. | HIGH | HMAC-SHA256 over `timestamp + "." + body` via `_sign_body`; receiver-side verification. Replay protection via the timestamp + idempotency on `signal_id`. | `ml/fire_detection/alerts.py:_sign_body` (PR #2, MERGED); `signal_id` UUIDv4 in schema |
| **T** Tampering | **SD-card swap on the Mavic** — adversary substitutes an SD card with crafted MP4 + flight-log files between flight and post-process. | MEDIUM | `mavic_post_flight.py` parses files as data only (no exec); JSON-schema validation on the resulting signal; no path-traversal in the URI generator. | `ml/fire_detection/mavic_post_flight.py`; signal schema validates output |
| **R** Repudiation | **Drone claims it did not emit a particular signal** — important for FD-side accountability. | MEDIUM today, HIGH on partnership scale | Per-emit `signal_id` UUIDv4 + idempotency in the bridge. **Gap:** today the HMAC protects the channel, not the payload — a shared key cannot prove which drone emitted. **FUTURE: per-drone Ed25519 (S-7).** | `sapphire_integration/wildfire_signal_schema.json` (`signal_id`); per-drone keypair FUTURE |
| **R** Repudiation | **Operator alters the JSONL after the fact** to remove an embarrassing emit. | MEDIUM | JSONL is append-only by convention. **FUTURE: rolling hash chain or merkle root** (Phase 1+, threat-model 5.3). | none today |
| **I** Information disclosure | **GCS evidence URI exposes private location** — frame URIs include exact emit coords (in metadata) + GPS time. A leaked URL reveals where (and when) someone was. | MEDIUM | GCS bucket private (`allUsers` denied); access via signed URL with `signed_url_expires_in`. Bucket configured no-public per [`data_classification.md`](../data_classification.md) Operational tier. | `ml/fire_detection/evidence.py:upload_evidence` (PR #7, MERGED) |
| **I** Information disclosure | **Telemetry channel passively recorded** — adversary sniffs the link. | MEDIUM | Phase 0 risk minimal (controller + operator physical proximity). Phase 1: Helix Mesh Rider AES-256 link encryption. | Phase 1 link layer |
| **D** Denial of service | **RF jamming of the telemetry uplink** — drone loses link. | HIGH (in flight, not in code) | Drone autonomy: on link loss, default `recommended_action=rtl`. The fail-closed default is the same fail-closed posture Sapphire's Hyperliquid executor uses (`hyperliquid_trading_pause` sentinel). FUTURE: ArduPilot RTL-on-link-loss behaviour to be wired in Phase 1 missions. | Phase 1 mission YAML; documented in threat-model 5.5 |
| **D** Denial of service | **Malicious drone floods the bridge** — buggy or hijacked drone sends infinite signals. | MEDIUM | **Risk register #5.** Token-bucket rate-limit on `drone_id` in the bridge — FUTURE Phase 0.5. | none today; risk register #5 |
| **D** Denial of service | **GPS jamming forces RTL or loss-of-mission** — wildfire goes undetected. | MEDIUM | Inertial-consistency fusion enables continued operation in degraded GPS for short windows; mission YAML FUTURE specifies `gps_outage_max_s`. | `sim/perception/jamming.py` models the threat; production hardening FUTURE |
| **E** Elevation of privilege | **Drone firmware compromise** — adversary writes their own firmware to the flight controller. | HIGH | Phase 0 (Mavic): out-of-scope; vendor-controlled. Phase 1: **Cube Orange+ secure-boot path** ([CubePilot US Defence docs](https://docs.cubepilot.org/user-guides/us-defence)); ArduPilot hash-pinned releases; airframe signing key in HSM. | Phase 1 HW boot chain; FUTURE wiring |
| **E** Elevation of privilege | **Companion-compute (Jetson) exploited via crafted RGB/thermal frame** that triggers a CV-stack RCE in `ultralytics` / `opencv`. | MEDIUM | Frames decoded via Pillow/opencv only on the operator's Mac in Phase 0; FUTURE on Jetson. CV libraries are widely-audited but have CVE history; Dependabot + SBOM tracking are the structural mitigations. | `pyproject.toml` `[ml]` extra; SBOM at `docs/sbom/` |

## Dependencies on other surfaces

- The signal that ultimately gets emitted from this surface is processed by [`02_signal_emit_pipeline.md`](./02_signal_emit_pipeline.md). Spoofed `coords` from this surface become a forged signal in that one.
- The bridge that receives the signal is [`04_sapphire_bridge.md`](./04_sapphire_bridge.md). HMAC verification is the seam.

## Open items

- [ ] Implement per-drone Ed25519 signing for non-repudiation (Phase 1; risk register #2).
- [ ] Wire ArduPilot RTL-on-link-loss behaviour (Phase 1 mission YAMLs).
- [ ] Token-bucket rate-limit on the bridge (Phase 0.5; risk register #5).
- [ ] Cube Orange+ secure-boot path documentation in `firmware/` (Phase 1).
