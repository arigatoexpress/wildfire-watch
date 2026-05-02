# Sim missions

Each YAML here describes one planned drone flight. Schema:

```yaml
name: <human readable mission name>
zone_id: <matches a zone_id in missions/zones.example.geojson>
airframe: mavic_mini_2 | holybro_x500_v2 | generic_quad
home: {lat: ..., lon: ..., alt_msl_m: ...}
flight_params:
  altitude_agl_m: 80
  cruise_speed_mps: 8
  rgb_overlap_pct: 70
waypoints:
  - {lat: ..., lon: ..., alt_agl_m: 80, action: capture}
  - ...
return_to_home: true
geofence_polygon:
  - [lat, lon]
  - ...
```

`monterey_pinnacles_east_1km2.yaml` is the canonical demo mission used
by the simulator's smoke test and matches the zone_id assumed by the
`single_smoke_plume` scenario.

The `geofence_polygon` is informational in this simulator (it is not
yet enforced by the runner). Real-flight enforcement happens in the
ground station via `sapphire_integration/`.
