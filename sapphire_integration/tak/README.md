# wildfire-watch — TAK / Cursor-on-Target emitter

This package converts wildfire-watch v1 signals into **Cursor-on-Target (CoT)**
XML events and ships them to any TAK Server, ATAK / WinTAK / iTAK client,
multicast SA mesh, or upstream platform that speaks CoT.

## Why this exists

CoT is the underlying wire protocol of the **Team Awareness Kit (TAK)**
ecosystem. TAK is the situational-awareness standard the entire defense +
first-responder community actually uses:

- **ATAK** is on every county fire-chief tablet — the open-source wildland-fire
  community has built ATAK plugins for incident command, smoke-jumper
  comms, and CalFire / USFS Incident Management Team coordination.
- **TAK Server / FreeTAKServer** is the canonical aggregator; pretty much
  every defense SA platform federates with it (Anduril Lattice, Palantir
  Apollo, Ondas Optimus, etc.).
- **Cursor-on-Target** itself is an open MITRE-published XML schema. Once a
  platform speaks CoT, it interoperates with every TAK client.

So: if wildfire-watch emits CoT, every fire-department tablet, every USFS
Incident Management Team laptop, and every defense SA system running
TAK Server federation can render our smoke / fire / wildlife / drone tracks
on their map without us writing per-vendor adapters. This is the highest
leverage interop move available to a small wildfire-detection project.

## What's in here

| File | Role |
|---|---|
| `cot_event.py`         | Build a CoT XML event from a `wildfire_signal` v1 record. Also self-position events and geofence polygons. |
| `cot_types.py`         | The dotted-CoT-type-code dictionary (`b-r-f-h-c`, `a-n-G`, etc.) + stale-window defaults per signal type. |
| `tak_server_client.py` | Synchronous TCP / UDP / TLS / multicast dispatch. Stdlib `socket` + `ssl`. |
| `atak_emitter.py`      | High-level facade: signal → XML → sink (server / file / stdout). |
| `cli.py`               | `python -m sapphire_integration.tak.cli` — emit, geofence, self-position, types. |
| `examples/`            | Canonical CoT XML for smoke, fire, drone self-position, AOR geofence. |
| `tests/`               | 50+ unit tests. Stdlib + pytest. No network at test time except a localhost listener. |

## Quickstart

```bash
# preview an emitted CoT event from a signal JSON
python3 -m sapphire_integration.tak.cli emit signal.json --out -

# send to a TAK Server
python3 -m sapphire_integration.tak.cli emit signal.json \
    --server tcp://atak.crestedbutte.local:8087

# build the AOR geofence as a CoT u-d-c-c drawing event
python3 -m sapphire_integration.tak.cli geofence \
    missions/zones/gunnison_crested_butte_corridor.geojson \
    --out fence.xml

# build a one-shot drone self-position event and broadcast on the SA mesh
python3 -m sapphire_integration.tak.cli self-position \
    wfw-unit01 38.910 -107.000 2820 --multicast

# inspect the type-code mapping
python3 -m sapphire_integration.tak.cli types
```

Programmatic use:

```python
from sapphire_integration.tak import emit

# build only
xml = emit(signal_dict)

# build and send
emit(signal_dict, server="tcp://atak.local:8087")

# build and dump to file
emit(signal_dict, out="/tmp/cot.xml")
```

## CoT type-code mapping

| `signal_type`     | CoT type     | Why                                                              |
|-------------------|--------------|------------------------------------------------------------------|
| `smoke`           | `b-r-f-h-s`  | bit / report / fire / hot / smoke — ATAK's smoke marker          |
| `fire`            | `b-r-f-h-c`  | fire / hot / confirmed (RGB+thermal both positive)               |
| `thermal_anomaly` | `b-r-f-h-h`  | fire / hot / hot-spot — IR-only, no flame yet                    |
| `wildlife`        | `a-n-G`      | atom / neutral / ground — *neutral*; we observe, not command     |
| `anomaly`         | `b-d`        | bit / detection — generic catch-all                              |
| `system_event`    | `b-m-p-s-m`  | machine / position / status / message — housekeeping             |

Drone self-position uses `a-f-A-M-F-Q-r` (atom / friend / Air / Military /
Fixed-wing / Q rotary). Geofence polygons use `u-d-c-c` (user-defined /
drawing / closed shape). See `cot_types.py` for the full description and
trade-off discussion.

## Stale windows

ATAK greys out and drops markers that have passed their `stale` timestamp.
Defaults baked into `cot_types.STALE_SECONDS_BY_SIGNAL_TYPE`:

| `signal_type`     | stale window |
|-------------------|--------------|
| `fire`            | 1 hour       |
| `smoke`           | 1 hour       |
| `thermal_anomaly` | 15 min       |
| `wildlife`        | 15 min       |
| `anomaly`         | 30 min       |
| `system_event`    | 24 hours     |

For self-position broadcasts the default is 30 seconds since these get
re-emitted at ~1 Hz.

## Wire transport

The `TAKServerClient` is **synchronous and one-shot** — it opens a socket,
writes the CoT bytes, closes. Good for batch emission and CLI use. For a
production drone uplink with persistent streaming, use `pytak` (the
canonical async TAK client library) on the ground-station side; the drone
itself can stay stdlib by piping to a local socket / file.

Supported schemes:

| URL form                          | Meaning                              |
|-----------------------------------|--------------------------------------|
| `tcp://host:8087`                 | TAK Server cleartext streaming       |
| `tls://host:8089`                 | TAK Server mutual-TLS streaming      |
| `udp://host:8088`                 | UDP unicast to TAK Server            |
| `mcast://239.2.3.1:6969`          | UDP multicast to the SA mesh         |
| `tak://host` / `host:8087`        | aliases for tcp://host:8087          |

TLS supports `--tls-cafile`, `--tls-certfile`, `--tls-keyfile` (the standard
client-cert pinning flow against a TAK Server CA). **Cert-pinning by
SHA-256** is documented in `tak_server_client.py` but not wired in yet.

## Production-grade alternatives

This module is deliberately stdlib-only. If you need sustained streaming,
TAK Server federation, or COT-router middle-box behaviour, use:

- **[`pytak`](https://github.com/snstac/pytak)** — async Python TAK client.
  `pip install pytak`. Production-grade.
- **[`takproto`](https://github.com/snstac/takproto)** — TAK protobuf
  encoding (lower-bandwidth wire format).
- **TAK Server** itself — Java reference implementation; the Tactical
  Assault Kit Product Center publishes builds.
- **FreeTAKServer (FTS)** — open-source TAK Server. Drop-in for
  most ATAK / WinTAK clients; great for bench / dev.

## Out of scope

- TAK Server federation (enterprise feature; configure on the server itself).
- MIL-STD-2525B/C 2D iconography mapping (beyond what CoT type codes already
  do — ATAK auto-renders icons from the type code).
- COT-router / fan-out logic (use a real TAK Server).
- Mission packages (`.zip`-style ATAK data packages).
- Encrypted-at-rest CoT (TAK Server handles this; we are stateless).

## Verifying

```bash
cd ~/Code/wildfire-watch
python3 -m pytest sapphire_integration/tak/tests/ -q
```

End-to-end demo:

```bash
echo '{"action":"list","limit":1}' \
  | python3 ~/Code/Sapphire/plugins/claw-sapphire/tools/wildfire.py \
  | jq '.signals[0]' > /tmp/sig.json
python3 -m sapphire_integration.tak.cli emit /tmp/sig.json --out /tmp/cot.xml
xmllint --format /tmp/cot.xml | head -30
```

(If no live signal is available, the canonical examples in `examples/` are
ready to load.)
