# Security Policy

This is the GitHub-native security policy for **wildfire-watch**. The project ships civilian wildfire-detection drones, AOR coordinates, evidence frames, and a Sapphire bridge. Anything that affects the integrity of a signal, the privacy of an evidence frame, the safety of a drone in flight, or the trust an FD partner places in our pages is a security concern. Take vulnerabilities seriously even when the codebase looks small.

## Reporting a vulnerability

Three reporting channels, in priority order:

1. **GitHub Security Advisories (preferred)** — open a private advisory at
   https://github.com/arigatoexpress/wildfire-watch/security/advisories/new
   This is the canonical channel. It is private to maintainers; the advisory becomes public only at disclosure time.
2. **Email** — `security@wildfire-watch.dev` (placeholder; this alias forwards to the maintainer's primary mailbox until a dedicated team exists). Use this channel if GitHub is unavailable or if the report is highly sensitive.
3. **Private GitHub issue** — open an issue in the repository with the prefix `[SECURITY]` and the body marked confidential. This channel is the lowest-trust of the three; do not include exploit details until a maintainer has acknowledged and you have a private channel.

When reporting, include:
- A description of the vulnerability (what it is, what it lets the attacker do).
- The version / commit SHA you tested against.
- Reproduction steps. If a PoC is risky to share publicly, share it via GitHub Security Advisories or email rather than an issue.
- Your assessment of severity (CVSS v3.1 score is welcome but not required).
- Whether you would like to be credited.

### Response SLA

| Stage | Target |
|---|---|
| Acknowledge receipt | < 72 hours |
| Triage and severity assessment | < 5 business days |
| Fix in `main` for HIGH / CRITICAL | < 30 days |
| Fix in `main` for MEDIUM | < 90 days |
| Public advisory + CVE | At fix release |

These are targets, not guarantees. The project is currently maintained part-time by a single primary author. Expect best-effort within the stated windows.

## Supported versions

| Version | Supported |
|---|---|
| `main` (rolling) | Yes — all security fixes land here first |
| Model `wfw-fire-heuristic-v0.0.1` | Yes — first registered model artifact |
| Schema `wildfire_signal v1.0.0` | Yes — canonical signal contract |
| Anything pre-`main`-tagged | No |

The project is pre-1.0. Until a tagged release exists, only `main` and the published artifacts above are supported. Forks are unsupported by this policy; downstream maintainers are responsible for their own security posture.

## Responsible disclosure

We ask reporters not to publicly disclose a vulnerability until either (a) a fix has shipped to `main`, (b) we have communicated that we will not fix and explained why, or (c) **90 days** have passed from the date of acknowledgement, whichever comes first. The 90-day window is a hard ceiling, not a maintainer veto on legitimate disclosure.

If a vulnerability is being actively exploited in the wild, we will publish a partial advisory and coordinate disclosure with affected users (including any partner fire department that has integrated with us) on an accelerated timeline. Public-safety integrations are treated as critical.

## Scope

### In scope

- The `arigatoexpress/wildfire-watch` repository (this repo).
- The `wildfire_signal` schema at `sapphire_integration/wildfire_signal_schema.json` — schema bypasses, schema-version downgrades, JSON-injection that survives the schema gate.
- The HMAC-signed alert webhook at `ml/fire_detection/alerts.py` — signature forgery, replay, timing attacks.
- The TAK / CoT emitter at `sapphire_integration/tak/` — XML injection, certificate handling, multicast amplification.
- The model artifacts under `ml/fire_detection/runs/v0.0.1/` — model substitution, manifest tampering.
- The flight simulator under `sim/` — deserialization gadgets in mission YAMLs (Phase 0.5 sandbox concern), path traversal in evidence-URI generators.
- The frontend dashboard at `frontend/app.py` — `ADMIN_TOKEN` auth bypass, XSS in signal rendering, SSRF via URI fields.
- The Sapphire bridge `~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py` (PR #551, MERGED 2026-05-02) when invoked from this repo. The bridge's broader Sapphire posture is documented at [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md) (private); this scope covers only the bridge's contract with wildfire-watch.

### Out of scope

- The user's private hermes / Sapphire configuration. Sapphire's own security posture is documented in [`~/Code/Sapphire/CLAUDE.md`](https://github.com/arigatoexpress/Sapphire/blob/main/CLAUDE.md); reach out via the Sapphire repo for issues there.
- Downstream forks of this repository; they own their own posture.
- Issues that require physical access to a drone, a partner FD's TAK Server, or a maintainer's workstation. (We will still take these seriously, but they fall outside the standard SLA.)
- Issues in third-party dependencies — please report those upstream first; we will pull the fix once it lands.
- Denial-of-service against a single self-hosted dashboard instance with no real users behind it.

## Hall of fame

Reporters who responsibly disclose a security issue will be credited here (with consent) once an advisory is published. As of 2026-05-02 the list is empty.

## Bug bounty

There is no monetary bug bounty program at this time. We will revisit when the project has a sustaining sponsor or has graduated past the "personal-project + partnership pilot" stage. In the meantime, public credit and a hall-of-fame entry are the only formal acknowledgement we can offer.
