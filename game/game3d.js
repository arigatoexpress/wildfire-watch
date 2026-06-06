/* =====================================================================
 * Wildfire Watch: FIREFIGHT — 3D
 * ---------------------------------------------------------------------
 * A true 3D firefighting drone simulator over the real wildfire-watch
 * AOR (Slate River drainage, Gunnison Valley + Crested Butte, CO).
 *
 * The simulation core (fire-spread grid, AI fleet, suppression, scoring,
 * and the real flight-log export) is identical in spirit to the 2D build
 * and operates purely in grid space — only the renderer and flight
 * controls are 3D. Built on a locally-vendored Three.js (r128); no CDN,
 * works offline on file://.  Keyboard + Gamepad.
 * ===================================================================== */
'use strict';

/* ----------------------------- Real AOR geo ----------------------------- */
const ZONE = {
  id: 'slate-river-drainage',
  fuel_load_class: 'high',
  primary_risk: 'beetle-kill spruce/fir',
  lonMin: -107.0060, lonMax: -106.9940,
  latMin: 38.9035, latMax: 38.9165,
  alt_msl_m: 2743,
};

/* ----------------------------- Tunables ----------------------------- */
const COLS = 84, ROWS = 54;
const CELL = 4;                      // world units per grid cell
const AMP = 26;                      // terrain height amplitude
const RIVER_DEPTH = 6;
const HOVER = 14;                    // default drone height above terrain

const T = { ROCK: 0, FUEL: 1, BURNING: 2, BURNT: 3, WATER: 4, STRUCT: 5, STRUCT_BURNT: 6 };

// ---- real-world scale + airframe (from sim/airframe.py + the 1 km² mission) ----
const METERS_PER_CELL = 9;           // grid cell ground size (m); 84*9 ≈ 0.76 km within the 1 km² zone
// Heavy-lift firefighting multirotor carrying water/retardant. Speed envelope
// from the Mavic-class profile in sim/airframe.py, derated for payload + the
// ~9,000 ft / 30% high-altitude derating noted in the Slate River mission YAML.
const AF = { cruiseMps: 9, maxMps: 16, climbMps: 4, batteryMin: 13, ceilingAGL: 120 };
const M2C = (m) => m / METERS_PER_CELL;            // m/s  -> cells/s
const C2M = (c) => c * METERS_PER_CELL;            // cells/s -> m/s
const DRONE_SPEED = M2C(AF.maxMps);                // top speed, cells/s
const ACCEL = M2C(7.5);                            // flight inertia, cells/s^2
const BATT_DRAIN_PS = 100 / (AF.batteryMin * 60);  // %/s at nominal load

const TANK_MAX = 100;                // % of a ~40 L retardant payload
const TANK_LITERS = 40;
const TANK_SPRAY_RATE = 22;          // %/s while spraying
const TANK_REFILL_RATE = 24;         // %/s scooping over the river
const SPRAY_POWER = 3.1;             // intensity knocked down /s at the nozzle
const SPRAY_RADIUS = 2.3;
const BOMB_RADIUS = 4.6;
const BOMB_COUNT_START = 2;
const MATCH_SECONDS = 180;

// ---- fire behaviour (wind + slope driven, Rothermel-flavoured) ----
const IGNITE_BASE = 0.10;            // base spread coefficient (calibrated to ~1-2 m/s head-fire)
const BURN_RATE = 0.09;              // fuel consumed /s at full intensity
const INTENSITY_GROW = 0.3;          // young fires stay weak (and killable) longer
const WIND_BIAS = 1.05;             // downwind acceleration
const SLOPE_BIAS = 1.8;             // uphill acceleration (per unit normalized slope)
const LIGHTNING_EVERY = 10.0;        // sustained ignition pressure keeps the race alive
const WET_FUEL_SECONDS = 30;         // firebreaks / wet lines hold longer
const SPOT_CHANCE_PS = 0.022;        // per-burning-cell chance/s to throw a downwind ember

/* ----------------------------- helpers ----------------------------- */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const lerp = (a, b, t) => a + (b - a) * t;
const idx = (c, r) => r * COLS + c;
const inBounds = (c, r) => c >= 0 && c < COLS && r >= 0 && r < ROWS;
const gridToLat = (gy) => lerp(ZONE.latMax, ZONE.latMin, gy / ROWS);
const gridToLon = (gx) => lerp(ZONE.lonMin, ZONE.lonMax, gx / COLS);
// grid <-> world (Y is up). worldX ~ gx, worldZ ~ gy.
const wx = (gx) => (gx - COLS / 2) * CELL;
const wz = (gy) => (gy - ROWS / 2) * CELL;

/* ===================================================================== */
/*  Particle field (reused for fire / smoke / spray)                     */
/* ===================================================================== */
function radialTexture(inner, outer) {
  const s = 64, cv = document.createElement('canvas'); cv.width = cv.height = s;
  const x = cv.getContext('2d');
  const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  g.addColorStop(0, inner); g.addColorStop(0.4, inner); g.addColorStop(1, outer);
  x.fillStyle = g; x.fillRect(0, 0, s, s);
  const tex = new THREE.CanvasTexture(cv); return tex;
}

class ParticleField {
  constructor(scene, max, size, blending, texture, opacity) {
    this.max = max; this.pool = [];
    this.pos = new Float32Array(max * 3);
    this.col = new Float32Array(max * 3);
    this.geo = new THREE.BufferGeometry();
    this.geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    this.geo.setAttribute('color', new THREE.BufferAttribute(this.col, 3));
    this.mat = new THREE.PointsMaterial({
      size, map: texture, transparent: true, depthWrite: false,
      blending, vertexColors: true, opacity: opacity == null ? 1 : opacity,
      sizeAttenuation: true,
    });
    this.points = new THREE.Points(this.geo, this.mat);
    this.points.frustumCulled = false;
    scene.add(this.points);
  }
  spawn(x, y, z, vx, vy, vz, life, r, g, b, grav) {
    if (this.pool.length >= this.max) return;
    this.pool.push({ x, y, z, vx, vy, vz, life, max: life, r, g, b, grav: grav || 0 });
  }
  update(dt) {
    const p = this.pool;
    for (let i = p.length - 1; i >= 0; i--) {
      const o = p[i];
      o.x += o.vx * dt; o.y += o.vy * dt; o.z += o.vz * dt;
      o.vy += o.grav * dt; o.life -= dt;
      if (o.life <= 0) { p[i] = p[p.length - 1]; p.pop(); }
    }
    const n = p.length, pos = this.pos, col = this.col;
    for (let i = 0; i < n; i++) {
      const o = p[i], k = o.life / o.max;
      pos[i * 3] = o.x; pos[i * 3 + 1] = o.y; pos[i * 3 + 2] = o.z;
      col[i * 3] = o.r * k; col[i * 3 + 1] = o.g * k; col[i * 3 + 2] = o.b * k;
    }
    this.geo.setDrawRange(0, n);
    this.geo.attributes.position.needsUpdate = true;
    this.geo.attributes.color.needsUpdate = true;
  }
  clear() { this.pool.length = 0; this.geo.setDrawRange(0, 0); }
}

/* ===================================================================== */
/*  GAME                                                                 */
/* ===================================================================== */
class Game3D {
  constructor(glCanvas, hudCanvas) {
    this.gl = glCanvas; this.hud = hudCanvas; this.hctx = hudCanvas.getContext('2d');
    this.state = 'menu'; this.difficulty = 1;
    this.best = this._loadBest();
    this.input = new Input3D(glCanvas);
    this.audio = new AudioEngine();
    this.menuSel = 1; this.shake = 0; this.popups = []; this.toast = null; this.toastT = 0;
    this.showInputDebug = false;
    let inv = false, sens = 1.0;
    try { inv = localStorage.getItem('wfw_ff3d_invx') === '1'; sens = parseFloat(localStorage.getItem('wfw_ff3d_sens')) || 1.0; } catch (e) {}
    this.invertCamX = inv; this.camSens = sens;
    this.input.onConnect = (name) => { this.toast = 'CONTROLLER CONNECTED — ' + name; this.toastT = 3.2; this.input.rumble(0.5, 0.4, 220); };

    this.renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true });
    this.renderer.setClearColor(0x9fb8cc);
    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x9fb8cc, CELL * COLS * 0.85, CELL * COLS * 1.9);
    this.camera = new THREE.PerspectiveCamera(60, 1, 0.5, 4000);
    this.camYaw = 0; this.orbit = 0; this.camDist = 44; this.camPitch = 0.95;
    this.camPos = new THREE.Vector3(0, 200, 200);

    // lights
    this.scene.add(new THREE.HemisphereLight(0xcfe3ff, 0x3a3326, 0.9));
    this.scene.add(new THREE.AmbientLight(0x404040, 0.5));
    const sun = new THREE.DirectionalLight(0xfff2d8, 1.0);
    sun.position.set(120, 260, 80); this.scene.add(sun);
    this.fireLight = new THREE.PointLight(0xff6622, 0, 260, 2);
    this.scene.add(this.fireLight);

    // particle textures + fields
    const soft = radialTexture('rgba(255,255,255,1)', 'rgba(255,255,255,0)');
    this.pFire = new ParticleField(this.scene, 4000, 7, THREE.AdditiveBlending, soft, 1);
    this.pSmoke = new ParticleField(this.scene, 2600, 12, THREE.NormalBlending, soft, 0.28);
    this.pSpray = new ParticleField(this.scene, 1800, 4.5, THREE.AdditiveBlending, soft, 1);

    this.terrainMesh = null; this.droneObjs = [];
    this.pickupMeshes = [];
    this.message = null; this.messageTimer = 0;

    this._resize();
    window.addEventListener('resize', () => this._resize());
    this.last = 0;
    requestAnimationFrame((t) => this._loop(t));
  }

  _loadBest() { try { return JSON.parse(localStorage.getItem('wfw_firefight3d_best') || 'null'); } catch (e) { return null; } }
  _saveBest(b) { try { localStorage.setItem('wfw_firefight3d_best', JSON.stringify(b)); } catch (e) {} }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.W = window.innerWidth; this.H = window.innerHeight;
    this.renderer.setPixelRatio(dpr); this.renderer.setSize(this.W, this.H, false);
    this.camera.aspect = this.W / this.H; this.camera.updateProjectionMatrix();
    this.hud.width = Math.floor(this.W * dpr); this.hud.height = Math.floor(this.H * dpr);
    this.hud.style.width = this.W + 'px'; this.hud.style.height = this.H + 'px';
    this.hctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  /* --------------------------- match setup --------------------------- */
  start(difficulty) {
    this.difficulty = difficulty;
    this.seed = (Date.now() & 0x7fffffff) ^ Math.floor(performance.now());
    this.rng = mulberry32(this.seed);
    this.time = 0; this.lightningTimer = LIGHTNING_EVERY;
    this.frames = []; this.frameAccum = 0;
    this.pFire.clear(); this.pSmoke.clear(); this.pSpray.clear();
    this.message = null; this.messageTimer = 0;

    this._buildTerrain();
    this._buildTerrainMesh();
    this._buildScenery();

    const wa = this.rng() * Math.PI * 2;
    const windBase = [0.4, 0.6, 0.85][this.difficulty];
    this.wind = { x: Math.cos(wa), y: Math.sin(wa), spd: windBase + this.rng() * 0.25, ang: wa };
    this.fireMult = [0.78, 1.0, 1.32][this.difficulty];   // spread aggression by difficulty

    const nAI = [1, 2, 3][this.difficulty];
    let aiSkill = [0.55, 0.78, 0.95][this.difficulty];
    if (this.best && this.best.playerScore > this.best.aiScore) { aiSkill = clamp(aiSkill + 0.08, 0, 1); this.aiAdapted = true; }
    else this.aiAdapted = false;

    // remove old drone meshes + pads
    for (const o of this.droneObjs) this.scene.remove(o.group);
    this.droneObjs = [];
    for (const m of (this.padMeshes || [])) this.scene.remove(m);
    this.padMeshes = [];
    for (const m of (this.pickupMeshes || [])) this.scene.remove(m);
    this.pickupMeshes = [];
    this.agents = [];
    this.player = new Drone('YOU', 0x27e0ff, COLS * 0.18, ROWS * 0.82, true);
    this.agents.push(this.player);
    const aiColors = [0xff8a3d, 0xc77dff, 0xffd23d];
    for (let i = 0; i < nAI; i++) {
      const ai = new Drone('wfw-ai0' + (i + 1), aiColors[i % 3], COLS * (0.7 + i * 0.08), ROWS * 0.85, false);
      ai.skill = aiSkill; this.agents.push(ai);
    }
    for (const a of this.agents) {
      const d = buildDroneMesh(a.color, a.player);
      a.alt = this._terrainH(a.gx, a.gy) + HOVER;
      this.scene.add(d.group); this.droneObjs.push(d); a._mesh = d;
      // home / return-to-home pad (battery swap + retardant reload)
      const ring = new THREE.Mesh(new THREE.RingGeometry(4, 6, 24),
        new THREE.MeshBasicMaterial({ color: a.color, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
      ring.rotation.x = -Math.PI / 2;
      ring.position.set(wx(a.padGx), this._terrainH(a.padGx, a.padGy) + 0.5, wz(a.padGy));
      this.scene.add(ring); this.padMeshes.push(ring);
    }

    // ignite
    this.activeFires = 0;
    let seeds = [5, 7, 10][this.difficulty], placed = 0, tries = 0;
    while (placed < seeds && tries < 4000) {
      tries++;
      const c = 2 + Math.floor(this.rng() * (COLS - 4)), r = 2 + Math.floor(this.rng() * (ROWS - 4));
      const cell = this.grid[idx(c, r)];
      if (cell.type === T.FUEL && cell.fuelLoad > 0.55) { this._ignite(c, r, 0.5); placed++; }
    }
    this.structuresTotal = this.structures.length; this.structuresLost = 0;
    // camera start
    this.camYaw = 0; this.orbit = 0;
    this.state = 'playing';
  }

  _buildTerrain() {
    const g = new Array(COLS * ROWS), rng = this.rng;
    const noise = (x, y) => {
      let v = Math.sin(x * 0.20 + 1.3) * Math.cos(y * 0.18 + 0.7);
      v += 0.5 * Math.sin(x * 0.41 - 0.6) * Math.cos(y * 0.37 + 2.1);
      v += 0.25 * Math.sin(x * 0.83 + 2.4) * Math.cos(y * 0.79 - 1.1);
      return v / 1.75;
    };
    this.structures = [];
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const n = noise(c, r) + (rng() - 0.5) * 0.25;
      let cell;
      if (n < -0.42) cell = { type: T.ROCK, fuelLoad: 0 };
      else cell = { type: T.FUEL, fuelLoad: clamp(0.5 + n * 0.7, 0.18, 1) };
      cell.elev = (n + 1) * 0.5 * AMP + 2;
      cell.fuel = 1.0; cell.intensity = 0; cell.wetTimer = 0; cell.by = null; cell._struct = false;
      g[idx(c, r)] = cell;
    }
    // Slate River
    let rx = COLS * 0.30;
    for (let r = 0; r < ROWS; r++) {
      rx = clamp(rx + (rng() - 0.5) * 2.4, 4, COLS - 5);
      const w = 1 + (r % 7 === 0 ? 1 : 0);
      for (let d = -1; d <= w; d++) {
        const c = Math.round(rx) + d;
        if (inBounds(c, r)) { const cell = g[idx(c, r)]; cell.type = T.WATER; cell.fuelLoad = 0; cell.elev = Math.max(0, cell.elev - RIVER_DEPTH); }
      }
    }
    // cabins (WUI)
    const clusters = [[COLS * 0.66, ROWS * 0.30], [COLS * 0.78, ROWS * 0.62], [COLS * 0.45, ROWS * 0.5]];
    for (const [cx, cy] of clusters) {
      const n = 3 + Math.floor(rng() * 3);
      for (let i = 0; i < n; i++) {
        const c = Math.round(cx + (rng() - 0.5) * 7), r = Math.round(cy + (rng() - 0.5) * 7);
        if (inBounds(c, r) && g[idx(c, r)].type === T.FUEL) {
          const cell = g[idx(c, r)]; cell.type = T.STRUCT; cell.fuel = 1.0; cell.fuelLoad = 0.9;
          this.structures.push({ c, r });
        }
      }
    }
    this.grid = g;
  }

  _cellColor(cell) {
    switch (cell.type) {
      case T.ROCK: return [0.32, 0.34, 0.38];
      case T.WATER: return [0.08, 0.27, 0.42];
      case T.BURNT: return [0.10, 0.08, 0.07];
      case T.STRUCT_BURNT: return [0.14, 0.10, 0.08];
      case T.STRUCT: return cell.wetTimer > 0 ? [0.22, 0.42, 0.46] : [0.55, 0.42, 0.30];
      case T.FUEL: {
        const f = cell.fuelLoad;
        if (cell.wetTimer > 0) return [0.18, 0.36, 0.32];
        return [0.12 + f * 0.10, 0.30 + f * 0.34, 0.16 + f * 0.10];
      }
      case T.BURNING: {
        const i = cell.intensity;
        return [1.0, lerp(0.55, 0.16, i), lerp(0.18, 0.04, i)];
      }
      default: return [0, 0, 0];
    }
  }

  _terrainH(gx, gy) {
    const c = clamp(Math.round(gx), 0, COLS - 1), r = clamp(Math.round(gy), 0, ROWS - 1);
    return this.grid[idx(c, r)].elev;
  }

  _buildTerrainMesh() {
    if (this.terrainMesh) { this.scene.remove(this.terrainMesh); this.terrainMesh.geometry.dispose(); }
    const VX = COLS + 1, VZ = ROWS + 1, n = VX * VZ;
    const pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
    const vertH = (i, j) => {
      // average elevation of cells touching this vertex
      let s = 0, k = 0;
      for (const [dc, dr] of [[0, 0], [-1, 0], [0, -1], [-1, -1]]) {
        const c = i + dc, r = j + dr;
        if (inBounds(c, r)) { s += this.grid[idx(c, r)].elev; k++; }
      }
      return k ? s / k : 0;
    };
    for (let j = 0; j < VZ; j++) for (let i = 0; i < VX; i++) {
      const vi = j * VX + i;
      pos[vi * 3] = (i - COLS / 2) * CELL;
      pos[vi * 3 + 1] = vertH(i, j);
      pos[vi * 3 + 2] = (j - ROWS / 2) * CELL;
    }
    const indices = [];
    for (let j = 0; j < ROWS; j++) for (let i = 0; i < COLS; i++) {
      const a = j * VX + i, b = a + 1, c = a + VX, d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    geo.setIndex(indices);
    geo.computeVertexNormals();
    this.terrainGeo = geo; this.terrainVX = VX; this.terrainVZ = VZ;
    const mat = new THREE.MeshLambertMaterial({ vertexColors: true });
    this.terrainMesh = new THREE.Mesh(geo, mat);
    this.scene.add(this.terrainMesh);
    this._recolorTerrain();
  }

  _recolorTerrain() {
    const VX = this.terrainVX, VZ = this.terrainVZ, col = this.terrainGeo.attributes.color.array;
    for (let j = 0; j < VZ; j++) for (let i = 0; i < VX; i++) {
      const c = clamp(i, 0, COLS - 1), r = clamp(j, 0, ROWS - 1);
      const rgb = this._cellColor(this.grid[idx(c, r)]);
      const vi = j * VX + i;
      col[vi * 3] = rgb[0]; col[vi * 3 + 1] = rgb[1]; col[vi * 3 + 2] = rgb[2];
    }
    this.terrainGeo.attributes.color.needsUpdate = true;
    this._updateScenery();
  }

  _buildScenery() {
    if (this.treeMesh) { this.scene.remove(this.treeMesh); this.treeMesh.geometry.dispose(); this.treeMesh = null; }
    if (this.cabinMesh) { this.scene.remove(this.cabinMesh); this.cabinMesh.geometry.dispose(); this.cabinMesh = null; }
    const dummy = new THREE.Object3D(), col = new THREE.Color();
    // ---- pine trees on forested cells ----
    this.treeCells = []; const tm = [];
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const cell = this.grid[idx(c, r)];
      if (cell.type !== T.FUEL || cell.fuelLoad < 0.42) continue;
      if (((c * 7 + r * 13) % 10) > 6) continue;          // deterministic ~70% density
      this.treeCells.push(idx(c, r));
      tm.push({ c, r, h: 4 + cell.fuelLoad * 5 + (this.rng() * 2), sc: 0.7 + this.rng() * 0.6, rot: this.rng() * 6.28 });
    }
    const tgeo = new THREE.ConeGeometry(1.25, 1, 6);      // unit height; scaled per-instance
    const tmat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    const trees = new THREE.InstancedMesh(tgeo, tmat, tm.length || 1);
    trees.frustumCulled = false;
    for (let i = 0; i < tm.length; i++) {
      const t = tm[i], elev = this.grid[idx(t.c, t.r)].elev, hh = t.h;
      dummy.position.set(wx(t.c + 0.5), elev + hh * 0.5, wz(t.r + 0.5));
      dummy.rotation.set(0, t.rot, 0); dummy.scale.set(t.sc, hh, t.sc);
      dummy.updateMatrix(); trees.setMatrixAt(i, dummy.matrix);
      trees.setColorAt(i, col.setRGB(0.12, 0.34, 0.16));
    }
    trees.instanceMatrix.needsUpdate = true; if (trees.instanceColor) trees.instanceColor.needsUpdate = true;
    this.scene.add(trees); this.treeMesh = trees;
    // ---- cabins (WUI structures) as little boxes ----
    const cgeo = new THREE.BoxGeometry(3.2, 3, 3.2);
    const cmat = new THREE.MeshLambertMaterial({ color: 0xffffff });
    const cabins = new THREE.InstancedMesh(cgeo, cmat, this.structures.length || 1);
    cabins.frustumCulled = false;
    for (let i = 0; i < this.structures.length; i++) {
      const s = this.structures[i], elev = this.grid[idx(s.c, s.r)].elev;
      dummy.position.set(wx(s.c + 0.5), elev + 1.5, wz(s.r + 0.5)); dummy.rotation.set(0, 0, 0); dummy.scale.set(1, 1, 1);
      dummy.updateMatrix(); cabins.setMatrixAt(i, dummy.matrix);
      cabins.setColorAt(i, col.setRGB(0.62, 0.46, 0.32));
    }
    cabins.instanceMatrix.needsUpdate = true; if (cabins.instanceColor) cabins.instanceColor.needsUpdate = true;
    this.scene.add(cabins); this.cabinMesh = cabins;
  }

  _updateScenery() {
    const col = new THREE.Color();
    if (this.treeMesh && this.treeCells) {
      for (let i = 0; i < this.treeCells.length; i++) {
        const cell = this.grid[this.treeCells[i]];
        if (cell.type === T.BURNING) { const k = cell.intensity; col.setRGB(0.9 + k * 0.1, 0.4 - k * 0.2, 0.08); }
        else if (cell.type === T.BURNT) col.setRGB(0.09, 0.07, 0.06);
        else if (cell.wetTimer > 0) col.setRGB(0.12, 0.42, 0.40);
        else col.setRGB(0.11, 0.30 + cell.fuelLoad * 0.12, 0.15);
        this.treeMesh.setColorAt(i, col);
      }
      if (this.treeMesh.instanceColor) this.treeMesh.instanceColor.needsUpdate = true;
    }
    if (this.cabinMesh) {
      for (let i = 0; i < this.structures.length; i++) {
        const cell = this.grid[idx(this.structures[i].c, this.structures[i].r)];
        if (cell.type === T.STRUCT_BURNT) col.setRGB(0.12, 0.09, 0.07);
        else if (cell.type === T.BURNING) col.setRGB(0.95, 0.35, 0.1);
        else col.setRGB(0.62, 0.46, 0.32);
        this.cabinMesh.setColorAt(i, col);
      }
      if (this.cabinMesh.instanceColor) this.cabinMesh.instanceColor.needsUpdate = true;
    }
  }

  _ignite(c, r, intensity) {
    if (!inBounds(c, r)) return;
    const cell = this.grid[idx(c, r)];
    if ((cell.type === T.FUEL || cell.type === T.STRUCT) && cell.wetTimer <= 0) {
      if (cell.type === T.STRUCT) cell._struct = true;
      cell.type = T.BURNING; cell.intensity = Math.max(cell.intensity, intensity);
      this.activeFires++;
    }
  }

  /* ------------------------------ loop ------------------------------ */
  _loop(t) {
    const dt = this.last ? Math.min((t - this.last) / 1000, 0.05) : 0;
    this.last = t;
    this.input.poll();
    if (this.input.anyInput) this.audio.init();
    if (this.toastT > 0) this.toastT -= dt;
    if (this.input.pressed('KeyI') || this.input.gpPressed(8)) this.showInputDebug = !this.showInputDebug;
    if (this.input.pressed('KeyC') || this.input.gpPressed(3)) {
      this.invertCamX = !this.invertCamX;
      try { localStorage.setItem('wfw_ff3d_invx', this.invertCamX ? '1' : '0'); } catch (e) {}
      this.toast = 'CAMERA X-AXIS: ' + (this.invertCamX ? 'INVERTED' : 'NORMAL'); this.toastT = 1.8;
    }
    if (this.input.pressed('KeyV')) {
      this.camSens = this.camSens >= 1.4 ? 0.6 : +(this.camSens + 0.4).toFixed(1);
      try { localStorage.setItem('wfw_ff3d_sens', String(this.camSens)); } catch (e) {}
      this.toast = 'CAMERA SENSITIVITY: ' + this.camSens.toFixed(1) + 'x'; this.toastT = 1.8;
    }
    if (this.state === 'menu') { this._menuUpdate(); this.audio.quiet(); }
    else if (this.state === 'playing') this._update(dt);
    else if (this.state === 'over') { this._overUpdate(); this.audio.quiet(); }
    if (this.state !== 'menu') this.renderer.render(this.scene, this.camera);
    this._renderHUD();
    this.input.endFrame();
    requestAnimationFrame((tt) => this._loop(tt));
  }

  _menuUpdate() {
    const inp = this.input;
    if (inp.pressed('Digit1')) return this.start(0);
    if (inp.pressed('Digit2')) return this.start(1);
    if (inp.pressed('Digit3')) return this.start(2);
    let nav = 0;
    if (inp.pressed('ArrowDown') || inp.pressed('KeyS') || inp.gpPressed(13)) nav = 1;
    if (inp.pressed('ArrowUp') || inp.pressed('KeyW') || inp.gpPressed(12)) nav = -1;
    const ls = inp.axes();
    this._navCD = Math.max(0, (this._navCD || 0) - 0.016);
    if (ls && Math.abs(ls.ly) > 0.6 && this._navCD <= 0) { nav = ls.ly > 0 ? 1 : -1; this._navCD = 0.22; }
    if (nav) this.menuSel = (this.menuSel + nav + 3) % 3;
    // confirm: Enter / Space / bottom-face (0) / Start (9) / right-trigger (7)
    if (inp.pressed('Enter') || inp.pressed('Space') || inp.gpPressed(0) || inp.gpPressed(9) || inp.gpPressed(7)) this.start(this.menuSel);
  }
  _overUpdate() {
    if (this.input.pressed('Enter') || this.input.pressed('Space') || this.input.gpPressed(0)) this.state = 'menu';
    if (this.input.pressed('KeyL') || this.input.gpPressed(2)) this.downloadLog();
  }

  _update(dt) {
    this.time += dt;
    this.wind.ang += (this.rng() - 0.5) * 0.4 * dt;
    this.wind.x = Math.cos(this.wind.ang); this.wind.y = Math.sin(this.wind.ang);
    this.windGust = clamp(1 + 0.4 * Math.sin(this.time * 0.7) + (this.rng() - 0.5) * 0.2, 0.55, 1.9);

    this._stepFire(dt);
    this._lightning(dt);
    for (const a of this.agents) {
      if (a.player) this._controlPlayer(a, dt); else this._controlAI(a, dt);
      this._integrate(a, dt);
      this._suppress(a, dt);
      this._power(a, dt);
    }
    this._pickups(dt);
    this._emitFireSmoke(dt);
    this.pFire.update(dt); this.pSmoke.update(dt); this.pSpray.update(dt);
    this._recolorTerrain();
    this._updateMeshes(dt);
    this._updateCamera(dt);
    this._recordFrame(dt);
    // audio levels + game-feel
    this.audio.setSpray(this.player.spraying && this.player.tank > 0 && this.player.swapT <= 0);
    this.audio.setFire(this.activeFires / 38);
    this.audio.setRotor(0.25 + (this.player.speed / DRONE_SPEED) * 0.6);
    if (this._pScore > 0) {
      this.popups.push({ x: wx(this.player.gx), y: this.player.alt + 5, z: wz(this.player.gy), txt: '+' + this._pScore, life: 0.9, max: 0.9 });
      if (this.popups.length > 24) this.popups.shift();
      this._pScore = 0;
    }
    for (let i = this.popups.length - 1; i >= 0; i--) { const q = this.popups[i]; q.life -= dt; q.y += dt * 6; if (q.life <= 0) this.popups.splice(i, 1); }
    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 2.5);
    if (this.messageTimer > 0) this.messageTimer -= dt;

    const timeUp = this.time >= MATCH_SECONDS;
    const contained = this.activeFires <= 0 && this.time > 1.5;
    const overrun = this.structuresLost >= this.structuresTotal && this.structuresTotal > 0;
    if (timeUp || contained || overrun) this._endMatch(contained, overrun);
  }

  _lightning(dt) {
    this.lightningTimer -= dt;
    if (this.lightningTimer <= 0) {
      this.lightningTimer = LIGHTNING_EVERY * (0.6 + this.rng());
      for (let k = 0; k < 12; k++) {
        const c = Math.floor(this.rng() * COLS), r = Math.floor(this.rng() * ROWS);
        const cell = this.grid[idx(c, r)];
        if (cell.type === T.FUEL && cell.fuelLoad > 0.4) { this._ignite(c, r, 0.4); break; }
      }
    }
  }

  _stepFire(dt) {
    const g = this.grid, ign = [], spots = [];
    const gust = this.windGust || 1;
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const cell = g[idx(c, r)];
      if (cell.wetTimer > 0) cell.wetTimer -= dt;
      if (cell.type !== T.BURNING) continue;
      cell.intensity = clamp(cell.intensity + INTENSITY_GROW * dt, 0, 1);
      cell.fuel -= BURN_RATE * dt * (0.4 + cell.intensity);
      if (cell.fuel <= 0) {
        cell.type = cell._struct ? T.STRUCT_BURNT : T.BURNT; cell.intensity = 0; this.activeFires--;
        if (cell._struct) this.structuresLost++;
        continue;
      }
      const neigh = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1]];
      for (const [dc, dr] of neigh) {
        const nc = c + dc, nr = r + dr;
        if (!inBounds(nc, nr)) continue;
        const nb = g[idx(nc, nr)];
        if ((nb.type !== T.FUEL && nb.type !== T.STRUCT) || nb.wetTimer > 0) continue;
        const len = Math.hypot(dc, dr) || 1;
        const align = (dc / len) * this.wind.x + (dr / len) * this.wind.y;
        const windF = Math.max(0.06, 1 + WIND_BIAS * this.wind.spd * gust * align);
        // slope factor — fire spreads markedly faster uphill (Rothermel)
        const dElev = (nb.elev - cell.elev) / METERS_PER_CELL;   // ~ tan(slope)
        const slopeF = Math.max(0.25, 1 + SLOPE_BIAS * dElev);
        const diag = len > 1.1 ? 0.7 : 1.0;
        let chance = IGNITE_BASE * this.fireMult * cell.intensity * nb.fuelLoad * windF * slopeF * diag * dt;
        if (nb.type === T.STRUCT) chance *= 0.8;
        if (this.rng() < chance) ign.push([nc, nr]);
      }
      // ember spotting: a crowning fire lofts embers far downwind
      if (cell.intensity > 0.7 && this.rng() < SPOT_CHANCE_PS * this.fireMult * this.wind.spd * gust * dt) {
        const dist = 5 + Math.floor(this.rng() * 11);
        spots.push([Math.round(c + this.wind.x * dist + (this.rng() - 0.5) * 4),
          Math.round(r + this.wind.y * dist + (this.rng() - 0.5) * 4)]);
      }
    }
    for (const [c, r] of ign) { const cell = g[idx(c, r)]; if (cell.type === T.STRUCT) cell._struct = true; this._ignite(c, r, 0.18); }
    for (const [c, r] of spots) {
      if (!inBounds(c, r)) continue;
      const cell = g[idx(c, r)];
      if ((cell.type === T.FUEL || cell.type === T.STRUCT) && cell.wetTimer <= 0) {
        if (cell.type === T.STRUCT) cell._struct = true; this._ignite(c, r, 0.12);
      }
    }
  }

  /* --------------------------- player control (3D) --------------------------- */
  _controlPlayer(a, dt) {
    const inp = this.input;
    let strafe = 0, ahead = 0;
    if (inp.down('ArrowLeft') || inp.down('KeyA')) strafe -= 1;
    if (inp.down('ArrowRight') || inp.down('KeyD')) strafe += 1;
    if (inp.down('ArrowUp') || inp.down('KeyW')) ahead += 1;
    if (inp.down('ArrowDown') || inp.down('KeyS')) ahead -= 1;
    const ls = inp.axes();
    if (ls) { strafe += ls.lx; ahead -= ls.ly; }
    // --- camera orbit FIRST (camera yaw is independent of the drone) ---
    const rs = inp.axesR();
    let orb = 0;
    if (inp.down('KeyQ')) orb += 1; if (inp.down('KeyE')) orb -= 1;
    if (rs) orb += rs.rx;                         // right-stick rotates the camera
    const inv = this.invertCamX ? -1 : 1, sens = this.camSens;
    this.camYaw += orb * 2.4 * dt * sens * inv;   // sticks / keys
    this.camYaw += inp.mouseDX * 0.6 * sens * inv; // mouse drag (already a per-frame delta)
    if (rs && Math.abs(rs.ry) > 0.01) this.camPitch = clamp(this.camPitch - rs.ry * 1.2 * dt, 0.2, 1.3);
    this.camDist = clamp(this.camDist + inp.wheel * 0.03, 22, 90);

    // --- screen-relative movement (W = away from camera, D = screen-right) ---
    // camera forward (grid) = (sin yaw, cos yaw); screen-right = (-cos yaw, sin yaw)
    // (verified against the live Three.js camera basis — see the dot-product test)
    const cy = this.camYaw, sn = Math.sin(cy), cs = Math.cos(cy);
    let mgx = -cs * strafe + sn * ahead;
    let mgy = sn * strafe + cs * ahead;
    const mag = Math.hypot(mgx, mgy);
    if (mag > 1) { mgx /= mag; mgy /= mag; }
    const top = a.maxSpeed();
    a.dvx = mgx * top; a.dvy = mgy * top;
    if (mag > 0.08) a.heading = Math.atan2(mgy, mgx);   // mesh facing only — does NOT move the camera

    // altitude nudge
    let dh = 0;
    if (inp.down('KeyR') || inp.gpDown(5)) dh += 1;
    if (inp.down('KeyF') || inp.gpDown(4)) dh -= 1;
    a.altOffset = clamp((a.altOffset || 0) + dh * 24 * dt, -6, 60);

    a.spraying = inp.down('Space') || inp.down('ShiftLeft') || inp.mouseLeft || inp.gpDown(7);
    if ((inp.pressed('KeyE') && false) || inp.pressed('Enter') || inp.mouseRightPressed || inp.gpPressed(0)) {
      if (a.bombs > 0) this._dropBomb(a);
    }
  }

  /* ----------------------------- AI control ----------------------------- */
  _controlAI(a, dt) {
    if (a.swapT > 0) { a.spraying = false; return; }
    // return-to-home for a battery swap when low, like the real RTH behaviour
    if (a.battery < 24) a.rth = true;
    if (a.rth) {
      this._steerTo(a, a.padGx, a.padGy); a.spraying = false;
      if (a.battery > 90) a.rth = false;
      return;
    }
    a.thinkT -= dt;
    let tgt = a.target && this.grid[idx(a.target.c, a.target.r)];
    if (!tgt || tgt.type !== T.BURNING || a.thinkT <= 0) { a.thinkT = lerp(0.55, 0.18, a.skill); a.target = this._aiPickTarget(a); }
    if (a.tank < 18 && !a.refilling) a.refilling = true;
    if (a.refilling) {
      const w = this._nearestWater(a);
      if (w) { this._steerTo(a, w.c + 0.5, w.r + 0.5); if (a.tank >= TANK_MAX - 2) a.refilling = false; a.spraying = false; return; }
      else a.refilling = false;
    }
    if (a.target) {
      const tc = a.target.c + 0.5, tr = a.target.r + 0.5;
      const d = Math.hypot(a.gx - tc, a.gy - tr);
      this._steerTo(a, tc, tr);
      a.spraying = d < SPRAY_RADIUS + 0.6 && a.tank > 0;
      if (a.bombs > 0 && d < 1.2 && this._fireDensity(a.target.c, a.target.r) >= 5 && a.skill > 0.7) this._dropBomb(a);
    } else { this._steerTo(a, COLS / 2, ROWS / 2); a.spraying = false; }
  }
  _steerTo(a, tc, tr) {
    let dx = tc - a.gx, dy = tr - a.gy; const d = Math.hypot(dx, dy) || 1;
    const spd = a.maxSpeed() * lerp(0.72, 1.0, a.skill);
    // ease off near the target so the AI doesn't overshoot (arrival behaviour)
    const arrive = clamp(d / 2.2, 0.25, 1);
    a.dvx = (dx / d) * spd * arrive; a.dvy = (dy / d) * spd * arrive;
    if (d > 0.3) a.heading = Math.atan2(dy, dx);
  }
  _aiPickTarget(a) {
    let best = null, bestScore = -1, g = this.grid;
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const cell = g[idx(c, r)]; if (cell.type !== T.BURNING) continue;
      const dist = Math.hypot(c - a.gx, r - a.gy);
      let threat = cell.intensity + this._fireDensity(c, r) * 0.12;
      if (this._nearStructure(c, r)) threat += 1.4;
      const score = threat - dist * lerp(0.06, 0.018, a.skill);
      if (score > bestScore) { bestScore = score; best = { c, r }; }
    }
    return best;
  }
  _fireDensity(c, r) { let n = 0; for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) if (inBounds(c + dc, r + dr) && this.grid[idx(c + dc, r + dr)].type === T.BURNING) n++; return n; }
  _nearStructure(c, r) { for (const s of this.structures) { const cell = this.grid[idx(s.c, s.r)]; if (cell.type === T.STRUCT_BURNT) continue; if (Math.abs(s.c - c) <= 2 && Math.abs(s.r - r) <= 2) return true; } return false; }
  _nearestWater(a) { let best = null, bd = 1e9, g = this.grid; for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) { if (g[idx(c, r)].type !== T.WATER) continue; const d = (c - a.gx) ** 2 + (r - a.gy) ** 2; if (d < bd) { bd = d; best = { c, r }; } } return best; }

  /* --------------------------- physics / actions --------------------------- */
  _integrate(a, dt) {
    // battery-swap landing: grounded, settle to the deck, no movement
    if (a.swapT > 0) {
      a.swapT -= dt; a.vx = a.vy = a.dvx = a.dvy = 0; a.speed = 0; a.rotor += dt * 5;
      a.alt = lerp(a.alt, this._terrainH(a.gx, a.gy) + 2.5, clamp(dt * 4, 0, 1));
      if (a.swapT <= 0) { a.battery = 100; a.tank = TANK_MAX; }   // fresh battery + reload
      return;
    }
    // acceleration-limited velocity (flight inertia / momentum)
    a.vx += clamp(a.dvx - a.vx, -ACCEL * dt, ACCEL * dt);
    a.vy += clamp(a.dvy - a.vy, -ACCEL * dt, ACCEL * dt);
    a.gx = clamp(a.gx + a.vx * dt, 0.4, COLS - 0.4);
    a.gy = clamp(a.gy + a.vy * dt, 0.4, ROWS - 0.4);
    a.speed = Math.hypot(a.vx, a.vy);
    a.rotor += dt * (26 + a.speed * 7);
    const targetAlt = this._terrainH(a.gx, a.gy) + HOVER + (a.altOffset || 0);
    a.alt = lerp(a.alt == null ? targetAlt : a.alt, targetAlt, clamp(dt * 4, 0, 1));
  }
  _power(a, dt) {
    const cell = this.grid[idx(clamp(Math.floor(a.gx), 0, COLS - 1), clamp(Math.floor(a.gy), 0, ROWS - 1))];
    if (cell && cell.type === T.WATER) a.tank = clamp(a.tank + TANK_REFILL_RATE * dt, 0, TANK_MAX); // scoop
    if (a.swapT > 0) return;
    // return-to-home pad: rapid battery swap + retardant reload
    if (Math.hypot(a.gx - a.padGx, a.gy - a.padGy) < 1.7 && a.speed < M2C(2.5)) {
      a.battery = clamp(a.battery + 30 * dt, 0, 100);
      a.tank = clamp(a.tank + 55 * dt, 0, TANK_MAX);
      return;
    }
    // drain: nominal hover + throttle + spray-pump load
    const throttle = a.speed / Math.max(0.001, DRONE_SPEED);
    const load = 0.5 + 0.75 * throttle + (a.spraying && a.tank > 0 ? 0.35 : 0);
    a.battery = clamp(a.battery - BATT_DRAIN_PS * load * dt, 0, 100);
    if (a.player && a.battery < 20 && !a.lowWarned) { a.lowWarned = true; this._flashMsg('LOW BATTERY — RTH', 1.4); this.audio.lowBatt(); this.input.rumble(0.4, 0.3, 200); }
    if (a.battery >= 60) a.lowWarned = false;
    if (a.battery <= 0) a.swapT = 5.0;                              // forced field swap
  }
  _suppress(a, dt) {
    if (!a.spraying || a.tank <= 0 || a.swapT > 0) { a.sprayFx = 0; return; }
    a.tank = clamp(a.tank - TANK_SPRAY_RATE * dt, 0, TANK_MAX); a.sprayFx = 1;
    const nx = a.gx + Math.cos(a.heading) * 1.1, ny = a.gy + Math.sin(a.heading) * 1.1;
    const cc = Math.round(nx), cr = Math.round(ny), R = Math.ceil(SPRAY_RADIUS);
    for (let dr = -R; dr <= R; dr++) for (let dc = -R; dc <= R; dc++) {
      const c = cc + dc, r = cr + dr;
      if (!inBounds(c, r) || Math.hypot(dc, dr) > SPRAY_RADIUS) continue;
      this._applyWater(c, r, a, SPRAY_POWER * dt);
    }
    // 3D spray particles from nozzle toward the ground ahead
    const ox = wx(a.gx), oy = a.alt, oz = wz(a.gy);
    const tx = wx(nx), tz = wz(ny), ty = this._terrainH(nx, ny) + 1;
    for (let i = 0; i < 3; i++) {
      const j = (this.rng() - 0.5) * 6;
      this.pSpray.spawn(ox, oy - 1, oz,
        (tx - ox) * 1.6 + j, (ty - oy) * 1.6, (tz - oz) * 1.6 + j,
        0.35, 0.55, 0.8, 1.0, -10);
    }
  }
  _applyWater(c, r, a, amount) {
    const cell = this.grid[idx(c, r)];
    if (cell.type === T.BURNING) {
      cell.intensity -= amount;
      if (this.rng() < 0.4) this.pSmoke.spawn(wx(c), this._terrainH(c, r) + 2, wz(r), 0, 4, 0, 0.6, 0.9, 0.95, 1.0, 1);
      if (cell.intensity <= 0) {
        cell.type = cell._struct ? T.STRUCT : T.FUEL; cell.intensity = 0; cell.wetTimer = WET_FUEL_SECONDS;
        cell.by = a.id; a.score++; this.activeFires--;
        if (a.player) this._pScore = (this._pScore || 0) + 1;
      }
    } else if ((cell.type === T.FUEL || cell.type === T.STRUCT) && cell.wetTimer < WET_FUEL_SECONDS) {
      cell.wetTimer = WET_FUEL_SECONDS; if (cell.by == null) cell.by = a.id;
    }
  }
  _dropBomb(a) {
    a.bombs--;
    const cc = Math.round(a.gx), cr = Math.round(a.gy), R = Math.ceil(BOMB_RADIUS);
    let got = 0;
    for (let dr = -R; dr <= R; dr++) for (let dc = -R; dc <= R; dc++) {
      const c = cc + dc, r = cr + dr;
      if (!inBounds(c, r) || Math.hypot(dc, dr) > BOMB_RADIUS) continue;
      const cell = this.grid[idx(c, r)];
      if (cell.type === T.BURNING) { cell.type = cell._struct ? T.STRUCT : T.FUEL; cell.intensity = 0; cell.wetTimer = WET_FUEL_SECONDS; cell.by = a.id; a.score++; this.activeFires--; got++; }
      else if (cell.type === T.FUEL || cell.type === T.STRUCT) cell.wetTimer = WET_FUEL_SECONDS;
    }
    const ox = wx(a.gx), oy = a.alt, oz = wz(a.gy);
    for (let i = 0; i < 120; i++) {
      const ang = this.rng() * Math.PI * 2, sp = 8 + this.rng() * 18;
      this.pSpray.spawn(ox, oy, oz, Math.cos(ang) * sp, -2 - this.rng() * 6, Math.sin(ang) * sp, 0.8, 0.6, 0.85, 1.0, -14);
    }
    if (a.player) {
      this._flashMsg('WATER BOMB  +' + got, 0.9); this.audio.bomb(); this.input.rumble(0.85, 0.6, 280); this.shake = 1.0;
      if (got > 0) this.popups.push({ x: ox, y: oy + 5, z: oz, txt: '+' + got, life: 1.1, max: 1.1 });
    }
  }

  /* --------------------------- pickups --------------------------- */
  _pickups(dt) {
    this.pickupTimer = (this.pickupTimer || 0) - dt;
    if (this.pickupTimer <= 0 && this.pickupMeshes.length < 3) {
      this.pickupTimer = 6 + this.rng() * 5;
      const kinds = ['bomb', 'tank', 'speed'], kind = kinds[Math.floor(this.rng() * kinds.length)];
      let c, r, tries = 0;
      do { c = 2 + Math.floor(this.rng() * (COLS - 4)); r = 2 + Math.floor(this.rng() * (ROWS - 4)); tries++; }
      while (tries < 40 && this.grid[idx(c, r)].type === T.WATER);
      const colr = kind === 'bomb' ? 0x9fe2ff : kind === 'tank' ? 0x7CFC00 : 0xffd23d;
      const m = new THREE.Mesh(new THREE.OctahedronGeometry(2.4), new THREE.MeshStandardMaterial({ color: colr, emissive: colr, emissiveIntensity: 0.6, metalness: 0.2, roughness: 0.4 }));
      m.position.set(wx(c + 0.5), this._terrainH(c, r) + 7, wz(r + 0.5));
      m.userData = { kind, gx: c + 0.5, gy: r + 0.5, t: 0 };
      this.scene.add(m); this.pickupMeshes.push(m);
    }
    for (let i = this.pickupMeshes.length - 1; i >= 0; i--) {
      const m = this.pickupMeshes[i], p = m.userData; p.t += dt;
      m.rotation.y += dt * 2; m.position.y = this._terrainH(Math.round(p.gx), Math.round(p.gy)) + 7 + Math.sin(p.t * 3) * 0.8;
      let taken = false;
      for (const a of this.agents) {
        if (Math.hypot(a.gx - p.gx, a.gy - p.gy) < 1.2) {
          if (p.kind === 'bomb') a.bombs += 2; else if (p.kind === 'tank') a.tank = TANK_MAX; else a.boost = 4;
          if (a.player) { this._flashMsg('+ ' + p.kind.toUpperCase(), 1.0); this.audio.pickup(); this.input.rumble(0.3, 0.3, 120); }
          taken = true; break;
        }
      }
      if (taken) { this.scene.remove(m); m.geometry.dispose(); this.pickupMeshes.splice(i, 1); }
    }
    for (const a of this.agents) if (a.boost > 0) a.boost -= dt;
  }

  /* --------------------------- fire/smoke emission --------------------------- */
  _emitFireSmoke(dt) {
    const g = this.grid; let fx = 0, fz = 0, fn = 0;
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const cell = g[idx(c, r)];
      if (cell.type !== T.BURNING) continue;
      fx += c; fz += r; fn++;
      const x = wx(c) + (this.rng() - 0.5) * CELL, z = wz(r) + (this.rng() - 0.5) * CELL, y = cell.elev + 1;
      if (this.rng() < 0.9 * cell.intensity + 0.2) {
        this.pFire.spawn(x, y, z, (this.rng() - 0.5) * 3, 10 + this.rng() * 12 + cell.intensity * 10, (this.rng() - 0.5) * 3,
          0.45 + this.rng() * 0.3, 1.0, 0.5 + this.rng() * 0.3, 0.12, 2);
      }
      if (this.rng() < 0.25) {
        this.pSmoke.spawn(x, y + 6, z, this.wind.x * this.wind.spd * 9 + (this.rng() - 0.5) * 3, 7 + this.rng() * 4, this.wind.y * this.wind.spd * 9 + (this.rng() - 0.5) * 3,
          1.8 + this.rng() * 1.2, 0.28, 0.28, 0.30, 1.5);
      }
      // embers: bright sparks lofted high and carried downwind from hot fire
      if (cell.intensity > 0.6 && this.rng() < 0.05) {
        this.pFire.spawn(x, y, z, this.wind.x * this.wind.spd * 9 + (this.rng() - 0.5) * 4, 22 + this.rng() * 18, this.wind.y * this.wind.spd * 9 + (this.rng() - 0.5) * 4,
          1.4 + this.rng() * 0.8, 1.0, 0.82, 0.4, 0.6);
      }
    }
    if (fn > 0) { this.fireLight.position.set(wx(fx / fn), 30, wz(fz / fn)); this.fireLight.intensity = clamp(0.6 + fn * 0.04, 0, 3.5) * (0.8 + this.rng() * 0.4); }
    else this.fireLight.intensity = 0;
  }

  /* --------------------------- mesh + camera --------------------------- */
  _updateMeshes(dt) {
    for (const a of this.agents) {
      const m = a._mesh; if (!m) continue;
      m.group.position.set(wx(a.gx), a.alt, wz(a.gy));
      // world facing from grid heading: world forward = (cos h, 0, sin h)
      m.group.rotation.y = Math.atan2(Math.cos(a.heading), Math.sin(a.heading));
      // bank into motion: pitch with forward speed, roll with lateral speed
      const fwd = a.vx * Math.cos(a.heading) + a.vy * Math.sin(a.heading);
      const lat = a.vx * Math.sin(a.heading) - a.vy * Math.cos(a.heading);
      const k = 0.85 / Math.max(0.001, DRONE_SPEED), s = clamp(dt * 5, 0, 1);
      m.tilt.rotation.x = lerp(m.tilt.rotation.x, clamp(fwd * k, -0.5, 0.5), s);
      m.tilt.rotation.z = lerp(m.tilt.rotation.z, clamp(-lat * k, -0.5, 0.5), s);
      for (const rt of m.rotors) rt.rotation.y = a.rotor;
      if (m.spray) m.spray.visible = a.spraying && a.tank > 0;
      if (m.boost) m.boost.visible = a.boost > 0;
    }
  }
  _updateCamera(dt) {
    // Independent follow-cam: orbits only on player input (set in _controlPlayer),
    // never auto-rotates to the drone's heading — so movement stays predictable.
    const a = this.player;
    const cx = wx(a.gx), cy = a.alt, cz = wz(a.gy);
    const ground = this._terrainH(a.gx, a.gy);
    const back = this.camDist, up = this.camDist * this.camPitch;
    const ex = cx - Math.sin(this.camYaw) * back, ez = cz - Math.cos(this.camYaw) * back;
    this.camPos.lerp(new THREE.Vector3(ex, cy + up, ez), clamp(dt * 5, 0, 1));
    this.camera.position.copy(this.camPos);
    if (this.shake > 0) { const j = this.shake * 3.5; this.camera.position.x += Math.sin(this.time * 91) * j; this.camera.position.y += Math.cos(this.time * 127) * j; }
    // keep the drone centred, biased a little toward the ground for awareness
    this.camera.lookAt(cx, (cy + ground) * 0.5 - 1, cz);
  }

  _flashMsg(t, dur) { if (t) { this.message = t; this.messageTimer = dur; } }

  // Simulated onboard perception: what the drone's RGB + thermal cameras read
  // from fire near/under it. These are SENSOR readings — the canonical
  // ml/fire_detection/infer.build_signal() / should_emit() turn them into
  // schema signals (see game/firefight_to_signals.py). We do NOT build signals
  // here, per the project rule that all signal paths compose against infer.
  _sensorReading(a) {
    const SR = 6;                                   // ~54 m sensor footprint
    let best = 0; const cc = Math.round(a.gx), cr = Math.round(a.gy);
    for (let dr = -SR; dr <= SR; dr++) for (let dc = -SR; dc <= SR; dc++) {
      const c = cc + dc, r = cr + dr; if (!inBounds(c, r)) continue;
      const cell = this.grid[idx(c, r)]; if (cell.type !== T.BURNING) continue;
      const d = Math.hypot(dc, dr); if (d > SR) continue;
      const v = cell.intensity * (1 - d / (SR + 1));
      if (v > best) best = v;
    }
    const rgb = +clamp(best * 1.15, 0, 1).toFixed(3);   // RGB-YOLO fire score
    const thermal = +(best * 48).toFixed(1);            // thermal delta vs local median (°C)
    return { rgb, thermal };
  }

  /* --------------------------- training log --------------------------- */
  _recordFrame(dt) {
    this.frameAccum += dt; if (this.frameAccum < 0.1) return; this.frameAccum = 0;
    for (const a of this.agents) {
      const s = this._sensorReading(a);
      this.frames.push({
        drone_id: a.id === 'YOU' ? 'wfw-player' : a.id, agent: a.player ? 'human' : 'ai',
        ts_iso: null, sim_time_s: +this.time.toFixed(2),
        lat: +gridToLat(a.gy).toFixed(7), lon: +gridToLon(a.gx).toFixed(7),
        alt_agl_m: +clamp(72 + (a.altOffset || 0) * 0.6, 0, AF.ceilingAGL).toFixed(1),
        alt_msl_m: +(ZONE.alt_msl_m + clamp(72 + (a.altOffset || 0) * 0.6, 0, AF.ceilingAGL)).toFixed(1),
        heading_deg: +((Math.atan2(Math.cos(a.heading), Math.sin(a.heading)) * 180 / Math.PI + 360) % 360).toFixed(2),
        speed_mps: +C2M(a.speed).toFixed(2),
        battery_pct: +a.battery.toFixed(1),
        suppressant_pct: +a.tank.toFixed(1),
        rgb_score: s.rgb, thermal_delta_c: s.thermal,
        gate_state: (s.rgb >= 0.65 && s.thermal >= 5.0) ? 'open' : 'closed',
        action: a.swapT > 0 ? 'battery_swap' : a.rth ? 'rtl' : a.spraying ? 'suppress' : 'transit',
        score: a.score, active_fires: this.activeFires,
      });
    }
  }
  buildBundle() {
    const stamp = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
    const t0 = Date.now() - this.time * 1000;
    const frames = this.frames.map((f) => ({ ...f, ts_iso: new Date(t0 + f.sim_time_s * 1000).toISOString() }));
    const manifest = {
      mission: 'gunnison-slate-river-1km2', zone_id: ZONE.id, scenario: 'firefight_game_3d',
      scenario_description: 'Human-vs-AI 3D suppression race recorded by Wildfire Watch: FIREFIGHT (3D). ' +
        'Per-tick agent state in the wildfire-watch flight-log schema for imitation/RL training.',
      generator: 'firefight-game-3d', difficulty: ['rookie', 'pro', 'inferno'][this.difficulty],
      seed: this.seed, tick_hz: 10.0, sim_seconds: +this.time.toFixed(1),
      wind_heading_deg: +((this.wind.ang * 180 / Math.PI + 360) % 360).toFixed(1), wind_speed: +this.wind.spd.toFixed(2),
      meters_per_cell: METERS_PER_CELL,
      airframe: { class: 'heavy_lift_firefighter', cruise_mps: AF.cruiseMps, max_mps: AF.maxMps, climb_mps: AF.climbMps, battery_min: AF.batteryMin, ceiling_agl_m: AF.ceilingAGL },
      perception: { rgb_thermal_logged: true, signal_builder: 'ml.fire_detection.infer.build_signal via game/firefight_to_signals.py' },
      agents: this.agents.map((a) => ({ id: a.id === 'YOU' ? 'wfw-player' : a.id, kind: a.player ? 'human' : 'ai', score: a.score })),
      structures_total: this.structuresTotal, structures_lost: this.structuresLost, result: this.result, frames: frames.length,
    };
    return { stamp, manifest, frames };
  }
  downloadLog() {
    const { stamp, manifest, frames } = this.buildBundle();
    const jsonl = frames.map((f) => JSON.stringify(f)).join('\n') + '\n';
    const dir = 'FIREFIGHT3D-' + stamp + '_human_vs_ai';
    this._download(dir + '__drones.jsonl', jsonl, 'application/x-ndjson');
    this._download(dir + '__manifest.json', JSON.stringify(manifest, null, 2), 'application/json');
    this._flashMsg('LOG EXPORTED', 1.4);
  }
  _download(name, text, mime) {
    const blob = new Blob([text], { type: mime }), url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = name;
    document.body.appendChild(a); a.click(); document.body.removeChild(a); setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  _endMatch(contained, overrun) {
    let saved = 0, burnt = 0, total = 0;
    for (const cell of this.grid) {
      if (cell.type === T.ROCK || cell.type === T.WATER) continue; total++;
      if (cell.type === T.BURNT || cell.type === T.STRUCT_BURNT) burnt++; else saved++;
    }
    const pct = total ? Math.round((saved / total) * 100) : 0;
    const playerScore = this.player.score;
    const aiList = this.agents.filter((a) => !a.player).map((a) => a.score);
    const aiBest = aiList.length ? Math.max(...aiList) : 0;
    const aiFleet = aiList.reduce((s, v) => s + v, 0);
    // a fair 1-v-best race: out-fly the lead AI drone (not the whole summed fleet)
    this.result = { contained, overrun, savedPct: pct, savedCells: saved, burntCells: burnt,
      playerScore, aiScore: aiBest, aiFleet,
      structuresSaved: this.structuresTotal - this.structuresLost, structuresTotal: this.structuresTotal,
      win: playerScore >= aiBest && !overrun };
    if (!this.best || playerScore > this.best.playerScore) { this.best = { playerScore, aiScore: aiBest, savedPct: pct }; this._saveBest(this.best); }
    this.audio.quiet();
    if (this.result.win) { this.audio.win(); this.input.rumble(0.6, 0.5, 500); }
    else { this.audio.lose(); this.input.rumble(0.9, 0.7, 700); }
    this.state = 'over';
  }

  /* ============================ HUD (2D overlay) ============================ */
  _renderHUD() {
    const ctx = this.hctx, W = this.W, H = this.H;
    ctx.clearRect(0, 0, W, H);
    if (this.state === 'menu') { this._renderMenu(); return; }
    // HUD bar
    const p = this.player;
    ctx.fillStyle = 'rgba(13,17,23,0.8)'; ctx.fillRect(0, 0, W, 64);
    const bx = 74, bw = 150, bh = 11;
    // retardant gauge
    ctx.fillStyle = '#7f8a99'; ctx.font = '10px monospace'; ctx.textAlign = 'right'; ctx.fillText('RTDNT', bx - 6, 19);
    ctx.fillStyle = '#222'; ctx.fillRect(bx, 10, bw, bh);
    ctx.fillStyle = p.tank > 25 ? '#27e0ff' : '#ff5d5d'; ctx.fillRect(bx, 10, bw * (p.tank / TANK_MAX), bh);
    ctx.strokeStyle = '#3a4757'; ctx.strokeRect(bx, 10, bw, bh);
    ctx.fillStyle = '#cdd6e0'; ctx.textAlign = 'left'; ctx.fillText(Math.round(p.tank / 100 * TANK_LITERS) + ' L', bx + bw + 6, 19);
    // battery gauge
    ctx.fillStyle = '#7f8a99'; ctx.textAlign = 'right'; ctx.fillText('BATT', bx - 6, 38);
    ctx.fillStyle = '#222'; ctx.fillRect(bx, 29, bw, bh);
    ctx.fillStyle = p.battery > 20 ? '#7CFC00' : '#ff5d5d'; ctx.fillRect(bx, 29, bw * (p.battery / 100), bh);
    ctx.strokeStyle = '#3a4757'; ctx.strokeRect(bx, 29, bw, bh);
    ctx.fillStyle = '#cdd6e0'; ctx.textAlign = 'left'; ctx.fillText(Math.round(p.battery) + '%' + (p.swapT > 0 ? ' SWAP' : p.rth ? ' RTL' : ''), bx + bw + 6, 38);
    // bombs (drawn droplets) + airspeed / altitude
    const obx = bx + bw + 52;
    ctx.fillStyle = '#7f8a99'; ctx.font = '10px monospace'; ctx.textAlign = 'left'; ctx.fillText('BOMBS', obx, 14);
    if (p.bombs <= 0) { ctx.fillStyle = '#555'; ctx.fillText('—', obx + 4, 24); }
    else { ctx.fillStyle = '#9fe2ff'; for (let i = 0; i < p.bombs; i++) { ctx.beginPath(); ctx.arc(obx + 6 + i * 12, 21, 4, 0, Math.PI * 2); ctx.fill(); } }
    ctx.fillStyle = '#7f8a99'; ctx.font = '10px monospace';
    ctx.fillText('SPD ' + C2M(p.speed).toFixed(1) + ' m/s   ALT ' + Math.round(clamp(72 + (p.altOffset || 0) * 0.6, 0, AF.ceilingAGL)) + ' m AGL', obx, 38);
    const aiScore = this.agents.filter((a) => !a.player).reduce((s, a) => Math.max(s, a.score), 0);
    ctx.textAlign = 'center'; ctx.font = 'bold 22px monospace';
    ctx.fillStyle = p.score >= aiScore ? '#7CFC00' : '#27e0ff'; ctx.fillText('YOU ' + p.score, W / 2 - 80, 30);
    ctx.fillStyle = '#7f8a99'; ctx.font = '14px monospace'; ctx.fillText('vs', W / 2, 28);
    ctx.fillStyle = '#ff8a3d'; ctx.font = 'bold 22px monospace'; ctx.fillText('AI ' + aiScore, W / 2 + 80, 30);
    ctx.fillStyle = '#7f8a99'; ctx.font = '11px monospace'; ctx.fillText('cells vs lead AI drone', W / 2, 48);
    ctx.textAlign = 'right'; const rx = W - 16;
    const tleft = Math.max(0, MATCH_SECONDS - this.time);
    ctx.fillStyle = tleft < 20 ? '#ff5d5d' : '#cdd6e0'; ctx.font = 'bold 22px monospace';
    ctx.fillText(`${String(Math.floor(tleft / 60)).padStart(2, '0')}:${String(Math.floor(tleft % 60)).padStart(2, '0')}`, rx, 28);
    ctx.font = '12px monospace'; ctx.fillStyle = '#ff8a3d'; ctx.fillText(this.activeFires + ' fires active', rx, 46);
    ctx.fillStyle = '#cdd6e0'; ctx.fillText('cabins ' + (this.structuresTotal - this.structuresLost) + '/' + this.structuresTotal, rx - 120, 46);
    // wind compass
    const wcx = W - 52, wcy = 104;
    ctx.save(); ctx.globalAlpha = 0.9; ctx.strokeStyle = '#9fb3c8'; ctx.fillStyle = '#9fb3c8'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(wcx, wcy, 22, 0, Math.PI * 2); ctx.stroke();
    ctx.translate(wcx, wcy); ctx.rotate(this.wind.ang);
    ctx.beginPath(); ctx.moveTo(-15, 0); ctx.lineTo(15, 0); ctx.lineTo(8, -5); ctx.moveTo(15, 0); ctx.lineTo(8, 5); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = '#9fb3c8'; ctx.font = '10px monospace'; ctx.textAlign = 'center'; ctx.fillText('WIND', wcx, wcy + 36);
    if (this.messageTimer > 0 && this.message) {
      ctx.textAlign = 'center'; ctx.font = 'bold 30px monospace'; ctx.globalAlpha = clamp(this.messageTimer, 0, 1);
      ctx.fillStyle = '#ffd23d'; ctx.fillText(this.message, W / 2, H * 0.2); ctx.globalAlpha = 1;
    }
    // controls hint (bottom)
    ctx.textAlign = 'center'; ctx.fillStyle = 'rgba(159,179,200,0.6)'; ctx.font = '11px monospace';
    ctx.fillText('WASD/stick fly · Space/RT spray · Enter/A bomb · R/F or LB/RB altitude · R-stick/drag orbit · [I] input test', W / 2, H - 14);
    this._renderReticle();
    this._renderPopups();
    this._renderMinimap();
    // low-battery edge warning
    if (this.state === 'playing' && p.battery < 20) {
      const a = 0.25 + 0.22 * Math.sin(this.time * 6);
      ctx.save(); ctx.strokeStyle = 'rgba(255,70,60,' + a.toFixed(2) + ')'; ctx.lineWidth = 8;
      ctx.strokeRect(6, 70, W - 12, H - 100); ctx.restore();
    }
    if (this.toastT > 0 && this.toast) {
      ctx.textAlign = 'center'; ctx.font = 'bold 13px monospace'; ctx.globalAlpha = clamp(this.toastT, 0, 1);
      ctx.fillStyle = '#7CFC00'; ctx.fillText(this.toast, W / 2, 72); ctx.globalAlpha = 1;
    }
    if (this.showInputDebug) this._renderInputDebug();
    if (this.state === 'over') this._renderOver();
  }

  _renderReticle() {
    if (this.state !== 'playing') return;
    const a = this.player; if (!a || a.swapT > 0) return;
    const nx = a.gx + Math.cos(a.heading) * 1.4, ny = a.gy + Math.sin(a.heading) * 1.4;
    const v = new THREE.Vector3(wx(nx), this._terrainH(nx, ny) + 1, wz(ny)).project(this.camera);
    if (v.z > 1) return;
    const sx = (v.x * 0.5 + 0.5) * this.W, sy = (-v.y * 0.5 + 0.5) * this.H;
    const cc = Math.round(nx), cr = Math.round(ny);
    const hot = inBounds(cc, cr) && this.grid[idx(cc, cr)].type === T.BURNING;
    const ctx = this.hctx;
    ctx.save();
    ctx.strokeStyle = a.spraying ? (hot ? '#ff5d3d' : '#9fe2ff') : (hot ? 'rgba(255,93,61,0.85)' : 'rgba(159,226,255,0.55)');
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(sx, sy, 13, 0, Math.PI * 2); ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(sx - 19, sy); ctx.lineTo(sx - 7, sy); ctx.moveTo(sx + 7, sy); ctx.lineTo(sx + 19, sy);
    ctx.moveTo(sx, sy - 19); ctx.lineTo(sx, sy - 7); ctx.moveTo(sx, sy + 7); ctx.lineTo(sx, sy + 19);
    ctx.stroke(); ctx.restore();
  }

  _renderPopups() {
    if (this.state !== 'playing' || !this.popups.length) return;
    const ctx = this.hctx, v = new THREE.Vector3();
    ctx.textAlign = 'center'; ctx.font = 'bold 18px monospace';
    for (const q of this.popups) {
      v.set(q.x, q.y, q.z).project(this.camera);
      if (v.z > 1) continue;
      const sx = (v.x * 0.5 + 0.5) * this.W, sy = (-v.y * 0.5 + 0.5) * this.H;
      ctx.globalAlpha = clamp(q.life / q.max, 0, 1); ctx.fillStyle = '#7CFC00';
      ctx.fillText(q.txt, sx, sy);
    }
    ctx.globalAlpha = 1;
  }

  _renderMinimap() {
    if (this.state !== 'playing') return;
    const ctx = this.hctx, mw = 156, mh = Math.round(mw * ROWS / COLS), mx = this.W - mw - 14, my = this.H - mh - 26;
    ctx.save(); ctx.globalAlpha = 0.92;
    ctx.fillStyle = 'rgba(8,12,16,0.7)'; ctx.fillRect(mx, my, mw, mh);
    ctx.strokeStyle = '#3a4757'; ctx.strokeRect(mx, my, mw, mh);
    const px = (c) => mx + (c / COLS) * mw, py = (r) => my + (r / ROWS) * mh;
    const g = this.grid, cwp = Math.ceil(mw / COLS) + 1, chp = Math.ceil(mh / ROWS) + 1;
    for (let r = 0; r < ROWS; r++) for (let c = 0; c < COLS; c++) {
      const t = g[idx(c, r)].type; let col = null;
      if (t === T.BURNING) col = '#ff7b2e';
      else if (t === T.BURNT || t === T.STRUCT_BURNT) col = '#241a16';
      else if (t === T.WATER && ((c + r) % 3 === 0)) col = '#1b4a66';
      if (col) { ctx.fillStyle = col; ctx.fillRect(px(c), py(r), cwp, chp); }
    }
    for (const s of this.structures) { const cell = g[idx(s.c, s.r)]; ctx.fillStyle = cell.type === T.STRUCT_BURNT ? '#5a2a22' : '#e6d2a8'; ctx.fillRect(px(s.c) - 1, py(s.r) - 1, 3, 3); }
    for (const a of this.agents) { ctx.strokeStyle = '#5a6473'; ctx.beginPath(); ctx.arc(px(a.padGx), py(a.padGy), 2.5, 0, Math.PI * 2); ctx.stroke(); }
    for (const a of this.agents) {
      const x = px(a.gx), y = py(a.gy); ctx.fillStyle = '#' + a.color.toString(16).padStart(6, '0');
      if (a.player) { ctx.save(); ctx.translate(x, y); ctx.rotate(Math.atan2(a.vy, a.vx) + Math.PI / 2); ctx.beginPath(); ctx.moveTo(0, -5); ctx.lineTo(3.5, 4); ctx.lineTo(-3.5, 4); ctx.closePath(); ctx.fill(); ctx.restore(); }
      else { ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI * 2); ctx.fill(); }
    }
    ctx.fillStyle = '#7f8a99'; ctx.font = '9px monospace'; ctx.textAlign = 'left'; ctx.fillText('SLATE RIVER DRAINAGE — radar', mx + 2, my - 4);
    ctx.restore();
  }

  _renderInputDebug() {
    const ctx = this.hctx, inp = this.input, W = this.W;
    const x = W - 250, y = 132, w = 234, h = 150;
    ctx.save(); ctx.globalAlpha = 0.94;
    ctx.fillStyle = 'rgba(8,12,16,0.85)'; ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = '#3a4757'; ctx.strokeRect(x, y, w, h);
    ctx.fillStyle = '#cdd6e0'; ctx.font = '10px monospace'; ctx.textAlign = 'left';
    ctx.fillText(inp.hasPad ? ('PAD: ' + inp.padName) : 'NO CONTROLLER — keyboard/mouse', x + 8, y + 16);
    ctx.fillStyle = '#7f8a99'; ctx.fillText('mapping: ' + (inp.padMapping || '—') + '    [I] hide', x + 8, y + 30);
    const stick = (cx, cy, ax, ay, label) => {
      ctx.strokeStyle = '#55606e'; ctx.beginPath(); ctx.arc(cx, cy, 20, 0, Math.PI * 2); ctx.stroke();
      ctx.fillStyle = '#27e0ff'; ctx.beginPath(); ctx.arc(cx + ax * 18, cy + ay * 18, 4, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#7f8a99'; ctx.textAlign = 'center'; ctx.font = '9px monospace'; ctx.fillText(label, cx, cy + 34);
    };
    const ls = inp.axes() || { lx: 0, ly: 0 }, rs = inp.axesR() || { rx: 0, ry: 0 };
    stick(x + 52, y + 66, ls.lx, ls.ly, 'L · move'); stick(x + 150, y + 66, rs.rx, rs.ry, 'R · camera');
    const names = [['A', 0], ['B', 1], ['X', 2], ['Y', 3], ['LB', 4], ['RB', 5], ['LT', 6], ['RT', 7]];
    for (let i = 0; i < names.length; i++) {
      const bx = x + 8 + i * 28, by = y + 122, on = inp.gpDown(names[i][1]);
      ctx.fillStyle = on ? '#7CFC00' : '#2a3340'; ctx.fillRect(bx, by, 24, 18);
      ctx.fillStyle = on ? '#06121a' : '#7f8a99'; ctx.textAlign = 'center'; ctx.font = '9px monospace'; ctx.fillText(names[i][0], bx + 12, by + 13);
    }
    ctx.restore();
  }

  _renderMenu() {
    const ctx = this.hctx, W = this.W, H = this.H;
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#10161f'); g.addColorStop(1, '#1a0f0a');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = 'center'; const u = Math.min(W / 1000, 1.25);
    ctx.fillStyle = '#ff6b2d'; ctx.font = `bold ${Math.round(60 * u)}px sans-serif`; ctx.fillText('WILDFIRE WATCH', W / 2, H * 0.2);
    ctx.fillStyle = '#27e0ff'; ctx.font = `bold ${Math.round(44 * u)}px sans-serif`; ctx.fillText('F I R E F I G H T  ·  3D', W / 2, H * 0.28);
    ctx.fillStyle = '#9fb3c8'; ctx.font = `${Math.round(14 * u)}px monospace`;
    ctx.fillText('Slate River drainage — Gunnison Valley + Crested Butte, CO  •  fuel load: HIGH (beetle-kill spruce/fir)', W / 2, H * 0.35);
    ctx.fillText('Pilot your suppression drone in 3D. Race the autonomous fleet. Defend the cabins. Beat the wind.', W / 2, H * 0.39);
    const items = [['1', 'ROOKIE', '1 AI drone · slow burn'], ['2', 'PRO', '2 AI drones · real fire spread'], ['3', 'INFERNO', '3 AI drones · high wind, dry fuel']];
    let y = H * 0.5;
    for (let i = 0; i < items.length; i++) {
      const [k, name, desc] = items[i], sel = i === this.menuSel;
      ctx.fillStyle = sel ? '#26405a' : '#1c2530'; ctx.fillRect(W / 2 - 260, y - 26, 520, 44);
      if (sel) { ctx.strokeStyle = '#27e0ff'; ctx.lineWidth = 2; ctx.strokeRect(W / 2 - 260, y - 26, 520, 44); }
      ctx.fillStyle = '#ffd23d'; ctx.textAlign = 'left'; ctx.font = 'bold 22px monospace'; ctx.fillText((sel ? '▸ ' : '  ') + '[' + k + ']', W / 2 - 248, y + 4);
      ctx.fillStyle = '#e6edf3'; ctx.font = 'bold 20px monospace'; ctx.fillText(name, W / 2 - 165, y + 4);
      ctx.fillStyle = '#7f8a99'; ctx.font = '14px monospace'; ctx.textAlign = 'right'; ctx.fillText(desc, W / 2 + 240, y + 4);
      y += 56;
    }
    // controller status
    ctx.textAlign = 'center';
    if (this.input.hasPad) { ctx.fillStyle = '#7CFC00'; ctx.font = `${Math.round(14 * u)}px monospace`; ctx.fillText('● CONTROLLER READY — ' + this.input.padName + '   (stick/D-pad to choose · A / Start to launch)', W / 2, H * 0.7); }
    else { ctx.fillStyle = '#7f8a99'; ctx.font = `${Math.round(13 * u)}px monospace`; ctx.fillText('Plug in an Xbox / Switch Pro / PlayStation / USB controller and press any button — or use keyboard', W / 2, H * 0.7); }
    ctx.fillStyle = '#9fb3c8'; ctx.font = `${Math.round(13 * u)}px monospace`;
    ctx.fillText('FLY  WASD / left stick      SPRAY  Space / RT      BOMB  Enter / A      ALT  R/F · LB/RB      ORBIT  R-stick · drag', W / 2, H * 0.84);
    ctx.fillText('CAMERA  X-axis: ' + (this.invertCamX ? 'INVERTED' : 'NORMAL') + ' [C / Y]    sensitivity: ' + this.camSens.toFixed(1) + 'x [V]    ·    [I] controller test', W / 2, H * 0.88);
    if (this.toastT > 0 && this.toast) { ctx.fillStyle = '#7CFC00'; ctx.font = `bold ${Math.round(15 * u)}px monospace`; ctx.fillText(this.toast, W / 2, H * 0.45); }
    if (this.best) {
      ctx.fillStyle = this.best.playerScore > this.best.aiScore ? '#7CFC00' : '#ff8a3d'; ctx.font = '13px monospace';
      const studied = this.best.playerScore > this.best.aiScore ? '  — the AI studied your win and trained harder' : '';
      ctx.fillText(`Best: you ${this.best.playerScore} – ai ${this.best.aiScore}  (${this.best.savedPct}% saved)` + studied, W / 2, H * 0.93);
    }
    if (this.showInputDebug) this._renderInputDebug();
  }

  _renderOver() {
    const ctx = this.hctx, W = this.W, H = this.H, R = this.result;
    ctx.fillStyle = 'rgba(6,9,14,0.84)'; ctx.fillRect(0, 0, W, H); ctx.textAlign = 'center';
    if (R.overrun) { ctx.fillStyle = '#ff5d5d'; ctx.font = 'bold 54px sans-serif'; ctx.fillText('BURNED OVER', W / 2, H * 0.26); }
    else if (R.win) { ctx.fillStyle = '#7CFC00'; ctx.font = 'bold 52px sans-serif'; ctx.fillText(R.contained ? 'FIRE CONTAINED — YOU WIN' : 'TIME — YOU WIN', W / 2, H * 0.26); }
    else { ctx.fillStyle = '#ff8a3d'; ctx.font = 'bold 52px sans-serif'; ctx.fillText('THE FLEET OUTFLEW YOU', W / 2, H * 0.26); }
    ctx.font = '22px monospace';
    const rows = [['You extinguished', R.playerScore + ' cells'], ['AI fleet extinguished', R.aiScore + ' cells'],
      ['Acreage saved', R.savedPct + '%  (' + R.savedCells + ' cells)'], ['Cabins saved', R.structuresSaved + ' / ' + R.structuresTotal]];
    let y = H * 0.38;
    for (const [a, b] of rows) { ctx.fillStyle = '#7f8a99'; ctx.textAlign = 'right'; ctx.fillText(a, W / 2 - 20, y); ctx.fillStyle = '#e6edf3'; ctx.textAlign = 'left'; ctx.fillText(b, W / 2 + 20, y); y += 38; }
    ctx.textAlign = 'center'; ctx.fillStyle = '#27e0ff'; ctx.font = 'bold 20px monospace';
    ctx.fillText('[ L ]  download training log  (drones.jsonl + manifest.json)', W / 2, y + 30);
    ctx.fillStyle = '#9fb3c8'; ctx.font = '16px monospace'; ctx.fillText('Enter / A — back to menu', W / 2, y + 64);
    if (this.aiAdapted) { ctx.fillStyle = '#ffd23d'; ctx.font = '13px monospace'; ctx.fillText('This fleet was trained on your previous winning run.', W / 2, y + 92); }
  }
}

/* ===================================================================== */
/*  Drone model + state                                                  */
/* ===================================================================== */
function buildDroneMesh(color, isPlayer) {
  const group = new THREE.Group();
  const tilt = new THREE.Group(); group.add(tilt);   // banking/pitch lives here
  const body = new THREE.Mesh(new THREE.BoxGeometry(3.2, 1.2, 3.6),
    new THREE.MeshStandardMaterial({ color, metalness: 0.5, roughness: 0.4,
      emissive: color, emissiveIntensity: isPlayer ? 0.55 : 0.2 }));
  tilt.add(body);
  if (isPlayer) {
    // a soft glow ring so you can always find your own drone over the burn scar
    const halo = new THREE.Mesh(new THREE.RingGeometry(3.0, 3.8, 24),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
    halo.rotation.x = -Math.PI / 2; halo.position.y = -1.6; tilt.add(halo);
  }
  const nose = new THREE.Mesh(new THREE.ConeGeometry(0.7, 1.6, 12),
    new THREE.MeshStandardMaterial({ color: 0x222831, metalness: 0.6, roughness: 0.3 }));
  nose.rotation.x = Math.PI / 2; nose.position.set(0, 0, 2.0); tilt.add(nose);
  // retardant pod underneath
  const pod = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, 2.4, 10),
    new THREE.MeshStandardMaterial({ color: 0xbfe9ff, metalness: 0.3, roughness: 0.5 }));
  pod.rotation.x = Math.PI / 2; pod.position.set(0, -1.0, 0); tilt.add(pod);
  const arm = new THREE.MeshStandardMaterial({ color: 0x2a2f38, metalness: 0.4, roughness: 0.6 });
  const rotors = [];
  const offs = [[2.4, 2.4], [2.4, -2.4], [-2.4, 2.4], [-2.4, -2.4]];
  for (const [ox, oz] of offs) {
    const a = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.3, Math.hypot(ox, oz) * 0.9), arm);
    a.position.set(ox / 2, 0, oz / 2); a.lookAt(0, 0, 0); tilt.add(a);
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 0.5, 8), arm);
    hub.position.set(ox, 0.3, oz); tilt.add(hub);
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.5, 0.08, 16),
      new THREE.MeshStandardMaterial({ color: 0xcfd8e3, transparent: true, opacity: 0.35, metalness: 0.2, roughness: 0.5 }));
    disc.position.set(ox, 0.6, oz); tilt.add(disc); rotors.push(disc);
  }
  const boost = new THREE.Mesh(new THREE.SphereGeometry(3.4, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0xffd23d, transparent: true, opacity: 0.18 }));
  boost.visible = false; group.add(boost);
  return { group, tilt, rotors, boost };
}

class Drone {
  constructor(id, color, gx, gy, player) {
    this.id = id; this.color = color; this.gx = gx; this.gy = gy; this.player = !!player;
    this.vx = 0; this.vy = 0; this.dvx = 0; this.dvy = 0;
    this.heading = -Math.PI / 2; this.speed = 0; this.rotor = 0;
    this.tank = TANK_MAX; this.battery = 100; this.swapT = 0; this.lowWarned = false;
    this.bombs = BOMB_COUNT_START; this.score = 0;
    this.spraying = false; this.sprayFx = 0; this.boost = 0; this.alt = null; this.altOffset = 0;
    this.padGx = gx; this.padGy = gy;
    this.skill = 0.8; this.target = null; this.thinkT = 0; this.refilling = false; this.rth = false;
  }
  maxSpeed() {
    let s = DRONE_SPEED;
    if (this.battery < 18) s *= 0.5;     // limp home on low battery
    if (this.boost > 0) s *= 1.3;
    return s;
  }
}

/* ===================================================================== */
/*  INPUT (keyboard + mouse + gamepad)                                   */
/* ===================================================================== */
/* ===================================================================== */
/*  AUDIO — fully synthesized (Web Audio), no asset files, offline-safe   */
/* ===================================================================== */
class AudioEngine {
  constructor() { this.ctx = null; this.ready = false; }
  init() {
    if (this.ctx) { if (this.ctx.state === 'suspended') this.ctx.resume(); return; }
    const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
    const ctx = this.ctx = new AC();
    this.master = ctx.createGain(); this.master.gain.value = 0.5; this.master.connect(ctx.destination);
    const n = Math.floor(ctx.sampleRate * 2); const buf = ctx.createBuffer(1, n, ctx.sampleRate);
    const d = buf.getChannelData(0); for (let i = 0; i < n; i++) d[i] = Math.random() * 2 - 1; this.noiseBuf = buf;
    const loop = (filterType, freq, vol) => {
      const src = ctx.createBufferSource(); src.buffer = buf; src.loop = true;
      const f = ctx.createBiquadFilter(); f.type = filterType; f.frequency.value = freq;
      const g = ctx.createGain(); g.gain.value = 0;
      src.connect(f); f.connect(g); g.connect(this.master); src.start(); return g;
    };
    this._sprayGain = loop('highpass', 2200, 0);     // suppressant hiss
    this._fireGain = loop('lowpass', 420, 0);         // fire ambient
    this._rotorOsc = ctx.createOscillator(); this._rotorOsc.type = 'sawtooth'; this._rotorOsc.frequency.value = 72;
    const rf = ctx.createBiquadFilter(); rf.type = 'lowpass'; rf.frequency.value = 280;
    this._rotorGain = ctx.createGain(); this._rotorGain.gain.value = 0;
    this._rotorOsc.connect(rf); rf.connect(this._rotorGain); this._rotorGain.connect(this.master); this._rotorOsc.start();
    this.ready = true;
  }
  _set(g, v, t) { if (this.ready) g.gain.setTargetAtTime(v, this.ctx.currentTime, t); }
  setSpray(on) { if (this.ready) this._set(this._sprayGain, on ? 0.16 : 0, 0.05); }
  setFire(level) { if (this.ready) this._set(this._fireGain, clamp(level, 0, 1) * 0.22, 0.3); }
  setRotor(level) { if (this.ready) { this._set(this._rotorGain, clamp(level, 0, 1) * 0.045, 0.1); this._rotorOsc.frequency.setTargetAtTime(70 + level * 55, this.ctx.currentTime, 0.1); } }
  _blip(freq, dur, type, vol) {
    if (!this.ready) return; const ctx = this.ctx, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type || 'sine'; o.frequency.setValueAtTime(freq, ctx.currentTime);
    g.gain.setValueAtTime(0.0001, ctx.currentTime); g.gain.exponentialRampToValueAtTime(vol || 0.2, ctx.currentTime + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
    o.connect(g); g.connect(this.master); o.start(); o.stop(ctx.currentTime + dur + 0.02);
  }
  bomb() {
    if (!this.ready) return; const ctx = this.ctx, t = ctx.currentTime;
    const o = ctx.createOscillator(); o.type = 'sawtooth'; o.frequency.setValueAtTime(420, t); o.frequency.exponentialRampToValueAtTime(60, t + 0.4);
    const g = ctx.createGain(); g.gain.setValueAtTime(0.3, t); g.gain.exponentialRampToValueAtTime(0.001, t + 0.5);
    o.connect(g); g.connect(this.master); o.start(); o.stop(t + 0.55);
    const ns = ctx.createBufferSource(); ns.buffer = this.noiseBuf; const nf = ctx.createBiquadFilter(); nf.type = 'bandpass'; nf.frequency.value = 1100;
    const ng = ctx.createGain(); ng.gain.setValueAtTime(0.4, t + 0.34); ng.gain.exponentialRampToValueAtTime(0.001, t + 0.85);
    ns.connect(nf); nf.connect(ng); ng.connect(this.master); ns.start(t + 0.33); ns.stop(t + 0.9);
  }
  pickup() { this._blip(660, 0.1, 'square', 0.16); setTimeout(() => this._blip(990, 0.12, 'square', 0.16), 90); }
  lowBatt() { this._blip(300, 0.16, 'square', 0.2); }
  win() { [523, 659, 784, 1047].forEach((f, i) => setTimeout(() => this._blip(f, 0.2, 'triangle', 0.22), i * 120)); }
  lose() { [392, 330, 262, 196].forEach((f, i) => setTimeout(() => this._blip(f, 0.24, 'sawtooth', 0.2), i * 150)); }
  quiet() { this.setSpray(false); this.setFire(0); this.setRotor(0); }
}

// Works with any controller the browser exposes through the Gamepad API in
// the W3C "standard" mapping — Xbox (USB/Bluetooth), Switch Pro / Joy-Con grip,
// PlayStation DualShock/DualSense, and most generic USB pads. Button *positions*
// are used (not letters), so the bottom face button is "confirm/bomb" whether
// it's labelled A (Xbox) or B (Nintendo).
class Input3D {
  constructor(canvas) {
    this.keys = {}; this.justPressed = {}; this.prevGp = {}; this.gpJust = {};
    this.mouseLeft = false; this.mouseRight = false; this.mouseRightPressed = false;
    this.mouseDX = 0; this._dragging = false; this._lastX = 0; this.wheel = 0;
    this.pad = null; this.padIndex = null; this.padName = ''; this.padMapping = ''; this.hasPad = false;
    this.anyInput = false;            // first real user gesture (unlocks audio)
    this.onConnect = null;
    window.addEventListener('keydown', (e) => {
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
      if (!this.keys[e.code]) this.justPressed[e.code] = true;
      this.keys[e.code] = true; this.anyInput = true;
    });
    window.addEventListener('keyup', (e) => { this.keys[e.code] = false; });
    window.addEventListener('blur', () => { this.keys = {}; });
    canvas.addEventListener('mousedown', (e) => {
      this.anyInput = true;
      if (e.button === 0) { this.mouseLeft = true; this._dragging = true; this._lastX = e.clientX; }
      if (e.button === 2) { this.mouseRight = true; this.mouseRightPressed = true; }
    });
    window.addEventListener('mouseup', (e) => { if (e.button === 0) { this.mouseLeft = false; this._dragging = false; } if (e.button === 2) this.mouseRight = false; });
    window.addEventListener('mousemove', (e) => { if (this._dragging) { this.mouseDX += (e.clientX - this._lastX) * 0.01; this._lastX = e.clientX; } });
    canvas.addEventListener('wheel', (e) => { this.wheel += e.deltaY; e.preventDefault(); }, { passive: false });
    canvas.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('gamepadconnected', (e) => this._onPad(e.gamepad));
    window.addEventListener('gamepaddisconnected', (e) => {
      if (this.padIndex === e.gamepad.index) { this.hasPad = false; this.pad = null; this.padIndex = null; }
    });
  }
  _onPad(gp) {
    this.padIndex = gp.index; this.padName = (gp.id || 'controller').replace(/\(.*\)/, '').trim().slice(0, 38) || 'controller';
    this.padMapping = gp.mapping || ''; this.hasPad = true;
    if (this.onConnect) this.onConnect(this.padName);
  }
  poll() {
    this.gpJust = {};
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    let pad = (this.padIndex != null && pads[this.padIndex]) ? pads[this.padIndex] : null;
    if (!pad) { for (const p of pads) if (p) { this._onPad(p); pad = p; break; } }
    this.pad = pad; this.hasPad = !!pad;
    if (!pad) return;
    for (let i = 0; i < pad.buttons.length; i++) {
      const pr = pad.buttons[i].pressed || pad.buttons[i].value > 0.5;
      if (pr && !this.prevGp[i]) { this.gpJust[i] = true; this.anyInput = true; }
      this.prevGp[i] = pr;
    }
    for (let i = 0; i < pad.axes.length; i++) if (Math.abs(pad.axes[i]) > 0.5) this.anyInput = true;
  }
  endFrame() { this.justPressed = {}; this.mouseDX = 0; this.wheel = 0; this.mouseRightPressed = false; }
  down(c) { return !!this.keys[c]; }
  pressed(c) { return !!this.justPressed[c]; }
  gpDown(i) { const b = this.pad && this.pad.buttons[i]; return !!b && (b.pressed || b.value > 0.5); }
  gpVal(i) { const b = this.pad && this.pad.buttons[i]; return b ? (b.value || (b.pressed ? 1 : 0)) : 0; }
  gpPressed(i) { return !!this.gpJust[i]; }
  // left stick (radial deadzone) folded with the D-pad
  axes() {
    if (!this.pad) return null;
    let lx = this.pad.axes[0] || 0, ly = this.pad.axes[1] || 0;
    if (Math.hypot(lx, ly) < 0.2) { lx = 0; ly = 0; }
    if (this.gpDown(14)) lx -= 1; if (this.gpDown(15)) lx += 1;
    if (this.gpDown(12)) ly -= 1; if (this.gpDown(13)) ly += 1;
    return { lx: clamp(lx, -1, 1), ly: clamp(ly, -1, 1) };
  }
  axesR() {
    if (!this.pad) return null;
    let rx = this.pad.axes[2] || 0, ry = this.pad.axes[3] || 0;
    if (Math.hypot(rx, ry) < 0.2) { rx = 0; ry = 0; }
    return { rx, ry };
  }
  rumble(strong, weak, ms) {
    const p = this.pad;
    if (p && p.vibrationActuator && p.vibrationActuator.playEffect) {
      try { p.vibrationActuator.playEffect('dual-rumble', { duration: ms, strongMagnitude: strong, weakMagnitude: weak }); } catch (e) {}
    }
  }
}

/* ----------------------------- boot ----------------------------- */
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    window.__game = new Game3D(document.getElementById('gl'), document.getElementById('hud'));
  });
}
