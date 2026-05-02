/* wildfire-watch sim viewer — vanilla JS state machine.
 *
 * Globals provided by index.html:
 *   - L           Leaflet
 *   - Chart       Chart.js
 */

(function () {
  "use strict";

  // ---- state ----------------------------------------------------------

  var state = {
    flightId: null,
    manifest: null,
    log: [],            // full flight_log rows
    signals: [],        // emitted signals
    analysis: null,
    map: null,
    layers: {
      planned: null,
      flown: null,
      drone: null,
      signals: [],
      geofence: null,
    },
    flownPath: [],      // accumulating array of [lat, lon] for flown polyline
    charts: { rgb: null, thermal: null, persistence: null },
    chartBuffer: { rgb: [], thermal: [], persistence: [] },
    chartLabels: [],
    sse: null,
    playing: false,
    speed: 10,
    cursor: 0,          // index into log
  };

  var SIGNAL_COLOR = {
    smoke: "#9da7b3",
    fire: "#ef5350",
    thermal_anomaly: "#ff9800",
    wildlife: "#66bb6a",
    anomaly: "#ce93d8",
    system_event: "#90a4ae",
  };

  // ---- helpers --------------------------------------------------------

  function fmt2(n) {
    n = Math.max(0, Math.floor(n));
    return (n < 10 ? "0" + n : "" + n);
  }
  function fmtClock(seconds) {
    return fmt2(seconds / 60) + ":" + fmt2(seconds % 60);
  }
  function tsSeconds(ts) {
    return Math.floor(new Date(ts).getTime() / 1000);
  }
  function $(id) { return document.getElementById(id); }

  function fetchJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.json();
    });
  }

  // ---- map ------------------------------------------------------------

  function initMap() {
    state.map = L.map("map", { zoomControl: true, attributionControl: true })
      .setView([36.49, -121.18], 14);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>',
    }).addTo(state.map);
  }

  function clearMapLayers() {
    Object.keys(state.layers).forEach(function (k) {
      var v = state.layers[k];
      if (Array.isArray(v)) {
        v.forEach(function (m) { state.map.removeLayer(m); });
        state.layers[k] = [];
      } else if (v) {
        state.map.removeLayer(v);
        state.layers[k] = null;
      }
    });
    state.flownPath = [];
  }

  function renderManifestOnMap() {
    if (!state.manifest) return;
    var m = state.manifest;

    if (m.geofence_polygon && m.geofence_polygon.length) {
      state.layers.geofence = L.polygon(m.geofence_polygon, {
        color: "#4fc3f7", weight: 1.5, fillColor: "#4fc3f7", fillOpacity: 0.12,
      }).addTo(state.map);
    }

    if (m.waypoints && m.waypoints.length) {
      var coords = m.waypoints.map(function (w) { return [w.lat, w.lon]; });
      state.layers.planned = L.polyline(coords, {
        color: "#4fc3f7", weight: 2, dashArray: "4,4", opacity: 0.7,
      }).addTo(state.map);
      m.waypoints.forEach(function (w) {
        L.circleMarker([w.lat, w.lon], {
          radius: 8, color: "#4fc3f7", fillColor: "#4fc3f7", fillOpacity: 0.6,
        }).bindTooltip(w.label || ("WP" + (w.index + 1)), { permanent: true, direction: "right" })
          .addTo(state.map);
      });
    }

    if (m.home) {
      L.circleMarker([m.home.lat, m.home.lon], {
        radius: 6, color: "#ff8c42", fillColor: "#ff8c42", fillOpacity: 0.9,
      }).bindTooltip("home", { permanent: true, direction: "left" }).addTo(state.map);
    }

    state.layers.flown = L.polyline([], { color: "#ef5350", weight: 3, opacity: 0.9 })
      .addTo(state.map);

    // Fit bounds to manifest extent.
    var bounds = [];
    if (m.geofence_polygon) bounds = bounds.concat(m.geofence_polygon);
    if (m.waypoints) bounds = bounds.concat(m.waypoints.map(function (w) { return [w.lat, w.lon]; }));
    if (m.home) bounds.push([m.home.lat, m.home.lon]);
    if (bounds.length) state.map.fitBounds(bounds, { padding: [30, 30] });
  }

  function renderSignalsOnMap() {
    state.signals.forEach(function (s) {
      var color = SIGNAL_COLOR[s.signal_type] || "#9da7b3";
      var radius = 6 + Math.round((s.risk_score || 0) / 12);
      var lat = (s.target_coords && s.target_coords.lat) || s.coords.lat;
      var lon = (s.target_coords && s.target_coords.lon) || s.coords.lon;
      var marker = L.circleMarker([lat, lon], {
        radius: radius, color: color, fillColor: color, fillOpacity: 0.6, weight: 2,
      }).addTo(state.map);
      var html = '<div><strong>' + s.signal_type + '</strong>'
        + (s.signal_subtype ? ' / ' + s.signal_subtype : '') + '</div>'
        + '<div class="sig-row"><span class="k">conf</span><span>' + (s.confidence || 0).toFixed(2) + '</span></div>'
        + '<div class="sig-row"><span class="k">risk</span><span>' + (s.risk_score || 0).toFixed(0) + '</span></div>'
        + '<div class="sig-row"><span class="k">action</span><span>' + (s.recommended_action || "-") + '</span></div>'
        + '<div class="sig-row"><span class="k">drone</span><span>' + (s.drone_id || "-") + '</span></div>'
        + '<div class="sig-row"><span class="k">target</span><span>' + lat.toFixed(5) + ', ' + lon.toFixed(5) + '</span></div>'
        + '<div class="sig-row"><span class="k">evidence</span><span>' + ((s.evidence && s.evidence.frame_uris && s.evidence.frame_uris.length) || 0) + ' frames</span></div>';
      marker.bindPopup(html);
      state.layers.signals.push(marker);
    });
  }

  function ensureDroneMarker(lat, lon, heading) {
    if (!state.layers.drone) {
      var icon = L.divIcon({
        className: "drone-marker-wrap",
        html: '<div class="drone-marker" style="transform: rotate(' + (heading || 0) + 'deg);">'
          + '<svg viewBox="0 0 24 24" width="24" height="24" xmlns="http://www.w3.org/2000/svg">'
          + '<polygon points="12,2 18,18 12,14 6,18" fill="#ff8c42" stroke="#000" stroke-width="1.2"/>'
          + '</svg></div>',
        iconSize: [24, 24], iconAnchor: [12, 12],
      });
      state.layers.drone = L.marker([lat, lon], { icon: icon }).addTo(state.map);
    } else {
      state.layers.drone.setLatLng([lat, lon]);
      var el = state.layers.drone.getElement();
      if (el) {
        var inner = el.querySelector(".drone-marker");
        if (inner) inner.style.transform = "rotate(" + (heading || 0) + "deg)";
      }
    }
  }

  // ---- charts ---------------------------------------------------------

  function makeChart(canvasId, color, ymax) {
    var ctx = $(canvasId).getContext("2d");
    return new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [{
          data: [],
          borderColor: color,
          backgroundColor: color + "33",
          borderWidth: 1.4,
          pointRadius: 0,
          fill: true,
          tension: 0.25,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { min: 0, max: ymax, ticks: { color: "#8a93a0", font: { size: 9 } },
               grid: { color: "#2a313a" } },
        },
      },
    });
  }

  function initCharts() {
    state.charts.rgb = makeChart("chart-rgb", "#ff8c42", 1.0);
    state.charts.thermal = makeChart("chart-thermal", "#ef5350", 30.0);
    state.charts.persistence = makeChart("chart-persistence", "#4fc3f7", 8.0);
  }

  function pushChartPoint(g, t) {
    // Retain ~60 points (~60 seconds at 1Hz).
    var KEEP = 60;
    state.chartLabels.push(t);
    state.chartBuffer.rgb.push(g.rgb_score || 0);
    state.chartBuffer.thermal.push(g.thermal_delta_c || 0);
    state.chartBuffer.persistence.push(g.persistence || 0);
    if (state.chartLabels.length > KEEP) {
      state.chartLabels.shift();
      state.chartBuffer.rgb.shift();
      state.chartBuffer.thermal.shift();
      state.chartBuffer.persistence.shift();
    }
    ["rgb", "thermal", "persistence"].forEach(function (k) {
      var c = state.charts[k];
      c.data.labels = state.chartLabels;
      c.data.datasets[0].data = state.chartBuffer[k];
      c.update("none");
    });
  }

  // ---- replay loop ----------------------------------------------------

  function applyRow(row, idx) {
    if (!row) return;
    state.flownPath.push([row.lat, row.lon]);
    if (state.layers.flown) state.layers.flown.setLatLngs(state.flownPath);
    ensureDroneMarker(row.lat, row.lon, row.heading_deg);

    var startTs = state.log.length ? tsSeconds(state.log[0].ts) : 0;
    var curTs = tsSeconds(row.ts);
    var elapsed = Math.max(0, curTs - startTs);
    var total = state.manifest && state.manifest.duration_s
      ? Math.floor(state.manifest.duration_s) : 0;
    $("hud-t").textContent = fmtClock(elapsed) + " / " + fmtClock(total);
    $("hud-batt").textContent = (row.battery_pct != null ? row.battery_pct.toFixed(1) : "--") + "%";
    $("hud-alt").textContent = (row.alt_agl_m != null ? row.alt_agl_m.toFixed(0) : "--") + "m";
    $("hud-spd").textContent = (row.speed_mps != null ? row.speed_mps.toFixed(1) : "--") + "m/s";

    var gs = row.gate_state || {};
    pushChartPoint(gs, elapsed);
    var label = $("gate-state-label");
    if (gs.open) {
      label.textContent = "GATE OPEN  rgb=" + (gs.rgb_score || 0).toFixed(2)
        + "  thΔ=" + (gs.thermal_delta_c || 0).toFixed(1) + "  pers=" + (gs.persistence || 0);
      label.classList.add("open");
    } else {
      label.textContent = "gate closed  rgb=" + (gs.rgb_score || 0).toFixed(2)
        + "  thΔ=" + (gs.thermal_delta_c || 0).toFixed(1) + "  pers=" + (gs.persistence || 0);
      label.classList.remove("open");
    }
    state.cursor = idx;
  }

  function startReplay() {
    if (state.playing) return;
    if (state.sse) { state.sse.close(); state.sse = null; }
    if (!state.flightId) return;

    state.playing = true;
    $("btn-play").disabled = true;
    $("btn-pause").disabled = false;

    var url = "/api/flights/" + encodeURIComponent(state.flightId)
      + "/replay?speed=" + state.speed;
    var sse = new EventSource(url);
    state.sse = sse;
    sse.addEventListener("tick", function (ev) {
      try {
        var data = JSON.parse(ev.data);
        applyRow(data.row, data.index);
      } catch (e) { /* swallow */ }
    });
    sse.addEventListener("end", function () {
      stopReplay();
    });
    sse.onerror = function () {
      // browser auto-reconnects; we just stop.
      stopReplay();
    };
  }

  function stopReplay() {
    state.playing = false;
    if (state.sse) { state.sse.close(); state.sse = null; }
    $("btn-play").disabled = false;
    $("btn-pause").disabled = true;
  }

  function restartReplay() {
    stopReplay();
    state.flownPath = [];
    if (state.layers.flown) state.layers.flown.setLatLngs([]);
    state.chartBuffer = { rgb: [], thermal: [], persistence: [] };
    state.chartLabels = [];
    ["rgb", "thermal", "persistence"].forEach(function (k) {
      state.charts[k].data.labels = [];
      state.charts[k].data.datasets[0].data = [];
      state.charts[k].update("none");
    });
    state.cursor = 0;
    startReplay();
  }

  // ---- analysis + signals table --------------------------------------

  function renderAnalysis(a) {
    if (!a) return;
    var grid = $("analysis-grid");
    function set(k, v) {
      var el = grid.querySelector('[data-k="' + k + '"]');
      if (el) el.textContent = v;
    }
    set("area", a.area_covered_km2 + " km²");
    set("path", a.path_length_km + " km");
    set("signals", a.signals_total);
    set("bytype", Object.keys(a.signals_by_type || {}).length
      ? Object.keys(a.signals_by_type).map(function (k) {
        return k + " " + a.signals_by_type[k];
      }).join(", ") : "-");
    set("bypri", Object.keys(a.signals_by_priority || {}).length
      ? Object.keys(a.signals_by_priority).map(function (k) {
        return k + " " + a.signals_by_priority[k];
      }).join(", ") : "-");
    var pct = a.gate_approaches > 0
      ? " (" + Math.round(100 * a.gate_hit_rate) + "%)"
      : "";
    set("gate", a.gate_hits + " / " + a.gate_approaches + pct);
    set("risk", a.max_risk_score);
    set("batt", a.battery_consumed_pct + "%");
    set("alt", a.max_alt_agl_m + " m");
    set("spd", a.mean_speed_mps + " m/s");
  }

  function renderSignalsTable() {
    var tbody = document.querySelector("#signals-table tbody");
    tbody.innerHTML = "";
    var startTs = state.log.length ? tsSeconds(state.log[0].ts) : 0;
    state.signals.forEach(function (s) {
      var dt = Math.max(0, tsSeconds(s.timestamp) - startTs);
      var tr = document.createElement("tr");
      tr.innerHTML = "<td>T+" + dt + "s</td>"
        + "<td>" + s.signal_type + "</td>"
        + "<td>" + Math.round((s.confidence || 0) * 100) + "%</td>"
        + "<td>" + (s.recommended_action || "-").replace(/_/g, " ") + "</td>";
      tr.addEventListener("click", function () {
        var lat = (s.target_coords && s.target_coords.lat) || s.coords.lat;
        var lon = (s.target_coords && s.target_coords.lon) || s.coords.lon;
        state.map.setView([lat, lon], 16);
      });
      tbody.appendChild(tr);
    });
  }

  // ---- flight loading -------------------------------------------------

  function selectFlight(flightId) {
    stopReplay();
    state.flightId = flightId;
    state.log = [];
    state.signals = [];
    state.analysis = null;
    clearMapLayers();
    state.chartBuffer = { rgb: [], thermal: [], persistence: [] };
    state.chartLabels = [];
    if (state.charts.rgb) {
      ["rgb", "thermal", "persistence"].forEach(function (k) {
        state.charts[k].data.labels = [];
        state.charts[k].data.datasets[0].data = [];
        state.charts[k].update("none");
      });
    }

    var prefix = "/api/flights/" + encodeURIComponent(flightId);
    Promise.all([
      fetchJson(prefix + "/manifest"),
      fetchJson(prefix + "/flight_log"),
      fetchJson(prefix + "/signals"),
      fetchJson(prefix + "/analysis"),
    ]).then(function (vals) {
      state.manifest = vals[0];
      state.log = vals[1];
      state.signals = vals[2];
      state.analysis = vals[3];
      renderManifestOnMap();
      renderSignalsOnMap();
      renderSignalsTable();
      renderAnalysis(state.analysis);

      // Show first row immediately so the user sees the takeoff state.
      if (state.log.length) applyRow(state.log[0], 0);
    }).catch(function (err) {
      console.error("flight load failed", err);
    });
  }

  function loadFlightList() {
    return fetchJson("/api/flights").then(function (flights) {
      var sel = $("flight-select");
      sel.innerHTML = "";
      flights.forEach(function (f) {
        var opt = document.createElement("option");
        opt.value = f.flight_id;
        var label = (f.mission_name || f.flight_id) + " — " + (f.scenario_name || "")
          + (f.signals_count != null ? " · " + f.signals_count + " sig" : "");
        opt.textContent = label;
        sel.appendChild(opt);
      });
      if (flights.length) selectFlight(flights[0].flight_id);
    });
  }

  // ---- wire up --------------------------------------------------------

  document.addEventListener("DOMContentLoaded", function () {
    initMap();
    initCharts();
    loadFlightList();

    $("flight-select").addEventListener("change", function (e) {
      selectFlight(e.target.value);
    });
    $("btn-play").addEventListener("click", startReplay);
    $("btn-pause").addEventListener("click", stopReplay);
    $("btn-restart").addEventListener("click", restartReplay);
    $("speed-select").addEventListener("change", function (e) {
      state.speed = parseFloat(e.target.value);
      if (state.playing) restartReplay();
    });
  });
})();
