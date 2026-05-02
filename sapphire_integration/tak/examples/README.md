# TAK / CoT example output

These files are canonical CoT XML output from the wildfire-watch emitter.
They double as fixtures for downstream consumers (TAK Server testing,
ATAK plugin developers integrating wildfire-watch as an upstream feed,
Anduril Lattice / Palantir Apollo connector authors).

| File                      | Built from                                                                 |
|---------------------------|----------------------------------------------------------------------------|
| `smoke_signal.xml`        | A persistent-plume smoke signal at 86% confidence, target offset by ~120m  |
| `fire_signal.xml`         | A confirmed flame signal (RGB+thermal both very high) at 99% confidence    |
| `drone_self_position.xml` | The drone's own track for SA-mesh broadcast on `239.2.3.1:6969`            |
| `geofence.xml`            | The Crested Butte / Slate River corridor as a CoT `u-d-c-c` drawing event  |

To verify any of these files parse:

```bash
xmllint --noout sapphire_integration/tak/examples/smoke_signal.xml
```

To re-render them from the live emitter (if the schema or default callsigns
are tweaked):

```bash
python3 -m sapphire_integration.tak.cli emit examples/smoke_input.json \
    --out sapphire_integration/tak/examples/smoke_signal.xml
```

Pretty-print one inline:

```bash
xmllint --format sapphire_integration/tak/examples/fire_signal.xml
```
