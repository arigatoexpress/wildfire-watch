---
platform: linkedin
target_date: 2026-05-13
length_words: 400
hashtags: [wildfire, opensource, dronesforgood, simulation, Colorado, raspberrypi, Python]
---

Phase 0 of wildfire-watch ships on hardware most people already own.

If you have a Mac mini or any laptop with Python 3.11 plus a copy of the repo, you can be looking at a post-flight map in your browser — with a synthetic smoke plume, the AOR polygon, the planned route, the flown polyline, and the fusion-gate confidence chart — within sixty seconds of cloning.

[ placeholder: screenshot of the browser viewer showing the Slate River drainage with route, plume pin, and Chart.js confidence overlay ]

Here is the entire onramp:

```
git clone https://github.com/arigatoexpress/wildfire-watch
cd wildfire-watch
python3 -m pytest -q                                   # 240 tests, under 7 seconds
python3 -m sim.cli run \
    sim/missions/gunnison_slate_river_1km2.yaml \
    --scenario single_smoke_plume --speed-multiplier 5
python3 -m sim.web.server                              # http://127.0.0.1:8088
```

That is Phase 0. No drone required. No GPU required. The simulator is deterministic with a `--seed` argument, which means the same flight reproduces tick-for-tick — a property that turns out to matter a lot for regression-testing detection logic.

The actual hardware Phase 0 wants on top of the simulator: a DJI Mavic Mini for manual scout flights, a Mac mini for post-flight YOLO inference, and two Raspberry Pis (in my case rari1 and rari2 on Tailscale) for heartbeat and system-event emission. All three are stopgap on purpose — the DJI Mavic specifically is a Phase 0 prototype, not a foundation, because the 2026 NDAA and Sec. 848 environment make any DJI bet expire by 2027.

Phase 0.5 ($215) adds an RTL-SDR Blog v4 (ADS-B + RAWS receive), a Plantower PMS5003 for direct PM2.5 / PM10 smoke sensing, a Bosch BME688 for fire-weather, two Heltec V3 Meshtastic radios for a license-free LoRa mesh, and a Pi 5 AI HAT+ Hailo-8L for edge YOLOv8-fire at 30+ FPS.

Phase 1 ($2,613) is the Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super 8 GB + Arducam IMX477 + FLIR Lepton 3.5 + uAvionix pingRX/pingRID stack — autonomous, multimodal, ADS-B In and Remote ID compliant, and Blue UAS-substitutable per `BLUE-UAS-LINEAGE.md` in the repo.

The whole project ladders to a $25–75M strategic-acquisition conversation by mid-2027 (the math is in `docs/strategy/POSITIONING_BRIEF-2026-05-02.md`), but that is downstream. Today's leverage is something a high-school AP CS student can run in 60 seconds.

If you are a fire department or a maker who wants in: aristotlespec@gmail.com.

https://github.com/arigatoexpress/wildfire-watch
