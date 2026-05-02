---
platform: linkedin
target_date: 2026-06-24
length_words: 500
hashtags: [BlueUAS, NDAA, defensetech, droneindustry, Section848, supplychain, opensource]
---

A short note for anyone building a drone-adjacent product in 2026 who has not yet thought carefully about supply-chain provenance. The legal landscape changed twice in the last six months, and "we'll deal with it later" is no longer a viable plan.

The reality, briefly. NDAA FY20 Section 848 has banned DoD procurement of UAS or UAS components from covered foreign entities since 2019. NDAA FY24 Section 1822 / the American Security Drone Act of 2023 extended that ban government-wide effective December 22, 2025 — federal civilian agencies (DHS, DOI, USDA, DOJ — all relevant to wildfire mission) cannot procure or use federal grant funds to buy non-compliant UAS. The FAR clause 52.240-1 has been in effect since November 12, 2024. As of December 23, 2025, DJI and other foreign-made UAS landed on the FCC Covered List, blocking new equipment authorizations and effectively banning import of new DJI models. The DCMA Blue UAS Cleared List grew to 50+ airframes by March 2026, and management transferred from DIU to DCMA on January 1, 2026.

Translation: any project that wants to be acquirable by Anduril, Ondas, Red Cat, AeroVironment, or any other defense-adjacent buyer with DoD or federal-civilian customers has to be built NDAA-clean from day one. "We're a US-made drone" is no longer a moat — Blue UAS has 50+ vendors. The moat is the diligence work being done before the acquirer's M&A team has to do it themselves.

What I did about it on wildfire-watch. I shipped a `BLUE-UAS-LINEAGE.md` document yesterday. It is a per-line trace of every component in the BOM — Phase 0 (DJI Mavic Mini placeholder), Phase 0.5 (RTL-SDR, PMS5003, BME688, Heltec V3 Meshtastic, Pi 5 AI HAT+), Phase 1 (Holybro X500 V2, Cube Orange+, Jetson Orin Nano Super, Arducam IMX477 / Sony sensor, FLIR Lepton 3.5, uAvionix pingRX/pingRID) — to its provenance and the Blue UAS-substitutable alternative. The Phase 1 BOM is already NDAA-eligible at the major-component level (Cube Orange+ is Australian-designed; Jetson Orin Nano Super is NVIDIA US; FLIR Lepton 3.5 is Teledyne FLIR Goleta CA; Sony IMX477 is Japanese-allied; uAvionix is Bigfork MT). The exposure points and substitution flags are the LTE modem (Quectel — covered, substitute Sierra Wireless or Telit), the battery (Tattu Li-Ion cells — covered-entity check pending, substitute Inspired Energy / Bren-Tronics), and the field charger (ISDT — covered, substitute iCharger / PowerLab).

Software is hardware-agnostic. Every signal-emit path on wildfire-watch composes against a single `build_signal()` function. Sim, post-flight processor, swarm voter, TAK emitter all run identically on a Mavic, a Skydio X10D, a Teal 2, a Parrot ANAFI USA, an Optimus, or a custom Holybro X500. That portability is the second moat.

The single-document deliverable is worth a 1.5–2× multiple uplift at acquisition time, per the strategic research in `docs/strategy/ACQUIRER_FIT-2026-05-02.md`. Anduril, Ondas, Red Cat, AeroVironment will all pay for this diligence work to be already done.

The doc is at https://github.com/arigatoexpress/wildfire-watch/blob/main/BLUE-UAS-LINEAGE.md. Apache-2.0. Steal it.
