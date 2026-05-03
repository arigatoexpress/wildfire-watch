# Copyright 2026 wildfire-watch contributors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# See the LICENSE file in the repo root for the full text.
"""wildfire-watch demo recording engine + single-file HTML report.

The companion of ``sim.web.server`` — that one is a Flask + Leaflet
live viewer; this module is the *static, bundle-friendly, email-ready*
counterpart. ``recorder`` runs a deterministic canonical flight (a
single-drone Mavic profile + a 3-drone consensus swarm, both seeded);
``renderer`` turns either flight directory into a single self-contained
HTML file with no external CSS/JS/font dependencies.

Public surface:

    from sim.demo.recorder import record_canonical_flight
    from sim.demo.renderer import render_report
"""

__all__ = ["recorder", "renderer", "cli"]
