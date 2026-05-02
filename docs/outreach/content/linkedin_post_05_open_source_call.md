---
platform: linkedin
target_date: 2026-05-20
length_words: 400
hashtags: [opensource, makers, dronesforgood, wildfire, ArduPilot, 3Dprinting, volunteer]
---

A call for help. wildfire-watch is open source, Apache-2.0, and built on the premise that a county-scale autonomous wildfire patrol fleet does not have to depend on any one vendor — or any one operator. The Ukrainian DrukArmy + Brave1 model proved decentralized volunteer-builder networks can ship hardware faster than any incumbent supply chain. I would like to do something analogous for civilian wildfire detection in the American West, starting in the Gunnison Valley.

Specifically, I am looking for five kinds of contributor.

**3D-printer makers.** The Phase 1 BOM points at a 3D-printed airframe (Holybro X500 V2 carbon-fiber chassis as the template; print-replaceable parts for the payload bay, GPS mast, antenna mount, camera gimbal carrier). If you have a Bambu, a Prusa, a Voron, or anything else and you want to be on a printer-rotation list for replacement parts, reach out. The .stl files will land in `hardware/3d-print/` over the next few weeks under Apache-2.0.

**ArduPilot tinkerers.** The flight-controller firmware is Cube Orange+ on ArduCopter. If you have written a custom mission script, a wildfire-relevant Lua extension, or a YAML mission template you would publish under Apache-2.0, the `firmware/` subtree wants you. Geofence-with-exclusion-polygons (so wilderness boundaries are hard-subtracted) is an open issue I would gladly hand off.

**Fire-department contacts.** If you know a fire chief in California, Colorado, Oregon, Washington, Idaho, Montana, New Mexico, or anywhere else with a beetle-killed forest and a budget — even a thirty-second LinkedIn intro is the highest-leverage thing you can do for the project. The valuation engine flags one signed Letter of Authorization as +$3M to the mid-band.

**ML / computer-vision researchers.** The Phase 1 perception stack is FASDD → FLAME-2 fine-tune on YOLOv8, with a multimodal RGB + LWIR + acoustic + behavioral wildlife fusion gate. If you have done the dataset work, the fine-tuning, or the latency-budget engineering, the `ml/` subtree wants you.

**Anyone who flies a Mavic in the Gunnison Valley.** If you live in the Crested Butte / Gunnison corridor and you fly drones recreationally, I would value 30 minutes of local knowledge — flight conditions, wind patterns, ridgelines that block radio, the actual texture of operating an airframe at 9,000 ft.

A Discord / Matrix invite is at TBD (will edit this post once stood up).

Repo: https://github.com/arigatoexpress/wildfire-watch
Email: aristotlespec@gmail.com

No commercial element. No equity. Just the project, in the open, with whoever wants to build it.
