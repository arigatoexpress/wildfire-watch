"""Foundry ontology bindings for wildfire-watch.

See ontology.py for the 6 ontology object types + serializers.
See README.md for the architectural rationale.
"""

from .ontology import (
    SCHEMA_VERSION,
    BatteryCycle,
    Drone,
    FireDepartmentUnit,
    FlightLog,
    WildfireSignal,
    Zone,
    from_foundry_json,
    to_foundry_json,
    wildfire_signal_from_v1,
    zone_from_geojson_feature,
)

__all__ = [
    "SCHEMA_VERSION",
    "Drone",
    "Zone",
    "FireDepartmentUnit",
    "FlightLog",
    "BatteryCycle",
    "WildfireSignal",
    "to_foundry_json",
    "from_foundry_json",
    "wildfire_signal_from_v1",
    "zone_from_geojson_feature",
]
