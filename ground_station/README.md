# Ground Station

The ground station is the operator's Mac (`100.67.171.79`) running:

| Component | Role | Port |
|---|---|---|
| Mission Planner (or QGroundControl) | RPIC console: arm/disarm, mission upload, manual takeover | n/a |
| `mavlink-router` | Forks MAVLink stream to Mission Planner, Jetson, and TAK adapter | UDP 14550 / 14555 / 14560 |
| MediaMTX | RTSP/SRT video relay from drone to TAK + Sapphire | 8554 (RTSP), 8889 (HLS) |
| Free TAK Server (FTS) or partner agency's TAK | Ingests CoT XML for ATAK clients | 8089 (TLS) / 8087 (TCP) |
| `tak_adapter.py` | Translates wildfire_signal → CoT XML, pushes to TAK | n/a |
| `sapphire_adapter.py` | Forwards wildfire_signal to `signal_logger:18081` | n/a |
| `geofence_check.py` | Refuse-to-arm if pre-flight conditions fail | n/a |

## docker-compose (sketch — not yet shipped)

```yaml
services:
  fts:
    image: freetakteam/fts:latest
    ports: ["8089:8089", "8087:8087"]
    volumes: ["./fts:/data"]

  mediamtx:
    image: bluenviron/mediamtx:latest
    ports: ["8554:8554", "8889:8889"]

  mavrouter:
    image: ghcr.io/intel/mavlink-router:latest
    network_mode: host
    command: ["mavlink-routerd", "-e", "127.0.0.1:14550", "-e", "127.0.0.1:14555"]
```

## TAK CoT message format

We emit CoT XML conforming to MIL-STD-2525 / TAK extensions. Our message type
for a fire signal:

```xml
<event version="2.0" uid="wfw-{signal_id}" type="a-h-G-X-I"
       time="{ISO8601}" start="{ISO8601}" stale="{ISO8601 + 1h}" how="m-g">
  <point lat="{target_lat}" lon="{target_lon}" hae="{alt_msl_m}" ce="{horiz_uncertainty_m}" le="9999"/>
  <detail>
    <contact callsign="WFW-{drone_id}"/>
    <link uid="wfw-evidence-{signal_id}" type="b-x-i" relation="extra"
          remarks="{first frame_uri}"/>
    <remarks>fire-watch detection conf={confidence:.2f} risk={risk_score}/100</remarks>
    <__group name="UAS" role="UAS"/>
  </detail>
</event>
```

Type code `a-h-G-X-I` = "atom, hostile, ground, indicator-of-incident". Adjust to
match the partner agency's COTAK schema during integration; some California
public-safety agencies use custom types under the COTAK extension.

## ATAK UAS Tool integration

Per the 2026 public-safety ATAK ecosystem documentation, ATAK UAS Tool can ingest
MAVLink natively. We expose the drone's MAVLink stream over the
`mavlink-router` UDP forwarder; the chief / IC's ATAK device subscribes and sees
the drone as a friendly UAS marker plus our CoT events as fire markers.

## Pre-flight refusal-to-arm

`geofence_check.py` polls FAA TFR list, NOAA winds aloft, and the drone's GPS
HDOP. The ground station refuses to send the `MAV_CMD_COMPONENT_ARM_DISARM`
command unless all checks pass. RPIC override is logged.
