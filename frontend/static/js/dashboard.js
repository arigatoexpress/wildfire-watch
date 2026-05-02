// wildfire-watch operator console — dashboard JS
// No build step. Plain ES2020 + Leaflet (CDN).

(function () {
  'use strict';

  const cfg = window.WFW_CONFIG || {};
  const headers = cfg.adminToken ? { 'X-Admin-Token': cfg.adminToken } : {};

  const AOR_CENTER = [38.78, -106.96]; // mid-corridor
  const AOR_ZOOM = 11;

  let map, signalsLayer, aorLayer;

  function setStatus(label, klass) {
    const el = document.getElementById('conn-status');
    if (!el) return;
    el.textContent = label;
    el.classList.remove('ok', 'err');
    if (klass) el.classList.add(klass);
  }

  async function jget(url) {
    const r = await fetch(url, { headers });
    if (!r.ok) throw new Error(`${url} -> ${r.status}`);
    return r.json();
  }

  function fmtTs(iso) {
    if (!iso) return '—';
    try {
      const d = new Date(iso);
      if (isNaN(d)) return iso;
      return d.toISOString().replace('T', ' ').replace('Z', 'Z');
    } catch (_) {
      return iso;
    }
  }

  function fmtNum(n, digits = 1) {
    if (n === null || n === undefined || Number.isNaN(n)) return '—';
    return Number(n).toFixed(digits);
  }

  function riskClass(r) {
    if (r === null || r === undefined) return '';
    if (r >= 75) return 'risk-hi';
    if (r >= 50) return 'risk-mid';
    return 'risk-low';
  }

  function markerColor(sig) {
    if (sig.signal_type === 'system_event') return '#7c8597';
    const r = Number(sig.risk_score) || 0;
    if (r >= 75) return '#ef4444';
    if (r >= 50) return '#f59e0b';
    return '#22c55e';
  }

  // ----- map -----
  function initMap() {
    map = L.map('map', { zoomControl: true }).setView(AOR_CENTER, AOR_ZOOM);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap',
      className: 'wfw-tiles'
    }).addTo(map);
    signalsLayer = L.layerGroup().addTo(map);
  }

  function styleAOR(feature) {
    const props = feature.properties || {};
    if (props.zone_id && props.zone_id.includes('wilderness')) {
      return { color: '#ef4444', weight: 2, dashArray: '6,4', fillColor: '#ef4444', fillOpacity: 0.06 };
    }
    return { color: '#3b82f6', weight: 2, fillColor: '#3b82f6', fillOpacity: 0.08 };
  }

  function aorPopup(feature) {
    const p = feature.properties || {};
    const rows = [
      ['zone', p.zone_id || '—'],
      ['fuel_load', p.fuel_load_class || '—'],
      ['risk', p.primary_risk || '—'],
      ['elev (m)', p.elevation_min_m && p.elevation_max_m ? `${p.elevation_min_m}–${p.elevation_max_m}` : '—'],
      ['phase', p.phase !== undefined ? `Phase ${p.phase}` : '—']
    ];
    return rows.map(r => `<div><strong>${r[0]}</strong>: <span class="mono">${r[1]}</span></div>`).join('');
  }

  async function loadAOR() {
    try {
      const data = await jget('/api/aor');
      aorLayer = L.geoJSON(data, {
        style: styleAOR,
        onEachFeature: (f, lyr) => lyr.bindPopup(aorPopup(f))
      }).addTo(map);
      try {
        const b = aorLayer.getBounds();
        if (b.isValid()) map.fitBounds(b, { padding: [20, 20] });
      } catch (_) {}
    } catch (e) {
      console.warn('aor load failed', e);
    }
  }

  function signalPopup(s) {
    const rows = [
      ['ts', fmtTs(s.timestamp)],
      ['zone', s.zone_id || '—'],
      ['type', s.signal_type || '—'],
      ['risk', s.risk_score !== undefined ? s.risk_score : '—'],
      ['conf', s.confidence !== undefined ? fmtNum(s.confidence, 2) : '—'],
      ['drone', s.drone_id || '—'],
      ['action', s.recommended_action || '—']
    ];
    return rows.map(r => `<div><strong>${r[0]}</strong>: <span class="mono">${r[1]}</span></div>`).join('');
  }

  function renderMarkers(signals) {
    signalsLayer.clearLayers();
    signals.forEach(s => {
      const c = (s.target_coords && s.target_coords.lat) ? s.target_coords : s.coords;
      if (!c || c.lat === undefined || c.lon === undefined) return;
      const isHB = s.signal_type === 'system_event';
      const radius = isHB ? 4 : (Number(s.risk_score) >= 75 ? 9 : 7);
      L.circleMarker([c.lat, c.lon], {
        radius,
        color: markerColor(s),
        fillColor: markerColor(s),
        fillOpacity: isHB ? 0.5 : 0.85,
        weight: isHB ? 1 : 2
      })
        .bindPopup(signalPopup(s))
        .addTo(signalsLayer);
    });
  }

  // ----- KPI render -----
  function renderKPIs(k) {
    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = (val === null || val === undefined || val === '') ? '—' : val;
    };
    set('kpi-24h', k.last_24h);
    set('kpi-7d', k.last_7d);
    set('kpi-total', k.total);
    set('kpi-zone', k.highest_risk_zone || '—');
    set('kpi-zone-risk', k.highest_risk_value !== null ? `avg risk ${k.highest_risk_value}` : '—');
    set('kpi-heartbeat', fmtTs(k.last_heartbeat));
    set('kpi-retry', k.retry_queue_depth);
  }

  // ----- sensors -----
  function renderSensors(sensors) {
    const tbody = document.querySelector('#sensor-table tbody');
    const counter = document.getElementById('sensor-count');
    if (counter) counter.textContent = `${sensors.length} sensor${sensors.length === 1 ? '' : 's'}`;
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!sensors.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="dim-cell">no sensor heartbeats yet</td></tr>';
      return;
    }
    for (const s of sensors) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${s.drone_id}</td>
        <td><span class="badge ${s.status}">${s.status}</span></td>
        <td>${fmtTs(s.last_seen)}</td>
        <td>${fmtNum(s.last_seen_age_min)}</td>
        <td>${s.signal_count}</td>
        <td>${s.last_zone || '—'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  // ----- signals table -----
  function renderSignalsTable(signals) {
    const tbody = document.querySelector('#signals-table tbody');
    if (!tbody) return;
    tbody.innerHTML = '';
    if (!signals.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="dim-cell">no signals match the current filters</td></tr>';
      return;
    }
    for (const s of signals) {
      const tr = document.createElement('tr');
      const r = s.risk_score;
      tr.innerHTML = `
        <td>${fmtTs(s.timestamp)}</td>
        <td>${s.zone_id || '—'}</td>
        <td>${s.signal_type || '—'}</td>
        <td class="${riskClass(r)}">${r !== undefined ? r : '—'}</td>
        <td>${s.confidence !== undefined ? fmtNum(s.confidence, 2) : '—'}</td>
        <td>${s.drone_id || '—'}</td>
        <td>${s.recommended_action || '—'}</td>
      `;
      tbody.appendChild(tr);
    }
  }

  function populateZoneFilter(signals) {
    const sel = document.getElementById('filter-zone');
    if (!sel) return;
    const zones = Array.from(new Set(signals.map(s => s.zone_id).filter(Boolean))).sort();
    // wipe but keep "all"
    while (sel.options.length > 1) sel.remove(1);
    for (const z of zones) {
      const opt = document.createElement('option');
      opt.value = z;
      opt.textContent = z;
      sel.appendChild(opt);
    }
  }

  // ----- main load -----
  async function loadAll() {
    try {
      const [kpis, sigs, sensors] = await Promise.all([
        jget('/api/kpis'),
        jget('/api/signals?limit=500'),
        jget('/api/sensors')
      ]);
      renderKPIs(kpis);
      renderMarkers(sigs.signals || []);
      populateZoneFilter(sigs.signals || []);
      renderSignalsTable(sigs.signals || []);
      renderSensors(sensors.sensors || []);
      setStatus('live', 'ok');
    } catch (e) {
      console.error(e);
      setStatus('error', 'err');
    }
  }

  async function applyFilters() {
    const zone = document.getElementById('filter-zone').value;
    const type = document.getElementById('filter-type').value;
    const risk = document.getElementById('filter-risk').value;
    const params = new URLSearchParams();
    if (zone) params.set('zone', zone);
    if (type) params.set('signal_type', type);
    if (risk) params.set('min_risk', risk);
    params.set('limit', '500');
    try {
      const data = await jget('/api/signals?' + params.toString());
      renderSignalsTable(data.signals || []);
      renderMarkers(data.signals || []);
    } catch (e) {
      console.error(e);
      setStatus('error', 'err');
    }
  }

  function bindUi() {
    document.getElementById('filter-apply').addEventListener('click', applyFilters);
    const modal = document.getElementById('howto-modal');
    document.getElementById('howto-btn').addEventListener('click', () => modal.classList.remove('hidden'));
    document.getElementById('howto-close').addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.add('hidden'); });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    initMap();
    bindUi();
    await loadAOR();
    await loadAll();
    // poll every 30s
    setInterval(loadAll, 30_000);
  });
})();
