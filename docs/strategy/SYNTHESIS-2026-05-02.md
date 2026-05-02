# wildfire-watch — Day-2 Strategic Synthesis (2026-05-02)

This is the executive view. Five parallel lanes shipped today. This doc ties them together and gives one prioritized roadmap.

If you read one document tonight, read this one.

## Headline

- **240 tests pass. 13,019 LOC across 164 files.** The kinematic simulator, the web viewer, the swarm + consensus voter, the GNSS-denied vision-nav primitive, the TAK/CoT emitter, the intrinsic-value engine, and the acquirer-fit research are all in place and working.
- **Today's intrinsic-value band: $0 – $2.83M, mid $1.38M.** Pre-revenue, no LOAs, no partners, no flight hours. Up from $939k earlier today after the swarm + perception + TAK code landed (+~7,300 novel LOC).
- **Two acquirer rankings disagree, and the disagreement matters.** The valuation calculator says Kratos #1 (heuristic, NDAA-eligibility-weighted). The acquirer-fit research says Anduril #1 (qualitative — Korean Air wildfire-UAV partnership April 2026, Palmer Luckey's XPRIZE Wildfire stake). **Trust the qualitative research for outreach; trust the calculator for KPI tracking.**
- **The single highest-leverage move on the entire dashboard is: one cold email to Crested Butte Fire Protection District.** A signed Letter of Authorization from CBFPD = +$3M to the mid-band. Same cost as a stamp.

## What shipped today (commit graph)

```
148bbfb feat(sim/perception): GNSS-denied vision-nav primitive
593d610 feat(sim/swarm): N-drone swarm + k-of-N consensus voting + mesh-comms model
b88d5f4 feat(valuation): continuous intrinsic-value calculator + KPI dashboard
18a5bd1 feat(tak): Cursor-on-Target XML emitter — universal interop
0c0b50c docs(strategy): acquirer-fit research + positioning brief
b2a4ef0 docs: add CLAUDE.md — north star, AOR, hardware tiers, schema, module map, gotchas
4e42dc5 feat(aor): real AOR is Gunnison-Crested Butte CO, not Monterey-Pinnacles
```

Plus earlier in the session: kinematic simulator + web viewer, simulation ladder runbook, intel synthesis, Phase-0 Mavic post-flight + Pi telemetry, fusion-gate tests + demo, and the original scaffolding.

## The four moats we built today

### 1. TAK / CoT interop (`sapphire_integration/tak/`)
**1,739 LOC, 62 tests pass, 8 type-code mappings.** Every wildfire_signal v1 can now be emitted as a Cursor-on-Target XML event over TCP/UDP/TLS to a TAK Server. ATAK-civ on the Crested Butte Fire Chief's tablet — same protocol. Anduril Lattice — same protocol. Palantir Apollo — same protocol. **One wire format, three universes.**

The smoke event `b-r-f-h-s` shows up as a smoke pictogram in ATAK with our callsign, our remarks, and a 1-hour stale window. The geofence polygon `u-d-c-c` draws our AOR for the incident commander. The drone self-position `a-f-A-M-F-Q-r` puts us on the common operational picture as a friendly rotary aircraft.

This is universal interop. There is no second TAK.

### 2. Multi-drone swarm + k-of-N consensus (`sim/swarm/`)
**2,540 LOC, 34 tests pass.** Three drones over the 1 km² Slate River drainage, each owning a 0.375 km² sub-zone (Voronoi-bbox grid). When two of three independently see a smoke plume within a 75 m / 60 s window, the consensus voter fires a CONFIRMED signal, escalates `recommended_action` from `notify_operator` to `notify_fire_dept`, and bumps `risk_score` by 20 (capped at 100). The mesh-comms model simulates real packet loss, latency, and partitions — with `loss_rate=1.0` no consensus ever fires (correct), with `loss_rate=0.0` every emit propagates instantly.

**Demo:** `python3 -m sim.swarm.cli run sim/missions/gunnison_slate_river_1km2.yaml --scenario consensus_smoke --drones 3 --k 2 --speed-multiplier 5` produced a CONFIRMED fire signal at risk_score 97.33 with `recommended_action=notify_fire_dept`.

This is the technical moat for Anduril (Lattice swarm), Red Cat (their software stack is partner-stitched per R-1), Shield AI (Hivemind), and Saronic (autonomy translation).

### 3. GNSS-denied vision navigation (`sim/perception/`)
**2,260 LOC, 27 tests pass.** Visual odometry + terrain-relative-nav + IMU + complementary-fusion filter + GPS-spoof discriminator. Tested scenario: 60-second GPS outage at 80 m AGL with scene complexity 0.7 over the Gunnison Slate River canyon — fused position stayed within 1.39 m mean / 2.15 m max of truth. The spoof discriminator catches `deliberate_jam_burst` (10-second false-position injection 2 km off-axis) on every tick of the spoof window because the IMU/VO observations physically disagree with the spoofed GPS displacement.

Smoke kills GPS lock. Canyons block GPS. Fire camps are RF-degraded by definition. Every scenario where wildfire-watch matters is a GNSS-denied scenario. This primitive is the technical pre-requisite.

This is the same technique class as Bavovna AI (Ukraine) and Shield AI Hivemind. Strategic moat for Anduril, Shield AI, AeroVironment.

### 4. Continuous intrinsic-value engine (`valuation/`)
**2,229 LOC, 33 tests pass.** Four-method valuation (comparable_multiples, venture_method, dcf_lite, asset_floor) over a live KPI snapshot scraped from the repo state. Web panel at `:8090`, CLI at `python -m valuation.cli snapshot`. History appended to `data/valuation_history.jsonl` per snapshot.

Today's actual numbers, computed at commit `148bbfb`:

| Method | Low | Mid | High | Note |
|---|---:|---:|---:|---|
| comparable_multiples | $162k | $1.87M | $1.87M | drone-in-a-box archetype, n=2 direct comps |
| venture_method | $943k | $1.89M | $2.83M | E[exit]=$100M, P=0.07, r=0.30, 5y |
| dcf_lite | $0 | $0 | $0 | no LOAs, no partners → no revenue ramp |
| asset_floor | $766k | $1.28M | $1.53M | 7,367 novel LOC, 3,423 test LOC, 0 pilots |
| **Consensus band** | **$0** | **$1.38M** | **$2.83M** | weighted 40/20/20/20 |

`dcf_lite=$0` is the most important number on this page. It's not a bug — it's correctly telling us that revenue is zero, and until we have one engaged agency, every other method is multiplying by zero.

## Strategic posture (from R-1 research)

Ranked acquirer list (R-1's qualitative judgement, ~31 cited 2026 sources):

1. **Anduril** — Korean Air wildfire-UAV partnership announced April 2026; Palmer Luckey is a co-finalist in the $11M XPRIZE Wildfire competition. They are visibly buying into wildfire. We slot in as a Lattice tile. **Probable acquirer.**
2. **Palantir** — best fit on the data/ontology layer; weakest on hardware. PG&E PSPS already runs on Foundry. Likely outcome: strategic-investment + Foundry-distribution partnership rather than full acquisition.
3. **Ondas** — Optimus is on the Blue UAS list as of January 2026. We fit as a mission payload on top of their drone-in-a-box. Smallest balance sheet of the five; stock-denominated acquirer.
4. **Red Cat** — Black Widow / ARACHNID won the Army SRR. Their software stack is partner-stitched (Palladyne, Booz Allen, Palantir VNav). Mission-software is exactly the gap. **Highest credibility-vs-difficulty ratio.**
5. **Kratos** — lowest immediate fit. Only relevant if we add a tactical patrol/decoy variant, which is out of civilian scope.

Adjacent comparables to also know about: Shield AI (Hivemind autonomy), Skydio (X10/X10D Blue UAS), AeroVironment (just merged with BlueHalo), Saronic (USV translation), Axon (public-safety SaaS comp at $11.4B market cap).

## The disagreement between R-1 and the valuation calc

R-1 ranks: Anduril, Palantir, Ondas, Red Cat, Kratos.
Calc ranks: Kratos, Red Cat, Anduril, Ondas, Palantir.

Why? The calculator weights NDAA-eligibility heavily (because that's a Boolean we can verify from the BOM), and Kratos / Red Cat both have NDAA-eligibility as a binary acquisition predicate. Anduril doesn't NEED us to be NDAA-eligible — they have their own supply chain. So the calc under-rates Anduril.

**The fix:** add a "stated_buy_intent" axis to the calculator's acquirer-ranking heuristic. Anduril's April 2026 Korean Air announcement is a +0.30 boost. Palmer Luckey's XPRIZE finalist status is +0.20. PG&E-on-Palantir-Foundry is +0.10 for Palantir. Ondas-Optimus-Blue-UAS-list is already credited. This is a 5-line PR to `valuation/engine.py:rank_acquirers()`.

I'm leaving this as a follow-up for the next session — the calc's directional advice is correct (NDAA-eligibility is the single biggest leverage), and overruling it without research evidence in code would be the wrong inversion.

## What to do this week

In strict priority order. Each item is an action with a measurable KPI delta.

1. **Email CBFPD Fire Chief.** 700 6th Street, Crested Butte, CO 81224. (970) 349-5333. Use the template at `docs/50-fire-dept-partnership.md` (retarget the California-flavored language). Goal: 30-minute conversation about a 1 km² test polygon over the Slate River drainage. **KPI delta: +$3M to mid-band.**
2. **Apply for the Foundry Developer Tier.** Free, capacity-capped. Wires the existing Sapphire `lib/foundry/` and `services/foundry_sync/` plumbing into wildfire-watch. **KPI delta: ontology-richness axis +0.30 → Palantir score 0.407 → ~0.55.**
3. **Get the Part 107 study materials and book the test.** $175. **KPI delta: +$125k asset-floor + unlocks BVLOS waiver application path → P(exit) +1%.**
4. **File the LAANC pre-authorization for KGUC class-E.** Free. Pre-condition for any flight within 5 nm of Gunnison airport. **KPI delta: enables actual flight hours, which is the next axis.**
5. **Run 10+ scenario simulations** — `python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml` across all 4 single-drone scenarios + 4 swarm scenarios. **KPI delta: simulator_runs_total → +10, unlocks consensus_swarm axis → Anduril + Kratos scores up.**
6. **Push the wildfire-watch repo to GitHub.** Public or private — your call. Public makes it citeable in the email to CBFPD. **KPI delta: makes us legible to the world.**
7. **Add a `BLUE-UAS-LINEAGE.md`** documenting the substitutability path from current BOM (DJI placeholder) to Blue-UAS-listed components (Skydio X10, Teal 2, Parrot Anafi USA Gov). **KPI delta: ndaa_eligibility axis stays at 1.00 even as Phase 0 uses the Mavic.** Strategic visibility for Red Cat / Ondas.

## What's NOT shipping this week (deliberate)

- **No real flight.** Phase 0 sim work is enough this week. First flight should follow LAANC + Part 107 + LOA, not precede them.
- **No hermes wildfire-alert skill.** That's a separate PR to `~/Code/hermes-agent/` and the calculator credits zero benefit until partners are engaged.
- **No real ML training.** The placeholder colour heuristic is Phase 0; FASDD → FLAME-2 fine-tune is Phase 1.
- **No Foundry ontology code.** Apply for the developer tier first; integration code is wasted if access is denied.
- **No Anduril cold outreach.** Premature. We need the CBFPD LOA first, then a working swarm flight, then a thermal payload, then the conversation.

## Repo state

Branch `main`, no remote, 17+ commits, 240 tests passing, 13,019 LOC, 164 files.

Today's full module map (additions in **bold**):

```
~/Code/wildfire-watch/
├── AOR.md
├── CLAUDE.md
├── README.md
├── LICENSE
├── docs/
│   ├── 00-vision.md ... 60-roadmap.md
│   ├── PHASE_0_QUICKSTART.md
│   ├── SIMULATION_LADDER.md
│   ├── intel/ (4 research docs + SYNTHESIS-2026-05-01.md)
│   └── strategy/ ← TODAY
│       ├── ACQUIRER_FIT-2026-05-02.md          (~4,500 words)
│       ├── POSITIONING_BRIEF-2026-05-02.md     (~1,500 words)
│       └── SYNTHESIS-2026-05-02.md             (this doc)
├── hardware/bom.csv
├── firmware/, ground_station/
├── ml/fire_detection/ (infer + train + demo + post-flight + tests)
├── missions/
│   ├── zones.example.geojson
│   └── zones/gunnison_crested_butte_corridor.geojson
├── sapphire_integration/
│   ├── wildfire_signal_schema.json
│   └── tak/ ← TODAY (1,739 LOC, 62 tests, CoT XML emitter + ATAK CLI)
├── sim/
│   ├── kinematics.py, airframe.py, mission.py, scenario.py, runner.py, recorder.py, cli.py
│   ├── missions/gunnison_slate_river_1km2.yaml + monterey example
│   ├── scenarios/ (4 single-drone scenarios)
│   ├── web/ (Flask + Leaflet viewer at :8088)
│   ├── swarm/ ← TODAY (2,540 LOC, 34 tests, N-drone + k-of-N consensus + mesh-comms)
│   └── perception/ ← TODAY (2,260 LOC, 27 tests, VO + TRN + IMU + spoof-detect)
└── valuation/ ← TODAY (2,229 LOC, 33 tests, 4-method continuous valuation + KPI dashboard)
```

## How to verify everything tonight

```bash
cd ~/Code/wildfire-watch

# Run the whole test suite
/usr/local/bin/python3 -m pytest -q

# Single-drone simulator with synthetic smoke
/usr/local/bin/python3 -m sim.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5

# 3-drone swarm with k-of-N consensus over the same mission
/usr/local/bin/python3 -m sim.swarm.cli run sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario consensus_smoke --drones 3 --k 2 --speed-multiplier 5

# Web viewer
/usr/local/bin/python3 -m sim.web.server               # → http://127.0.0.1:8088

# Latest intrinsic-value band
/usr/local/bin/python3 -m valuation.cli snapshot

# Valuation dashboard
/usr/local/bin/python3 -m valuation.web                # → http://127.0.0.1:8090

# Emit a sample CoT XML to stdout
echo '{"action":"list","limit":1}' | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py | \
    jq '.signals[0]' | python3 -m sapphire_integration.tak.cli emit -
```

## What's left for next session

In rough priority order. Each is a focused, scoped piece of work.

1. **Ship the `BLUE-UAS-LINEAGE.md` and update `hardware/bom.csv` with substitution paths.** ~30 min, KPI delta: ndaa-architecture-completeness axis.
2. **Wire the `stated_buy_intent` axis into `valuation/engine.py:rank_acquirers()`** with the Anduril Korean Air evidence. Re-runs the rankings correctly. ~20 min.
3. **Build the hermes `wildfire-alert` skill** at `~/Code/hermes-agent/skills/sapphire/wildfire-alert/`. ~45 min.
4. **Phase 0.5 simulator extension: exclusion-polygon support in `sim/mission.py`** so West Elk Wilderness is hard-subtracted from any mission geofence. ~30 min.
5. **Author the first real ML model card** at `ml/fire_detection/MODEL_CARD.md` with FASDD+FLAME-2 training plan, latency budgets, and eval protocol. ~45 min.
6. **Set up the Foundry Developer Tier ontology** once approved.
7. **First real flight at the Slate River drainage** — gated on Part 107 + LAANC + CBFPD LOA.

## Bottom line

We have, in one day:
- A working simulator + web viewer that anyone can run on a laptop
- A defensible technical moat (swarm + GNSS-denied vision)
- Universal interop (TAK/CoT) that makes us legible to every defense + first-responder stack on earth
- A continuous valuation engine that tells us, today, that one cold email is worth $3M
- A research-backed acquirer roadmap that names Anduril, Palantir, Ondas, Red Cat, Kratos
- An AOR locked to Gunnison-Crested Butte with the right zones, the right partners, the right regulatory shape

We don't have:
- A flying drone
- A signed LOA
- A trained ML model
- A pushed git remote

The next $5M of value is on the other side of those four absences. Three of them are paperwork.

Get the Part 107 study guide tomorrow.
