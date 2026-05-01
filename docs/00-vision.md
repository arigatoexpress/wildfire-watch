# Vision — wildfire-watch

## The 60-second pitch

Wildfires kill people, level neighborhoods, and burn billions of dollars of timber and
infrastructure every year in California. The first 30 minutes of a fire decide
whether it stays small or becomes catastrophic. Today, ignition is detected by:

1. **Citizens calling 911** — slow, often after smoke is already large.
2. **Mountaintop fire-lookout cameras** (ALERTCalifornia / ALERTWildfire) — fixed
   viewpoints, blind spots, and only flag visible-spectrum smoke.
3. **Polar-orbit satellites** (GOES, VIIRS) — best resolution ~375 m, revisit every
   few hours, useless for sub-acre ignitions in the first hour.
4. **Aerial reconnaissance** — only after a confirmed fire, dispatched from a base.

**wildfire-watch is the missing layer**: a mesh of cheap, autonomous, 3D-printed
drones that continuously patrol high-risk zones (wildland-urban interface, power
line corridors, parks adjacent to housing), running on-board AI to detect smoke
plumes, anomalous heat signatures, and unusual wildlife movement (a stampede out
of a draw is a fire signal). When a drone fires a positive, it tags GPS + thermal
imagery + visible-spectrum imagery + confidence score, and pushes a Cursor-on-Target
(CoT) message to the local fire department's TAK server within seconds.

The same flight produces ecological telemetry — species counts via MegaDetector v6,
bird song via BirdNET, fuel-load mapping — that we publish as open data to back
research and grant funding.

## Why now (2026)

- Edge-AI inference cost collapsed: $249 Jetson Orin Nano Super gets 67 TOPS in 25W.
- FAA streamlined Part 107 BVLOS path: Public Safety Shielded Operations Waiver
  (1-mile BVLOS) is now available to public safety agencies through Drone Zone,
  and Parts 108/146 finalize in 2026.
- TAK ecosystem matured: COTAK (Colorado public-safety TAK) launched 2024, CAL FIRE
  is integrating, ATAK UAS Tools natively ingest MAVLink.
- 3D-printable frames + commodity flight controllers (Pixhawk 6X, Cube Orange+) make
  a $2.5k unit possible at hobbyist scale.
- MegaDetector v6 dropped 50% of parameters with better recall — wildlife-ID at the edge
  is a free side effect of the fire-detection compute envelope.

## Why us

The operator runs the [Sapphire intelligence stack](https://github.com/arigatoexpress) —
a 4-tier compute mesh (Windows GPU + Mac + 2× Pi cluster on Tailscale) with
hermes-agent for Telegram alerts, an OpenBB-backed financial intel pipeline, and
TradingView orchestration. Drone telemetry plugs directly into that mesh:

- Drone → `signal_logger:18081` (existing, JSONL persistence + Telegram fan-out)
- Signal → Sapphire dashboard (`:8080`) for visualization
- High-confidence fire signals → hermes-agent → Telegram bot → on-call operator
- Aggregated ecology data → Cloud Run (`sapphire-479610`) for public read API

## What we're not

- We are **not** firefighters. We don't drop water. We don't fly into active fires.
- We are **not** a replacement for ALERTWildfire or satellite-based detection.
  We're a complementary layer covering the sub-acre, sub-30-minute window they miss.
- We are **not** a surveillance product. Wildlife and ecology imagery is the public
  good. We do **not** capture identifiable images of people, do not fly over private
  residences, and operate only within FAA-compliant geofenced zones with documented
  fire-department or land-manager authorization.

## The ask

- Fire departments / land managers: **define a zone we can patrol** (a county park,
  a power-line corridor, a watershed). We fly it, you get the data feed.
- Researchers: **pull our public ecology dataset** to study fauna patterns at the
  wildland-urban interface.
- Grant funders: **a $50k pilot funds 2 drones, a ground station, and 100 hours of
  patrol over a fire season** — measurable detection-time deltas vs. existing systems.
