# Firmware — ArduPilot Copter on Cube Orange+

## Stack

- **Autopilot**: ArduPilot Copter 4.6 (latest stable as of 2026-Q2). PX4 is a
  near-equivalent alternative; we standardize on ArduPilot for community size,
  Lua scripting, and superior failsafe handling.
- **Flight controller**: Hex/ProfiCNC Cube Orange+ on Carrier Standard.
- **Companion computer**: Jetson Orin Nano Super, MAVLink2 over UART (TELEM2 →
  Jetson UART1 at 921600 baud).

## Flashing

```bash
# 1. Install Mission Planner (Windows) or QGroundControl (cross-platform)
# 2. Connect Cube via USB-C
# 3. Mission Planner → Initial Setup → Install Firmware → Copter 4.6 stable
# 4. Calibrate accelerometer, compass, ESC, RC, battery monitor
```

## Required parameters (initial set)

```text
# Failsafe — fail-closed defaults (Sapphire pattern)
FS_BATT_ENABLE        2     # Land on critical battery
FS_GCS_ENABLE         2     # RTL on lost GCS link
FS_THR_ENABLE         3     # SmartRTL on lost RC
FS_OPTIONS            8     # Continue mission if RC lost (autonomous patrol)
GPS_HDOP_GOOD         140   # Refuse arm above this HDOP

# Geofence — hard limit
FENCE_ENABLE          1
FENCE_TYPE            7     # Altitude + Circle + Polygon
FENCE_ACTION          1     # RTL on breach
FENCE_RADIUS          1000  # 1 km from home; tune per-zone
FENCE_ALT_MAX         120   # 120 m AGL ceiling (FAA 400 ft)
FENCE_ALT_MIN         10    # 10 m floor for terrain-following

# EKF + GPS
EK3_ENABLE            1
EK3_GPS_TYPE          0     # Use GPS for horizontal + vertical

# Companion / MAVLink2
SERIAL2_PROTOCOL      2     # MAVLink 2
SERIAL2_BAUD          921   # 921600 to Jetson UART1
SR2_EXTRA1            10    # 10 Hz attitude
SR2_POSITION          5     # 5 Hz position
SR2_RAW_SENS          5
SR2_RC_CHAN           5

# ADS-B In (uAvionix pingRX Pro on SERIAL5)
SERIAL5_PROTOCOL      35    # ADSB
SERIAL5_BAUD          57
ADSB_ENABLE           1
ADSB_LIST_RADIUS      5000  # 5 km tracked
AVD_ENABLE            1     # Auto-avoid
AVD_W_ACTION          2     # RTL on collision warning

# Remote ID (uAvionix pingRID on CAN1)
CAN_P1_DRIVER         1
DID_ENABLE            1
DID_OPTIONS           1     # Enforce ARM check
```

Save these as `firmware/params/wildfire_watch_base.parm`. Per-unit overrides go in
`firmware/params/<unit_id>.parm`.

## Mission scripting

Patrol missions are auto-generated from a GeoJSON zone (see `missions/`):

```bash
python firmware/zone_to_mission.py \
  --zone missions/zones/example_park.geojson \
  --altitude_agl 80 \
  --speed_mps 8 \
  --overlap_pct 30 \
  --output firmware/missions/example_park.waypoints
```

Loaded via Mission Planner or pushed via MAVLink from the ground station.

## MAVLink topics consumed by Jetson

| Topic | Rate | Use |
|---|---:|---|
| `GLOBAL_POSITION_INT` | 5 Hz | Sign and stamp every emitted signal |
| `ATTITUDE` | 10 Hz | Camera-ray geolocation of detected targets |
| `BATTERY_STATUS` | 1 Hz | Mission-abort decisions |
| `HEARTBEAT` | 1 Hz | Cube health |
| `STATUSTEXT` | as-emitted | Forward to ground station log |

## MAVLink topics emitted by Jetson

| Topic | Rate | Use |
|---|---:|---|
| `STATUSTEXT` (severity 4-6) | as-emitted | Inference status, e.g. "WFW: smoke 0.78" |
| `COMMAND_LONG` (`MAV_CMD_NAV_LOITER_UNLIM`) | rare | Auto-loiter on high-confidence detection |

We **do not** emit `SET_POSITION_TARGET` or arm/disarm commands from the Jetson.
Cube remains the sole arming authority.

## Pre-flight checklist (enforced by ground station refusal-to-arm)

1. GPS HDOP < 1.4
2. Battery > 80% nominal
3. Compass not warning
4. ADS-B receiver heartbeat present
5. Remote ID broadcasting (verified via second-radio sniff)
6. Geofence loaded for current zone
7. Wind speed < 8 m/s (per ground-station weather feed)
8. No active TFR over zone (per FAA TFR list query)
9. RPIC has signed off via ground-station UI

## OTA model updates

The Jetson runs a small auth'd updater that pulls signed model bundles from
the operator's GCS bucket only when on Tailscale and at the home base. Drones
do **not** auto-update mid-flight or in the field.

## Logs

ArduPilot DataFlash log → microSD on the Cube. Pulled at end of flight, parsed
with `pymavlink`, archived to GCS for incident review and FAA accident
reporting if needed.
