# Acquirer-specific technical spec sheets

These are the technical attachments to the cold-outreach emails in
`docs/outreach/emails/04_..` through `..08_`. Each spec sheet is a 2-3 page
document aimed at a senior engineer or technical-BD lead inside the target
company. The job they do is narrow: prove enough technical fit that the
reader greenlights a 30-minute eval call.

## Mapping

| Email | Spec sheet | Audience |
|---|---|---|
| `04_anduril_lattice_intro.md` | `01_anduril_lattice_tile.md` | Lattice partner-engineering / Mission Autonomy |
| `05_palantir_aip_bootcamp.md` | `02_palantir_aip_foundry.md` | AIP Bootcamp lead / Foundry partner engineering |
| `06_ondas_optimus_payload_intro.md` | `03_ondas_optimus_payload.md` | American Robotics payload program / OAS BD |
| `07_red_cat_software_intro.md` | `04_red_cat_software_stack.md` | Red Cat software / ARACHNID program management |
| `08_kratos_civilian_variant.md` | `05_kratos_civilian_variant.md` | Kratos Unmanned Systems Division strategy |

## Usage

Attach the matching spec sheet to the matching email at first send, OR send
the email cold and offer the spec sheet on reply. Either works; the spec
sheet is sized to be readable in 5-10 minutes.

## Tone

- Specific: every spec names real APIs, real SDKs, real programs, real
  components. No "modern AI platform" hand-waving.
- Honest: every spec is up-front about what wildfire-watch has today (a
  simulator, 240 tests, a TAK emitter, an ontology, no flight hours) and
  what it does not have.
- Asks are time-boxed and small: a Sandbox slot, a 30-minute call, a paid
  90-day evaluation. None of these say "buy us."

## TBDs flagged

Items the spec sheets explicitly mark TBD because public 2026 sources do not
verify them:

1. American Robotics Optimus payload-bay mechanical / electrical interface
   specification — not published; needs payload-program NDA.
2. Black Widow / ARACHNID onboard-compute SKU and Palladyne Pilot AI
   software-bus contract — public coverage names the partners but not the
   integration interface.
3. Anduril Lattice Sandbox capacity / approval timeline for a sub-revenue
   civilian project — the developer portal documents the program but not
   the qualification bar.

When any of those become known, update the relevant spec sheet's
"Technical interface" section and remove the TBD tag.
