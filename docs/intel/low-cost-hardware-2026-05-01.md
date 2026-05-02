# Low-cost hardware survey for wildfire-watch — 2026-05-01

Status: research note. Author: Sapphire intel.
Scope: pivot from "$2,500 single drone" MVP toward a layered, mesh-of-cheap-nodes posture. Frame every part by what data it produces and how that data lands in `signal_logger:18081` or the wildfire dashboard.

Owned today: DJI Mavic Mini 1 or 2, Mac mini (Sapphire commander), Raspberry Pis `rari1` (100.120.191.1) and `rari2` (100.87.225.89), both Tailscale-connected.

---

## 1. TL;DR

- **Flipper Zero ($199): SKIP for wildfire-watch.** It's a fun gadget. For the receive-only sensing this project needs (433 MHz weather telemetry, ADS-B, 915 MHz Remote ID), an [RTL-SDR Blog v4 dongle at ~$40](https://www.rtl-sdr.com/v4/) + a $10 antenna outperforms it on every relevant axis: bandwidth, sensitivity, decoder ecosystem (`rtl_433`, `dump1090`), and Pi integration. Flipper's NFC, iButton, and IR sub-systems do not contribute to fire-risk inference. Reconsider only if you start auditing your own LoRa / smart-lock / RF supply chain.
- **First $100 buys the most:** an [RTL-SDR Blog v4 starter kit](https://www.rtl-sdr.com/v4/) + a [PMS5003 particulate sensor](https://www.adafruit.com/product/3686) + a [BME688](https://shop.pimoroni.com/products/bme688-breakout). Plug into `rari1`, get smoke-particulate + fuel-moisture-proxy + multi-band RF receive online the same evening.
- **Mesh comms decision:** start with [Meshtastic on Heltec V3](https://heltec.org/product-category/lora/meshtastic/) (~$20/node) for in-AOR text + telemetry. Add one [Swarm M138](https://nootropicdesign.com/projectlab/2022/07/30/swarm-vs-iridium-for-satellite-iot/) ($150 hw, $5/mo) as the satellite-of-last-resort uplink for a remote sensor pod. Skip Iridium RockBLOCK and Starlink Mini until ROI is proven.
- **Edge AI:** the [Raspberry Pi 5 + Hailo-8L AI HAT+ at $70](https://www.jeffgeerling.com/blog/2024/testing-raspberry-pis-ai-kit-13-tops-70/) is the right starting point for a ground-station vision node (13 TOPS, M.2 over the Pi 5's PCIe lane). Coral USB Accelerator is older and slower; OAK-D Lite is great but $150+ and overkill if `rari1` is doing the inference.
- **Phase 0 deliverable today: $0.** Fly the Mavic Mini, ingest its photo+video manually, build the `wildfire_signal` JSON adapter on Mac mini, and stand up `rari1` as a passive sensor + ML-inference node. No new hardware required.
- **Total Phase 0.5 budget cap: $300** gets a real distributed sensor mesh (1 RF SDR, 1 environmental node, 2 Meshtastic radios, 1 AI HAT) without touching the existing $2,500 drone BOM.

---

## 2. Phase 0 ($0) — what to build with what's already on the bench

The Mavic Mini 1/2 is a 249 g consumer drone. It does not run on-board CV. It does not have thermal. It cannot lift a Jetson. **It is still useful** because it produces the one thing we don't have: airborne photos of the AOR, geo-tagged.

### 2.1 What the Mavic Mini contributes

| Capability | How |
|---|---|
| Visual reconnaissance | Manual flights with [Litchi for DJI](https://flylitchi.com/help) (Mavic Mini 1 + Mini 2 supported as of 2026) for waypoint missions; export photos + GPS EXIF |
| Wildfire ground-truth dataset | Each flight produces ~30-100 geo-tagged JPEGs. Feed those into the `ml/fire_detection/` training set as negative samples (no smoke) and, after a real burn, positive samples |
| Pre-flight zone survey | Mark hot-spots (dead trees, dry brush) into `missions/zones/*.geojson` before deploying the real Holybro X500 |
| FAA Remote ID experience | Both Minis have built-in FAA-compliant Remote ID broadcast; a good live target for the Remote ID receiver work in Phase 0.5 |

**What the Mavic Mini does NOT do:** real-time uplink to Sapphire (no SDK on the gimbal stream), thermal imaging, on-board ML, BVLOS. Treat it as a **reconnaissance camera + flight-skill trainer**, not a sensor node.

### 2.2 What the Mac mini already does

Per CLAUDE.md the Mac mini already runs:
- `signal_logger:18081` (wildfire signals can land here under their own JSONL file, same plumbing as trading)
- `dashboard:8080` (add `/wildfire` route)
- `inference-proxy:11435` (4-tier: GPU on Windows → Pi → Mac → Kimi)
- `hermes-agent` (Telegram bot — fire alerts on the same channel as trading)

**Phase 0 work item:** in `sapphire_integration/`, add a JSONL writer that POSTs `wildfire_signal` events to `signal_logger:18081`. Schema is already drafted in `sapphire_integration/wildfire_signal_schema.json`. Hermes already paginates alerts; one Python adapter is the whole plumbing.

### 2.3 What rari1 and rari2 can do today

Both are Pi 5s (per CLAUDE.md), Tailscale-meshed, Ollama running. With zero new hardware:
- **rari1 (100.120.191.1):** designate as the *sensor node*. Cron a `python sensor_poll.py` that scrapes free public APIs:
  - [USFS RAWS](https://raws.nifc.gov/) gridded fire-weather (temp, RH, wind, fuel moisture)
  - [NIFC public RAWS layer](https://data-nifc.opendata.arcgis.com/datasets/nifc::public-view-interagency-remote-automatic-weather-stations-raws/about)
  - NOAA HRRR / GFS wind & RH point forecasts
  - GOES-East / GOES-West fire detection product (FDC)
  - PurpleAir + AirNow PM2.5 within 25 km of zone
- **rari2 (100.87.225.89):** designate as the *inference node*. Run YOLOv8n-fire on the 4 Mavic JPEGs that come back from a flight; emit confidence to signal_logger.

### 2.4 The 3-sentence Phase 0 deliverable

Fly a Mavic Mini patrol over the target AOR weekly, producing 30-100 geo-tagged JPEGs that are dropped into a Tailscale-shared folder on `rari2` for YOLOv8n-fire to chew through. Have `rari1` poll RAWS + NOAA HRRR + GOES FDC every 15 minutes and write a hourly fire-weather risk score to `data/wildfire_signals.jsonl`. Both feeds POST to `signal_logger:18081`, surface on `dashboard:8080/wildfire`, and ping hermes Telegram on threshold breach — total cost $0 and total new hardware: zero.

---

## 3. Phase 0.5 (≤ $300) — first 5 cheap upgrades, ranked by impact-per-dollar

| Rank | Item | Cost | What it adds | Where it plugs in |
|---|---|---:|---|---|
| 1 | [RTL-SDR Blog v4 starter kit](https://www.rtl-sdr.com/v4/) (dongle + dipole) | $40 | ADS-B, RAWS-via-GOES-downlink (137 MHz), 433 MHz weather sensors via [`rtl_433`](https://github.com/merbanan/rtl_433), Bluetooth/WiFi Remote ID via companion sniffer | USB on `rari1` |
| 2 | [PMS5003 PM2.5/PM10 sensor](https://www.adafruit.com/product/3686) | $25 | Smoke-plume detection at the ground station — empirically reads high during wildfires per [Pimoroni community](https://shop.pimoroni.com/products/pms5003-particulate-matter-sensor-with-cable) | UART or USB-UART on `rari1`, polled at 10s |
| 3 | [BME688 environmental sensor](https://shop.pimoroni.com/products/bme688-breakout) | $20 | Temp + RH + pressure + VOC; RH is the single best fuel-moisture proxy without going to soil probes | I²C on `rari1` |
| 4 | 2 × [Heltec WiFi LoRa 32 V3 + antenna + case](https://heltec.org/product-category/lora/meshtastic/) | $50 ($25 ea) | [Meshtastic](https://meshtastic.org) mesh between drone takeoff point and Mac mini; survives LTE outage; carries fire-alert text + GPS pings | USB/UART; Meshtastic Python API → signal_logger |
| 5 | [Raspberry Pi 5 AI HAT+ Hailo-8L 13 TOPS](https://www.amazon.com/AI-HAT-Intelligence-Accelerator-8L-13TOP/dp/B0DM956761) | $70 | Frees `rari2` from Ollama, runs YOLOv8 fire/smoke at 30+ FPS, brings inference home from cloud | Pi 5 PCIe via official AI HAT+ |

**Subtotal: $205.** Buffer left for shipping + a [PCIe x1 ribbon for rari1](https://www.pishop.us) or a cheap [12V LiFePO4 1Ah cell](https://www.litime.com/) for the LoRa node.

Decision rationale: this stack lets a single Pi simultaneously **listen** to public RF (RAWS, ADS-B, Remote ID), **measure** the air around the ground station (smoke, RH), **mesh-relay** alerts when LTE is down, and **infer** on imagery — all four pillars of a wildfire-watch node, for less than the cost of one Cube Orange+.

---

## 4. Sub-GHz RF intel — what to listen for and how

The wildfire AOR is full of useful RF traffic. The job is to receive it, decode it, and pipe it to `signal_logger`.

### 4.1 Receivers

| Receiver | Cost | Why pick it |
|---|---:|---|
| [RTL-SDR Blog v4](https://www.rtl-sdr.com/v4/) | $40 | Built-in HF direct sampling, 1 PPM TCXO, 500 kHz–1.7 GHz. Best $/perf in 2026. |
| [Nooelec NESDR Smart v5](https://www.nooelec.com/store/nesdr-smart-xtr-bundle.html) | $35 | Clone-class but solid; secondary unit for ADS-B-only |
| [Airspy Mini](https://airspy.com/airspy-mini/) | $99 | Higher dynamic range; only worth it if RTL-SDR overloads near a 100 W repeater |
| [HackRF One](https://greatscottgadgets.com/hackrf/one/) | $300+ | TX-capable. **Not recommended** — a civilian wildfire user has no legal need to transmit on aviation/RAWS/ISM bands. The receive-only path covers everything we want. |
| [Ubertooth One](https://greatscottgadgets.com/ubertoothone/) | discontinued | Skip. Bluetooth Remote ID can be sniffed by an ESP32-S3 or with a $10 Nordic nRF52840 dongle. |

### 4.2 Decoders to run on `rari1`

- **`rtl_433`** ([github](https://github.com/merbanan/rtl_433), [device list](https://triq.org/rtl_433/)) — decodes Acurite 5n1/Atlas, Davis Vue, Ambient WS-2902, Ecowitt WH-series, Fine Offset, Oregon Scientific, La Crosse. **Output mode: MQTT or stdout JSON → systemd → POST to signal_logger.** Any neighbor's Acurite within 200 m becomes a free zone-edge fire-weather sensor.
- **`dump1090`** for ADS-B at 1090 MHz. Shows manned aircraft over the AOR. Critical for **TFR awareness** when fire incident command pushes a TFR — your drone needs to land BEFORE a SEAT or Type 1 rotor-wing shows up.
- **`acarsdec` + `dumphfdl`** — ACARS/HFDL for tactical aviation comms (often used by USFS air ops). Receive-only, fully legal.
- **OsmoCom GnuRadio flowgraphs** — for the GOES downlink at 1694.1 MHz, RAWS reports come through this with a small dish ($30 grid + $20 LNA). Probably Phase 1, not Phase 0.5.
- **[snifflee](https://github.com/sxlmnwb/sniffle) / nRF52840 + WarDragon stack** — Drone Remote ID broadcast frames over Bluetooth 5 LR + WiFi NaN. See [WarDragon write-up at rtl-sdr.com](https://www.rtl-sdr.com/wardragon-real-time-drone-remote-id-tracking-with-snifflee-tar1090-and-atak/). $30 dongle + open source = zero-cost airspace deconfliction.

### 4.3 RAWS — the realistic path

[RAWS](https://en.wikipedia.org/wiki/Remote_Automated_Weather_Station) stations transmit via GOES on UHF (401–402 MHz) — receivable but the protocol is proprietary DCS. **Easier path: pull the public REST feed** from [raws.nifc.gov](https://raws.nifc.gov/) or the [NIFC ArcGIS endpoint](https://data-nifc.opendata.arcgis.com/datasets/nifc::public-view-interagency-remote-automatic-weather-stations-raws/about). Costs $0 and updates hourly. Save the SDR for the *neighbor's* Acurite within radio range of the AOR.

### 4.4 Drone Remote ID — what receive-side actually buys you

The FAA Remote ID rule (effective 2024 enforcement, fully entrenched 2026) means **every legal drone in the AOR is broadcasting its location, ID, and operator location** over BLE Long Range or WiFi NaN. With a $30 nRF52840 USB dongle on `rari1`:

- See every other drone in the AOR — including your own Mavic Mini for sanity.
- Auto-land your X500 if a manned firefighting aircraft enters the airspace (combined with `dump1090` ADS-B feed).
- Exposes you to [DroneTag Scout](https://dronetag.com/receivers/) / [DroneScout](https://dronescout.co/) data formats — pre-built receivers exist at $300-900 for fire-department deployments, but for our use the OSS [drone-remote-id](https://drone-remote-id.com/) stack is sufficient.

---

## 5. Environmental sensor stack — $200 builds a real ground node

Goal: one weatherproof box at the AOR edge, solar-powered, reporting to `signal_logger` every minute.

| Sensor | Cost | What it reports | Why it matters for fire |
|---|---:|---|---|
| [PMS5003](https://www.adafruit.com/product/3686) (Plantower) | $25 | PM1, PM2.5, PM10 µg/m³ | **Direct smoke detection.** Spikes 5-30× during wildfires. Most underrated sensor in this list. |
| [BME688](https://shop.pimoroni.com/products/bme688-breakout) (Bosch) | $20 | T, RH, P, gas resistance | RH < 25% + T > 32 °C is the canonical red-flag fire-weather signature |
| [SHT40](https://shop.pimoroni.com/products/sht40-breakout) (Sensirion) | $10 | Precision T+RH (±0.1 °C, ±1.5% RH) | Calibration reference for the BME688 |
| [Davis Anemometer 6410 + reed sensor](https://www.davisinstruments.com) clone | $35 | Wind speed + direction | Wind is the #1 fire-spread variable |
| [Vegetronix VH400 soil moisture probe](https://vegetronix.com/soil-moisture-sensor) | $40 | Volumetric water content (proxy for live fuel moisture) | Direct input into Nelson dead-fuel model |
| [MQ-2 + MQ-7 combustion gas](https://www.adafruit.com/) | $10 | CO + smoke + LPG ppm | Cheap second-vote on PMS5003 |
| 32 GB SD + Pi Zero 2 W + waterproof case | $60 | Edge buffer, MQTT pub | Survives LTE outage; ships data when reconnected |

**Total: ~$200.** Mounted on a 6 ft 1" pole + grounding rod, draws ~1 W average. With Phase 0.5 LoRa it can be 5+ km from any LTE/WiFi.

Bridges to `signal_logger`: [`ecowitt2mqtt`](https://github.com/bachya/ecowitt2mqtt) if you go with an Ecowitt WS90 instead of DIY (~$150 saves a lot of soldering); or a 60-line Python Pi Zero script publishing JSON over Tailscale.

For a **commercial fast path**: a [Davis Vantage Pro 2 ($600)](https://www.davisinstruments.com) with the [Davis Vantage HA integration](https://www.home-assistant.io/integrations/davis_vantage/) gives a full pro-grade fire-weather station with one wire. Worth it if the AOR is a commercial property and the partner is paying.

---

## 6. Mesh comms — recommended: Meshtastic + Swarm

Three contenders:

### 6.1 Meshtastic on LoRa — recommended primary

[Meshtastic](https://meshtastic.org) on a [Heltec V3 board (~$20)](https://heltec.org/product-category/lora/meshtastic/) gives encrypted, mesh-routed text + GPS over 915 MHz LoRa with 5-30 km line-of-sight range, multi-watt nodes ([RAK Wireless 1 W gateways are 2026 new](https://store.rakwireless.com/collections/meshtastic)) extending that to 50+ km. License-free in the US (915 MHz ISM). Survives LTE outages. Battery-friendly: a 2200 mAh 18650 runs a node for a week.

**Wildfire-watch use:** a Meshtastic node on the drone, one at the truck, one at the operator's house, one at the IC tent. Fire alert text = 200 bytes = transmits in 200 ms. The sensor pod from §5 also gets a Meshtastic radio so it can report when LTE is dead.

### 6.2 Iridium / Swarm — secondary, only for sat-uplink

| Option | Hardware | Airtime | Best for |
|---|---:|---|---|
| [RockBLOCK 9603 (Iridium SBD)](https://www.groundcontrol.com/product/rockblock-9603-compact-plug-and-play-satellite-transmitter/) | $267 + $70 antenna | $17/mo + $0.14/credit (50 bytes) | Mission-critical, low-latency, near-global |
| [Swarm M138](https://nootropicdesign.com/projectlab/2022/07/30/swarm-vs-iridium-for-satellite-iot/) | $150 | $5/mo (192 bytes/packet, ~10 min latency) | Cheapest sat-IoT in 2026; perfect for a remote sensor pod that just needs to say "I'm alive, T=34°C, RH=18%" |

**Recommendation:** if you need any sat uplink, Swarm M138 is a 1-of category. Iridium is for "ambulance won't get here in time" scenarios; we don't need <60 s latency for a 6-hour fire-weather forecast cycle.

### 6.3 Starlink Mini — overkill for our payload

[Starlink Mini](https://www.starlink.com/business/mini) at $499 hardware + $50/mo Roam service is fantastic but it's a 100 Mbps backbone for video, not for the few KB/min of sensor data we'd send. Recommend only for a fire-incident command vehicle deployment with live drone video. Not Phase 0.5, not Phase 1.

### 6.4 Reticulum and APRS — interesting, deferred

[Reticulum](https://reticulum.network) over LoRa is philosophically aligned (decentralized, encrypted, transport-agnostic) but Meshtastic has 100× the install base and existing mobile apps. APRS over 144.39 MHz works but requires a HAM Technician license and the user base is shrinking. Defer.

### 6.5 Recommendation

**Two-layer comms:** Meshtastic primary (in-AOR + 50-km perimeter), Swarm M138 fallback (only on the most remote sensor pod). Total Phase 0.5+1 cost: $50-200.

---

## 7. Edge inference — what to add to a Pi to make it a vision node

The Mac mini already runs `inference-proxy:11435` and the Sapphire ML stack, so cloud / remote inference is solved. The interesting question is **what to add to rari1 / rari2** so they can chew through Mavic Mini photos locally.

| Option | Cost | TOPS | Pro / Con |
|---|---:|---:|---|
| [Raspberry Pi AI Kit / AI HAT+ Hailo-8L](https://www.raspberrypi.com/products/ai-hat) | $70 | 13 | Best $/TOPS in 2026, official Pi support, M.2 over PCIe ([Geerling benchmark](https://www.jeffgeerling.com/blog/2024/testing-raspberry-pis-ai-kit-13-tops-70/)) |
| [AI HAT+ Hailo-8 (full)](https://www.raspberrypi.com/products/ai-hat) | $110 | 26 | If you want headroom for YOLOv8m or SAM-mobile |
| [Coral USB Accelerator](https://www.coral.ai/products/accelerator) | $60 | 4 | Older (2019), 1-2 FPS on Pi 5 [per Seeed comparison](https://www.seeedstudio.com/blog/2024/07/16/raspberry-pi-ai-kit-vs-coral-usb-accelerator-vs-coral-m-2-accelerator-with-dual-edge-tpu/). Skip in 2026. |
| [Luxonis OAK-D Lite](https://shop.luxonis.com/) | $150 | 4 (Myriad X) | All-in-one stereo camera + on-board CV. Brilliant for a drone-mounted node, overkill on the ground. |
| [ESP32-S3-CAM (XIAO Sense)](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html) | $14 | <0.1 | TinyML smoke classifier on a $14 board. **Distributed visual nodes** at $20/each could be deployed in the dozens — see [LILYGO T-Camera S3](https://www.hackster.io/news/lilygo-launches-esp32-s3-based-t-camera-s3-for-tinyml-computer-vision-projects-47d1a46249ec). Genuinely promising for Phase 1. |

**Recommendation:** Pi 5 + Hailo-8L AI HAT+ ($70) on `rari2`, ESP32-S3-CAM ($14) for any "stick a 4th camera in a tree on solar" experiments in Phase 1. Skip Coral; revisit OAK-D when the Holybro X500 build starts and we want a stereo CV camera on the drone (different decision then).

---

## 8. Flipper Zero — honest verdict

**Skip.** $199 spent on a Flipper Zero buys ~$30 of relevant capability for wildfire-watch.

| Flipper subsystem | Wildfire-watch relevance |
|---|---|
| 433/868/915 MHz sub-GHz RX/TX | Inferior to a $40 RTL-SDR for receive (lower bandwidth, no continuous waterfall, smaller decoder ecosystem). For transmit: we don't transmit. |
| 125 kHz / 13.56 MHz NFC | Could tag drone batteries / SD cards for inventory. Cute, but a $5 NFC reader on the Mac mini does it cheaper. |
| iButton / 1-Wire | DS18B20 temperature probes are useful at remote sensor sites — but you connect them to a Pi, not to a Flipper. |
| Infrared TX | Zero relevance. |
| GPIO + GPIO extension boards | Sensible for a tinkerer; same GPIO is already free on `rari1` and `rari2`. |
| 2.4 GHz (with sub-board) | An ESP32-S3 covers this for $14. |

The Flipper is a delightful general-purpose pen-test toy. **It is not a wildfire sensor node.** The closest justified use case would be auditing the *drone's own* RC link (915 MHz Holybro SiK V3) for jamming/interference signature, but a $40 SDR with `gqrx` does that better.

**Verdict: skip until the project pivots into RF-supply-chain-audit territory.** That's a different mission.

---

## 9. Updated BOM — phase tagging

`hardware/bom.csv` is updated to include a `phase` column. New rows tagged `phase-0.5` (low-cost augmentations) and `phase-1` (sensor pod + edge AI build-out). Existing drone parts retain their place under `phase-1` (the airframe is still the centerpiece, just no longer the *only* deliverable).

---

## Sources

- [RTL-SDR Blog V4 product page](https://www.rtl-sdr.com/v4/)
- [RTL-SDR V4 review on policeradioencryption.com](https://policeradioencryption.com/learn/rtl-sdr-v4-review)
- [rtl_433 GitHub](https://github.com/merbanan/rtl_433)
- [rtl_433 device list / triq.org](https://triq.org/rtl_433/)
- [Acurite device support in rtl_433](https://github.com/merbanan/rtl_433/blob/master/src/devices/acurite.c)
- [Pimoroni PMS5003 listing](https://shop.pimoroni.com/en-us/products/pms5003-particulate-matter-sensor-with-cable)
- [Adafruit PMS5003 with breadboard adapter](https://www.adafruit.com/product/3686)
- [BME688 Pimoroni breakout](https://shop.pimoroni.com/products/bme688-breakout)
- [Vegetronix VH400 spec page](https://vegetronix.com/soil-moisture-sensor)
- [Raspberry Pi RAWS forum reference](https://forums.raspberrypi.com/viewtopic.php?t=276916)
- [Heltec Meshtastic boards](https://heltec.org/product-category/lora/meshtastic/)
- [RAK Wireless Meshtastic store](https://store.rakwireless.com/collections/meshtastic)
- [Best Meshtastic devices 2026 — Ham Radio Therapy](https://hamradiotherapy.com/lora-mesh-networks/best-meshtastic-device/)
- [Rokland Meshtastic + LILYGO T-Beam pricing](https://store.rokland.com/pages/meshtastic-hardware-rak-lilygo)
- [RockBLOCK 9603 Ground Control](https://www.groundcontrol.com/product/rockblock-9603-compact-plug-and-play-satellite-transmitter/)
- [Swarm vs Iridium for IoT — Project Lab](https://nootropicdesign.com/projectlab/2022/07/30/swarm-vs-iridium-for-satellite-iot/)
- [SparkFun RockBLOCK 9603N](https://www.sparkfun.com/rockblock-9603n-iridium-satcomm-module.html)
- [Raspberry Pi AI Kit / Hailo-8L review — Jeff Geerling](https://www.jeffgeerling.com/blog/2024/testing-raspberry-pis-ai-kit-13-tops-70/)
- [Frigate + Hailo on Pi — Jeff Geerling 2026](https://www.jeffgeerling.com/blog/2026/frigate-with-hailo-for-object-detection-on-a-raspberry-pi/)
- [Coral USB Accelerator vs Hailo-8L — Seeed comparison](https://www.seeedstudio.com/blog/2024/07/16/raspberry-pi-ai-kit-vs-coral-usb-accelerator-vs-coral-m-2-accelerator-with-dual-edge-tpu/)
- [Coral USB Accelerator product page](https://www.coral.ai/products/accelerator)
- [u-blox ZED-F9P module](https://www.u-blox.com/en/product/zed-f9p-module)
- [u-blox NEO-M9N module](https://www.u-blox.com/en/product/neo-m9n-module)
- [ArduSimple simpleRTK2B board](https://www.ardusimple.com/product/simplertk2b/)
- [USFS RAWS portal](https://raws.nifc.gov/)
- [NIFC RAWS public ArcGIS feature service](https://data-nifc.opendata.arcgis.com/datasets/nifc::public-view-interagency-remote-automatic-weather-stations-raws/about)
- [Wikipedia: Remote Automated Weather Station](https://en.wikipedia.org/wiki/Remote_Automated_Weather_Station)
- [HackRF One — Great Scott Gadgets](https://greatscottgadgets.com/hackrf/one/)
- [Ubertooth One — Great Scott Gadgets](https://greatscottgadgets.com/ubertoothone/)
- [Flipper Zero product page](https://flipper.net/products/flipper-zero)
- [Flipper Zero 2026 review — Comicbook.com](https://comicbook.com/gear/review/flipper-zero-review-multi-tool-for-tech-tinkerers/)
- [Flipper Zero — Kyser Clark pen-test review](https://www.kyserclark.com/post/is-the-flipper-zero-worth-it-a-penetration-tester-s-review)
- [Litchi for DJI Mavic Mini](https://flylitchi.com/help)
- [Drone Remote ID overview — FAA](https://www.faa.gov/uas/getting_started/remote_id)
- [Drone Remote ID compliance 2026 — Rotate](https://www.rotatepilot.com/guides/remote-id-guide)
- [WarDragon Remote ID stack — RTL-SDR.com](https://www.rtl-sdr.com/wardragon-real-time-drone-remote-id-tracking-with-snifflee-tar1090-and-atak/)
- [DroneTag RIDER product](https://www.dronetag.com/products/rider)
- [DroneScout receivers](https://dronescout.co/dronescout-remote-id-receiver/)
- [Ecowitt Home Assistant integration](https://www.home-assistant.io/integrations/ecowitt/)
- [ecowitt2mqtt GitHub](https://github.com/bachya/ecowitt2mqtt)
- [Davis Vantage Pro 2 + HA — Home Assistant](https://www.home-assistant.io/integrations/ambient_station/)
- [LILYGO T-Camera S3 for TinyML](https://www.hackster.io/news/lilygo-launches-esp32-s3-based-t-camera-s3-for-tinyml-computer-vision-projects-47d1a46249ec)
- [XIAO ESP32-S3 Sense — Seeed](https://www.seeedstudio.com/XIAO-ESP32S3-Sense-p-5639.html)
- [LiTime 12 V 50 Ah LiFePO4](https://www.litime.com/products/litime-12v-50ah-lifepo4-lithium-ion-battery)
- [Off-grid LiFePO4 sizing calculator](https://lifepo4calculator.com/en/)
