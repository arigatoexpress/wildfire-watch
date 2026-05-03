# sim/demo/ — canonical recorded-flight artifact + HTML report

This package is the static, bundle-friendly counterpart to the live
viewer at `sim/web/server.py`.

- `recorder.py` — drives the existing `sim.runner.SimulationRunner` and
  `sim.swarm.runner.SwarmRunner` against the canonical Slate River
  mission + smoke-plume scenarios, with a fixed seed. Idempotent on
  (seed, mission, scenario).
- `renderer.py` — turns any flight directory into one self-contained
  HTML file: inline SVG map of the AOR with planned + flown paths, an
  inline SVG plot of the fusion gate over time, a table of emitted
  signals, and a "how to read this" section for non-technical readers.
  No JavaScript, no external CSS / fonts / images, target size < 200 KB.
- `cli.py` — `record` / `render` / `all` subcommands.

## Generate the report

```bash
cd ~/Code/wildfire-watch
/usr/local/bin/python3 -m sim.demo.cli all
```

This writes `sim/demo/canonical/wildfire_watch_demo.html` plus the
underlying flight directories. Open the HTML file in any browser — no
server, no internet, no JavaScript required.

## Render an existing flight

```bash
/usr/local/bin/python3 -m sim.demo.cli render \
    /path/to/flight_dir \
    --output report.html
```

The flight dir can be either a direct sim/swarm output dir (containing
`manifest.json`) or the top-level canonical dir (containing
`single/` + `swarm/`).

## Why a static HTML report?

The live viewer is for the operator running a flight in real time:
Leaflet basemap, time scrubbing, Server-Sent-Events replay. Useful to
the engineer; useless in an outreach email.

The static report exists for:

- **README embedding** — one link, opens locally.
- **Outreach attachments** — Crested Butte FPD, Anduril, Palantir, etc.
  inboxes mostly strip script tags and external resources; the report
  has neither.
- **Static hosting** — drop it on `wildfire.sapphirealpha.xyz/demo`.
- **Print** — the CSS has a `@media print` block so it prints
  cleanly on a single sheet for in-person briefings.

## License

Code is Apache-2.0 (see `LICENSE` at the repo root). The rendered
report's text + numbers are CC-BY-4.0; no third-party imagery is
embedded.
