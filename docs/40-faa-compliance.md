# FAA Compliance — Part 107 + BVLOS path (2026)

## Operating context

We are flying small UAS (sub-2 kg) for **commercial fire-risk monitoring** with
a **public-safety partnership**. Two regulatory regimes apply:

1. **Part 107** — default for non-government commercial operations. Requires
   licensed Remote Pilot in Command (RPIC), VLOS, daylight, ≤400 ft AGL,
   ≤100 mph, no flying over people without waiver, no BVLOS without waiver.
2. **Part 91 with COA / Part 89 (Public Aircraft Operations)** — once a fire
   department contracts us as their UAS operator, public-aircraft rules apply
   to those flights, with significantly broader latitude (night, BVLOS at the
   department's discretion under their own SOPs and a COA).

## Phase 1 — pure Part 107 (MVP)

What we can do today, no waiver, with one Part-107-certified pilot:

- VLOS patrol over a defined zone within RPIC's line of sight (~0.5–1 mile
  radius depending on terrain).
- Daylight only (civil twilight to civil twilight; night requires waiver but
  see Part-107 Night Ops update).
- Below 400 ft AGL, controlled airspace requires LAANC authorization (instant
  via DroneZone or Aloft for most Class C/D up to a per-grid ceiling).
- Mandatory: Remote ID compliance (uAvionix pingRID is in our BOM).

**Permits / artifacts needed**:
- [ ] Part 107 Remote Pilot Certificate (operator already has, or acquire — 6
      weeks training, $175 exam).
- [ ] FAA Drone Zone aircraft registration (for each unit, $5 / 3 yr).
- [ ] LAANC for any flights in controlled airspace.
- [ ] Operations manual (template at `docs/ops_manual_template.md` — TBD).

## Phase 2 — BVLOS via Public Safety Shielded Operations Waiver (PSSOW)

Released by FAA in 2025 and broadened through 2026. Available to **public
safety agencies** through DroneZone, allows up to **1 mile BVLOS** in
"shielded" environments (along structures, terrain, treelines). **Not
restricted to emergency missions** — can be used for routine patrol once the
agency holds the waiver.

We obtain PSSOW by partnering with a county fire department or CAL FIRE unit
that holds, or applies for, the waiver. We fly under their authorization as a
contracted UAS operator.

**Permits / artifacts needed**:
- [ ] Partnership MOU with a public-safety agency.
- [ ] Agency files PSSOW application via DroneZone.
- [ ] Joint operations manual + risk assessment (FAA reviews ~4-6 weeks per
      Skydio's 2026 numbers).
- [ ] Detect-and-avoid (DAA) plan: ADS-B In via uAvionix pingRX Pro is on the
      drone; ground-based visual observers as secondary.

## Phase 3 — Part 108 / Part 146 (finalized 2026)

The FAA's proposed **Part 108** (BVLOS operations) and **Part 146** (drone
operations support services) are expected to finalize in 2026. They replace
the per-flight waiver model with a **type-certified BVLOS operations
authorization**, introducing new operator roles:

- **Operations Supervisor** — replaces the traditional sole RPIC for BVLOS
  ops; oversees a shift of multi-aircraft operations.
- **Flight Coordinator** — handles airspace deconfliction and DAA monitoring.

**Action when finalized**:
- [ ] Restructure team to include Ops Supervisor + Flight Coordinator roles.
- [ ] File for Part 108 authorization once rulemaking text is final and FAA
      starts accepting applications.
- [ ] Re-certify aircraft against Part 108 type-cert requirements (likely
      includes durability + DAA performance demonstrations).

## California-specific

**AB 1749** (signed 2024) — pilots holding an FAA Part 107 operational waiver
are **exempt** from new wildfire-related drone operation penalties. This
materially de-risks fire-zone operations for waivered pilots.

**TFRs over wildfires** — we **must not** fly within a Temporary Flight
Restriction. CAL FIRE issues TFRs over active fires; our pre-ignition role is
upstream of the TFR. If a zone we patrol becomes a TFR, we land immediately
and ground until the TFR lifts or we have express authorization from the
incident commander.

## Detect-and-avoid (DAA) stack

Required for PSSOW and Part 108. Our stack:

- **ADS-B In** — uAvionix pingRX Pro on each drone, alerts 5 nm, auto-RTL
  trigger at 2 nm + closing.
- **Visual Observer** — Phase 1: VO in radio comms with RPIC. Phase 2:
  ground-station visual feed + AI sky scan.
- **Acoustic** — TBD Phase 3, low-priority since GA aircraft over our zones
  are infrequent and ADS-B-equipped.

## Who in FAA to talk to

- **FAA UAS Integration Office** — `9-AVS-AFS-UASIntegrationOffice@faa.gov` —
  start here for Part 108 / Part 146 questions and PSSOW pre-application
  guidance.
- **Local Flight Standards District Office (FSDO)** — FSDO Sacramento or
  Oakland for California ops; meet in person before any waiver app.
- **ALPA / AOPA / RTCA SC-228** — industry working groups on UAS DAA standards
  worth attending for awareness.

## Insurance

Required by most public-safety partnership agreements. Recommended floor:

- $1M per occurrence aviation liability (Verifly / SkyWatch.AI / Avion).
- Hull coverage on the drone if BOM > $2k (we are).
- Errors & omissions for any data products we publish.

## Open compliance questions

- Will Part 108 grandfather PSSOW operators or require fresh application?
  (Industry guidance unclear as of 2026-Q2; track FAA NPRMs on
  [federalregister.gov](https://federalregister.gov).)
- Remote ID compliance for swarms (Phase 2): each drone broadcasts
  individually today; FAA may move toward "fleet-ID" packets for cellular Net-RID.
- Night ops via Part 107 waiver vs. via fire-department COA — pick the
  faster approval path per zone.
