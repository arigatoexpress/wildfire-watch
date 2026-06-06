# Wildfire Watch: FIREFIGHT

A playable simulator layered on the real wildfire-watch AOR. You pilot a
suppression drone over the corridor's **most critical fire zone** —
`slate-river-drainage` (fuel load **HIGH**, beetle-kill spruce/fir) — and race
the autonomous fleet to put out a spreading wildfire before it reaches the
cabins in the wildland-urban interface.

It's a game *and* a data generator: every match is recorded in the project's
real flight-log schema and exports a `drones.jsonl` + `manifest.json` bundle
that drops straight into `wildfire-watch-flights/` for imitation / RL training.

Two builds, same simulation core:

- **3D** (`index.html`) — true WebGL flight sim: heightmap terrain of the
  drainage, an instanced **pine forest** that chars as it burns, cabins, 3D
  quadcopters with spinning rotors and banking, additive flame/smoke/spray
  particles, a chase camera, a **minimap/radar**, synthesized **audio**, and
  **controller rumble**. Built on a locally-vendored **Three.js r128**
  (`vendor/three.min.js`) — no CDN, runs offline.
- **2D** (`2d.html`) — the original top-down arcade view. Lighter, identical
  rules.

## Controllers (Xbox / Switch Pro / PlayStation / generic USB)

Plug in a controller and **press any button** — it's auto-detected through the
browser Gamepad API. The menu shows `CONTROLLER CONNECTED — <name>`, and a short
rumble confirms it. Button *positions* are used (not letters), so the bottom
face button is "confirm / bomb" whether it reads A (Xbox) or B (Nintendo).

- **Live input test:** press **`I`** (or the Back/Select/− button) any time to
  toggle an overlay showing both sticks and every button lighting up — use it to
  confirm your pad maps correctly before you fly.
- **Rumble** fires on water-bomb drops, low battery, pickups, and win/lose
  (controllers that expose `vibrationActuator`).
- Switch Pro controllers / Joy-Con grips and DualShock/DualSense report the W3C
  `standard` mapping in Chrome/Edge, so they work out of the box. Connect over
  USB or Bluetooth.

## Run it

No build step, no network dependency, works offline.

```bash
# from repo root
python3 -m http.server 8099 --directory game
# then open http://127.0.0.1:8099   (3D)   ·   .../2d.html   (top-down)
```

Or just open `game/index.html` directly in a browser (`file://` works too).

## Controls — 3D (`index.html`)

Movement is **screen-relative** (W = away from the camera, D = screen-right) and
the camera is a **free follow-cam** — it stays where you point it and only
orbits on your input, so left/right never flips on you. A reticle on the ground
shows where your suppressant will land.

| Action        | Keyboard                       | Controller (standard)   |
|---------------|--------------------------------|-------------------------|
| Fly           | `WASD` / arrows (screen-rel.)  | left stick / D-pad      |
| Spray         | `Space` / `Shift` / left-click | RT (hold)               |
| Water bomb    | `Enter` / right-click          | A (bottom face button)  |
| Altitude      | `R` / `F`                      | RB / LB                 |
| Orbit camera  | `Q` / `E` / mouse-drag         | right stick             |
| Zoom          | mouse wheel                    | —                       |
| Menu navigate | `↑`/`↓` or `1` `2` `3`         | left stick / D-pad      |
| Menu launch   | `Enter`                        | A / Start / RT          |
| Input test    | `I`                            | Back / Select / −       |
| Download log  | `L` (on results screen)        | X                       |

## Controls — 2D (`2d.html`)

| Action      | Keyboard                    | Controller            |
|-------------|-----------------------------|-----------------------|
| Move        | `WASD` / arrow keys         | left stick            |
| Spray       | `Space` / `Shift` (hold)    | RT / RB (hold)        |
| Water bomb  | `E` / `Enter`               | A                     |
| Menu select | `1` `2` `3` / `Enter`       | A / D-pad / Start     |
| Download log| `D` (on results screen)     | X                     |

## How to play

- **Spray** burning cells to knock them down — the cell you put out is credited
  to **you** (or the AI that did it). Most cells extinguished wins.
- Your **suppressant tank** drains as you spray. Fly over the **Slate River**
  (the blue channel) to refill — it's also a natural firebreak.
- **Water bombs** clear a wide radius instantly and pre-wet the ground. Grab the
  floating pickups for more (**B** = bombs, **F** = fuel/tank refill, **S** = speed).
- **Battery** drains with throttle and the spray pump; land on your **home pad**
  (the colored ring) to swap the battery and reload retardant. It limps on a low
  cell — return to home before it dies.
- **Wind** (compass) and **slope** drive the fire: it runs faster downwind and
  uphill, and a crowning fire throws embers ahead. Fight the downwind/upslope edge.
- Pre-spraying unburnt forest lays a wet **firebreak** that resists ignition.
- Protect the **cabins**. Lose them all and you burn over.
- A round ends when the fire is **contained**, the **timer** runs out, or
  everything burns.

## "Train AI against me"

- Every agent's per-tick state is logged at 10 Hz in the wildfire-watch
  flight-log schema (`drone_id`, `lat`, `lon`, `heading_deg`, `speed_mps`,
  `battery_pct`, `suppressant_pct`, plus simulated onboard perception
  `rgb_score` / `thermal_delta_c` / `gate_state`, and `action`) with **real
  Slate River lat/lon** derived from the zone polygon in
  `missions/zones/gunnison_crested_butte_corridor.geojson`.
- On the results screen press **L** (or controller **X**) to export
  `FIREFIGHT3D-<stamp>_human_vs_ai__drones.jsonl` and `__manifest.json`. The
  manifest mirrors `sim` swarm manifests (`zone_id`, `seed`, `tick_hz`,
  `wind_*`, `airframe`, per-agent scores, result). Drop the pair into a
  `wildfire-watch-flights/FIREFIGHT3D-.../` directory and it parses like any
  recorded flight — `agent: human|ai` separates your demonstrations from the
  bots for imitation learning.
- **Adaptive opponents:** your best result is stored in `localStorage`. Beat the
  lead AI drone and next match it "trains on your winning run" — the fleet comes
  back faster and more aggressive.

### Detection signals → the real pipeline

The match log carries the same perception fields (`rgb_score`,
`thermal_delta_c`) the real `drones.jsonl` does, so a match can be replayed
through the **canonical fusion gate + signal builder** — it does not
reimplement them, it composes against `ml/fire_detection/infer.py`:

```bash
# from repo root, after exporting a match log
python3 game/firefight_to_signals.py FIREFIGHT3D-<stamp>_human_vs_ai__drones.jsonl
# -> writes FIREFIGHT3D-<stamp>_human_vs_ai__signals.jsonl
```

`firefight_to_signals.py` runs each frame through `infer.should_emit()` (the
multimodal `rgb >= 0.65` + `thermal_delta >= 5 °C` + persistence gate) and emits
`wildfire_signal` v1.0.0 records via `infer.build_signal()`. The output is
schema-valid against `sapphire_integration/wildfire_signal_schema.json` and
drops straight into the Sapphire `signal_logger` ingest path — so playing the
game produces real, schema-conformant detection signals.

## Where the realism comes from

| Game element            | Real project source                                            |
|-------------------------|----------------------------------------------------------------|
| Play-field bounds       | `slate-river-drainage` polygon (corridor geojson), ~9 m/cell   |
| Field elevation         | `alt_msl_m: 2743` (Slate River 1 km² mission YAML)             |
| Fuel-load heatmap        | `fuel_load_class: high` — beetle-kill spruce/fir               |
| Flight envelope         | `sim/airframe.py` Mavic-class: 16 m/s max, 9 m/s cruise, 120 m ceiling, ~13 min battery |
| Flight dynamics         | acceleration-limited inertia + banking; battery drain by throttle/spray load |
| Return-to-home pad      | `return_to_home` in the mission YAML — land to swap battery + reload |
| Fire spread             | wind- **and** slope-driven (Rothermel-flavoured) + gusts + ember spotting |
| Slate River firebreak   | the drainage the AOR is named for; also the refill source      |
| Cabins / WUI stakes     | README "first 30 minutes … 1,000 structures" framing           |
| Log schema + manifest   | `wildfire-watch-flights/*/drones.jsonl` + `manifest.json` (now logs real m/s, battery vs. retardant, AGL within ceiling) |
| Onboard perception      | `rgb_score` / `thermal_delta_c` / `gate_state` per frame — same fields the real flight log carries |
| Detection signals       | `firefight_to_signals.py` composes against `ml/fire_detection/infer.build_signal()` + `should_emit()` → schema-valid `wildfire_signal` v1.0.0 |
| Deterministic seeding   | logged `seed` reproduces the match (mulberry32)                |

> The flight + fire model is plausibility-tuned, not certified: real airframe
> speeds/endurance and wind+slope fire physics, balance-tested across difficulties
> so the fire is containable and the race is fair. It's the *game* layer — a
> companion to `sim/` (the kinematic simulator), not a replacement for it.
