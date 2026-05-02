# wildfire-watch — Day-1 Synthesis (2026-05-01)

This is the "what do I do tomorrow morning" reference. It folds four parallel research dispatches — Palantir Foundry, Ukrainian drone ecosystem, low-cost hardware + Flipper Zero, Phase-0 with existing hardware — into a single unified plan.

If you only read one document, read this one. Drill into the four source docs only when you need to defend a specific decision.

## TL;DR

1. **Phase 0 ships this week.** Use the Mavic Mini + Mac mini + rari1/rari2 you already own. Fly weekly, post-flight YOLO on rari2, RAWS/HRRR/GOES poll on rari1. Cost: $0. Code is already on disk (`ml/fire_detection/mavic_post_flight.py`, `ground_station/pi_telemetry_collector.py`).
2. **Phase 0.5 buys $215 of leverage.** RTL-SDR Blog v4 ($40) + PMS5003 smoke sensor ($25) + BME688 fire-weather ($20) + 2× Heltec V3 Meshtastic ($50) + Pi 5 AI HAT+ Hailo-8L ($70). **Skip Flipper Zero** — wrong tool for the job; $40 RTL-SDR beats it on every relevant axis.
3. **Foundry: conditional yes.** Stand up Postgres+PostGIS as the system of record this week. Apply to the **free Foundry Developer Tier** in parallel for the ontology + AIP Logic agent + demo surface. Don't put the primary signal store inside Foundry — vendor-lock-in is real. Reuse Sapphire's existing `lib/foundry/` and `services/foundry_sync/` plumbing.
4. **Ukraine playbook: three direct lifts.** (a) Codified open BOMs as the procurement moat. (b) Distributed 3D-printer volunteer network — recruit local makerspaces. (c) Vision-based GNSS-denied navigation for smoke + canyon flight.
5. **DJI Mavic Mini is a Phase-0 stopgap, not a foundation.** The 2026 NDAA + Countering CCP Drones Act environment makes any DJI bet expire by 2027. Plan migration now. Keep the Mini for manual scout flights; build the autonomous fleet on US/EU stack (Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super, already in `hardware/bom.csv`).
6. **Federal UAS-fire (CAL FIRE / USFS / BLM) is Esri-locked.** Do NOT pitch them on a Foundry-backed system. Target **county and municipal fire departments** instead — they have real autonomy and a real budget gap.

## What you do this week (no new hardware)

```bash
# 1) Update local Sapphire main, install bridge
cd ~/Code/Sapphire && git pull origin main
echo '{"action":"schema_info"}' | python3 plugins/claw-sapphire/tools/wildfire.py

# 2) Confirm the synthetic demo emits a valid v1 signal end-to-end
cd ~/Code/wildfire-watch && python3 ml/fire_detection/demo.py --pipe-to-sapphire

# 3) Plan a Litchi waypoint mission over a small parcel:
#    50–100m AGL, 4–6 m/s, 70% RGB overlap, pre-cache satellite tiles.
#    Filing — Part 107 if not yet certified (volunteer fire-watch is non-recreational).

# 4) Pre-flight checklist (every single time):
#    - tfr.faa.gov check (California Penal Code 402 + 14 CFR 91.137 = $5K + jail for TFR incursion)
#    - B4UFLY app
#    - Battery temp logged

# 5) Land. SD card → ~/wildfire-watch-flights/2026-MM-DD/
#    cd ~/Code/wildfire-watch
#    python3 ml/fire_detection/mavic_post_flight.py ~/wildfire-watch-flights/2026-MM-DD/ --pipe-to-sapphire

# 6) Watch detections appear in the Sapphire dashboard at http://mac.local:8080
#    (event_bus delivers wildfire.signal.detected events to the SSE feed)
```

## Spend $215, get teeth (Phase 0.5)

| # | Item | Cost | Why it matters |
|---|---|---:|---|
| 1 | RTL-SDR Blog v4 + antenna kit | $40 | ADS-B (manned-aircraft TFR awareness over the AOR), `rtl_433` for RAWS weather telemetry, Remote ID receive |
| 2 | Plantower PMS5003 PM2.5/PM10 | $25 | Direct smoke detection — particulates spike 5–30× during wildfires |
| 3 | Bosch BME688 (T/RH/P/VOC) | $20 | RH < 25% + T > 32 °C is the canonical fire-weather red-flag |
| 4 | 2 × Heltec V3 Meshtastic (915 MHz) | $50 | License-free LoRa mesh, survives LTE outage. Connect rari1 + rari2 + future field nodes |
| 5 | Pi 5 AI HAT+ Hailo-8L (13 TOPS) | $70 | Replaces older Coral; rari2 runs YOLOv8-fire at 30+ FPS for live ingest |

Total: $205 plus shipping/tax buffers to ~$215.

**Explicitly NOT buying:** Flipper Zero. The $199 sticker buys ~$30 of relevant capability for this project. Reconsider only if scope expands into RF-supply-chain auditing.

## What costs more than $215 but is on the critical path

The original BOM at `hardware/bom.csv` (~$2,613 for the autonomous flight-capable unit) is unchanged. Long-lead items to order **only after Phase 0 is shipping** and you've decided to scale:

- Cube Orange+ flight controller ($350, 2-4 wk lead time)
- Jetson Orin Nano Super 8 GB ($249, 2-4 wk)
- Holybro X500 V2 frame kit (~$300)
- FLIR Lepton 3.5 + PureThermal 3 (~$400 combined)
- uAvionix pingRX Pro (ADS-B In) + pingRID (Remote ID) for FAA compliance (~$650 combined)

Print PETG-CF Jetson pod + gimbal cradle on the Bambu while parts ship.

## Foundry posture

Read [`foundry-research-2026-05-01.md`](foundry-research-2026-05-01.md) for the full thesis. The condensed version:

| Decision | Choice | Why |
|---|---|---|
| **System of record** | Postgres + PostGIS on Mac mini | Zero vendor-lock, geospatial primitives, free, runs forever |
| **Ontology + AIP** | Foundry Developer Tier (apply this week) | Free, capacity-capped, AIP Logic replaces the rule-based `_priority_for()` in `wildfire.py` |
| **Demo surface for fire dept pitches** | Foundry workshop or PG&E PSPS-style scoping app | Strongest existing precedent — same risk-score-over-polygon shape |
| **Federal UAS-fire (CAL FIRE / USFS / BLM)** | Don't pitch | Locked to Esri/ArcGIS Online; political headwind too strong |
| **County / municipal FD** | Pitch hard | Real autonomy, real budget gap, can move in weeks |

**6 new ontology types** to add to Sapphire's existing Foundry schema: `WildfireSignal`, `Drone`, `Zone`, `FireDepartmentUnit`, `FlightLog`, `BatteryCycle` plus 1 media set. Reuse existing `Alert` and `Incident`. Reuse existing `lib/foundry/` and `services/foundry_sync/` plumbing — no new daemon.

## Ukraine playbook → fire-watch mapping

Read [`ukraine-drone-playbook-2026-05-01.md`](ukraine-drone-playbook-2026-05-01.md). Three patterns transfer directly:

1. **Codified open BOMs + a catalog/marketplace** (Brave1 model). Git-versioned BOM per airframe class, JSON mission-profile schema, published GeoJSON detection format. The fire department becomes the "frontline unit" picking from the catalog.
2. **Distributed 3D-printer volunteer network** (DrukArmy: ~10K printers). Single highest-leverage idea for a county-scale fleet. Recruit local makerspaces. Publish STL repo. Ship antenna mounts and Pelican-case inserts.
3. **Vision-based GNSS-denied navigation** (OSCAR, KrattWorks Ghost Dragon, Bavovna AI). Smoke kills GPS; the same techniques Ukrainians use against jamming solve canyon and smoke-plume flight.

What does NOT transfer: weaponization, autonomous strike, ITAR/EAR-controlled hardware. Stay civilian.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| DJI ban / Remote ID / NDAA changes brick the Mavic mid-program | High | Treat Mini as Phase-0 only; design the autonomous fleet on Holybro/Cube/Jetson from day one |
| TFR incursion during a real fire | Catastrophic | Pre-flight `tfr.faa.gov` + B4UFLY check is mandatory; build into mission-supervisor preflight script |
| False-positive flood from RGB-only Phase 0 detector | High | Phase 0 caps `recommended_action=notify_operator`; `risk_score` capped at 60 (no thermal corroboration); operator-in-loop |
| Foundry vendor lock-in | Medium | Postgres+PostGIS as system of record; Foundry as demo + ontology layer only |
| Volunteer-pilot insurance gap | Medium | Carry your own commercial UAS policy; don't fly on a fire dept's behalf without their explicit insurance coverage |
| ITAR/EAR drift if scope expands beyond civilian | High | Stay civilian; any defense-adjacent work spawns a separate org with separate counsel |

## Three shoulder-tap follow-ups

These don't fit Phase 0 but should be in the user's calendar:

1. **CAL FIRE San Benito-Monterey unit** — cold email this week using the template at [`docs/50-fire-dept-partnership.md`](../50-fire-dept-partnership.md). Get a written letter of authorization for a 1 km² test polygon before any flight on their behalf.
2. **Local makerspaces** — find 1-2 within driving distance and pitch the volunteer-print model. Ukrainians are doing this with thousands of printers; you can start with ten.
3. **Foundry Developer Tier application** — submit this week so the trial slot is open by the time Phase 0 has signal data to play with.

## Source docs

- [`foundry-research-2026-05-01.md`](foundry-research-2026-05-01.md) — Palantir Foundry deep dive (~3,940 words, 25 sources)
- [`ukraine-drone-playbook-2026-05-01.md`](ukraine-drone-playbook-2026-05-01.md) — Decentralized creation playbook (Brave1, Aerorozvidka, DrukArmy)
- [`low-cost-hardware-2026-05-01.md`](low-cost-hardware-2026-05-01.md) — Flipper Zero verdict + $215 shopping list + Phase 0 deliverable
- [`../PHASE_0_QUICKSTART.md`](../PHASE_0_QUICKSTART.md) — Operator quickstart for the existing-hardware MVP
