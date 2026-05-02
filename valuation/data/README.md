# valuation/data — sourcing notes

This directory holds curated inputs to the wildfire-watch intrinsic-value calculator.

## comps_2026.yaml

Comparable transactions used by `methods.py::comparable_multiples`. Each
entry must include:

- `target` — name of the company being valued at the comp event
- `acquirer` — null for a primary (Series X) round; populated for an M&A
- `date` — ISO-8601, the event date
- `amount_usd` — round size for primaries, deal value for M&A, or current
  market cap for public references (with `acquirer: null`)
- `revenue_estimate_usd` — best public estimate at event time; nullable
- `multiple` — `amount_usd / revenue_estimate_usd` when both are set
- `archetype` — see methods.py for the canonical set
- `source` — public URL or filing identifier
- `notes` — free-form caveats (estimate quality, distortion factors)

### Sourcing approach

Public market refs come from the company's most recent 10-K / 10-Q +
end-period market cap. Private rounds come from the announcing press
release + Crunchbase confirmation; revenue estimates are public-reporting
ranges (caveat lector).

When two figures conflict (eg. press release vs. PitchBook), we use the
more conservative number and document the spread in `notes`.

### Multiples are sales multiples

`amount_usd / revenue_estimate_usd` gives us a price-to-sales (P/S).
Defense-tech sales multiples in the 2024-2026 environment have ranged
from ~3x (mature primes — Kratos, AeroVironment) to ~80x (early-stage
hot autonomy plays — Saronic). For wildfire-watch we anchor against the
full distribution, not just the median, because acquirer fit varies
wildly across the 5 strategic targets.

## partners.yaml

Partner-agency engagement state. Two booleans matter for KPIs:

- `engaged` — has there been a real bilateral conversation, not just an
  email? Counts toward `partner_agencies_engaged`.
- `loa_signed` — written letter of authorization to fly. Counts toward
  `letters_of_authorization_count`.

The default state is all-false. Update in-place as relationships develop.

## team.yaml

Team roster. The single KPI that reads from here is
`faa_part107_certified_pilots`. Other fields are advisory.

## valuation_history.jsonl

Runtime output, gitignored. Created on the first `valuation.cli snapshot`
run. Append-only — each snapshot is one line of JSON with the full
`compute_valuation()` output plus the commit SHA.
