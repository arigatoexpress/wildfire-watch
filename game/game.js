/* =====================================================================
 * Wildfire Watch: FIREFIGHT
 * ---------------------------------------------------------------------
 * An arcade firefighting simulator layered on the real wildfire-watch
 * AOR (Gunnison Valley + Crested Butte, Colorado). You pilot a
 * suppression drone over the most critical fire zone in the corridor —
 * slate-river-drainage (fuel load: HIGH, beetle-kill spruce/fir) —
 * and race autonomous AI drones to put out a spreading wildfire before
 * it reaches the cabins in the wildland-urban interface.
 *
 * Every frame of play is recorded in the project's real flight-log
 * schema (drone_id / lat / lon / heading_deg / speed_mps / battery_pct
 * ...) so a finished match exports a drones.jsonl + manifest.json bundle
 * that drops straight into wildfire-watch-flights/ for AI training.
 *
 * Pure vanilla JS + Canvas. No build step, no network, works on file://.
 * Keyboard + Gamepad (controller) supported.
 * ===================================================================== */
'use strict';

/* ----------------------------- Real AOR geo ----------------------------- */
// slate-river-drainage polygon bounds (from
// missions/zones/gunnison_crested_butte_corridor.geojson). The play field
// maps 1:1 onto this ~1 km^2 patch so logged lat/lon are real coordinates.
const ZONE = {
  id: 'slate-river-drainage',
  fuel_load_class: 'high',
  primary_risk: 'beetle-kill spruce/fir',
  lonMin: -107.0060, lonMax: -106.9940,
  latMin: 38.9035, latMax: 38.9165,
  alt_msl_m: 2743,
};

/* ----------------------------- Tunables ----------------------------- */
const COLS = 84, ROWS = 54;          // fire-sim grid
const HUD_H = 64;                    // top HUD bar height (px)

// cell types
const T = { ROCK: 0, FUEL: 1, BURNING: 2, BURNT: 3, WATER: 4, STRUCT: 5, STRUCT_BURNT: 6 };

const TANK_MAX = 100;                // suppressant tank
const TANK_SPRAY_RATE = 26;          // tank units / sec while spraying
const TANK_REFILL_RATE = 55;         // tank units / sec over water
const SPRAY_POWER = 1.9;             // intensity removed / sec at nozzle
const SPRAY_RADIUS = 1.7;            // cells
const DRONE_SPEED = 16.5;            // cells / sec (player)
const BOMB_RADIUS = 4.2;             // cells
const BOMB_COUNT_START = 2;
const MATCH_SECONDS = 150;

// fire model
const IGNITE_BASE = 0.85;            // base spread coefficient
const BURN_RATE = 0.10;              // fuel consumed / sec at full intensity
const INTENSITY_GROW = 0.45;         // how fast a burning cell ramps to 1
const WIND_BIAS = 0.9;               // how strongly wind skews spread
const LIGHTNING_EVERY = 11.0;        // avg seconds between new random ignitions
const WET_FUEL_SECONDS = 18;         // how long a pre-wet firebreak resists

/* ----------------------------- Seeded RNG ----------------------------- */
// Mulberry32 — deterministic, matches the project's "deterministic seeding"
// ethos so a logged seed reproduces the match.
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ----------------------------- Utilities ----------------------------- */
const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
const lerp = (a, b, t) => a + (b - a) * t;
const idx = (c, r) => r * COLS + c;
const inBounds = (c, r) => c >= 0 && c < COLS && r >= 0 && r < ROWS;
function gridToLat(gy) { return lerp(ZONE.latMax, ZONE.latMin, gy / ROWS); }
function gridToLon(gx) { return lerp(ZONE.lonMin, ZONE.lonMax, gx / COLS); }

/* ===================================================================== */
/*  GAME                                                                 */
/* ===================================================================== */
class Game {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.state = 'menu';            // menu | playing | over
    this.difficulty = 1;            // 0 rookie, 1 pro, 2 inferno
    this.input = new Input(canvas);
    this.particles = [];
    this.pickups = [];
    this.frames = [];               // training-log frames
    this.best = this._loadBest();
    this._resize();
    window.addEventListener('resize', () => this._resize());
    this.last = 0;
    requestAnimationFrame((t) => this._loop(t));
  }

  _loadBest() {
    try { return JSON.parse(localStorage.getItem('wfw_firefight_best') || 'null'); }
    catch (e) { return null; }
  }
  _saveBest(b) {
    try { localStorage.setItem('wfw_firefight_best', JSON.stringify(b)); } catch (e) {}
  }

  _resize() {
    const dpr = window.devicePixelRatio || 1;
    this.cssW = window.innerWidth; this.cssH = window.innerHeight;
    this.canvas.width = Math.floor(this.cssW * dpr);
    this.canvas.height = Math.floor(this.cssH * dpr);
    this.canvas.style.width = this.cssW + 'px';
    this.canvas.style.height = this.cssH + 'px';
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // play field = canvas minus HUD bar, with grid aspect preserved
    const availW = this.cssW, availH = this.cssH - HUD_H;
    const aspect = COLS / ROWS;
    let fw = availW, fh = availW / aspect;
    if (fh > availH) { fh = availH; fw = availH * aspect; }
    this.field = { x: (availW - fw) / 2, y: HUD_H + (availH - fh) / 2, w: fw, h: fh };
    this.cw = fw / COLS; this.ch = fh / ROWS;
  }

  sx(gx) { return this.field.x + gx * this.cw; }
  sy(gy) { return this.field.y + gy * this.ch; }

  /* --------------------------- match setup --------------------------- */
  start(difficulty) {
    this.difficulty = difficulty;
    this.seed = (Date.now() & 0x7fffffff) ^ Math.floor(performance.now());
    this.rng = mulberry32(this.seed);
    this.time = 0;
    this.lightningTimer = LIGHTNING_EVERY;
    this.frames = [];
    this.frameAccum = 0;
    this.particles = [];
    this.pickups = [];
    this.message = null;
    this.messageTimer = 0;

    this._buildTerrain();

    // wind: blows toward (windX,windY), magnitude up to 1
    const wa = this.rng() * Math.PI * 2;
    this.wind = { x: Math.cos(wa), y: Math.sin(wa), spd: 0.55 + this.rng() * 0.35, ang: wa };

    // agents: player + AI drones (count & skill scale with difficulty,
    // and with how well the player did last time — "train AI against me")
    const nAI = [1, 2, 3][this.difficulty];
    let aiSkill = [0.55, 0.78, 0.95][this.difficulty];
    if (this.best && this.best.playerScore > this.best.aiScore) {
      // the AI studied your winning run and came back sharper
      aiSkill = clamp(aiSkill + 0.08, 0, 1.0);
      this.aiAdapted = true;
    } else { this.aiAdapted = false; }

    this.agents = [];
    this.player = new Drone('YOU', '#27e0ff', COLS * 0.18, ROWS * 0.82, true);
    this.agents.push(this.player);
    const aiColors = ['#ff8a3d', '#c77dff', '#ffd23d'];
    for (let i = 0; i < nAI; i++) {
      const ai = new Drone('wfw-ai0' + (i + 1), aiColors[i % 3],
        COLS * (0.7 + i * 0.08), ROWS * 0.85, false);
      ai.skill = aiSkill;
      this.agents.push(ai);
    }

    // ignite the fire: a few seeds in the densest forest
    this.activeFires = 0;
    let seeds = [2, 3, 4][this.difficulty];
    let placed = 0, tries = 0;
    while (placed < seeds && tries < 4000) {
      tries++;
      const c = 2 + Math.floor(this.rng() * (COLS - 4));
      const r = 2 + Math.floor(this.rng() * (ROWS - 4));
      const cell = this.grid[idx(c, r)];
      if (cell.type === T.FUEL && cell.fuelLoad > 0.55) {
        this._ignite(c, r, 0.5); placed++;
      }
    }
    this.structuresTotal = this.structures.length;
    this.structuresLost = 0;
    this.state = 'playing';
    this.input.consumeBuffered();
  }

  _buildTerrain() {
    const g = new Array(COLS * ROWS);
    const rng = this.rng;
    // base fractal-ish fuel field via summed sine noise (deterministic)
    const noise = (x, y) => {
      let v = 0;
      v += Math.sin(x * 0.20 + 1.3) * Math.cos(y * 0.18 + 0.7);
      v += 0.5 * Math.sin(x * 0.41 - 0.6) * Math.cos(y * 0.37 + 2.1);
      v += 0.25 * Math.sin(x * 0.83 + 2.4) * Math.cos(y * 0.79 - 1.1);
      return v / 1.75; // ~[-1,1]
    };
    this.structures = [];
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const n = noise(c, r) + (rng() - 0.5) * 0.25;
        let cell;
        if (n < -0.42) cell = { type: T.ROCK, fuelLoad: 0 };            // alpine rock / meadow
        else cell = { type: T.FUEL, fuelLoad: clamp(0.5 + n * 0.7, 0.18, 1) };
        cell.fuel = 1.0; cell.intensity = 0; cell.wetTimer = 0; cell.by = null;
        g[idx(c, r)] = cell;
      }
    }
    // Slate River — a meandering firebreak + refill source (water column)
    let rx = COLS * 0.30;
    for (let r = 0; r < ROWS; r++) {
      rx += (rng() - 0.5) * 2.4;
      rx = clamp(rx, 4, COLS - 5);
      const w = 1 + (r % 7 === 0 ? 1 : 0);
      for (let d = -1; d <= w; d++) {
        const c = Math.round(rx) + d;
        if (inBounds(c, r)) { const cell = g[idx(c, r)]; cell.type = T.WATER; cell.fuelLoad = 0; }
      }
    }
    // Cabins in the wildland-urban interface (protect these — the README's
    // "1,000 structures" stakes). Cluster near the SE corner downslope.
    const clusters = [[COLS * 0.66, ROWS * 0.30], [COLS * 0.78, ROWS * 0.62], [COLS * 0.45, ROWS * 0.5]];
    for (const [cx, cy] of clusters) {
      const n = 3 + Math.floor(rng() * 3);
      for (let i = 0; i < n; i++) {
        const c = Math.round(cx + (rng() - 0.5) * 7);
        const r = Math.round(cy + (rng() - 0.5) * 7);
        if (inBounds(c, r) && g[idx(c, r)].type === T.FUEL) {
          const cell = g[idx(c, r)];
          cell.type = T.STRUCT; cell.fuel = 1.0; cell.fuelLoad = 0.9;
          this.structures.push({ c, r });
        }
      }
    }
    this.grid = g;
  }

  _ignite(c, r, intensity) {
    if (!inBounds(c, r)) return;
    const cell = this.grid[idx(c, r)];
    if (cell.type === T.FUEL || cell.type === T.STRUCT) {
      if (cell.wetTimer > 0) return;
      cell.type = cell.type === T.STRUCT ? T.STRUCT : T.BURNING;
      if (cell.type === T.STRUCT) { cell._struct = true; }
      cell.type = T.BURNING;
      cell.intensity = Math.max(cell.intensity, intensity);
      this.activeFires++;
    }
  }

  /* ------------------------------ loop ------------------------------ */
  _loop(t) {
    const dt = this.last ? Math.min((t - this.last) / 1000, 0.05) : 0;
    this.last = t;
    this.input.poll();
    if (this.state === 'menu') this._menuUpdate();
    else if (this.state === 'playing') this._update(dt);
    else if (this.state === 'over') this._overUpdate();
    this._render();
    this.input.endFrame();
    requestAnimationFrame((tt) => this._loop(tt));
  }

  _menuUpdate() {
    if (this.input.pressed('Digit1') || this.input.gpPressed(14)) { this.start(0); }
    else if (this.input.pressed('Digit2') || this.input.gpPressed(0)) { this.start(1); }
    else if (this.input.pressed('Digit3') || this.input.gpPressed(15)) { this.start(2); }
    else if (this.input.pressed('Enter') || this.input.gpPressed(9)) { this.start(this.difficulty); }
  }

  _overUpdate() {
    if (this.input.pressed('Enter') || this.input.pressed('Space') || this.input.gpPressed(0)) {
      this.state = 'menu';
    }
    if (this.input.pressed('KeyD') || this.input.gpPressed(2)) { this.downloadLog(); }
  }

  _update(dt) {
    this.time += dt;
    // wind slowly rotates
    this.wind.ang += (this.rng() - 0.5) * 0.4 * dt;
    this.wind.x = Math.cos(this.wind.ang); this.wind.y = Math.sin(this.wind.ang);

    this._stepFire(dt);
    this._lightning(dt);
    for (const a of this.agents) {
      if (a.player) this._controlPlayer(a, dt);
      else this._controlAI(a, dt);
      this._integrate(a, dt);
      this._suppress(a, dt);
      this._tank(a, dt);
    }
    this._pickups(dt);
    this._stepParticles(dt);
    this._recordFrame(dt);
    if (this.messageTimer > 0) this.messageTimer -= dt;

    // end conditions
    const timeUp = this.time >= MATCH_SECONDS;
    const contained = this.activeFires <= 0 && this.time > 1.5;
    const overrun = this.structuresLost >= this.structuresTotal && this.structuresTotal > 0;
    if (timeUp || contained || overrun) this._endMatch(contained, overrun);
  }

  _lightning(dt) {
    this.lightningTimer -= dt;
    if (this.lightningTimer <= 0) {
      this.lightningTimer = LIGHTNING_EVERY * (0.6 + this.rng());
      // strike a random forested cell
      for (let k = 0; k < 12; k++) {
        const c = Math.floor(this.rng() * COLS), r = Math.floor(this.rng() * ROWS);
        const cell = this.grid[idx(c, r)];
        if (cell.type === T.FUEL && cell.fuelLoad > 0.4) {
          this._ignite(c, r, 0.4);
          this._flash(c, r);
          break;
        }
      }
    }
  }

  _stepFire(dt) {
    const g = this.grid;
    const ign = [];           // deferred ignitions {c,r,i}
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const cell = g[idx(c, r)];
        if (cell.wetTimer > 0) cell.wetTimer -= dt;
        if (cell.type !== T.BURNING) continue;
        // ramp intensity, consume fuel
        cell.intensity = clamp(cell.intensity + INTENSITY_GROW * dt, 0, 1);
        cell.fuel -= BURN_RATE * dt * (0.4 + cell.intensity);
        if (cell.fuel <= 0) {
          cell.type = cell._struct ? T.STRUCT_BURNT : T.BURNT;
          cell.intensity = 0; this.activeFires--;
          if (cell._struct) this.structuresLost++;
          this._smoke(c, r, 1.2);
          continue;
        }
        // emit smoke + try to spread
        if (this.rng() < 0.25) this._smoke(c, r, cell.intensity);
        const neigh = [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, 1], [1, -1], [-1, -1]];
        for (const [dc, dr] of neigh) {
          const nc = c + dc, nr = r + dr;
          if (!inBounds(nc, nr)) continue;
          const nb = g[idx(nc, nr)];
          if ((nb.type !== T.FUEL && nb.type !== T.STRUCT) || nb.wetTimer > 0) continue;
          // wind alignment: spread faster downwind
          const len = Math.hypot(dc, dr) || 1;
          const align = (dc / len) * this.wind.x + (dr / len) * this.wind.y;
          const windF = 1 + WIND_BIAS * this.wind.spd * align;
          const diag = len > 1.1 ? 0.7 : 1.0;
          let chance = IGNITE_BASE * cell.intensity * nb.fuelLoad * windF * diag * dt;
          if (nb.type === T.STRUCT) chance *= 0.7;
          if (this.rng() < chance) ign.push([nc, nr]);
        }
      }
    }
    for (const [c, r] of ign) {
      const cell = g[idx(c, r)];
      if (cell.type === T.STRUCT) cell._struct = true;
      this._ignite(c, r, 0.18);
    }
  }

  /* --------------------------- player control --------------------------- */
  _controlPlayer(a, dt) {
    const inp = this.input;
    let mx = 0, my = 0;
    if (inp.down('ArrowLeft') || inp.down('KeyA')) mx -= 1;
    if (inp.down('ArrowRight') || inp.down('KeyD')) mx += 1;
    if (inp.down('ArrowUp') || inp.down('KeyW')) my -= 1;
    if (inp.down('ArrowDown') || inp.down('KeyS')) my += 1;
    const gp = inp.axes();
    if (gp) { mx += gp.lx; my += gp.ly; }
    const mag = Math.hypot(mx, my);
    if (mag > 1) { mx /= mag; my /= mag; }
    a.vx = mx * DRONE_SPEED; a.vy = my * DRONE_SPEED;
    if (mag > 0.08) a.heading = Math.atan2(my, mx);

    a.spraying = inp.down('Space') || inp.down('ShiftLeft') || inp.gpDown(7) || inp.gpDown(5);
    if ((inp.pressed('KeyE') || inp.pressed('Enter') || inp.gpPressed(0)) && a.bombs > 0) {
      this._dropBomb(a);
    }
  }

  /* ----------------------------- AI control ----------------------------- */
  _controlAI(a, dt) {
    // re-target periodically or when target gone
    a.thinkT -= dt;
    let tgt = a.target && this.grid[idx(a.target.c, a.target.r)];
    if (!tgt || tgt.type !== T.BURNING || a.thinkT <= 0) {
      a.thinkT = lerp(0.55, 0.18, a.skill);
      a.target = this._aiPickTarget(a);
    }
    // refill if low and a target exists far away
    if (a.tank < 18 && !a.refilling) a.refilling = true;
    if (a.refilling) {
      const w = this._nearestWater(a);
      if (w) {
        this._steerTo(a, w.c + 0.5, w.r + 0.5, dt);
        if (a.tank >= TANK_MAX - 2) a.refilling = false;
        a.spraying = false;
        return;
      } else a.refilling = false;
    }
    if (a.target) {
      const tc = a.target.c + 0.5, tr = a.target.r + 0.5;
      const d = Math.hypot((a.gx - tc), (a.gy - tr));
      this._steerTo(a, tc, tr, dt);
      a.spraying = d < SPRAY_RADIUS + 0.6 && a.tank > 0;
      // skilled AI uses water bombs on dense fire clusters
      if (a.bombs > 0 && d < 1.2 && this._fireDensity(a.target.c, a.target.r) >= 5 && a.skill > 0.7) {
        this._dropBomb(a);
      }
    } else {
      // patrol toward zone center if nothing burning yet
      this._steerTo(a, COLS / 2, ROWS / 2, dt);
      a.spraying = false;
    }
  }

  _steerTo(a, tc, tr, dt) {
    let dx = tc - a.gx, dy = tr - a.gy;
    const d = Math.hypot(dx, dy) || 1;
    const spd = DRONE_SPEED * lerp(0.78, 1.02, a.skill);
    a.vx = (dx / d) * spd; a.vy = (dy / d) * spd;
    a.heading = Math.atan2(dy, dx);
  }

  _aiPickTarget(a) {
    // score burning cells by intensity + structure-proximity threat,
    // discounted by distance to this drone
    let best = null, bestScore = -1;
    const g = this.grid;
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const cell = g[idx(c, r)];
        if (cell.type !== T.BURNING) continue;
        const dist = Math.hypot(c - a.gx, r - a.gy);
        let threat = cell.intensity + this._fireDensity(c, r) * 0.12;
        if (this._nearStructure(c, r)) threat += 1.4;     // prioritize WUI defense
        const score = threat - dist * lerp(0.06, 0.018, a.skill);
        if (score > bestScore) { bestScore = score; best = { c, r }; }
      }
    }
    return best;
  }

  _fireDensity(c, r) {
    let n = 0;
    for (let dr = -1; dr <= 1; dr++) for (let dc = -1; dc <= 1; dc++) {
      if (inBounds(c + dc, r + dr) && this.grid[idx(c + dc, r + dr)].type === T.BURNING) n++;
    }
    return n;
  }
  _nearStructure(c, r) {
    for (const s of this.structures) {
      const cell = this.grid[idx(s.c, s.r)];
      if (cell.type === T.STRUCT_BURNT) continue;
      if (Math.abs(s.c - c) <= 2 && Math.abs(s.r - r) <= 2) return true;
    }
    return false;
  }
  _nearestWater(a) {
    let best = null, bd = 1e9;
    const g = this.grid;
    for (let r = 0; r < ROWS; r += 1) for (let c = 0; c < COLS; c += 1) {
      if (g[idx(c, r)].type !== T.WATER) continue;
      const d = (c - a.gx) ** 2 + (r - a.gy) ** 2;
      if (d < bd) { bd = d; best = { c, r }; }
    }
    return best;
  }

  /* --------------------------- physics / actions --------------------------- */
  _integrate(a, dt) {
    a.gx = clamp(a.gx + a.vx * dt, 0.4, COLS - 0.4);
    a.gy = clamp(a.gy + a.vy * dt, 0.4, ROWS - 0.4);
    a.speed = Math.hypot(a.vx, a.vy);
    a.rotor += dt * (8 + a.speed * 1.5);
  }

  _tank(a, dt) {
    const cell = this.grid[idx(Math.floor(a.gx), Math.floor(a.gy))];
    if (cell && cell.type === T.WATER) {
      a.tank = clamp(a.tank + TANK_REFILL_RATE * dt, 0, TANK_MAX);
      if (this.rng() < 0.3) this._splash(a.gx, a.gy, '#7fd4ff');
    }
  }

  _suppress(a, dt) {
    if (!a.spraying || a.tank <= 0) { a.sprayFx = 0; return; }
    a.tank = clamp(a.tank - TANK_SPRAY_RATE * dt, 0, TANK_MAX);
    a.sprayFx = 1;
    // nozzle is just ahead of the drone in its heading
    const nx = a.gx + Math.cos(a.heading) * 1.1;
    const ny = a.gy + Math.sin(a.heading) * 1.1;
    const cc = Math.round(nx), cr = Math.round(ny);
    const R = Math.ceil(SPRAY_RADIUS);
    for (let dr = -R; dr <= R; dr++) for (let dc = -R; dc <= R; dc++) {
      const c = cc + dc, r = cr + dr;
      if (!inBounds(c, r)) continue;
      if (Math.hypot(dc, dr) > SPRAY_RADIUS) continue;
      this._applyWater(c, r, a, SPRAY_POWER * dt);
    }
    // spray particles
    for (let i = 0; i < 2; i++) {
      const spread = (this.rng() - 0.5) * 0.5;
      this.particles.push({
        k: 'spray', x: a.gx, y: a.gy,
        vx: Math.cos(a.heading + spread) * 9, vy: Math.sin(a.heading + spread) * 9,
        life: 0.32, max: 0.32, col: a.color,
      });
    }
  }

  _applyWater(c, r, a, amount) {
    const cell = this.grid[idx(c, r)];
    if (cell.type === T.BURNING) {
      cell.intensity -= amount;
      if (this.rng() < 0.25) this._steam(c, r);
      if (cell.intensity <= 0) {
        // extinguished -> wet, credited to whoever put it out
        cell.type = cell._struct ? T.STRUCT : T.FUEL;
        cell.intensity = 0; cell.wetTimer = WET_FUEL_SECONDS;
        cell.by = a.id; a.score++; this.activeFires--;
        this._steam(c, r);
      }
    } else if ((cell.type === T.FUEL || cell.type === T.STRUCT) && cell.wetTimer < WET_FUEL_SECONDS) {
      // pre-wet a firebreak
      cell.wetTimer = WET_FUEL_SECONDS;
      if (cell.by == null) cell.by = a.id;
    }
  }

  _dropBomb(a) {
    a.bombs--;
    const cc = Math.round(a.gx), cr = Math.round(a.gy);
    const R = Math.ceil(BOMB_RADIUS);
    for (let dr = -R; dr <= R; dr++) for (let dc = -R; dc <= R; dc++) {
      const c = cc + dc, r = cr + dr;
      if (!inBounds(c, r)) continue;
      if (Math.hypot(dc, dr) > BOMB_RADIUS) continue;
      const cell = this.grid[idx(c, r)];
      if (cell.type === T.BURNING) {
        cell.type = cell._struct ? T.STRUCT : T.FUEL;
        cell.intensity = 0; cell.wetTimer = WET_FUEL_SECONDS; cell.by = a.id;
        a.score++; this.activeFires--;
      } else if (cell.type === T.FUEL || cell.type === T.STRUCT) {
        cell.wetTimer = WET_FUEL_SECONDS;
      }
    }
    // big splash ring
    for (let i = 0; i < 60; i++) {
      const ang = (i / 60) * Math.PI * 2;
      this.particles.push({
        k: 'splash', x: a.gx, y: a.gy,
        vx: Math.cos(ang) * (6 + this.rng() * 6), vy: Math.sin(ang) * (6 + this.rng() * 6),
        life: 0.6, max: 0.6, col: '#9fe2ff',
      });
    }
    this._flashMsg(a.player ? 'WATER BOMB!' : '', 0.8);
  }

  /* --------------------------- pickups --------------------------- */
  _pickups(dt) {
    this.pickupTimer = (this.pickupTimer || 0) - dt;
    if (this.pickupTimer <= 0 && this.pickups.length < 3) {
      this.pickupTimer = 6 + this.rng() * 5;
      const kinds = ['bomb', 'tank', 'speed'];
      const kind = kinds[Math.floor(this.rng() * kinds.length)];
      let c, r, tries = 0;
      do { c = 2 + Math.floor(this.rng() * (COLS - 4)); r = 2 + Math.floor(this.rng() * (ROWS - 4)); tries++; }
      while (tries < 40 && this.grid[idx(c, r)].type === T.WATER);
      this.pickups.push({ kind, gx: c + 0.5, gy: r + 0.5, t: 0 });
    }
    for (let i = this.pickups.length - 1; i >= 0; i--) {
      const p = this.pickups[i]; p.t += dt;
      for (const a of this.agents) {
        if (Math.hypot(a.gx - p.gx, a.gy - p.gy) < 1.0) {
          if (p.kind === 'bomb') a.bombs += 2;
          else if (p.kind === 'tank') a.tank = TANK_MAX;
          else if (p.kind === 'speed') a.boost = 4;
          if (a.player) this._flashMsg('+ ' + p.kind.toUpperCase(), 1.0);
          this.pickups.splice(i, 1);
          break;
        }
      }
    }
    for (const a of this.agents) { if (a.boost > 0) a.boost -= dt; }
  }

  /* --------------------------- particles --------------------------- */
  _smoke(c, r, s) {
    this.particles.push({
      k: 'smoke', x: c + 0.5, y: r + 0.5,
      vx: this.wind.x * this.wind.spd * 3 + (this.rng() - 0.5),
      vy: this.wind.y * this.wind.spd * 3 - 1.2,
      life: 1.6 + this.rng(), max: 2.6, r: 0.6 + s, col: '#555',
    });
  }
  _steam(c, r) {
    this.particles.push({ k: 'steam', x: c + 0.5, y: r + 0.5, vx: (this.rng() - 0.5), vy: -1.5, life: 0.7, max: 0.7, col: '#eee' });
  }
  _splash(x, y, col) {
    this.particles.push({ k: 'splash', x, y, vx: (this.rng() - 0.5) * 4, vy: -(1 + this.rng() * 2), life: 0.5, max: 0.5, col });
  }
  _flash(c, r) {
    this.particles.push({ k: 'flash', x: c + 0.5, y: r + 0.5, vx: 0, vy: 0, life: 0.25, max: 0.25, col: '#fff' });
  }
  _flashMsg(t, dur) { if (t) { this.message = t; this.messageTimer = dur; } }
  _stepParticles(dt) {
    for (let i = this.particles.length - 1; i >= 0; i--) {
      const p = this.particles[i];
      p.x += p.vx * dt; p.y += p.vy * dt; p.life -= dt;
      if (p.k === 'spray' || p.k === 'splash') p.vy += 6 * dt;
      if (p.life <= 0) this.particles.splice(i, 1);
    }
  }

  /* --------------------------- training log --------------------------- */
  _recordFrame(dt) {
    this.frameAccum += dt;
    if (this.frameAccum < 0.1) return;       // log at ~10 Hz (matches tick_hz)
    this.frameAccum = 0;
    for (const a of this.agents) {
      this.frames.push({
        drone_id: a.id === 'YOU' ? 'wfw-player' : a.id,
        agent: a.player ? 'human' : 'ai',
        ts_iso: null,                          // stamped at export
        sim_time_s: +this.time.toFixed(2),
        lat: +gridToLat(a.gy).toFixed(7),
        lon: +gridToLon(a.gx).toFixed(7),
        alt_agl_m: 80.0,
        alt_msl_m: ZONE.alt_msl_m + 80,
        heading_deg: +((a.heading * 180 / Math.PI + 360) % 360).toFixed(2),
        speed_mps: +(a.speed * 0.9).toFixed(2),     // cells/s -> ~m/s (1 km / 84)
        battery_pct: +a.tank.toFixed(1),            // suppressant tank as battery analog
        action: a.spraying ? 'suppress' : 'transit',
        score: a.score,
        active_fires: this.activeFires,
      });
    }
  }

  buildBundle() {
    const stamp = new Date().toISOString().replace(/[:.]/g, '').slice(0, 15);
    const t0 = Date.now() - this.time * 1000;
    const frames = this.frames.map((f) => ({
      ...f, ts_iso: new Date(t0 + f.sim_time_s * 1000).toISOString(),
    }));
    const manifest = {
      mission: 'gunnison-slate-river-1km2',
      zone_id: ZONE.id,
      scenario: 'firefight_game',
      scenario_description: 'Human-vs-AI suppression race recorded by Wildfire Watch: FIREFIGHT. ' +
        'Each agent flies the slate-river-drainage zone and the per-tick state is logged in the ' +
        'wildfire-watch flight-log schema for imitation/RL training.',
      generator: 'firefight-game',
      difficulty: ['rookie', 'pro', 'inferno'][this.difficulty],
      seed: this.seed,
      tick_hz: 10.0,
      sim_seconds: +this.time.toFixed(1),
      wind_heading_deg: +((this.wind.ang * 180 / Math.PI + 360) % 360).toFixed(1),
      wind_speed: +this.wind.spd.toFixed(2),
      agents: this.agents.map((a) => ({ id: a.id === 'YOU' ? 'wfw-player' : a.id, kind: a.player ? 'human' : 'ai', score: a.score })),
      structures_total: this.structuresTotal,
      structures_lost: this.structuresLost,
      result: this.result,
      frames: frames.length,
    };
    return { stamp, manifest, frames };
  }

  downloadLog() {
    const { stamp, manifest, frames } = this.buildBundle();
    const jsonl = frames.map((f) => JSON.stringify(f)).join('\n') + '\n';
    const dir = 'FIREFIGHT-' + stamp + '_human_vs_ai';
    this._download(dir + '__drones.jsonl', jsonl, 'application/x-ndjson');
    this._download(dir + '__manifest.json', JSON.stringify(manifest, null, 2), 'application/json');
    this._flashMsg('LOG EXPORTED', 1.4);
  }
  _download(name, text, mime) {
    const blob = new Blob([text], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; document.body.appendChild(a); a.click();
    document.body.removeChild(a); setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  /* ----------------------------- end ----------------------------- */
  _endMatch(contained, overrun) {
    // acres saved = green cells (fuel/struct, including wet) still standing
    let saved = 0, burnt = 0, total = 0;
    for (const cell of this.grid) {
      if (cell.type === T.ROCK || cell.type === T.WATER) continue;
      total++;
      if (cell.type === T.BURNT || cell.type === T.STRUCT_BURNT) burnt++;
      else saved++;
    }
    const pct = total ? Math.round((saved / total) * 100) : 0;
    const playerScore = this.player.score;
    const aiScore = this.agents.filter((a) => !a.player).reduce((s, a) => s + a.score, 0);
    this.result = {
      contained, overrun, savedPct: pct, savedCells: saved, burntCells: burnt,
      playerScore, aiScore,
      structuresSaved: this.structuresTotal - this.structuresLost,
      structuresTotal: this.structuresTotal,
      win: playerScore >= aiScore && !overrun,
    };
    const prevBest = this.best;
    if (!prevBest || playerScore > prevBest.playerScore) {
      this.best = { playerScore, aiScore, savedPct: pct };
      this._saveBest(this.best);
    }
    this.state = 'over';
  }

  /* ============================ RENDER ============================ */
  _render() {
    const ctx = this.ctx;
    ctx.fillStyle = '#0a0d12';
    ctx.fillRect(0, 0, this.cssW, this.cssH);
    if (this.state === 'menu') { this._renderMenu(); return; }
    this._renderField();
    this._renderHUD();
    if (this.state === 'over') this._renderOver();
  }

  _renderField() {
    const ctx = this.ctx, cw = this.cw, ch = this.ch, g = this.grid;
    // cells
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const cell = g[idx(c, r)];
        let col;
        switch (cell.type) {
          case T.ROCK: col = '#2b2f38'; break;
          case T.WATER: col = '#15445e'; break;
          case T.BURNT: col = '#1a1714'; break;
          case T.STRUCT_BURNT: col = '#241a16'; break;
          case T.STRUCT: col = cell.wetTimer > 0 ? '#3a6e7a' : '#6b5b4a'; break;
          case T.FUEL: {
            const f = cell.fuelLoad;
            const gr = Math.floor(lerp(70, 150, f));
            col = cell.wetTimer > 0 ? '#2f5a52' : `rgb(${Math.floor(28 + f * 20)},${gr},${Math.floor(40 + f * 25)})`;
            break;
          }
          case T.BURNING: {
            const i = cell.intensity;
            col = `rgb(255,${Math.floor(lerp(180, 40, i))},${Math.floor(lerp(60, 10, i))})`;
            break;
          }
          default: col = '#000';
        }
        ctx.fillStyle = col;
        ctx.fillRect(this.sx(c), this.sy(r), cw + 0.6, ch + 0.6);
        if (cell.type === T.STRUCT && cell.wetTimer <= 0) {
          ctx.fillStyle = '#caa'; ctx.fillRect(this.sx(c) + cw * 0.3, this.sy(r) + ch * 0.3, cw * 0.4, ch * 0.4);
        }
      }
    }
    // particles (under drones)
    this._renderParticles();
    // pickups
    for (const p of this.pickups) {
      const x = this.sx(p.gx), y = this.sy(p.gy);
      const pulse = 1 + Math.sin(p.t * 6) * 0.15;
      ctx.save(); ctx.translate(x, y);
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = p.kind === 'bomb' ? '#9fe2ff' : p.kind === 'tank' ? '#7CFC00' : '#ffd23d';
      const rad = Math.min(cw, ch) * 0.9 * pulse;
      ctx.beginPath(); ctx.arc(0, 0, rad, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#06121a'; ctx.font = `bold ${rad * 1.1}px monospace`;
      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(p.kind === 'bomb' ? 'B' : p.kind === 'tank' ? 'F' : 'S', 0, 1);
      ctx.restore();
    }
    // drones
    for (const a of this.agents) this._renderDrone(a);
    // wind compass
    this._renderWind();
  }

  _renderParticles() {
    const ctx = this.ctx;
    for (const p of this.particles) {
      const x = this.sx(p.x), y = this.sy(p.y);
      const a = clamp(p.life / p.max, 0, 1);
      if (p.k === 'smoke') {
        ctx.globalAlpha = a * 0.4;
        ctx.fillStyle = p.col;
        const rad = lerp(p.r, p.r * 3, 1 - a) * this.cw;
        ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2); ctx.fill();
      } else if (p.k === 'steam') {
        ctx.globalAlpha = a * 0.6; ctx.fillStyle = '#dfeaf0';
        ctx.beginPath(); ctx.arc(x, y, this.cw * (1 - a) * 1.5 + 1, 0, Math.PI * 2); ctx.fill();
      } else if (p.k === 'flash') {
        ctx.globalAlpha = a; ctx.fillStyle = '#fffbe0';
        ctx.fillRect(x - this.cw, y - this.ch * 4, this.cw * 2, this.ch * 8);
      } else { // spray / splash
        ctx.globalAlpha = a * 0.9; ctx.fillStyle = p.col || '#bfe9ff';
        ctx.beginPath(); ctx.arc(x, y, this.cw * 0.5, 0, Math.PI * 2); ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }

  _renderDrone(a) {
    const ctx = this.ctx, x = this.sx(a.gx), y = this.sy(a.gy);
    const s = Math.min(this.cw, this.ch) * 1.7;
    // spray cone
    if (a.spraying && a.tank > 0) {
      ctx.save(); ctx.translate(x, y); ctx.rotate(a.heading);
      const grad = ctx.createLinearGradient(0, 0, s * 3, 0);
      grad.addColorStop(0, 'rgba(180,235,255,0.55)');
      grad.addColorStop(1, 'rgba(180,235,255,0)');
      ctx.fillStyle = grad;
      ctx.beginPath(); ctx.moveTo(s * 0.4, 0);
      ctx.lineTo(s * 3, -s * 1.0); ctx.lineTo(s * 3, s * 1.0); ctx.closePath(); ctx.fill();
      ctx.restore();
    }
    ctx.save(); ctx.translate(x, y); ctx.rotate(a.heading);
    // body
    ctx.fillStyle = a.color;
    ctx.beginPath(); ctx.moveTo(s * 0.7, 0); ctx.lineTo(-s * 0.45, -s * 0.45);
    ctx.lineTo(-s * 0.25, 0); ctx.lineTo(-s * 0.45, s * 0.45); ctx.closePath(); ctx.fill();
    // rotors
    ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.lineWidth = Math.max(1, s * 0.06);
    for (const [ox, oy] of [[s * 0.4, s * 0.5], [s * 0.4, -s * 0.5], [-s * 0.4, s * 0.5], [-s * 0.4, -s * 0.5]]) {
      ctx.beginPath(); ctx.arc(ox, oy, s * 0.32 * (0.8 + 0.2 * Math.sin(a.rotor)), 0, Math.PI * 2); ctx.stroke();
    }
    ctx.restore();
    // boost glow
    if (a.boost > 0) {
      ctx.globalAlpha = 0.4; ctx.fillStyle = '#ffd23d';
      ctx.beginPath(); ctx.arc(x, y, s * 1.2, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
    }
    // label
    ctx.fillStyle = a.color; ctx.font = `${Math.max(9, s * 0.5)}px monospace`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    ctx.fillText(a.id, x, y - s * 0.8);
  }

  _renderWind() {
    const ctx = this.ctx;
    const cx = this.field.x + this.field.w - 46, cy = this.field.y + 46;
    ctx.save(); ctx.globalAlpha = 0.85;
    ctx.strokeStyle = '#9fb3c8'; ctx.fillStyle = '#9fb3c8'; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, 26, 0, Math.PI * 2); ctx.stroke();
    ctx.translate(cx, cy); ctx.rotate(this.wind.ang);
    ctx.beginPath(); ctx.moveTo(-18, 0); ctx.lineTo(18, 0);
    ctx.lineTo(10, -6); ctx.moveTo(18, 0); ctx.lineTo(10, 6); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = '#9fb3c8'; ctx.font = '11px monospace'; ctx.textAlign = 'center';
    ctx.fillText('WIND', cx, cy + 40);
  }

  _renderHUD() {
    const ctx = this.ctx, W = this.cssW;
    ctx.fillStyle = '#0d1117'; ctx.fillRect(0, 0, W, HUD_H);
    ctx.fillStyle = '#1b222c'; ctx.fillRect(0, HUD_H - 2, W, 2);
    const p = this.player;
    // tank bar
    const bx = 16, by = 14, bw = 200, bh = 16;
    ctx.fillStyle = '#222'; ctx.fillRect(bx, by, bw, bh);
    ctx.fillStyle = p.tank > 25 ? '#27e0ff' : '#ff5d5d';
    ctx.fillRect(bx, by, bw * (p.tank / TANK_MAX), bh);
    ctx.strokeStyle = '#3a4757'; ctx.strokeRect(bx, by, bw, bh);
    ctx.fillStyle = '#cdd6e0'; ctx.font = '11px monospace'; ctx.textAlign = 'left';
    ctx.fillText('SUPPRESSANT', bx, by + bh + 13);
    // bombs (drawn droplets)
    if (p.bombs <= 0) { ctx.fillStyle = '#555'; ctx.font = '16px monospace'; ctx.fillText('—', bx + bw + 28, by + 14); }
    else { ctx.fillStyle = '#9fe2ff'; for (let i = 0; i < p.bombs; i++) { ctx.beginPath(); ctx.arc(bx + bw + 30 + i * 16, by + 8, 5, 0, Math.PI * 2); ctx.fill(); } }
    ctx.fillStyle = '#7f8a99'; ctx.font = '11px monospace'; ctx.fillText('WATER BOMBS', bx + bw + 24, by + bh + 13);

    // scores
    const aiScore = this.agents.filter((a) => !a.player).reduce((s, a) => s + a.score, 0);
    ctx.textAlign = 'center'; ctx.font = 'bold 22px monospace';
    ctx.fillStyle = '#27e0ff'; ctx.fillText('YOU ' + p.score, W / 2 - 80, 30);
    ctx.fillStyle = '#7f8a99'; ctx.font = '14px monospace'; ctx.fillText('vs', W / 2, 28);
    ctx.fillStyle = '#ff8a3d'; ctx.font = 'bold 22px monospace'; ctx.fillText('AI ' + aiScore, W / 2 + 80, 30);
    ctx.fillStyle = '#7f8a99'; ctx.font = '11px monospace';
    ctx.fillText('cells extinguished', W / 2, 48);

    // right: timer, fires, structures
    ctx.textAlign = 'right'; const rx = W - 16;
    const tleft = Math.max(0, MATCH_SECONDS - this.time);
    ctx.fillStyle = tleft < 20 ? '#ff5d5d' : '#cdd6e0'; ctx.font = 'bold 22px monospace';
    ctx.fillText(`${String(Math.floor(tleft / 60)).padStart(2, '0')}:${String(Math.floor(tleft % 60)).padStart(2, '0')}`, rx, 28);
    ctx.font = '12px monospace'; ctx.fillStyle = '#ff8a3d';
    ctx.fillText(this.activeFires + ' fires active', rx, 46);
    ctx.fillStyle = '#cdd6e0';
    ctx.fillText('cabins ' + (this.structuresTotal - this.structuresLost) + '/' + this.structuresTotal, rx - 110, 46);

    // center flash message
    if (this.messageTimer > 0 && this.message) {
      ctx.textAlign = 'center'; ctx.font = 'bold 28px monospace';
      ctx.globalAlpha = clamp(this.messageTimer, 0, 1);
      ctx.fillStyle = '#ffd23d';
      ctx.fillText(this.message, this.cssW / 2, this.field.y + this.field.h * 0.18);
      ctx.globalAlpha = 1;
    }
  }

  _renderMenu() {
    const ctx = this.ctx, W = this.cssW, H = this.cssH;
    // backdrop gradient
    const g = ctx.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0, '#10161f'); g.addColorStop(1, '#1a0f0a');
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = 'center';
    const u = Math.min(W / 1000, 1.25);     // responsive scale unit
    ctx.fillStyle = '#ff6b2d'; ctx.font = `bold ${Math.round(64 * u)}px sans-serif`;
    ctx.fillText('WILDFIRE WATCH', W / 2, H * 0.22);
    ctx.fillStyle = '#27e0ff'; ctx.font = `bold ${Math.round(48 * u)}px sans-serif`;
    ctx.fillText('F I R E F I G H T', W / 2, H * 0.30);
    ctx.fillStyle = '#9fb3c8'; ctx.font = `${Math.round(15 * u)}px monospace`;
    ctx.fillText('Slate River drainage — Gunnison Valley + Crested Butte, CO  •  fuel load: HIGH (beetle-kill spruce/fir)', W / 2, H * 0.37);
    ctx.fillText('Race the autonomous fleet to suppress the fire. Defend the cabins. Don’t let the wind win.', W / 2, H * 0.41);

    const items = [
      ['1', 'ROOKIE', '1 AI drone · slow burn'],
      ['2', 'PRO', '2 AI drones · real fire spread'],
      ['3', 'INFERNO', '3 AI drones · high wind, dry fuel'],
    ];
    let y = H * 0.52;
    for (const [k, name, desc] of items) {
      ctx.fillStyle = '#1c2530'; ctx.fillRect(W / 2 - 260, y - 26, 520, 44);
      ctx.fillStyle = '#ffd23d'; ctx.textAlign = 'left'; ctx.font = 'bold 22px monospace';
      ctx.fillText('[' + k + ']', W / 2 - 240, y + 4);
      ctx.fillStyle = '#e6edf3'; ctx.font = 'bold 20px monospace'; ctx.fillText(name, W / 2 - 175, y + 4);
      ctx.fillStyle = '#7f8a99'; ctx.font = '14px monospace'; ctx.textAlign = 'right';
      ctx.fillText(desc, W / 2 + 240, y + 4);
      y += 56;
    }
    ctx.textAlign = 'center'; ctx.fillStyle = '#9fb3c8'; ctx.font = `${Math.round(13 * u)}px monospace`;
    ctx.fillText('MOVE  WASD / ←↑↓→ / left stick      SPRAY  Space / Shift / RT      WATER BOMB  E / Enter / A', W / 2, H * 0.86);
    ctx.fillText('Controller auto-detected · every match is logged to the real flight-log schema for AI training', W / 2, H * 0.90);

    if (this.best) {
      ctx.fillStyle = this.best.playerScore > this.best.aiScore ? '#7CFC00' : '#ff8a3d';
      ctx.font = '13px monospace';
      const line = `Best: you ${this.best.playerScore} – ai ${this.best.aiScore}  (${this.best.savedPct}% saved)`;
      const studied = this.best.playerScore > this.best.aiScore ? '  — the AI studied your win and trained harder' : '';
      ctx.fillText(line + studied, W / 2, H * 0.95);
    }
  }

  _renderOver() {
    const ctx = this.ctx, W = this.cssW, H = this.cssH, R = this.result;
    ctx.fillStyle = 'rgba(6,9,14,0.86)'; ctx.fillRect(0, 0, W, H);
    ctx.textAlign = 'center';
    if (R.overrun) { ctx.fillStyle = '#ff5d5d'; ctx.font = 'bold 56px sans-serif'; ctx.fillText('BURNED OVER', W / 2, H * 0.26); }
    else if (R.win) { ctx.fillStyle = '#7CFC00'; ctx.font = 'bold 56px sans-serif'; ctx.fillText(R.contained ? 'FIRE CONTAINED — YOU WIN' : 'TIME — YOU WIN', W / 2, H * 0.26); }
    else { ctx.fillStyle = '#ff8a3d'; ctx.font = 'bold 56px sans-serif'; ctx.fillText('THE FLEET OUTFLEW YOU', W / 2, H * 0.26); }

    ctx.font = '22px monospace';
    const rows = [
      ['You extinguished', R.playerScore + ' cells'],
      ['AI fleet extinguished', R.aiScore + ' cells'],
      ['Acreage saved', R.savedPct + '%  (' + R.savedCells + ' cells)'],
      ['Cabins saved', R.structuresSaved + ' / ' + R.structuresTotal],
    ];
    let y = H * 0.38;
    for (const [a, b] of rows) {
      ctx.fillStyle = '#7f8a99'; ctx.textAlign = 'right'; ctx.fillText(a, W / 2 - 20, y);
      ctx.fillStyle = '#e6edf3'; ctx.textAlign = 'left'; ctx.fillText(b, W / 2 + 20, y);
      y += 38;
    }
    ctx.textAlign = 'center';
    ctx.fillStyle = '#27e0ff'; ctx.font = 'bold 20px monospace';
    ctx.fillText('[ D ]  download training log  (drones.jsonl + manifest.json)', W / 2, y + 30);
    ctx.fillStyle = '#9fb3c8'; ctx.font = '16px monospace';
    ctx.fillText('Enter / A — back to menu', W / 2, y + 64);
    if (this.aiAdapted) {
      ctx.fillStyle = '#ffd23d'; ctx.font = '13px monospace';
      ctx.fillText('This fleet was trained on your previous winning run.', W / 2, y + 92);
    }
  }
}

/* ===================================================================== */
/*  DRONE                                                                */
/* ===================================================================== */
class Drone {
  constructor(id, color, gx, gy, player) {
    this.id = id; this.color = color; this.gx = gx; this.gy = gy; this.player = !!player;
    this.vx = 0; this.vy = 0; this.heading = -Math.PI / 2; this.speed = 0; this.rotor = 0;
    this.tank = TANK_MAX; this.bombs = BOMB_COUNT_START; this.score = 0;
    this.spraying = false; this.sprayFx = 0; this.boost = 0;
    // AI
    this.skill = 0.8; this.target = null; this.thinkT = 0; this.refilling = false;
  }
}

/* ===================================================================== */
/*  INPUT (keyboard + gamepad)                                           */
/* ===================================================================== */
class Input {
  constructor(canvas) {
    this.keys = {};            // currently down
    this.justPressed = {};     // pressed this frame
    this.buffered = {};        // pressed since last consume
    this.prevGp = {};          // gamepad button prev state
    this.gpJust = {};          // gamepad just-pressed this frame
    window.addEventListener('keydown', (e) => {
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.code)) e.preventDefault();
      if (!this.keys[e.code]) { this.justPressed[e.code] = true; this.buffered[e.code] = true; }
      this.keys[e.code] = true;
    });
    window.addEventListener('keyup', (e) => { this.keys[e.code] = false; });
    window.addEventListener('blur', () => { this.keys = {}; });
  }
  poll() {
    // gamepad just-pressed edge detection
    this.gpJust = {};
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    this.pad = null;
    for (const p of pads) { if (p) { this.pad = p; break; } }
    if (this.pad) {
      for (let i = 0; i < this.pad.buttons.length; i++) {
        const pressed = this.pad.buttons[i].pressed || this.pad.buttons[i].value > 0.5;
        if (pressed && !this.prevGp[i]) this.gpJust[i] = true;
        this.prevGp[i] = pressed;
      }
    }
  }
  endFrame() { this.justPressed = {}; }
  consumeBuffered() { this.buffered = {}; }
  down(code) { return !!this.keys[code]; }
  pressed(code) { return !!this.justPressed[code]; }
  gpDown(i) { return this.pad ? (this.pad.buttons[i] && (this.pad.buttons[i].pressed || this.pad.buttons[i].value > 0.5)) : false; }
  gpPressed(i) { return !!this.gpJust[i]; }
  axes() {
    if (!this.pad) return null;
    let lx = this.pad.axes[0] || 0, ly = this.pad.axes[1] || 0;
    const dz = 0.18;
    if (Math.abs(lx) < dz) lx = 0; if (Math.abs(ly) < dz) ly = 0;
    return { lx, ly };
  }
}

/* ----------------------------- boot ----------------------------- */
if (typeof window !== 'undefined') {
  window.addEventListener('load', () => {
    const canvas = document.getElementById('game');
    window.__game = new Game(canvas);
  });
}
if (typeof module !== 'undefined') { module.exports = { mulberry32, clamp, lerp, ZONE, COLS, ROWS }; }
