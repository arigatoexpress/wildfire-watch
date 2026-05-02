---
to: Director or Research Liaison, Colorado Division of Fire Prevention and Control (TBD — confirm contact via dfpc.colorado.gov; the Wildland Fire Management Section is the relevant unit)
subject: Colorado-resident wildfire-watch research project — DFPC awareness + research-collaboration interest
priority: medium
intent: research-collab
gated_on: A first Phase 0 flight log; a written AOR brief and regulatory plan; an LOA from Crested Butte FPD as the first authorized partner
---

Hello,

I am writing as a Colorado resident with a wildfire-detection research project whose AOR (Gunnison Valley plus Crested Butte corridor) is in DFPC's state. I want to give DFPC the chance to know the project exists, well before there is anything to authorize, in case there is a research-collaboration angle DFPC would find useful.

The project is wildfire-watch (https://github.com/arigatoexpress/wildfire-watch). Open source under Apache-2.0. Civilian-first patrol layer designed for the sub-30-minute ignition window in beetle-killed lodgepole and Engelmann spruce stands at 7,700–9,000+ ft. Today it has a kinematic flight simulator, a browser viewer, a multi-drone swarm with k-of-N consensus voting, a GNSS-denied vision-nav primitive, a TAK / Cursor-on-Target XML emitter, a documented Blue UAS-substitution path for the BOM, and 240 tests passing. What it does not have today: any flight hours, any signed LOA, any trained ML model. Phase 0 first flight is a few weeks out behind Part 107 cert, LAANC pre-auth at KGUC, and an LOA from Crested Butte FPD.

The reason for writing DFPC: if a citizen-pilot project starts producing a structured fire-signal data feed over the Gunnison-Crested Butte corridor through a fire season, DFPC is a natural recipient. The data is structured (UUIDv4 IDs per signal, 6 signal types — smoke / fire / thermal anomaly / wildlife / anomaly / system event — with confidence, risk score, recommended action, and georeferenced frame URIs). It can be emitted in TAK / Cursor-on-Target XML to a TAK Server DFPC already runs, or as JSONL to whatever DFPC's wildfire-data ingestion looks like, or both.

A specific research-collaboration framing, if it interests DFPC: a structured feed of patrol-derived multimodal fire signals out of a single high-fire-risk corridor through one season would be a useful comparator against DFPC's existing detection layers (CO Centennial Helitack, Multi-Mission Aircraft, partner-FD reports). A co-pilot pattern — DFPC gets the data feed, I get DFPC's operational guidance and an embargo / publish protocol — is what I have in mind, but I am open to whatever shape DFPC prefers.

Lower-priority: if there is a CSU Forest Service forester or a DFPC analyst who works on beetle-kill mapping in the GMUG, I would value a pointer. Even a coarse "here is where to start" beats reverse-engineering it from public CSFS shapefiles.

There is no commercial element here. The data is open. The AOR is in your state. I am happy to coordinate at whatever pace DFPC prefers — I am moving slowly on purpose, and I will not be flying anywhere until the LOA, LAANC, and Part 107 are all in hand.

No rush. If the right contact is the Wildland Fire Management Section directly, point me there.

— TBD (operator name)
TBD (operator phone)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch
