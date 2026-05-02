"""Wildfire-watch admin frontend.

Dedicated Flask app for the wildfire-watch operator console:

- Live signal map (LeafletJS over the AOR GeoJSON)
- KPI strip (24h / 7d / all-time signal counts, highest-risk zone, last
  sensor heartbeat, retry-queue depth)
- Recent signals table (filterable by zone, risk level, signal type)
- AOR overview (Gunnison-Crested Butte corridor polygons)
- Sensor health (drone / Pi heartbeats from system_event signals)

Auth is gated by a stub ``@requires_admin`` decorator that checks
``X-Admin-Token`` against the ``ADMIN_TOKEN`` env var; production will
swap this for WebAuthn.
"""

from frontend.app import create_app

__all__ = ["create_app"]
