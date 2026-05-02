# Area of Operations — Gunnison-Crested Butte, Colorado

This file is the source of truth for the wildfire-watch AOR. Earlier scaffolding referenced Monterey-Pinnacles-East as a placeholder example; the real operational area is the **Gunnison Valley + Crested Butte corridor in Gunnison County, Colorado**. Treat any "Monterey" / "Pinnacles" reference in `sim/missions/monterey_pinnacles_east_1km2.yaml`, the bundled web-viewer fixture, or the agent-generated intel docs as a generic example to be retargeted.

## Geography

| Anchor | Lat | Lon | Elevation | Notes |
|---|---:|---:|---:|---|
| Town of Crested Butte | 38.8697 N | 106.9878 W | 8,909 ft / 2,716 m | Historic mining town, fire station HQ |
| Mt. Crested Butte | 38.8975 N | 106.9647 W | 9,375 ft / 2,857 m | Resort, peak elevation 12,162 ft |
| Town of Gunnison | 38.5458 N | 106.9253 W | 7,703 ft / 2,348 m | County seat, GFD HQ |
| Gunnison-Crested Butte Airport (KGUC) | 38.5339 N | 106.9332 W | 7,680 ft / 2,341 m | KGUC class E, ADS-B mandatory above 10,000 MSL |
| West Elk Wilderness boundary | varies | varies | 8,400–13,000 ft | **No-fly: 36 CFR 261.16 prohibits aircraft in wilderness, drones included** |

The valley floor sits at ~7,700 ft and the surrounding ridges climb to 13,000 ft within ~10 km. The corridor between Gunnison and Crested Butte (~28 mi via CO-135) is the primary AOR.

## Topography + fuel load

- **High-elevation montane** — lodgepole pine, Engelmann spruce, subalpine fir.
- **Beetle-killed timber** is the dominant wildfire-risk amplifier. Mountain pine beetle and spruce beetle infestations have left extensive standing-dead fuel across the GMUG (Grand Mesa, Uncompahgre, Gunnison) National Forest. Ground-truth this on every mission planning cycle — beetle-kill maps are public via the Colorado State Forest Service.
- **Aspen + sagebrush** in the lower valley (Gunnison side) — lower fuel intensity, faster spread.
- **Wildland-urban interface (WUI)** is sharp and extensive on the Crested Butte side; lots of $$$ second-home density adjacent to dead-timber stands.

## Climate / fire season

- Short but explosive fire season: typically late-June through mid-September, with peaks in July-August dry-lightning episodes.
- Spring red-flag windows (April-June) when winter snowpack has retreated but green-up hasn't caught up.
- Cold winters render flight ops basically useless Nov-March (Mavic Mini operating range is 0–40°C; Lipo cells fail below freezing).

## Regulatory environment

- **FAA Part 107** — same as everywhere else. Class E airspace below 10,000 ft MSL through most of the AOR. Above 10,000 MSL, ADS-B mandatory and Part 107 ceiling kicks in (400 ft AGL above terrain, with surveyed-structure-relative exceptions).
- **KGUC airport class E** — LAANC authorization is needed for any flight in the airport surface area (~5 nm radius of KGUC) below 1,200 ft AGL.
- **USFS Wilderness no-fly** — West Elk Wilderness, Maroon Bells-Snowmass Wilderness (just north), Raggeds Wilderness — hard prohibition, FAA + USFS jointly enforce.
- **Colorado Revised Statute 33-14.5** — drone harassment of wildlife is a state misdemeanor, especially relevant during deer/elk rut + sage grouse lekking seasons.
- **Wildfire TFR** — `tfr.faa.gov` plus the FAA's UAS Facility Maps. **California Penal Code 402 doesn't apply here, but** 14 CFR 91.137 still does and Colorado has its own enforcement teeth.
- **USFS GMUG district contact** — the Forest Service requires coordination for any UAS flights over National Forest land that are NOT incidental recreation. Volunteer fire-watch is a structured operation requiring at least notification.
- **High-altitude UAS performance** — Mavic Mini service ceiling is 13,123 ft (4,000 m) on paper, but battery duration drops 25-35% above 9,000 ft and motor authority for wind tolerance drops similarly. Plan with 70% of nominal endurance.

## Likely partner agencies

Listed in priority order for outreach. Pitch templates live in `docs/50-fire-dept-partnership.md` (currently California-flavored — retarget on use).

1. **Crested Butte Fire Protection District (CBFPD)** — small district, high WUI risk, second-home tax base means actual budget. Fire Chief office on 6th Street, 700 6th Street, Crested Butte, CO 81224. Phone (970) 349-5333.
2. **Gunnison County Fire Protection District (GCFPD)** — covers Gunnison + unincorporated county; broader AOR than CBFPD. HQ at 200 W Tomichi Ave, Gunnison.
3. **Mt. Crested Butte Fire Protection District** — covers the resort + above-town. Smaller, tightly coupled with CBFPD.
4. **GMUG National Forest — Gunnison Ranger District** — Forest Service, 216 N Colorado St, Gunnison. Required coordination partner for any flight over USFS land.
5. **Colorado Division of Fire Prevention and Control (DFPC)** — state-level, runs CO Centennial Helitack and the Multi-Mission Aircraft program. Probably not first-tier for a citizen pilot project but useful to know exists.
6. **Western State Colorado University (WCU)** — local university in Gunnison, has a tradition of environmental research. Potential academic-partner pathway.

**Do NOT lead with** federal agencies (USFS HQ, BLM, NPS) — too slow, Esri-locked per `docs/intel/foundry-research-2026-05-01.md`. County and municipal first.

## Hardware implications of the actual AOR

The BOM at `hardware/bom.csv` (Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super) is fine for this AOR but with caveats:

- **Battery sizing** — derate by 30% for elevation. Spec'd 8000 mAh Tattu Li-Ion gives ~35 min nominal at sea level → ~24 min at 9,000 ft. Plan a 5-cell 5500 mAh pack as an "endurance" alternative.
- **Cold-weather lithium chemistry** — for shoulder-season ops, switch to LiPo with self-heating (or hand-warmer pre-heat) below 5°C. LiFePO4 doesn't cut it under the C-rate demands.
- **Motor sizing** — the X500 V2's stock T-Motor MN3110 KV470 + 11" props are sized for sea-level + payload. At 9,000 ft you lose 25% thrust margin. Either upsize props to 12" (frame allows) or accept reduced max-takeoff-weight.
- **Wind tolerance** — Crested Butte's Wind Pillow is real; 25-35 kt mid-day winds in summer. The Mavic Mini's 10.5 m/s (~20 kt) wind resistance is borderline; Holybro X500 with the upgraded motors handles it.
- **Comms** — KGUC tower is at 7,680 ft; Tailscale + Starlink Mini + LoRa-Meshtastic mesh from `docs/intel/low-cost-hardware-2026-05-01.md` all work fine here. Cell coverage is patchy on the back side of any ridge.

## Phase 0 mission targets (Mavic Mini)

In priority order, all within 5 km of the town of Crested Butte:

1. **Slate River drainage west of Mt. Crested Butte** — beetle-kill stands above the Slate River, accessible from the gondola road. Good initial test polygon (~1 km²).
2. **Cement Creek drainage south of Crested Butte** — adjacent USFS land, dispersed dead-timber, less pilot traffic.
3. **East River corridor north of CB** — riparian zone, lower fire risk but good for wildlife / ecology baseline imagery.
4. **Long Lake / Lake Irwin** — west of Mt. Crested Butte, sees recreation traffic and historical lightning starts.

Each target gets a `sim/missions/<name>.yaml` + a `missions/zones/<name>.geojson` once chosen.

## What needs renaming in the existing scaffolding

These files were written before the AOR was confirmed. Treat as placeholders:

| Path | Current placeholder | Action |
|---|---|---|
| `sim/missions/monterey_pinnacles_east_1km2.yaml` | Monterey-Pinnacles | Rename / replace with `gunnison_*` mission YAMLs |
| `missions/zones.example.geojson` | Monterey example coords | Add Colorado examples; keep Monterey as a README example |
| `docs/intel/SYNTHESIS-2026-05-01.md` | Says CAL FIRE San Benito-Monterey | Mention is incorrect; the right outreach is CBFPD |
| `docs/intel/foundry-research-2026-05-01.md` | California-flavored | Foundry analysis still valid, but partner-agency examples should mention Colorado FDs |
| `docs/50-fire-dept-partnership.md` | CAL FIRE pitch template | Retarget the email template to CBFPD / GCFPD / GMUG |

I have NOT yet rewritten these — they're left in place as agent output, with this AOR.md as the override.

## Open questions

- **Insurance** — what does the user's own UAS commercial liability policy cover at high altitude? (Phase 1 question, not Phase 0.)
- **Beetle-kill ground truth** — does the user have a relationship with a USFS forester or CSU ranger who can hand over the latest beetle-kill polygon shapefiles? This dramatically improves the priority-zone selection.
- **Wilderness-edge drift** — how aggressively does the AOR butt up against West Elk Wilderness? Need to import the wilderness GeoJSON and add a mandatory geofence subtraction step in `sim/mission.py`.
- **Local pilot community** — is there an existing volunteer drone-pilot network in the valley? Worth checking with Crested Butte Mountain Heritage Museum's events board, the Gunnison Library, and the Crested Butte Center for the Arts.

The mission planner in `sim/` currently treats geofences as a single inclusion polygon. For Gunnison the geofence model needs to support **inclusion AND exclusion** polygons (so wilderness is carved out). This is a Phase 0.5 code change, not Phase 0.
