# Simulation Ladder — kinematic to real flight

**Audience**: operator, sole RPIC, single Mac mini (Apple Silicon).
**Hardware in flight**: Holybro X500 V2 + Cube Orange+ + Jetson Orin Nano Super (per [`hardware/bom.csv`](../hardware/bom.csv) and [`docs/adr/0001-edge-compute-selection.md`](adr/0001-edge-compute-selection.md)).
**Last updated**: 2026-05-01.

This is the runbook for graduating wildfire-watch from a pure-Python kinematic
sandbox into a high-fidelity flight-controller-in-the-loop test rig, and from
there to first flight. It is a *ladder*: each rung adds fidelity and cost, you
only climb a rung when the rung below is green.

---

## 1. TL;DR

- The ladder has five rungs: **kinematic Python sim** (already built in
  [`sim/`](../sim/), runs on the Mac in seconds, no install) → **ArduPilot SITL on
  Mac** (real flight code, `MAVProxy --map`, no Gazebo) → **PX4 SITL + Gazebo
  Harmonic in a Linux VM** (rendered world, real MAVLink, ~30 min setup) →
  **HITL on the Cube Orange+** once the hardware lands (truest fidelity short
  of flight) → **real flight** under [`docs/40-faa-compliance.md`](40-faa-compliance.md).
- We are an **ArduPilot** shop (per ADR-0001 and [`firmware/README.md`](../firmware/README.md))
  and that decision still holds. We document the PX4 path because Gazebo
  Harmonic's first-class flight stack is PX4 and using PX4 SITL is the cheapest
  way to exercise a Gazebo world.
- **Gazebo on macOS Apple Silicon is unsupported by Open Robotics.** Official
  binaries cover macOS Big Sur / Monterey / Ventura on Intel only. Run Gazebo
  in a Linux VM (Lima or UTM with Apple Virtualization Framework) — do not
  fight a source build.
- ArduPilot SITL itself **does** run natively on Apple Silicon: clone, install
  Xcode CLT plus a few brews, run `sim_vehicle.py -v ArduCopter --console
  --map` and you have real ArduCopter firmware flying a fake quad in MAVProxy.
  This is the highest-leverage rung — it gets you ~80% of bug-finding value
  with zero VM overhead.
- Surprising finding: ArduPilot ships a **"Simulation on Hardware"** build
  target (`CubeOrange-SimOnHardWare`) that runs SITL physics *on the actual
  autopilot ARM core*. This is HITL with no second computer: the same Cube
  Orange+ that will fly the X500 V2 runs the simulation in its idle cycles.
  Once the Cube arrives, this is the single most valuable test rig we own.

---

## 2. Decision matrix — PX4 vs ArduPilot

| Axis | ArduPilot Copter 4.6 | PX4 v1.16 | Wildfire-watch lean |
|---|---|---|---|
| License | GPLv3 (copyleft) | BSD-3 | ArduPilot — we do not ship modified firmware |
| Vehicle types | Plane, Copter, Rover, Sub, Blimp, Antenna Tracker | Same vehicle classes | Tie |
| Lua scripting on flight controller | Yes, mature | No (uORB-only) | **ArduPilot** for failsafe scripting |
| Failsafe maturity | Battery, GCS, RC, fence, EKF — extensive params | Modular but younger | **ArduPilot** |
| ADS-B In native | Yes (`AVD_*` params, our [`firmware/README.md`](../firmware/README.md)) | Plugin / external | **ArduPilot** for our DAA stack |
| Remote ID native | Yes (`DID_*`) | Yes via uORB | Tie |
| Gazebo Harmonic support | `ardupilot_gazebo` plugin (community-blessed, official upstream) | First-class, ships with PX4 | PX4 wins fidelity, ArduPilot wins coverage |
| ROS 2 / micro-XRCE-DDS | `ardupilot_dds` (preview) | Mature, default in PX4 v1.16 | **PX4** if you need DDS |
| Community on multirotor reliability | Larger, older codebase | Tighter, modular | **ArduPilot** for long-range survey |
| Precision landing / fast inner loops | Good | Better (lower-latency control) | **PX4** for racing / industrial inspection |
| Mac SITL support | Native via Homebrew + `sim_vehicle.py` | Requires `--sim-tools` Homebrew, XQuartz, or VM | **ArduPilot** on macOS |

ADR-0001 picked ArduPilot because of the failsafe + Lua + ADS-B story; nothing
in 2026's PX4 v1.16 changes that calculus. We use **PX4 only as a Gazebo
driver** in Tier 3.

Sources: [PX4 vs ArduPilot — ThinkRobotics 2026 guide](https://thinkrobotics.com/blogs/learn/px4-vs-ardupilot-complete-comparison-guide-for-drone-developers),
[ArduPilot Discourse — when to choose what](https://discuss.ardupilot.org/t/px4-vs-ardupilot-when-to-choose-what/14262),
[PX4 Gazebo Sim docs](https://docs.px4.io/main/en/sim_gazebo_gz/).

---

## 3. Tier 1 — kinematic sim (already running)

**Where**: [`sim/`](../sim/) — sister agent is shipping it as we speak.
**Stack**: stdlib + pyyaml + requests, no NumPy, no Gazebo, no MAVLink.
**What it does**: integrates a kinematic model of a Mavic Mini 2 / Holybro
X500 V2 / generic quad ([`sim/airframe.py`](../sim/airframe.py)) along a YAML mission
([`sim/mission.py`](../sim/mission.py)) using WGS84 great-circle math
([`sim/kinematics.py`](../sim/kinematics.py)). Emits Mavic-shaped telemetry and a DJI Fly
SRT subtitle stream so the rest of the wildfire-watch pipeline (the
[`ml/fire_detection/infer.py`](../ml/fire_detection/infer.py) fusion gate) sees data shaped exactly like
post-flight footage from the real Mavic.

**When to use it**: every CI run. Every regression. Every time you change a
mission YAML or the fusion gate. Costs zero seconds of your attention.
**When it stops being enough**: the moment you need a real flight mode,
real EKF behaviour, real failsafe action, or a 3D rendered camera frame.

**Cross-reference**: this doc covers *what comes after*. Do not modify
`sim/` from this rung; it is the contract surface against `ml/`.

---

## 4. Tier 2 — ArduPilot SITL on Mac

**Goal**: real ArduCopter 4.6 firmware flying in MAVProxy, on the Mac, no VM.
**Time budget**: 60-90 minutes from clean machine to first virtual takeoff.

### 4.1 Install Xcode + Homebrew toolchain

```bash
xcode-select --install
brew update
brew install gcc-arm-none-eabi genromfs python3 gawk wxwidgets
python3 -m pip install --user empy pyserial future lxml pymavlink mavproxy
```

`mavproxy.py` is the GCS that ArduPilot SITL launches by default.

### 4.2 Clone and build

```bash
git clone --recursive https://github.com/ArduPilot/ardupilot.git
cd ardupilot
./Tools/environment_install/install-prereqs-mac.sh -y
. ~/.profile   # picks up PATH additions
./waf configure --board sitl
./waf copter
```

ArduCopter SITL builds cleanly on Apple Silicon — no Rosetta, no Docker.
Reference: [ArduPilot macOS build setup](https://ardupilot.org/dev/docs/building-setup-mac.html).

### 4.3 First flight

```bash
cd ardupilot
./Tools/autotest/sim_vehicle.py -v ArduCopter --console --map
```

Two windows pop up: a **MAVProxy console** (telemetry text) and a **map
window** (Tk-based, shows the simulated copter at the default home location).
Type `arm throttle` then `takeoff 50` in MAVProxy and you have a virtual
ArduCopter at 50 m AGL. `mode auto` runs whatever waypoints you've loaded.

Reference: [ArduPilot SITL guide](https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html).

### 4.4 Connect a real GCS

You probably want a richer GCS than MAVProxy. Two choices on Mac:

**QGroundControl** — cross-platform, signed, but non-Apple-signed builds need
the standard "right-click → Open" macOS bypass. Install via Homebrew:

```bash
brew install --cask qgroundcontrol
```

QGroundControl on Mac runs natively on Apple Silicon. Reference:
[QGroundControl download docs](https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html),
[Homebrew formula](https://formulae.brew.sh/cask/qgroundcontrol).

**Mission Planner** — first-class on Windows; on Mac runs only via
CrossOver/Wine or Parallels. Skip it on Mac unless you specifically need a
feature QGC lacks (the wildfire-watch base param file works in either).

To connect, in QGC select *Application Settings → Comm Links → Add* with type
UDP, port 14550 (the default `sim_vehicle.py` GCS port). MAVProxy will
auto-forward to QGC.

### 4.5 Load wildfire-watch base params

Once you have SITL up:

```text
MAVProxy> param load firmware/params/wildfire_watch_base.parm
MAVProxy> param fetch
```

Now SITL exhibits the same fence behaviour, failsafe profile, and SR2 stream
rates as a real Cube Orange+. This is the real win of this rung — *the
firmware behaviour you see in SITL is bit-identical to what your Cube will do
on the bench*.

### 4.6 ArduPilot SITL with ROS 2 (optional)

If you want a ROS 2 node receiving MAVLink — most importantly the
[`ground_station/`](../ground_station/) `tak_adapter.py` and `sapphire_adapter.py`
forwarders — install MAVROS in the Linux VM (Tier 3) and have it talk to
SITL on the host. Reference: [ArduPilot ROS 2 + Gazebo guide](https://ardupilot.org/dev/docs/ros2-gazebo.html).

Native ROS 2 on Apple Silicon works for ROS 2 Jazzy via the IOES-Lab
[ROS2 Jazzy macOS Native Apple Silicon](https://github.com/IOES-Lab/ROS2_Jazzy_MacOS_Native_AppleSilicon)
build, but the install is fragile. Prefer the VM unless you have a specific
reason to keep ROS on bare macOS.

---

## 5. Tier 3 — PX4 SITL + Gazebo Harmonic via a Linux VM

**Goal**: real flight code (we use PX4 here as the Gazebo driver) flying a
quadcopter in a 3D rendered world with a virtual camera, virtual GPS noise,
and virtual wind. Connect the wildfire-watch pipeline to that camera feed.

**Time budget**: 3-4 hours first time. 30 minutes every subsequent time.

### 5.1 Why a Linux VM and not native macOS

Gazebo Harmonic (LTS, supported through September 2028) ships official
binaries for Ubuntu 22.04/24.04 and macOS Big Sur / Monterey / Ventura
(*Intel only*). There is no official Apple Silicon build. Source builds
exist (the `idesign0/gz-macOS` community project) but are fragile and not
worth the time when you can run a clean Ubuntu VM that gets you a tested
binary in fifteen minutes. References:
[Gazebo Harmonic macOS source install](https://gazebosim.org/docs/harmonic/install_osx_src/),
[gz-macOS community project](https://github.com/idesign0/gz-macOS),
[Gazebo Garden EOL announcement](https://discourse.openrobotics.org/t/gazebo-garden-officially-end-of-life-x-post-gazebo-sim-community/41044).

### 5.2 VM: pick OrbStack (recommended) or UTM

**OrbStack** is fastest on Apple Silicon — Apple Virtualization Framework
under the hood, sub-second VM start, file-system mounting that just works.
It runs **arm64** Linux natively and **x86_64** Linux via Rosetta with a
small perf hit (~10-20%). Either works for Gazebo; arm64 is faster.

```bash
brew install --cask orbstack
orb create --arch arm64 ubuntu:24.04 sim
orb -m sim
```

You are now on Ubuntu 24.04 arm64 with the host file system mounted at
`/mnt/mac`. Reference: [OrbStack Linux machines](https://docs.orbstack.dev/machines/),
[OrbStack vs UTM](https://docs.orbstack.dev/compare/utm).

**UTM** with Apple Virtualization Framework is the open-source fallback if
you want to avoid OrbStack's commercial license. Slower file sharing but
identical for compute. Reference: [UTM for Mac](https://mac.getutm.app/).

Either way: do **not** use Docker Desktop alone for Gazebo — the GUI rendering
path is painful, and the official PX4 docker containers are
[Linux-only](https://docs.px4.io/main/en/test_and_ci/docker.html).

### 5.3 Install PX4 + Gazebo Harmonic in the VM

```bash
# Inside the Ubuntu VM
sudo apt update
sudo apt install git build-essential cmake python3-pip
git clone https://github.com/PX4/PX4-Autopilot.git --recursive
cd PX4-Autopilot
bash ./Tools/setup/ubuntu.sh
# log out / log back in to pick up group changes
```

The `ubuntu.sh` setup pulls Gazebo Harmonic, the toolchain, and the
simulator dependencies. Reference:
[PX4 macOS dev env](https://docs.px4.io/main/en/dev_setup/dev_env_mac) (the macOS
script also exists but is not what we want here),
[PX4 Gazebo Sim](https://docs.px4.io/main/en/sim_gazebo_gz/).

### 5.4 First flight

```bash
cd ~/PX4-Autopilot
make px4_sitl gz_x500
```

Gazebo Harmonic launches with the X500 quadcopter on a runway. PX4 SITL
opens a UDP MAVLink endpoint on port 14540 (offboard) and 14550 (GCS).

Headless variant for faster iteration:

```bash
HEADLESS=1 make px4_sitl gz_x500
```

Windy variant for failure-mode testing:

```bash
make px4_sitl gz_x500_windy
```

### 5.5 Connect QGroundControl on the Mac

OrbStack exposes the VM at a hostname like `sim.orb.local` and forwards UDP
ports automatically. In QGC on the Mac: *Application Settings → Comm Links*
→ add UDP, port 14550, target host `sim.orb.local` (or the VM's Tailscale
address — both work). QGC autoconnects.

For HLS or RTSP video off the Gazebo camera, expose the VM's `:8554` to the
Mac the same way and point MediaMTX at it (the [`ground_station/`](../ground_station/)
`docker-compose` sketch is already wired for RTSP).

### 5.6 The ArduPilot path through Gazebo Harmonic

If you want ArduCopter (not PX4) flying inside the same Gazebo, install
[`ardupilot_gazebo`](https://github.com/ArduPilot/ardupilot_gazebo) in the VM:

```bash
sudo apt install libgz-sim8-dev rapidjson-dev libopencv-dev \
                 libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev
git clone https://github.com/ArduPilot/ardupilot_gazebo
cd ardupilot_gazebo && mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo && make -j$(nproc)
export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH=$PWD
```

Then in two terminals:

```bash
gz sim -v4 -r iris_runway.sdf
sim_vehicle.py -v ArduCopter -f gazebo-iris --model JSON --map --console
```

This is the configuration we use for "high-fidelity ArduPilot regression":
real ArduCopter firmware, real Gazebo Harmonic world, JSON simulation
lockstepping, ogre2 rendering. Reference:
[ArduPilot SITL with Gazebo](https://ardupilot.org/dev/docs/sitl-with-gazebo.html).

---

## 6. Tier 4 — HITL with the Cube Orange+

**Prerequisite**: actual Cube Orange+ in hand (Holybro X500 V2 ARF kit
arrives ~2-4 weeks from purchase per [`hardware/bom.csv`](../hardware/bom.csv)).

There are **two** flavours of "hardware in the loop" on ArduPilot, and the
distinction matters:

### 6.1 Classic HITL (external simulator + autopilot)

Cube Orange+ runs flight code, Gazebo on the Mac (or in the VM) runs
physics, they exchange MAVLink over USB. PX4 supports this directly — see
[PX4 HITL docs](https://docs.px4.io/main/en/simulation/hitl). ArduPilot
supports it via FlightGear or via PX4's HITL mode if the Cube is flashed
with PX4. For our ArduPilot stack, this is the *less interesting* option.

### 6.2 Simulation on Hardware — the surprise

ArduPilot ships a build target called `CubeOrange-SimOnHardWare` that runs
the SITL physics model **on the Cube's STM32H7 itself**. The autopilot runs
both the flight code and the simulator; you connect a GCS and fly the Cube
without it being plugged into anything but USB. Reference:
[ArduPilot Simulation on Hardware](https://ardupilot.org/dev/docs/sim-on-hardware.html).

```bash
# In the ardupilot/ checkout
./Tools/scripts/sitl-on-hw/sitl-on-hw.py \
  --board CubeOrangePlus --vehicle copter --frame quad
# upload the resulting .apj to the Cube via Mission Planner or QGC
```

You then talk to the Cube as if it were flying — same MAVLink stream rates,
same parameters, same failsafe behaviour, same EKF. The only difference is
that the IMU readings come from a built-in physics integrator instead of
the actual MEMS chips. **This is the highest-fidelity rung short of real
flight that we have access to without buying a motion table.**

When the Cube arrives, do this *first*, before you ever wire it to motors.

### 6.3 What HITL catches that SITL doesn't

- Real timing jitter on the H7's RTOS — you find scheduling regressions in
  Lua scripts that desktop SITL hides.
- DroneCAN / CAN1 bus behaviour for Remote ID (uAvionix pingRID is on CAN1
  per [`firmware/README.md`](../firmware/README.md)).
- Actual SD card write latency for DataFlash logs — relevant for incident
  reconstruction.
- Power-on / power-off sequencing of the EKF when GPS is starting up.

---

## 7. Real flight — Phase 1+

Once Tier 4 is green, you bridge to [`firmware/README.md`](../firmware/README.md)
for the flashing + parameter checklist and to
[`docs/40-faa-compliance.md`](40-faa-compliance.md) for the legal
checklist (Part 107, LAANC, Remote ID, TFR check, PSSOW path). The
`geofence_check.py` refusal-to-arm in [`ground_station/`](../ground_station/)
is the last line of defence; it is not a substitute for the simulation
ladder, it is a *backstop*.

A successful first flight requires:

- Tier 2 (ArduPilot SITL) green on the current branch.
- Tier 4 (Sim-on-Hardware on the actual Cube) green with the Cube's serial
  number recorded.
- Pre-flight checklist green per [`firmware/README.md`](../firmware/README.md) §
  *Pre-flight checklist*.
- RPIC sign-off, Part 107 cert in pocket, Remote ID broadcasting, TFR query
  clean, weather inside envelope, observer present.

---

## 8. Wildfire-specific extensions

### 8.1 Gazebo fire and smoke objects

Gazebo Harmonic has a **particle emitter** SDF element that does smoke
plumes well. Reference:
[Gazebo particle emitter](https://gazebosim.org/api/gazebo/6/particle_emitter.html),
[Gazebo Fuel model insertion](https://gazebosim.org/docs/harmonic/fuel_insert/).

Sketch for an in-world fire object — drop into a `.sdf` world file:

```xml
<model name="campfire_01">
  <pose>37.7749 -122.4194 50 0 0 0</pose>
  <static>true</static>
  <link name="fuel">
    <visual name="flame"><geometry><cylinder><radius>0.3</radius>
      <length>1.0</length></cylinder></geometry>
      <material><ambient>1 0.4 0 1</ambient></material></visual>
    <particle_emitter name="smoke" type="point">
      <emitting>true</emitting>
      <rate>30</rate>
      <duration>0</duration>
      <particle_size>0.5 0.5 0.5</particle_size>
      <lifetime>4</lifetime>
      <topic>fire/smoke</topic>
    </particle_emitter>
  </link>
</model>
```

Build a small library of these in `sim/scenarios/gazebo/` (Tier 3 only —
Tier 1 stays kinematic) so the YOLO loop has positive examples to chew on.

### 8.2 Camera plugin → ROS 2 → YOLO loop

Gazebo Harmonic ships a camera sensor plugin (`gz-sim-sensors-system`) that
publishes `gz.msgs.Image` on a topic. Bridge to ROS 2 via `ros_gz_bridge`,
subscribe in a Python node, hand frames to the existing `ml/fire_detection/`
inference path. The ML team's existing model artefacts work unchanged — the
Gazebo camera matches the IMX477 resolution we ship in the BOM.

The wildfire-watch fusion gate at `ml/fire_detection/infer.py` already
accepts a stream of frames + telemetry; the only new code is a `gz_source.py`
that pulls Gazebo image messages and stuffs them into the existing
`fire_detection.run_on_clip` API. Spec for the agent who builds it:

- Subscribe to `/world/<world>/model/<drone>/link/camera_link/sensor/camera/image`.
- For each frame, pull the matching `GLOBAL_POSITION_INT` from MAVLink
  (timestamp-aligned to within 100 ms).
- Emit a `(frame, telemetry)` tuple matching the same shape as the kinematic
  sim's output. Same downstream contract.

### 8.3 Mission converter — `sim/missions/*.yaml` to QGC `.plan`

The kinematic sim's mission YAML ([`sim/mission.py`](../sim/mission.py)) and
QGC's `.plan` JSON ([Plan File Format](https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html))
are isomorphic at the waypoint level. Build a converter at
`sim/converters/yaml_to_plan.py`:

| Our YAML field | QGC `.plan` mission item |
|---|---|
| `home.lat / home.lon / home.alt_msl_m` | `plannedHomePosition: [lat, lon, alt]` |
| `waypoints[i].lat / lon / alt_agl_m` | `params: [0,0,0,0, lat, lon, alt]`, `command: 16` (`MAV_CMD_NAV_WAYPOINT`), `frame: 3` (`MAV_FRAME_GLOBAL_RELATIVE_ALT`) |
| `flight_params.cruise_speed_mps` | leading `MAV_CMD_DO_CHANGE_SPEED` (cmd 178), `params: [1, speed_mps, -1, 0, 0, 0, 0]` |
| `geofence_polygon` | `geoFence.polygons[0].polygon` (array of `[lat, lon]`) |
| `return_to_home: true` | trailing `MAV_CMD_NAV_RETURN_TO_LAUNCH` (cmd 20) |

Reverse direction (`.plan` to YAML) is a one-day project; same table read
backward. Once the converter exists, **every** wildfire-watch mission can be
roundtripped through QGC, edited graphically, and shipped to either a SITL
copter or the real Cube.

---

## 9. Failure scenarios to script

These are the regressions we run on every release branch. Each one has a
seeded scenario in `sim/scenarios/` (Tier 1) and a Gazebo equivalent in
`sim/scenarios/gazebo/` (Tier 3 — to build).

| Scenario | Tier 1 (kinematic) | Tier 3 (Gazebo) | Tier 4 (HITL) | Success looks like |
|---|---|---|---|---|
| GPS denial mid-mission | Set `gps_active=false` 30 s in | `gz topic --pub` zero on `/navsat` | `param set SIM_GPS_DISABLE 1` | Drone holds attitude, EKF flags loss of position, RTL aborts to LOITER, status posted to GCS |
| Single motor failure | `airframe.disable_motor(2)` | Apply `gz model --link motor_2 --thrust 0` | `param set SIM_ENGINE_FAIL 2` | Quad enters auto-recovery (octocopter only), or copter triggers `LAND` failsafe within 2 s |
| Battery sag below 20% | Set voltage decay curve in airframe profile | Same | `param set BATT_LOW_VOLT` low | Mission aborts, RTL initiated, status text emitted, `BATTERY_STATUS` reflects on GCS |
| Wind shear (10→18 m/s gust) | Add lateral acceleration step | `make px4_sitl gz_x500_windy` | Run sim-on-hardware with `SIM_WIND_*` | Drone stays inside fence, controller compensates, no crash |
| GCS datalink loss for 60 s | Disconnect adapter | Drop UDP forwarder | Unplug telemetry radio | Per `FS_GCS_ENABLE=2`: RTL after timeout, reconnect cleanly when link returns |
| Thermal payload (Lepton) disconnect | Drop SRT subtitle stream | Stop camera plugin | Power-cycle Lepton USB | Mission *continues* (Lepton is non-critical), status logged |
| Geofence breach attempt | Plant a waypoint outside fence | Same | Same | Per `FENCE_ACTION=1`: refuse to navigate past, RTL triggered |
| RTH from far edge of zone | Mission ends 1 km from home | Same | Same with realistic battery | Battery budget honoured, returns with > 5 min reserve |
| ADS-B intruder closing | Inject fake `ADSB_VEHICLE` 2 nm out | Same | `param set SIM_ADSB_TYPES` | `AVD_ENABLE=1` triggers altitude break or RTL per `AVD_W_ACTION` |
| Remote ID stuck off | n/a (Tier 1 has no RID) | Stub `pingRID` heartbeat off | Power off pingRID | `geofence_check.py` refuses to arm; matches our pre-flight checklist |

---

## 10. Time and cost

| Tier | First-time setup | Steady-state launch | Software cost | Hardware cost |
|---|---|---|---|---|
| 1 — kinematic | 0 (already done) | seconds | $0 | $0 (Mac) |
| 2 — ArduPilot SITL on Mac | 60-90 min | 30 s | $0 | $0 |
| 3 — PX4 + Gazebo in VM | 3-4 hr | 30 s after VM resume | $0 (OrbStack free for personal; UTM is FOSS) | $0 (Mac mini already owned) |
| 4 — HITL on Cube | 30 min after Cube arrives | 60 s | $0 | $350 Cube Orange+ (in BOM, pending) |
| 5 — real flight | weeks (Part 107, LAANC, MOU) | hours per sortie | $0 | $3,411 full BOM + $175 Part 107 exam + $150 insurance / mo |

End-to-end "git clone → first virtual flight at Tier 2" is **under two
hours** on a clean Mac mini. Tier 3 (Gazebo) is **under four hours** counting
the OrbStack and PX4 install. Tier 4 is **under thirty minutes** once the
Cube physically arrives, because the firmware build is the slow part and
that is shared with Tier 2.

---

## Appendix A — Key URLs

- ArduPilot SITL: <https://ardupilot.org/dev/docs/using-sitl-for-ardupilot-testing.html>
- ArduPilot macOS build: <https://ardupilot.org/dev/docs/building-setup-mac.html>
- ArduPilot SITL with Gazebo: <https://ardupilot.org/dev/docs/sitl-with-gazebo.html>
- ArduPilot Simulation on Hardware: <https://ardupilot.org/dev/docs/sim-on-hardware.html>
- ArduPilot Gazebo plugin: <https://github.com/ArduPilot/ardupilot_gazebo>
- ArduPilot ROS 2 + Gazebo: <https://ardupilot.org/dev/docs/ros2-gazebo.html>
- PX4 Gazebo Sim: <https://docs.px4.io/main/en/sim_gazebo_gz/>
- PX4 macOS dev env: <https://docs.px4.io/main/en/dev_setup/dev_env_mac>
- PX4 Docker (Linux-only): <https://docs.px4.io/main/en/test_and_ci/docker.html>
- PX4 HITL: <https://docs.px4.io/main/en/simulation/hitl>
- Gazebo Harmonic releases: <https://gazebosim.org/docs/latest/releases/>
- Gazebo Harmonic macOS source install (caveat): <https://gazebosim.org/docs/harmonic/install_osx_src/>
- gz-macOS Apple-Silicon source build (community): <https://github.com/idesign0/gz-macOS>
- ROS 2 Jazzy on Apple Silicon (community): <https://github.com/IOES-Lab/ROS2_Jazzy_MacOS_Native_AppleSilicon>
- QGroundControl docs: <https://docs.qgroundcontrol.com/master/en/qgc-user-guide/getting_started/download_and_install.html>
- QGC `.plan` file format: <https://docs.qgroundcontrol.com/master/en/qgc-dev-guide/file_formats/plan.html>
- MAVLink common message set: <https://mavlink.io/en/messages/common.html>
- pymavlink mavgen guide: <https://mavlink.io/en/mavgen_python/>
- OrbStack docs: <https://docs.orbstack.dev/machines/>
- UTM for Mac: <https://mac.getutm.app/>
- ardupilot-sitl-docker (multi-arch including arm64): <https://github.com/uxduck/ardupilot-sitl-docker>

## Appendix B — MAVLink primer

Every message in the wildfire-watch ground station scaffolding is one of
roughly six MAVLink message types. If you understand these six, the rest of
the [`ground_station/README.md`](../ground_station/README.md) reads cleanly.

- `HEARTBEAT` (1 Hz) — "I am still here". Carries autopilot type, system
  status, custom mode (which encodes ArduCopter flight mode). Loss of three
  consecutive heartbeats triggers `FS_GCS_ENABLE`.
- `GLOBAL_POSITION_INT` (5 Hz on our SR2 schedule) — lat × 1e7, lon × 1e7,
  alt MSL mm, alt AGL mm, vx/vy/vz cm/s, hdg cdeg. This is what the Jetson
  signs and stamps on every emitted `wildfire_signal`.
- `ATTITUDE` (10 Hz) — roll/pitch/yaw rad and rates rad/s. Used for camera
  ray geolocation (the Jetson reprojects pixel coords from the camera frame
  into world frame).
- `BATTERY_STATUS` (1 Hz) — voltage, current, remaining %. The Jetson uses
  the remaining-% to decide mission-abort; the ground station refuses to
  arm if pre-flight battery is < 80 %.
- `STATUSTEXT` (as-emitted) — severity 0-7, free text up to 50 chars. Both
  the Jetson and the Cube emit these; they are the lingua franca for
  "something happened, log it".
- `COMMAND_LONG` / `COMMAND_INT` — the only command we ever send from the
  Jetson is `MAV_CMD_NAV_LOITER_UNLIM` (cmd 17) to auto-loiter on a
  high-confidence detection. We never emit `MAV_CMD_COMPONENT_ARM_DISARM`
  (cmd 400) — arming is the ground station's prerogative alone, see the
  wildfire-watch `firmware/README.md` MAVLink topic table for the full
  contract.

For a full reference: [MAVLink common.xml](https://mavlink.io/en/messages/common.html).
For Python: [pymavlink mavgen](https://mavlink.io/en/mavgen_python/), and
the canonical idiom is

```python
from pymavlink import mavutil
m = mavutil.mavlink_connection("udp:127.0.0.1:14550")
m.wait_heartbeat()
msg = m.recv_match(type="GLOBAL_POSITION_INT", blocking=True)
```

---

*End of ladder.*
