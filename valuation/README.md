# wildfire-watch / valuation

Continuously-updating intrinsic-value calculator + KPI dashboard.

Goal: **every commit and every shipped feature ticks a measurable, defensible
valuation number.** Four valuation methods triangulate a band; a primary
acquirer ranking points at who'd pay; a `what_to_do_next` list maps
KPI deltas to dollars.

## Quick start

```bash
cd ~/Code/wildfire-watch
python3 -m valuation.cli snapshot          # collect KPIs, print band, append to history
python3 -m valuation.cli kpi               # print KPIs only
python3 -m valuation.cli history --last 10 # tabular history
python3 -m valuation.cli compare <a> <b>   # delta between two stored commit SHAs
python3 -m valuation.web                   # http://localhost:8090
```

## What's measured

KPIs live in `kpis.py` and split four ways:

| Category    | Examples                                                        | Source                       |
|-------------|-----------------------------------------------------------------|------------------------------|
| engineering | loc_total, tests_passing, commits_30d, code_to_doc_ratio        | `git`, `wc -l`, `pytest --co`|
| product     | signals_emitted_total, simulator_runs_total, mission_zones_count| signals.jsonl, flights dir    |
| strategic   | LOAs, partner agencies engaged, briefings, media mentions       | `data/partners.yaml`         |
| compliance  | NDAA Blue UAS eligible, ITAR exposure, Part 107 pilots, secrets | BOM scan, regex sweep        |

## How the band is computed

Four methods (`methods.py`):

1. **comparable_multiples** — pick best-matching archetype from
   `data/comps_2026.yaml`, multiply implicit revenue by the comp set's
   low/mid/high P/S multiples. Implicit revenue is a proxy formula
   documented in the source.
2. **venture_method** — `mid = E[exit] * P(exit) / (1 + IRR)^5`.
   `P(exit)` is KPI-adjusted: LOAs, partner engagement, NDAA eligibility
   add probability; secrets in repo subtract.
3. **dcf_lite** — 5-year DCF with revenue ramped by LOAs + partners and
   growth tied to signal volume thresholds. 25% discount, 5x terminal.
4. **asset_floor** — code-asset value: $150/novel-LOC + $50/test-LOC +
   $125k per Part 107 pilot. The carcass.

Consensus band: `min(lows)` / weighted mid / `max(highs)`. Default weights
40/20/20/20 on comparable / venture / dcf / asset.

## Honest limitations

- **No revenue exists.** "Implicit revenue" is a proxy formula tied to
  LOC + sim runs + signals + LOAs. It is NOT a forecast of cash. The
  proxy multiplier is small on purpose so the comparable-multiples
  method doesn't run away with the band.
- **The acquirer ranking is heuristic.** Each axis has explicit weights
  in `engine.py::ACQUIRERS`. Treat it as a directional signal, not a
  pitch deck slide.
- **Comps are 2024-2026 snapshots.** Defense-tech multiples are volatile;
  re-source `data/comps_2026.yaml` quarterly.

## Tests

```
python3 -m pytest valuation/tests/ -q
```
