# Missions — defining a patrol zone

A zone is a GeoJSON `Feature` of type `Polygon` with metadata properties
specifying patrol parameters. Zones are converted to ArduPilot waypoint
missions by `firmware/zone_to_mission.py`.

## Required properties

| Property | Type | Description |
|---|---|---|
| `zone_id` | string | Stable identifier; appears in every emitted signal |
| `name` | string | Human-readable name |
| `authority` | string | Agency or landowner authorizing flight |
| `authorization_doc_uri` | string | Link to MOU / authorization letter (private) |
| `altitude_agl_m` | number | Patrol altitude AGL (typical 60-100) |
| `cruise_speed_mps` | number | 5-12 m/s typical |
| `overlap_pct` | number | Lateral overlap between sweeps for full coverage (typical 30) |
| `priority` | enum | "high" / "medium" / "low" — affects scheduler |
| `time_windows` | array | ISO 8601 time windows when patrol is permitted |

## Example

See [`zones.example.geojson`](zones.example.geojson) for a synthetic 1-km^2 zone.

## Generating a mission

```bash
python ../firmware/zone_to_mission.py \
  --zone zones/my_zone.geojson \
  --output ../firmware/missions/my_zone.waypoints
```

The generator lays a serpentine raster across the polygon at the specified
altitude and overlap, snapping to the polygon's bounding box.

## Operational geofence

The zone polygon is the **soft geofence** — patrol bounded to it.
The **hard geofence** in `firmware/params/wildfire_watch_base.parm` is the
zone polygon dilated by 100 m. Crossing the soft fence triggers a course
correction; crossing the hard fence triggers RTL.
