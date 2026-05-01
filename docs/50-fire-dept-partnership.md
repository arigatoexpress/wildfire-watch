# Fire Department Partnership — go-to-market

## The pitch (2 minutes, in person)

> "We've built a sub-$3k autonomous drone that runs fire detection on-board. We
> want to fly it over [your district / your zone] every day during fire season,
> for free, in exchange for letting us push detected smoke plumes into your TAK
> server. You get a new sensor layer covering the half-acre, half-hour gap
> between citizen 911 calls and your dispatch. We get a public-good ecology
> dataset. If after one fire season our signals beat your ALERTWildfire camera
> by 5 minutes on average, we ask you to consider us for procurement."

## Target customers (California, in priority order)

| Agency | Why first | Contact path |
|---|---|---|
| **CAL FIRE San Benito-Monterey Unit** | Already runs 7 airframe models + 10 trained pilots; receptive to UAS partnerships per public coverage. Manageable district size. | Unit Chief office — email + walk-in to Hollister station |
| **El Dorado County Fire Protection District** | Just launched UAS program (2025); seeking force-multipliers; CBS-covered = visible win. | Fire Marshal + UAS program lead |
| **San Bernardino County Fire Protection District** | Pilot-testing drones-as-first-responders for "unknown type" fire calls. | UAS Program Manager |
| **Pebble Beach Community Services District** | Small, well-funded, defined geographic scope (Del Monte Forest), high property-value motivation. | District general manager |
| **CAL FIRE Research Development & Innovation (RDI)** | Statewide RDI office actively funds wildfire-tech pilots; the door for moving from a single-unit pilot to a statewide one. | RDI Program Manager (cal.fire.ca.gov/what-we-do/research-and-development) |
| **CAL FIRE Aviation Program HQ (Sacramento)** | Final destination for statewide UAS standardization. Approach only after a successful unit-level pilot. | After Unit-level pilot only |

## Value proposition by stakeholder

### Fire chief / battalion chief
- **Earlier dispatch** = smaller fire = lower suppression cost = fewer civilians
  evacuated. The cost of one acre saved typically pays for the program.
- **Reduces lookout-tower / ALERTWildfire blind spots** — drones fly under tree
  canopy when needed; cameras can't.
- **Free during pilot**, low procurement cost if it works.

### UAS program manager / training officer
- **Open-source firmware (ArduPilot)** — no DJI vendor-lock; you can train your
  own pilots, repair your own units.
- **NDAA Section 848 compliant** — meets federal-grant procurement rules.
- **Integrates with your existing TAK** — CoT messages over your COTAK or
  local TAK Server. ATAK UAS Tool already supports the MAVLink stream.

### IT / cyber
- **Tailscale-only ingress** for our backend, no public exposure.
- **Stateless HMAC-SHA256 auth** for signal POSTs (Sapphire pattern, multi-instance safe).
- **All data stays in your TAK** — we publish the **ecology** dataset publicly,
  not the fire-signal evidence (which is your operational data).

### Public-affairs / community
- **Wildlife photography by-product** — chief gets to publish "wildlife of [the
  district]" calendar with our flight footage. Tangible community-good story
  that contextualizes the fire-spotting capability for skeptics.
- **Privacy story**: we don't capture identifiable images of people; flight
  paths are published; zones are over public lands or with explicit landowner
  consent.

## Procurement reality

Fire departments procure UAS through:

1. **GSA Schedule / state cooperative purchasing** — fastest path; we'd need to
   list (typically 12-18 months and $5-15k in compliance fees).
2. **Direct purchase under micro-purchase threshold** — up to $10k often
   doesn't require competitive bidding. Two MVP units fits cleanly.
3. **Federal grants** — FEMA AFG, USDA Forest Service, BLM. Typically
   department applies and names us as the equipment vendor.
4. **CAL FIRE RDI grant** — California-specific; designed for tech pilots.
   Most likely funding source for a 1-2 season trial.

We are too small to bid on the big DJI/Skydio replacement contracts (Skydio X10D
at $25k/unit). Our procurement story is: **2 units per district at <$5k
hardware + $10k support contract** = under most micro-purchase thresholds and
low-friction approval.

## The pilot offer (template)

> **Wildfire-watch Pilot — [District Name], 2026 Fire Season**
>
> We will provide:
> - 2 production wildfire-watch units (full BOM, deployed and configured)
> - 1 ground station (laptop + radios + TAK adapter)
> - Up to 100 hours of pilot-supervised patrol over a zone you select
> - All data published to your TAK Server in CoT format
> - Monthly report: signals emitted, true positives, false positives, mean
>   detection-time delta vs. ALERTWildfire / 911
>
> We ask in exchange:
> - Letter of authorization to operate within your jurisdiction
> - Access to your TAK Server (read-write for our adapter, no other access)
> - Co-author on any post-season report or grant application
>
> Cost to district: $0 hardware, $0 personnel during pilot.
> Cost if you procure post-pilot: ~$3k/unit + $1k/yr support.

## Outreach script (cold email)

> Subject: Free 2026-fire-season drone pilot for [District Name]
>
> Chief [Last Name],
>
> I'm a private operator building a sub-$3k autonomous fire-spotting drone that
> runs on-board AI for smoke detection. It's NDAA-compliant, ArduPilot-based,
> and pushes signals into TAK Servers in CoT format.
>
> I'd like to fly two of them over a zone of your choosing during the 2026
> fire season at no cost to your district, in exchange for the chance to prove
> a detection-time delta against your existing ALERTWildfire coverage. Data
> stays in your TAK; we publish only the ecology by-product.
>
> 15-minute conversation? I can also bring the unit by your station for a
> hover demo on your schedule.
>
> [Operator name]
> [Phone, email]

## Standards to align with

| Standard | Why | Status |
|---|---|---|
| MAVLink 2 | UAS telemetry, ATAK UAS Tool ingest | ArduPilot native |
| Cursor-on-Target (CoT) XML | TAK signal format | Adapter in `ground_station/` |
| STANAG 4586 | Military UAS interop (overkill, but future-proof) | Not Phase-1 |
| FAA Remote ID | Legal requirement | uAvionix pingRID in BOM |
| NDAA Section 848 | Component-origin compliance for federal procurement | All BOM items |

## Meeting notes / contact log

(Operator: keep this updated as conversations happen.)

| Date | Agency | Person | Outcome |
|---|---|---|---|
| TBD | | | |
