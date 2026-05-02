# wildfire-watch outreach kit

This is the operator's first-touch outreach kit. Nine email drafts, eight content drafts, and a dated calendar that lines up cold outreach, public posts, and the next-physical-actions to convert "interesting GitHub repo" into "people want to talk to us."

## How to use this kit

1. **Read the source documents first.** Every claim in this kit cites back to the repo. Before you send anything, re-read:
   - `~/Code/wildfire-watch/CLAUDE.md`
   - `~/Code/wildfire-watch/AOR.md`
   - `~/Code/wildfire-watch/README.md`
   - `~/Code/wildfire-watch/docs/strategy/POSITIONING_BRIEF-2026-05-02.md`
   - `~/Code/wildfire-watch/docs/strategy/PITCH-2026-05-02.md`
   - `~/Code/wildfire-watch/docs/strategy/SYNTHESIS-2026-05-02.md`
   - `~/Code/wildfire-watch/docs/strategy/ACQUIRER_FIT-2026-05-02.md`
   - `~/Code/wildfire-watch/BLUE-UAS-LINEAGE.md`
2. **The operator sends every email.** No draft in `emails/` is auto-sent. Fire-chief outreach is the operator's voice; everything else is reviewed before send.
3. **TBDs are real.** If a frontmatter field or body contains `TBD`, that means we did not verify the value from the repo or a reputable public source. Do not paper over a TBD with a guess; resolve it before send.
4. **Calendar drives sequencing.** Read `calendar.md` first. Each entry maps to a file in `emails/` or `content/` and tags the valuation-engine KPI that should move on completion.

## Layout

```
docs/outreach/
├── README.md                                   (this file)
├── calendar.md                                 (2-week + 1-quarter)
├── emails/
│   ├── 01_cbfpd_loa_request.md                 (HIGH — +$3M to mid-band)
│   ├── 02_gcfpd_introduction.md
│   ├── 03_gmug_district_ranger.md
│   ├── 04_anduril_lattice_intro.md
│   ├── 05_palantir_aip_bootcamp.md
│   ├── 06_ondas_optimus_payload_intro.md
│   ├── 07_red_cat_software_intro.md
│   ├── 08_kratos_civilian_variant.md            (longshot)
│   └── 09_cal_fire_dfpc_research_intro.md
└── content/
    ├── linkedin_post_01_announcement.md
    ├── linkedin_post_02_phase0_demo.md
    ├── linkedin_post_03_swarm_consensus.md
    ├── linkedin_post_04_blue_uas_lineage.md
    ├── linkedin_post_05_open_source_call.md
    ├── x_thread_01_demo.md
    ├── x_thread_02_marshall_fire_anniversary.md
    └── blog_post_01_phase0_walkthrough.md
```

## Frontmatter contract

Every email has YAML frontmatter:

```yaml
to: <name + role + best-guess email or contact form>
subject: <subject line>
priority: high|medium|low
intent: loa-request | bd-intro | research-collab | partnership-explore
gated_on: <what the recipient needs from us before they reply>
```

Every content piece has YAML frontmatter:

```yaml
platform: linkedin | x | medium | substack
target_date: <ISO-8601>
length_words: <count>
hashtags: [...]
```

## House style

- No emoji. Anywhere.
- Short subjects. Specific asks. Soft "no rush" closes.
- One link per email — the GitHub URL placeholder `https://github.com/arigatoexpress/wildfire-watch`.
- No revenue claims, no pricing, no "for sale" framing. We are asking for time, intros, and research collaboration.
- Real names and real numbers only. TBD anything not verified.

## What this kit does NOT include

- Investor pitch deck (separate artifact; positioning brief covers most).
- Press release / journalist outreach.
- RFP-response template.
- Podcast pitches.
- Phone-script for a CBFPD walk-in (use Email 01 as the basis).

## Sequencing

The single highest-leverage move on the dashboard is Email 01 to Crested Butte FPD. Send that one first. Everything else lines up behind it (see `calendar.md`).
