// La vue 3D du plateau (Three.js), en option à côté de la carte 2D.
//
// Le serveur envoie la route une fois par course (flamme_rouge/scene.py) : pour chaque case, ses bords gauche et
// droit dans le repère de la carte (une case = 1 de long, y vers le haut de la carte) et l'altitude de chaque bord,
// en cases de dénivelé. Ici, le repère Three.js : x = x de la carte, y = la hauteur, z = −y de la carte (le haut de
// la carte est au fond de l'écran, comme sur la carte 2D vue de face).
// Les coureurs se placent comme dans geometry.point_on_road : centre de leur file sur la case, puis ligne droite
// d'une case à la suivante.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";

const SKY = 0x16233a;
const ROAD_EDGE = "#e2e8f0", LANE_LINE = "#64748b", SQUARE_LINE = "#2a3444";
const CURRENT_RING = "#fde047", CRASH_MARK = "#ff4d4f";
const WHEEL = "#1e293b", FRAME = "#cbd5e1", SKIN = "#f1c27d";
const WALL_SHADE = 0.55; // les côtés de la route, plus sombres que le dessus
// le terrain en talus (voir class Terrain)
const ROAD_BORDER = 0.22; // la bordure fine sous la chaussée (plus profonde seulement si le terrain est plus bas)
const TERRAIN_DROP = 0.12; // le terrain passe juste sous la chaussée (la bordure le cache)
const TERRAIN_STEP = 0.5; // un point de terrain tous les 0,5 case
const TERRAIN_MARGIN = 8; // le terrain déborde de 8 cases autour du parcours (au-delà : la plaine)
const TERRAIN_TALUS = 0.7; // pente du talus : il descend de 0,7 par case en s'éloignant de la route
const TERRAIN_RISE = 1.9; // et ne monte jamais au-dessus d'une route voisine plus basse (pente maximale vers elle)
const TERRAIN_FILL = 3; // un creux de moins de 2 × 3 cases entre deux routes hautes est comblé (pas de cuvette)
const GRASS_TILE = 2; // la texture de pelouse se répète toutes les 2 cases
const TERRAIN_GREEN = "#2a6e44", TERRAIN_HIGH = "#3a8050"; // herbe (la texture l'assombrit un peu), plus claire en haut du talus
const CLIFF = "#6b5a48"; // la paroi de terre sous une route plus haute que le terrain
const SLICES = 6; // tranches d'une case droite : la route s'arrondit aux changements de pente
const LINE_LIFT = 0.006; // les traits flottent juste au-dessus de la route (pas de scintillement)
const START_DEPTH = 0.14; // largeur de la ligne de départ blanche, en fraction de case
const NUMBER_EVERY = 5; // numéro de case tous les 5 (et à l'arrivée)
const FOLLOW_DISTANCE = 7; // distance de la caméra au groupe suivi, en cases
const RACE_VIEW_AHEAD = 5; // vue course : les 5 prochaines cases devant le premier coureur (boardview.RACE_VIEW_AHEAD)
const MOVE_TIME = 0.6; // durée d'un changement de cadrage, en secondes
const FIT_MARGIN = 0.92; // vue d'ensemble : le parcours occupe 92 % du cadre
const RIDER_SCALE = 2.2; // les coureurs plus grands que nature : un vélo fait à peu près la longueur d'une case
const DUST_BITS = 40;
const SWEAT_DROPS = 6; // gouttes de sueur d'un coureur en montée
const SWEAT = "#bfe3ff";
const TIRED = "#ef4444"; // phase de fatigue : le maillot vire au rouge, un halo rouge pulse autour du coureur // grains du nuage de poussière d'une chute

const lerp = (a, b, f) => a + (b - a) * f;
const rnd = (seed) => { const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const lerp2 = (p, q, f) => [lerp(p[0], q[0], f), lerp(p[1], q[1], f)];

function shade(hex, f) {
  return new THREE.Color(hex).multiplyScalar(f);
}

// ------------------------------------------------------------------ le terrain
// Un talus sous la route : la route est posée sur une levée de terre qui redescend en pente douce, de chaque côté,
// jusqu'à une plaine plate. La hauteur d'un point est la plus haute des pentes descendant des routes voisines (ou la
// plaine), mais jamais au-dessus d'une route plus basse toute proche (épingles, lacets : la route reste visible).
// Sous la chaussée, le talus passe juste en dessous, caché par la bordure.

class Terrain {
  constructor(road) {
    // des points le long du milieu de la route : position, altitude, demi-largeur
    const pts = [];
    road.squares.forEach((_, s) => {
      const { left, right } = road.paths(s), m = left.length;
      for (let k = 0; k < m; k++) {
        const [x, y] = lerp2(left[k], right[k], 0.5);
        pts.push([x, -y, road.heightAt(s, k, m), Math.hypot(left[k][0] - right[k][0], left[k][1] - right[k][1]) / 2]);
      }
    });
    this.low = -TERRAIN_DROP; // la plaine
    const xs = pts.map((q) => q[0]), zs = pts.map((q) => q[1]);
    this.x0 = Math.min(...xs) - TERRAIN_MARGIN;
    this.z0 = Math.min(...zs) - TERRAIN_MARGIN;
    this.nx = Math.ceil((Math.max(...xs) + TERRAIN_MARGIN - this.x0) / TERRAIN_STEP) + 1;
    this.nz = Math.ceil((Math.max(...zs) + TERRAIN_MARGIN - this.z0) / TERRAIN_STEP) + 1;
    this.h = new Float32Array(this.nx * this.nz);
    const ceiling = new Float32Array(this.nx * this.nz);
    const top = Math.max(...pts.map((q) => q[2]));
    const reach = (top - this.low) / TERRAIN_TALUS + 1; // au-delà, le talus est déjà redescendu à la plaine
    for (let j = 0; j < this.nz; j++) {
      for (let i = 0; i < this.nx; i++) {
        const x = this.x0 + i * TERRAIN_STEP, z = this.z0 + j * TERRAIN_STEP;
        let mound = this.low, upper = Infinity; // le talus, et la hauteur à ne pas dépasser
        for (const [px, pz, py, half] of pts) {
          const dx = x - px, dz = z - pz;
          if (dx > reach || dx < -reach || dz > reach || dz < -reach) continue;
          const d = Math.max(Math.hypot(dx, dz) - half, 0); // 0 sur la chaussée
          mound = Math.max(mound, py - TERRAIN_DROP - TERRAIN_TALUS * d); // le talus de cette route
          upper = Math.min(upper, py - TERRAIN_DROP + TERRAIN_RISE * d); // jamais sur une route plus basse
        }
        this.h[j * this.nx + i] = mound;
        ceiling[j * this.nx + i] = upper;
      }
    }
    // entre deux routes hautes, le talus ne redescend pas : les creux étroits sont comblés jusqu'au plus bas de leurs
    // deux bords (une fermeture : chaque point prend le plus haut alentour, puis le plus bas de ces hauteurs)
    const r = Math.round(TERRAIN_FILL / TERRAIN_STEP);
    this.h = this.spread(this.spread(this.h, r, Math.max), r, Math.min);
    for (let k = 0; k < this.h.length; k++) this.h[k] = Math.min(this.h[k], ceiling[k]); // jamais sur une route
  }

  // le plus haut (ou le plus bas, selon `pick`) des points de la grille à moins de r cases, ligne puis colonne
  spread(src, r, pick) {
    const { nx, nz } = this, tmp = new Float32Array(src.length), out = new Float32Array(src.length);
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        let v = src[j * nx + i];
        for (let k = Math.max(0, i - r); k <= Math.min(nx - 1, i + r); k++) v = pick(v, src[j * nx + k]);
        tmp[j * nx + i] = v;
      }
    }
    for (let j = 0; j < nz; j++) {
      for (let i = 0; i < nx; i++) {
        let v = tmp[j * nx + i];
        for (let k = Math.max(0, j - r); k <= Math.min(nz - 1, j + r); k++) v = pick(v, tmp[k * nx + i]);
        out[j * nx + i] = v;
      }
    }
    return out;
  }

  // la hauteur du terrain en (x, z), entre les points de la grille
  at(x, z) {
    const fi = Math.min(Math.max((x - this.x0) / TERRAIN_STEP, 0), this.nx - 1.001);
    const fj = Math.min(Math.max((z - this.z0) / TERRAIN_STEP, 0), this.nz - 1.001);
    const i = Math.floor(fi), j = Math.floor(fj), u = fi - i, w = fj - j, n = this.nx;
    const a = this.h[j * n + i], b = this.h[j * n + i + 1], c = this.h[(j + 1) * n + i], d = this.h[(j + 1) * n + i + 1];
    return (a * (1 - u) + b * u) * (1 - w) + (c * (1 - u) + d * u) * w;
  }

  mesh() {
    const g = new THREE.PlaneGeometry((this.nx - 1) * TERRAIN_STEP, (this.nz - 1) * TERRAIN_STEP, this.nx - 1, this.nz - 1);
    g.rotateX(-Math.PI / 2); // à plat : x vers la droite, z vers l'avant
    g.translate(this.x0 + ((this.nx - 1) * TERRAIN_STEP) / 2, 0, this.z0 + ((this.nz - 1) * TERRAIN_STEP) / 2);
    const pos = g.attributes.position, top = Math.max(...this.h, 0.5);
    const colors = new Float32Array(pos.count * 3), low = new THREE.Color(TERRAIN_GREEN), high = new THREE.Color(TERRAIN_HIGH);
    const c = new THREE.Color();
    for (let v = 0; v < pos.count; v++) {
      const y = this.at(pos.getX(v), pos.getZ(v));
      pos.setY(v, y);
      c.copy(low).lerp(high, Math.max(0, Math.min(1, (y - this.low) / top)) * 0.8);
      colors.set([c.r, c.g, c.b], v * 3);
    }
    g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    g.computeVertexNormals();
    const map = grassTexture().clone();
    map.repeat.set(((this.nx - 1) * TERRAIN_STEP) / GRASS_TILE, ((this.nz - 1) * TERRAIN_STEP) / GRASS_TILE);
    map.needsUpdate = true;
    const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, map }));
    m.receiveShadow = true;
    return m;
  }
}

// une pelouse : des brins d'herbe clairs et foncés sur un fond presque blanc (la couleur vient du terrain, que la
// texture module), tirés au hasard une fois pour toutes ; elle se répète sans raccord visible
let grass = null;
function grassTexture() {
  if (grass) return grass;
  const size = 256, c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d");
  ctx.fillStyle = "rgb(214, 226, 206)";
  ctx.fillRect(0, 0, size, size);
  for (let k = 0; k < 90; k++) { // des touffes plus sombres ou plus claires
    const x = rnd(k * 3.1) * size, y = rnd(k * 5.7) * size, r = 8 + rnd(k * 2.3) * 22, l = 170 + rnd(k * 9.1) * 80;
    ctx.fillStyle = `rgba(${l - 20}, ${l}, ${l - 30}, 0.35)`;
    for (const [dx, dy] of [[0, 0], [size, 0], [-size, 0], [0, size], [0, -size]]) { // raccord sur les bords
      ctx.beginPath();
      ctx.arc(x + dx, y + dy, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.lineCap = "round";
  for (let k = 0; k < 5000; k++) { // les brins
    const x = rnd(k * 1.37 + 11) * size, y = rnd(k * 2.71 + 7) * size, len = 2 + rnd(k * 0.53) * 4;
    const a = -Math.PI / 2 + (rnd(k * 4.13) - 0.5) * 0.9, l = 150 + rnd(k * 6.67) * 105;
    ctx.strokeStyle = `rgb(${l - 25}, ${l}, ${l - 40})`;
    ctx.lineWidth = 0.8 + rnd(k * 8.9) * 0.8;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    ctx.stroke();
  }
  grass = new THREE.CanvasTexture(c);
  grass.wrapS = grass.wrapT = THREE.RepeatWrapping;
  grass.colorSpace = THREE.SRGBColorSpace;
  grass.anisotropy = 8;
  return grass;
}

// ------------------------------------------------------------------ la route

class Road {
  constructor(scene) {
    this.data = scene;
    this.lift = scene.lift;
    this.squares = scene.squares;
    this.z = scene.z;
    // altitude du milieu de chaque case (moyenne de ses bords), comme boardview.road_altitudes
    this.mid = this.squares.map((_, s) => (this.z[s] + this.z[s + 1]) / 2);
    // pentes aux bords des cases pour une route qui s'arrondit (interpolation cubique monotone) : nulle au passage
    // du plat à la montée ou de la montée à la descente, la moyenne des deux pentes au milieu d'une montée ;
    // la route ne dépasse jamais l'altitude des bords (pas de bosse ni de creux inventés)
    const z = this.z;
    this.slopes = z.map((_, i) => {
      if (i === 0 || i === z.length - 1) return 0;
      const before = z[i] - z[i - 1], after = z[i + 1] - z[i];
      return before * after <= 0 ? 0 : (before + after) / 2;
    });
  }

  // altitude (en cases de dénivelé) au bord fractionnaire u : u = s au bord arrière de la case s, s + 1 devant
  altitude(u) {
    const last = this.z.length - 1;
    u = Math.min(Math.max(u, 0), last);
    const i = Math.min(Math.floor(u), last - 1), t = u - i;
    if (last === 0) return this.z[0];
    const t2 = t * t, t3 = t2 * t;
    return (2 * t3 - 3 * t2 + 1) * this.z[i] + (t3 - 2 * t2 + t) * this.slopes[i]
      + (-2 * t3 + 3 * t2) * this.z[i + 1] + (t3 - t2) * this.slopes[i + 1];
  }

  // les bords gauche et droit d'une case, découpés finement (une ligne droite n'a que 2 points : la pente ne
  // pourrait pas s'arrondir dessus)
  paths(s) {
    const { left, right } = this.squares[s];
    if (left.length > 2) return { left, right };
    const cut = (a, b) => Array.from({ length: SLICES + 1 }, (_, k) => lerp2(a, b, k / SLICES));
    return { left: cut(left[0], left[1]), right: cut(right[0], right[1]) };
  }

  laneCenter(s, lane) { // comme SquareGeom.lane_center : 0 = file de droite
    const sq = this.squares[s];
    const left = sq.left, right = sq.right;
    const back = lerp2(right[0], left[0], (lane + 0.5) / sq.lanes);
    const front = lerp2(right[right.length - 1], left[left.length - 1], (lane + 0.5) / sq.lanes);
    return lerp2(back, front, 0.5);
  }

  // point de la route à la case `progress` (fractionnaire) et à la file `lane`, en coordonnées Three.js
  point(progress, lane, out = new THREE.Vector3()) {
    const last = this.squares.length - 1;
    const p = Math.min(Math.max(progress, 0), last);
    const i = Math.min(Math.floor(p), Math.max(last - 1, 0));
    const f = p - i;
    const a = this.laneCenter(i, lane);
    const [x, y] = last === 0 ? a : lerp2(a, this.laneCenter(i + 1, lane), f);
    return out.set(x, this.altitude(p + 0.5) * this.lift, -y); // le milieu de la case p est au bord p + ½
  }

  // hauteur de la route au point `k` (0 à m − 1) d'un bord de la case s
  heightAt(s, k, m) {
    return this.altitude(s + (m > 1 ? k / (m - 1) : 0)) * this.lift;
  }

  build() {
    const group = new THREE.Group();
    const top = [], topColors = [], walls = [], wallColors = [], edges = [], lanes = [], cross = [];
    this.terrain = new Terrain(this);
    group.add(this.terrain.mesh());
    const cliff = new THREE.Color(CLIFF);
    const v = (x, y, h) => [x, h, -y];
    const n = this.data.n;
    this.squares.forEach((sq, s) => {
      const { left, right } = this.paths(s), m = left.length;
      const fill = new THREE.Color(sq.fill), wall = shade(sq.fill, WALL_SHADE);
      for (let k = 0; k < m - 1; k++) {
        const h0 = this.heightAt(s, k, m), h1 = this.heightAt(s, k + 1, m);
        const l0 = v(...left[k], h0), r0 = v(...right[k], h0), l1 = v(...left[k + 1], h1), r1 = v(...right[k + 1], h1);
        top.push(...r0, ...l0, ...l1, ...r0, ...l1, ...r1);
        for (let t = 0; t < 6; t++) topColors.push(fill.r, fill.g, fill.b);
        { // la bordure fine sous la chaussée ; plus profonde là où le terrain est plus bas (jamais de route en l'air)
          const foot = (p, h) => Math.min(h - ROAD_BORDER, this.terrain.at(p[0], -p[1]) - 0.03);
          for (const [p0, ha, p1, hb] of [[left[k], h0, left[k + 1], h1], [right[k], h0, right[k + 1], h1]]) {
            const fa = foot(p0, ha), fb = foot(p1, hb);
            const a = v(...p0, ha), b = v(...p1, hb), a0 = v(...p0, fa), b0 = v(...p1, fb);
            walls.push(...a, ...a0, ...b0, ...a, ...b0, ...b);
            // la bordure garde la couleur de la route ; une paroi plus haute est en terre
            const deep = Math.max(ha - fa, hb - fb) > ROAD_BORDER * 2;
            const c = deep ? cliff : wall;
            for (let t = 0; t < 6; t++) wallColors.push(c.r, c.g, c.b);
          }
        }
        // bords blancs de la route
        edges.push(...v(...left[k], h0 + LINE_LIFT), ...v(...left[k + 1], h1 + LINE_LIFT));
        edges.push(...v(...right[k], h0 + LINE_LIFT), ...v(...right[k + 1], h1 + LINE_LIFT));
        // traits entre les files
        for (let j = 1; j < sq.lanes; j++) {
          const a = lerp2(right[k], left[k], j / sq.lanes), b = lerp2(right[k + 1], left[k + 1], j / sq.lanes);
          lanes.push(...v(...a, h0 + LINE_LIFT), ...v(...b, h1 + LINE_LIFT));
        }
      }
      // trait entre deux cases (on les compte comme sur la carte)
      const h = this.heightAt(s, 0, m) + LINE_LIFT;
      cross.push(...v(...left[0], h), ...v(...right[0], h));
    });
    const mesh = (positions, colors) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
      g.computeVertexNormals();
      const m = new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
      m.receiveShadow = true;
      return m;
    };
    group.add(mesh(top, topColors), mesh(walls, wallColors));
    const lines = (positions, color) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
      return new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color }));
    };
    group.add(lines(edges, ROAD_EDGE), lines(lanes, LANE_LINE), lines(cross, SQUARE_LINE));
    group.add(this.line(n, checkerTexture(), 0.22));
    group.add(this.line(this.data.start, null, START_DEPTH)); // ligne de départ (case 0 sans grille de départ)
    return group;
  }

  // une bande posée en travers de la route sur le bord arrière de la case s : arrivée (damier) ou départ (blanc)
  line(s, texture, depth) {
    const sq = this.squares[Math.min(s, this.squares.length - 1)];
    const h = this.heightAt(s, 0, 2) + LINE_LIFT * 2;
    const [l, r] = [sq.left[0], sq.right[0]];
    const [lf, rf] = [lerp2(sq.left[0], sq.left[1], depth), lerp2(sq.right[0], sq.right[1], depth)];
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute([
      r[0], h, -r[1], l[0], h, -l[1], lf[0], h, -lf[1], r[0], h, -r[1], lf[0], h, -lf[1], rf[0], h, -rf[1]], 3));
    g.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 0, 1, 1, 0, 1], 2));
    return new THREE.Mesh(g, new THREE.MeshBasicMaterial({ ...(texture ? { map: texture } : { color: "#ffffff" }), side: THREE.DoubleSide }));
  }

  // le dessus de la route des cases start à end − 1, soulevé de `lift` (route mouillée)
  topGeometry(start, end, lift) {
    const top = [];
    for (let s = start; s < end; s++) {
      const { left, right } = this.paths(s), m = left.length;
      for (let k = 0; k < m - 1; k++) {
        const h0 = this.heightAt(s, k, m) + lift, h1 = this.heightAt(s, k + 1, m) + lift;
        const r0 = [right[k][0], h0, -right[k][1]], l0 = [left[k][0], h0, -left[k][1]];
        const r1 = [right[k + 1][0], h1, -right[k + 1][1]], l1 = [left[k + 1][0], h1, -left[k + 1][1]];
        top.push(...r0, ...l0, ...l1, ...r0, ...l1, ...r1);
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(top, 3));
    g.computeVertexNormals();
    return g;
  }

  bounds() {
    const box = new THREE.Box3();
    const p = new THREE.Vector3();
    this.squares.slice(0, this.data.n + 2).forEach((sq, s) => {
      for (const q of [...sq.left, ...sq.right]) box.expandByPoint(p.set(q[0], this.mid[s] * this.lift, -q[1]));
    });
    return box;
  }
}

function checkerTexture() {
  const c = document.createElement("canvas");
  c.width = 64; c.height = 16;
  const ctx = c.getContext("2d");
  for (let i = 0; i < 8; i++) for (let j = 0; j < 2; j++) {
    ctx.fillStyle = (i + j) % 2 ? "#111111" : "#ffffff";
    ctx.fillRect(i * 8, j * 8, 8, 8);
  }
  const t = new THREE.CanvasTexture(c);
  t.magFilter = THREE.NearestFilter;
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

// ------------------------------------------------------------------ les coureurs
// Un coureur articulé, vu de profil dans son repère : +x = vers l'arrivée, y = la hauteur, z = sur le côté.
// Les jambes suivent les pédales (cinématique inverse à deux segments : cuisse et tibia), les roues et le pédalier
// tournent avec la distance parcourue. Posture : assis (rouleur droit, sprinteur bas et trapu), en danseuse dans
// les montées, recroquevillé dans les descentes (roue libre, il ne pédale pas). À terre après une chute : le vélo
// couché d'un côté, le coureur de l'autre, un nuage de poussière. La danseuse reste à l'arrêt dans une montée.

const BB = [0, 0.1]; // le pédalier
const CRANK = 0.045; // longueur d'une manivelle
const THIGH = 0.12, SHIN = 0.125;
const HANDS = [0.115, 0.235];
const WHEEL_R = 0.085;
const CADENCE = 2.2 * Math.PI * 2; // tours de pédalier par case parcourue (× 2π)
const POSES = { // hanche, épaules et tête (par rapport aux épaules), dans le repère du vélo
  rouleur: { hip: [-0.035, 0.245], shoulder: [0.072, 0.34], head: [0.028, 0.05] },
  sprinteur: { hip: [-0.03, 0.235], shoulder: [0.088, 0.3], head: [0.028, 0.05] },
  danseuse: { hip: [0.015, 0.29], shoulder: [0.105, 0.35], head: [0.028, 0.05] },
  // recherche de vitesse : les fesses en arrière, le buste à plat, la poitrine sur le guidon, la tête basse
  descente: { hip: [-0.06, 0.252], shoulder: [0.112, 0.252], head: [0.04, 0.03] },
};
const SHORTS = "#111827";
const DUST = "#eadcb8";
const Y_AXIS = new THREE.Vector3(0, 1, 0);

const parts = {
  wheel: new THREE.TorusGeometry(WHEEL_R, 0.012, 6, 22),
  spoke: new THREE.BoxGeometry(WHEEL_R * 2, 0.006, 0.006),
  tube: new THREE.CylinderGeometry(0.009, 0.009, 1, 6),
  limb: new THREE.CylinderGeometry(0.019, 0.016, 1, 8),
  joint: new THREE.SphereGeometry(0.02, 8, 6),
  torso: new THREE.CapsuleGeometry(0.05, 0.12, 4, 10),
  head: new THREE.SphereGeometry(0.04, 14, 10),
  helmet: new THREE.SphereGeometry(0.048, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2),
  glasses: new THREE.BoxGeometry(0.018, 0.014, 0.07),
  saddle: (() => { // une selle : large à l'arrière, fine au bec
    const shape = new THREE.Shape();
    shape.moveTo(-0.035, -0.022);
    shape.quadraticCurveTo(-0.045, 0, -0.035, 0.022);
    shape.lineTo(0.02, 0.009);
    shape.quadraticCurveTo(0.04, 0, 0.02, -0.009);
    shape.closePath();
    const g = new THREE.ExtrudeGeometry(shape, { depth: 0.012, bevelEnabled: true, bevelSize: 0.004,
                                                  bevelThickness: 0.004, bevelSegments: 2 });
    g.rotateX(-Math.PI / 2); // à plat, le bec vers +x
    return g;
  })(),
  crank: new THREE.BoxGeometry(CRANK, 0.008, 0.008),
  pedal: new THREE.BoxGeometry(0.03, 0.008, 0.03),
  drop: (() => { const g = new THREE.SphereGeometry(0.01, 8, 6); g.scale(1, 1.6, 1); return g; })(), // goutte allongée
  shadow: new THREE.CircleGeometry(0.24, 20), // ombre et anneaux au sol, à la taille des coureurs
  ring: new THREE.RingGeometry(0.3, 0.37, 28),
  halo: new THREE.SphereGeometry(0.26, 20, 14),
  wake: (() => { const g = new THREE.ConeGeometry(0.17, 0.9, 18, 1, true); g.rotateZ(Math.PI / 2); g.translate(-0.55, 0.22, 0); return g; })(),
};

// place un cylindre (ou un membre) de a à b ; `width` épaissit sans allonger
function stretch(mesh, a, b, width = 1) {
  const dir = new THREE.Vector3().subVectors(b, a);
  const length = dir.length();
  mesh.position.addVectors(a, b).multiplyScalar(0.5);
  mesh.scale.set(width, Math.max(length, 1e-4), width);
  mesh.quaternion.setFromUnitVectors(Y_AXIS, dir.normalize());
}

// le genou : à distance THIGH de la hanche et SHIN du pied, toujours vers l'avant
function knee(hip, foot) {
  const dx = foot[0] - hip[0], dy = foot[1] - hip[1];
  const d = Math.min(Math.max(Math.hypot(dx, dy), Math.abs(THIGH - SHIN) + 1e-3), THIGH + SHIN - 1e-3);
  const a = (THIGH * THIGH - SHIN * SHIN + d * d) / (2 * d), h = Math.sqrt(Math.max(THIGH * THIGH - a * a, 0));
  const ux = dx / Math.hypot(dx, dy), uy = dy / Math.hypot(dx, dy);
  return [hip[0] + a * ux - h * uy, hip[1] + a * uy + h * ux];
}

class RiderView {
  constructor(r, colors) {
    const fill = new THREE.Color(colors.fill[r.team]);
    this.sprinter = r.name.endsWith("S");
    this.base = this.sprinter ? POSES.sprinteur : POSES.rouleur;
    this.pose = { hip: [...this.base.hip], shoulder: [...this.base.shoulder], head: [...this.base.head] };
    const lambert = (color) => new THREE.MeshLambertMaterial({ color });
    const team = lambert(fill), skin = lambert(SKIN), dark = lambert(WHEEL), metal = lambert(FRAME);
    const shorts = lambert(SHORTS);
    this.teamMat = team;
    this.teamColor = fill.clone();

    this.group = new THREE.Group(); // à la place du coureur sur la route, tourné vers l'arrivée
    this.slope = new THREE.Group(); // penché comme la route : vélo, coureur, ombre et anneaux suivent la pente
    this.group.add(this.slope);
    this.model = new THREE.Group(); // à l'échelle des coureurs
    this.model.scale.setScalar(RIDER_SCALE);
    this.slope.add(this.model);
    this.bike = new THREE.Group();
    this.body = new THREE.Group();
    this.model.add(this.bike, this.body);

    // le vélo : deux roues à rayons, le cadre, le guidon, le pédalier
    this.wheels = [-0.12, 0.12].map((x) => {
      const w = new THREE.Group();
      w.position.set(x, WHEEL_R + 0.012, 0);
      w.add(new THREE.Mesh(parts.wheel, dark));
      for (const a of [0, Math.PI / 3, (2 * Math.PI) / 3]) {
        const s = new THREE.Mesh(parts.spoke, metal);
        s.rotation.z = a;
        w.add(s);
      }
      this.bike.add(w);
      return w;
    });
    const v = (x, y, z = 0) => new THREE.Vector3(x, y, z);
    const tubes = [[v(-0.12, 0.097), v(0, 0.1)], [v(0, 0.1), v(-0.035, 0.235)], [v(-0.035, 0.215), v(0.095, 0.215)],
                   [v(0, 0.1), v(0.095, 0.215)], [v(0.095, 0.215), v(0.12, 0.097)], [v(0.095, 0.215), v(0.11, 0.24)],
                   [v(-0.12, 0.097), v(-0.035, 0.215)]];
    for (const [a, b] of tubes) {
      const t = new THREE.Mesh(parts.tube, metal);
      stretch(t, a, b);
      this.bike.add(t);
    }
    const saddle = new THREE.Mesh(parts.saddle, dark); // en haut de la tige de selle
    saddle.position.set(-0.035, 0.232, 0);
    this.bike.add(saddle);
    const bar = new THREE.Mesh(parts.tube, metal);
    stretch(bar, v(0.115, 0.24, -0.05), v(0.115, 0.24, 0.05));
    this.bike.add(bar);
    this.crankSet = new THREE.Group();
    this.crankSet.position.set(BB[0], BB[1], 0);
    for (const side of [-1, 1]) {
      const arm = new THREE.Group();
      arm.rotation.z = side > 0 ? 0 : Math.PI;
      const c = new THREE.Mesh(parts.crank, metal);
      c.position.set(CRANK / 2, 0, side * 0.03);
      const p = new THREE.Mesh(parts.pedal, dark);
      p.position.set(CRANK, 0, side * 0.045);
      arm.add(c, p);
      this.crankSet.add(arm);
    }
    this.bike.add(this.crankSet);

    // le coureur : buste, tête, casque, lunettes, bras, jambes
    this.torso = new THREE.Mesh(parts.torso, team);
    this.torso.userData.width = this.sprinter ? 1.18 : 1;
    this.head = new THREE.Group();
    this.head.add(new THREE.Mesh(parts.head, skin));
    const helmet = new THREE.Mesh(parts.helmet, team);
    helmet.position.y = 0.004;
    helmet.scale.set(1.08, 0.85, 0.92);
    const glasses = new THREE.Mesh(parts.glasses, dark);
    glasses.position.set(0.036, 0.004, 0);
    this.head.add(helmet, glasses);
    this.neck = new THREE.Mesh(parts.limb, skin);
    this.body.add(this.torso, this.head, this.neck);
    this.arms = [-1, 1].map(() => { const m = new THREE.Mesh(parts.limb, team); this.body.add(m); return m; });
    this.legs = [-1, 1].map((side) => {
      const thigh = new THREE.Mesh(parts.limb, shorts), shin = new THREE.Mesh(parts.limb, skin);
      const joint = new THREE.Mesh(parts.joint, skin);
      this.body.add(thigh, shin, joint);
      return { side, thigh, shin, joint };
    });
    this.model.traverse((o) => { o.castShadow = true; });

    // l'ombre, l'anneau (celui qui choisit ; rouge à terre), l'étiquette
    const shadow = new THREE.Mesh(parts.shadow, new THREE.MeshBasicMaterial({ color: "#000000", transparent: true,
                                                                                opacity: 0.25, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = LINE_LIFT * 2;
    this.slope.add(shadow);
    this.ring = new THREE.Mesh(parts.ring, new THREE.MeshBasicMaterial({ color: CURRENT_RING, side: THREE.DoubleSide }));
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.position.y = LINE_LIFT * 3;
    this.slope.add(this.ring);
    const tag = document.createElement("div");
    tag.className = "rider3d";
    tag.textContent = r.name;
    tag.style.background = colors.fill[r.team];
    tag.style.color = colors.label[r.team];
    this.tag = tag;
    this.label = new CSS2DObject(tag);
    this.label.position.set(0, 0.42 * RIDER_SCALE + 0.12, 0);
    this.group.add(this.label);

    // aspiration : la poche d'air derrière celui qui protège, les traits de vitesse de celui qui est aspiré
    this.wake = new THREE.Mesh(parts.wake, new THREE.MeshBasicMaterial({ color: "#e0f2fe", transparent: true,
      opacity: 0, depthWrite: false, side: THREE.DoubleSide }));
    this.model.add(this.wake);
    const speed = new THREE.BufferGeometry();
    speed.setAttribute("position", new THREE.BufferAttribute(new Float32Array(6 * 6), 3));
    this.speed = new THREE.LineSegments(speed, new THREE.LineBasicMaterial({ color: "#f0f9ff", transparent: true, opacity: 0.8 }));
    this.speed.frustumCulled = false;
    this.model.add(this.speed);
    // chute : un petit nuage de poussière
    const dust = new THREE.BufferGeometry();
    dust.setAttribute("position", new THREE.BufferAttribute(new Float32Array(DUST_BITS * 3), 3));
    this.dust = new THREE.Points(dust, new THREE.PointsMaterial({ color: DUST, size: 0.075, transparent: true,
                                                                  opacity: 0.7, depthWrite: false }));
    this.dust.frustumCulled = false;
    this.model.add(this.dust);
    // fatigue : un halo rouge autour du coureur et un anneau rouge qui s'élargit au sol
    this.halo = new THREE.Mesh(parts.halo, new THREE.MeshBasicMaterial({ color: TIRED, transparent: true, opacity: 0,
      depthWrite: false, blending: THREE.AdditiveBlending }));
    this.halo.position.y = 0.2;
    this.model.add(this.halo);
    this.pulse = new THREE.Mesh(parts.ring, new THREE.MeshBasicMaterial({ color: TIRED, transparent: true, opacity: 0,
      depthWrite: false, side: THREE.DoubleSide }));
    this.pulse.rotation.x = -Math.PI / 2;
    this.pulse.position.y = LINE_LIFT * 4;
    this.slope.add(this.pulse);

    // montée : des gouttes de sueur perlent du visage et tombent
    this.sweat = Array.from({ length: SWEAT_DROPS }, (_, i) => {
      const drop = new THREE.Mesh(parts.drop, new THREE.MeshBasicMaterial({ color: SWEAT, transparent: true,
                                                                            opacity: 0.9, depthWrite: false }));
      // une goutte sur deux part d'une tempe (côté gauche ou droit), les autres de la nuque ; jamais du visage
      drop.userData = { phase: rnd(i * 13 + r.team), side: i % 2 ? 1 : -1, nape: i % 3 === 2,
                        speed: 0.9 + rnd(i * 3 + r.name.length) * 0.5, jitter: rnd(i * 7) };
      this.model.add(drop);
      return drop;
    });

    this.crank = rnd(r.name.length + r.team) * Math.PI * 2;
    this.wheel = 0;
    this.last = null;
  }

  // une image : place, posture, pédalage ; `draft` : aspiré en ce moment ; `wake` : il protège quelqu'un
  place(road, p, lane, { current, crashed, draft, wake, tired, t, dt }) {
    road.point(p, lane, this.group.position);
    const a = road.point(p - 0.25, lane), b = road.point(p + 0.25, lane);
    this.group.rotation.y = Math.atan2(-(b.z - a.z), b.x - a.x);
    // la pente de la route : le vélo monte le nez en l'air, descend le nez en bas (roues posées sur la route)
    this.slope.rotation.z = Math.atan2(b.y - a.y, Math.hypot(b.x - a.x, b.z - a.z));
    const moved = this.last ? this.last.distanceTo(this.group.position) : 0;
    this.last = (this.last || new THREE.Vector3()).copy(this.group.position);
    const moving = moved > 1e-4 && !crashed;
    const square = road.squares[Math.min(Math.max(Math.round(p), 0), road.squares.length - 1)];
    // en danseuse dans les montées, même à l'arrêt (on voit qui grimpe) ; recroquevillé en descente quand il roule
    // en danseuse dans les montées, écrasé sur le guidon dans les descentes, même à l'arrêt (on voit le relief)
    const target = square.kind === "A" ? POSES.danseuse : square.kind === "D" ? POSES.descente : this.base;
    const k = Math.min(1, dt * 6); // la posture change en douceur
    for (const key of ["hip", "shoulder", "head"]) {
      this.pose[key][0] = lerp(this.pose[key][0], target[key][0], k);
      this.pose[key][1] = lerp(this.pose[key][1], target[key][1], k);
    }
    const travel = moved / RIDER_SCALE;
    if (moving && square.kind !== "D") this.crank -= travel * CADENCE; // en descente : roue libre
    else if (square.kind === "D") { // pédales à plat pour la descente
      const level = Math.round(this.crank / Math.PI) * Math.PI;
      this.crank = lerp(this.crank, level, k);
    }
    if (moving) this.wheel -= travel / WHEEL_R;
    this.wheels.forEach((w) => { w.rotation.z = this.wheel; });
    this.crankSet.rotation.z = this.crank;
    // en danseuse, le vélo se balance d'un côté à l'autre au rythme des pédales
    const rock = moving && square.kind === "A" ? Math.sin(this.crank) * 0.12 : 0;
    this.pose3d(rock);

    this.fall(crashed, t);
    this.perspire(square.kind === "A" && !crashed, t);
    this.ring.visible = current || crashed;
    this.ring.material.color.set(crashed ? CRASH_MARK : CURRENT_RING);
    this.tag.classList.toggle("crashed", crashed);
    this.wake.material.opacity = wake ? 0.16 + 0.08 * Math.sin(t * 8) : 0;
    this.speed.visible = !!draft;
    if (draft) this.speedLines(t);
    this.tire(!!tired, t);
  }

  // il va prendre une carte Fatigue : maillot qui vire au rouge, halo et anneau rouges qui pulsent
  tire(tired, t) {
    const beat = 0.5 + 0.5 * Math.sin(t * 5);
    this.teamMat.color.copy(this.teamColor);
    if (tired) this.teamMat.color.lerp(new THREE.Color(TIRED), 0.55 + 0.3 * beat);
    this.halo.visible = this.pulse.visible = tired;
    this.tag.classList.toggle("tired", tired);
    if (!tired) return;
    this.halo.material.opacity = 0.12 + 0.14 * beat;
    this.halo.scale.setScalar(0.95 + 0.12 * beat);
    const wave = (t * 0.8) % 1; // l'anneau part du coureur et s'efface en s'élargissant
    this.pulse.scale.setScalar(1 + wave * 1.6);
    this.pulse.material.opacity = 0.7 * (1 - wave);
  }

  // le corps dans la posture du moment
  pose3d(rock) {
    const v = (x, y, z = 0) => new THREE.Vector3(x, y, z);
    const { hip, shoulder } = this.pose;
    this.bike.rotation.x = rock;
    this.body.rotation.x = rock;
    stretch(this.torso, v(...hip), v(...shoulder), this.torso.userData.width);
    this.torso.scale.y /= 0.22; // la capsule mesure 0,22 de haut
    // la tête posée au bout du buste, un peu au-dessus (le regard vers la route devant), reliée par le cou
    const head = this.pose.head;
    this.head.position.set(shoulder[0] + head[0], shoulder[1] + head[1], 0);
    this.head.rotation.z = -0.25;
    stretch(this.neck, v(shoulder[0] - 0.01, shoulder[1] - 0.005), v(this.head.position.x - 0.01, this.head.position.y - 0.02), 0.9);
    this.arms.forEach((arm, i) => {
      const z = i ? 0.04 : -0.04;
      stretch(arm, v(shoulder[0], shoulder[1] - 0.01, z), v(HANDS[0], HANDS[1], z * 1.2), 0.85);
    });
    for (const leg of this.legs) {
      const angle = this.crank + (leg.side > 0 ? 0 : Math.PI);
      const foot = [BB[0] + Math.cos(angle) * CRANK, BB[1] + Math.sin(angle) * CRANK];
      const kn = knee(hip, foot), z = leg.side * 0.038;
      stretch(leg.thigh, v(hip[0], hip[1], z), v(kn[0], kn[1], z), 1.1);
      stretch(leg.shin, v(kn[0], kn[1], z), v(foot[0], foot[1], z * 1.15), 0.85);
      leg.joint.position.set(kn[0], kn[1], z);
    }
  }

  // en montée : chaque goutte part du visage (front, tempes), glisse un peu puis tombe vers la route, et recommence
  perspire(on, t) {
    for (const drop of this.sweat) {
      drop.visible = on;
      if (!on) continue;
      const { phase, side, speed, nape, jitter } = drop.userData;
      const life = (t * speed + phase) % 1;
      const head = this.head.position;
      // sous le bord du casque : sur la tempe (le côté de la tête) ou dans la nuque (derrière), puis le long du cou
      const start = nape ? [head.x - 0.04, head.y - 0.005, side * 0.012 * jitter]
        : [head.x - 0.005 - 0.01 * jitter, head.y + 0.002, side * 0.043];
      const slide = nape ? [-0.008, -0.04, 0] : [-0.006, -0.042, side * -0.004]; // glisse vers le bas du cou
      if (life < 0.3) { // elle perle et glisse sur la peau
        const f = life / 0.3;
        drop.position.set(start[0] + slide[0] * f, start[1] + slide[1] * f, start[2] + slide[2] * f);
      } else { // elle se détache et tombe (accélérée), en reculant un peu avec la vitesse
        const f = (life - 0.3) / 0.7, y0 = start[1] + slide[1];
        drop.position.set(start[0] + slide[0] - 0.05 * f, y0 - (y0 - 0.05) * f * f, (start[2] + slide[2]) * (1 + 0.6 * f));
      }
      drop.material.opacity = life > 0.9 ? (1 - life) * 9 : 0.9;
    }
  }

  // à terre : le vélo couché sur un côté de la route, le coureur sur l'autre, la poussière qui retombe
  fall(crashed, t) {
    this.bike.position.set(crashed ? 0.08 : 0, crashed ? 0.012 : 0, crashed ? 0.21 : 0);
    if (crashed) this.bike.rotation.set(-Math.PI / 2, 0, 0.35);
    else this.bike.rotation.set(this.bike.rotation.x, 0, 0);
    this.body.position.set(crashed ? -0.05 : 0, crashed ? 0.04 : 0, crashed ? -0.2 : 0);
    if (crashed) this.body.rotation.set(Math.PI / 2, 0, -0.9); // allongé sur le flanc, à côté de son vélo
    else this.body.rotation.set(this.body.rotation.x, 0, 0);
    this.dust.visible = crashed;
    if (!crashed) return;
    const pos = this.dust.geometry.attributes.position;
    for (let i = 0; i < DUST_BITS; i++) {
      const life = (t * 0.4 + rnd(i * 7)) % 1, a = rnd(i * 3) * Math.PI * 2, r = 0.08 + life * (0.22 + rnd(i) * 0.14);
      pos.setXYZ(i, Math.cos(a) * r, 0.03 + Math.sin(Math.PI * life) * (0.12 + rnd(i * 5) * 0.12), Math.sin(a) * r);
    }
    pos.needsUpdate = true;
    this.dust.material.opacity = 0.55 + 0.2 * Math.sin(t * 2);
  }

  // l'aspiré : des traits de vitesse qui filent derrière lui
  speedLines(t) {
    const pos = this.speed.geometry.attributes.position;
    for (let i = 0; i < 6; i++) {
      const f = (t * 2.2 + i / 6) % 1, y = 0.08 + (i % 3) * 0.09, z = (i < 3 ? -1 : 1) * (0.07 + (i % 2) * 0.03);
      pos.setXYZ(2 * i, -0.15 - f * 0.35, y, z);
      pos.setXYZ(2 * i + 1, -0.32 - f * 0.35, y, z);
    }
    pos.needsUpdate = true;
  }
}

// ------------------------------------------------------------------ la météo
// Pluie : un nuage sombre au-dessus de la zone, des gouttes en traits qui tombent en biais, des éclaboussures
// qui s'élargissent sur la route et une route mouillée qui brille. Vent : des rafales en rubans ondulants qui
// filent dans le sens du vent, et une manche à air au bord de la
// route, tourné dans le sens du vent (dans le dos, de face ou de travers).

const RAIN_PER_SQUARE = 70; // gouttes par case : plus nombreuses mais plus fines
const RAIN_TOP = 5; // hauteur des nuages, d'où tombent les gouttes, en cases
const RAIN_STREAK = 0.14; // longueur d'une goutte
const RAIN_SLANT = 0.08; // biais des gouttes (un peu de vent)
const RAIN_OPACITY = 0.45; // des gouttes légères, à peine visibles une à une
const SPLASH_PER_SQUARE = 10;
const WET_COLOR = "#1d3b5c";
const CLOUD_COLOR = "#5d6b80";
const GUST_PER_SQUARE = 5; // rubans de vent par case
const GUST_POINTS = 12; // points le long d'un ruban
const SOCK_POLE = 1.5, SOCK_LENGTH = 0.85, SOCK_MOUTH = 0.13, SOCK_TIP = 0.06; // la manche à air, en cases
const SOCK_STRIPES = 5; // bandes rouges et blanches


class WeatherView {
  constructor(road, zones, colors) {
    this.road = road;
    this.colors = colors;
    this.group = new THREE.Group();
    this.items = [];
    this.grass = new THREE.Color(colors.grass);
    const fx = colors.effects;
    zones.forEach((zone, k) => {
      const start = zone.start, end = Math.min(zone.end, road.squares.length);
      if (start >= end) return;
      if (zone.effect === fx.rain) this.rain(start, end, k);
      else if (zone.effect === fx.tailwind || zone.effect === fx.headwind) {
        this.wind(start, end, k, zone.effect === fx.tailwind ? 1 : -1, colors.wind[zone.effect]);
      } else if (zone.effect === fx.crosswind) this.crosswind(start, end, k, colors.wind[zone.effect]);
      else if (zone.effect === fx.sunny) this.sun(start, end);
    });
  }

  // ---------------------------------------------------------------- pluie

  rain(start, end, k) {
    const road = this.road, length = end - start;
    const rain = new THREE.Color(this.colors.rain), sky = new THREE.Color(SKY);
    // route mouillée : un voile sombre et brillant posé sur les cases de la zone
    const wet = road.topGeometry(start, end, LINE_LIFT * 1.5);
    this.group.add(new THREE.Mesh(wet, new THREE.MeshPhongMaterial({
      color: WET_COLOR, transparent: true, opacity: 0.42, shininess: 90, specular: 0x9fb4cc, depthWrite: false,
      side: THREE.DoubleSide })));
    // le nuage : des boules grises aplaties le long de la zone, qui ondulent doucement
    const cloud = new THREE.Group();
    const puff = new THREE.SphereGeometry(0.55, 14, 10);
    const grey = new THREE.MeshLambertMaterial({ color: CLOUD_COLOR, transparent: true, opacity: 0.88 });
    const puffs = Math.max(3, Math.round(length * 1.4));
    for (let i = 0; i < puffs; i++) {
      const p = start + ((i + 0.5) / puffs) * length;
      const at = road.point(p, 0.5 + (rnd(i + k) - 0.5) * 1.6);
      const m = new THREE.Mesh(puff, grey);
      m.position.set(at.x, at.y + RAIN_TOP + 0.3 + rnd(i * 3 + k) * 0.4, at.z);
      m.scale.set(1.2 + rnd(i * 7) * 0.7, 0.5 + rnd(i * 5) * 0.2, 1.1 + rnd(i * 11) * 0.6);
      m.userData.base = m.position.y;
      m.userData.phase = rnd(i * 13) * 6;
      cloud.add(m);
    }
    this.group.add(cloud);
    // les gouttes : un trait chacune, pâle en haut (il se fond dans le ciel), net en bas
    const count = Math.round(RAIN_PER_SQUARE * length);
    const drops = Array.from({ length: count }, (_, d) => {
      const base = road.point(start + rnd(d + k * 1000) * length, -0.5 + rnd(d * 2 + 7) * 3);
      return { base, phase: rnd(d * 3 + 1), speed: 0.9 + rnd(d * 5) * 0.5 };
    });
    const positions = new Float32Array(count * 6), tint = new Float32Array(count * 6);
    const top = sky.clone().lerp(rain, 0.25);
    for (let i = 0; i < count; i++) {
      tint.set([top.r, top.g, top.b, rain.r, rain.g, rain.b], i * 6);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("color", new THREE.BufferAttribute(tint, 3));
    const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true,
                                                                          opacity: RAIN_OPACITY, depthWrite: false }));
    lines.frustumCulled = false;
    this.group.add(lines);
    // les éclaboussures : des anneaux qui s'élargissent et s'effacent dans la couleur de la route
    const splashes = Math.round(SPLASH_PER_SQUARE * length);
    const ring = new THREE.RingGeometry(0.025, 0.033, 16); // des éclaboussures fines
    ring.rotateX(-Math.PI / 2);
    const rings = new THREE.InstancedMesh(ring, new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.85,
                                                                              depthWrite: false }), splashes);
    rings.frustumCulled = false;
    const spots = Array.from({ length: splashes }, (_, d) => ({
      at: road.point(start + rnd(d * 17 + k) * length, -0.1 + rnd(d * 19) * 2.2), phase: rnd(d * 23) }));
    this.group.add(rings);
    const roadColor = new THREE.Color(WET_COLOR), color = new THREE.Color(), dummy = new THREE.Object3D();
    this.items.push((t) => {
      const pos = g.attributes.position;
      drops.forEach((d, i) => {
        const f = (t * d.speed * 1.4 + d.phase) % 1; // 0 = en haut, 1 = sur la route
        const h = RAIN_TOP * (1 - f), drift = h * RAIN_SLANT;
        pos.setXYZ(2 * i, d.base.x - drift - RAIN_STREAK * RAIN_SLANT, d.base.y + h + RAIN_STREAK, d.base.z + drift * 0.4);
        pos.setXYZ(2 * i + 1, d.base.x - drift, d.base.y + h, d.base.z + drift * 0.4);
      });
      pos.needsUpdate = true;
      spots.forEach((s, i) => {
        const age = (t * 1.7 + s.phase) % 1;
        dummy.position.set(s.at.x, s.at.y + LINE_LIFT * 3, s.at.z);
        dummy.scale.setScalar(0.4 + age * 2.6);
        dummy.updateMatrix();
        rings.setMatrixAt(i, dummy.matrix);
        rings.setColorAt(i, color.copy(rain).lerp(roadColor, age));
      });
      rings.instanceMatrix.needsUpdate = true;
      if (rings.instanceColor) rings.instanceColor.needsUpdate = true;
      cloud.children.forEach((m) => { m.position.y = m.userData.base + Math.sin(t * 0.6 + m.userData.phase) * 0.05; });
    });
  }

  // ---------------------------------------------------------------- vent

  // des rubans : chaque ruban va de `tail` à `head` (fonction de son âge 0..1) et ondule ; il naît et s'efface
  gusts(count, color, place) {
    const g = new THREE.BufferGeometry();
    const n = count * (GUST_POINTS - 1) * 2;
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true,
                                                                          opacity: 0.9, depthWrite: false }));
    lines.frustumCulled = false;
    this.group.add(lines);
    const wind = new THREE.Color(color), c = new THREE.Color(), a = new THREE.Vector3(), b = new THREE.Vector3();
    const streaks = Array.from({ length: count }, (_, d) => ({
      phase: rnd(d * 31), speed: 0.28 + rnd(d * 37) * 0.22, h: 0.12 + rnd(d * 41) * 0.75,
      lane: rnd(d * 43), wob: rnd(d * 47) * 6, len: 0.8 + rnd(d * 53) * 0.9 }));
    return (t) => {
      const pos = g.attributes.position, col = g.attributes.color;
      let v = 0;
      for (const s of streaks) {
        const life = (t * s.speed + s.phase) % 1, glow = Math.sin(Math.PI * life);
        for (let k = 0; k < GUST_POINTS - 1; k++) {
          for (const [u, out] of [[k / (GUST_POINTS - 1), a], [(k + 1) / (GUST_POINTS - 1), b]]) {
            place(s, life, u, t, out);
            out.y += s.h + Math.sin(u * 5 + t * 3 + s.wob) * 0.06;
          }
          pos.setXYZ(v, a.x, a.y, a.z);
          pos.setXYZ(v + 1, b.x, b.y, b.z);
          c.copy(this.grass).lerp(wind, glow * (k / (GUST_POINTS - 1)));
          col.setXYZ(v, c.r, c.g, c.b);
          c.copy(this.grass).lerp(wind, glow * ((k + 1) / (GUST_POINTS - 1)));
          col.setXYZ(v + 1, c.r, c.g, c.b);
          v += 2;
        }
      }
      pos.needsUpdate = true;
      col.needsUpdate = true;
    };
  }

  // une manche à air au bord de la route : un mât, un anneau, et la manche rayée rouge et blanc, gonflée,
  // tournée dans le sens du vent (`dir` : vecteur au sol) ; elle ondule et se balance un peu
  windsock(p, lane, dir) {
    const foot = this.road.point(p, lane);
    foot.y = this.road.terrain ? this.road.terrain.at(foot.x, foot.z) : foot.y; // le mât est planté dans l'herbe
    const metal = new THREE.MeshLambertMaterial({ color: "#e5e7eb" });
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.03, SOCK_POLE, 8), metal);
    pole.position.set(foot.x, foot.y + SOCK_POLE / 2, foot.z);
    pole.castShadow = true;
    this.group.add(pole);
    const sock = new THREE.Group(); // +x = le sens du vent, l'origine en haut du mât
    sock.position.set(foot.x, foot.y + SOCK_POLE, foot.z);
    sock.rotation.y = Math.atan2(-dir.z, dir.x);
    this.group.add(sock);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(SOCK_MOUTH, 0.012, 6, 20), metal); // l'anneau de l'entrée
    ring.rotation.y = Math.PI / 2;
    ring.position.x = 0.02;
    sock.add(ring);
    // la manche : un cône ouvert couché le long de +x, large à l'entrée, étroit au bout
    const cone = new THREE.CylinderGeometry(SOCK_TIP, SOCK_MOUTH, SOCK_LENGTH, 18, 10, true);
    cone.rotateZ(-Math.PI / 2); // le haut du cylindre (le bout étroit) part vers +x
    cone.translate(SOCK_LENGTH / 2 + 0.02, 0, 0);
    const rest = cone.attributes.position.array.slice();
    const tint = new Float32Array(cone.attributes.position.count * 3), c = new THREE.Color();
    for (let i = 0; i < cone.attributes.position.count; i++) {
      const f = (rest[3 * i] - 0.02) / SOCK_LENGTH; // 0 à l'entrée, 1 au bout
      c.set(Math.min(Math.floor(f * SOCK_STRIPES), SOCK_STRIPES - 1) % 2 ? "#f8fafc" : "#ef4444");
      tint.set([c.r, c.g, c.b], i * 3);
    }
    cone.setAttribute("color", new THREE.BufferAttribute(tint, 3));
    const mesh = new THREE.Mesh(cone, new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide }));
    mesh.castShadow = true;
    sock.add(mesh);
    return (t) => {
      const pos = cone.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        const x = rest[3 * i], y = rest[3 * i + 1], z = rest[3 * i + 2];
        const f = Math.max(0, (x - 0.02) / SOCK_LENGTH); // le bout bouge plus que l'entrée
        const sway = Math.sin(t * 2.3) * 0.05 * f * f + Math.sin(t * 7 + f * 6) * 0.015 * f;
        const droop = -0.06 * f * f + Math.sin(t * 3.1 + f * 4) * 0.02 * f;
        const breathe = 1 + Math.sin(t * 9 - f * 8) * 0.06 * f; // la toile se gonfle par vagues
        pos.setXYZ(i, x, y * breathe + droop, z * breathe + sway);
      }
      pos.needsUpdate = true;
      cone.computeVertexNormals();
      sock.rotation.z = Math.sin(t * 1.7) * 0.04; // tout l'ensemble se balance un peu au bout du mât
    };
  }

  wind(start, end, k, dir, color) {
    const road = this.road, length = end - start, lanes = road.squares[start].lanes;
    // le long de la route : de l'arrière vers l'avant (vent dans le dos) ou l'inverse (vent de face)
    const along = (s, life, u, t, out) => {
      const span = length + s.len;
      const head = dir > 0 ? start + life * span : end - life * span;
      const p = head - dir * s.len * (1 - u);
      const lane = -1 + s.lane * (lanes + 2) + Math.sin(u * 3 + t * 1.5 + s.wob) * 0.12;
      return road.point(Math.min(Math.max(p, start), end), lane, out);
    };
    const gusts = this.gusts(Math.round(GUST_PER_SQUARE * length), color, along);
    const a = road.point(start + 0.5, 0), b = road.point(start + 1.5, 0);
    const tangent = b.sub(a).setY(0).normalize().multiplyScalar(dir);
    const sock = this.windsock(start + 0.5, -1.4, tangent);
    this.items.push((t) => { gusts(t); sock(t); });
  }

  crosswind(start, end, k, color) {
    const road = this.road, length = end - start, lanes = road.squares[start].lanes;
    const far = lanes + 2.5, near = -2.5; // de la gauche de la route vers la droite
    const across = (s, life, u, t, out) => {
      const p = start + s.lane * length + Math.sin(u * 3 + t * 1.2 + s.wob) * 0.12;
      const head = far - life * (far - near + s.len);
      const lane = Math.min(Math.max(head + s.len * (1 - u), near), far);
      return road.point(Math.min(Math.max(p, start), end), lane, out);
    };
    const gusts = this.gusts(Math.round(GUST_PER_SQUARE * length), color, across);
    const mid = start + Math.min(0.5, length / 2);
    const left = road.point(mid, lanes), right = road.point(mid, 0);
    const sock = this.windsock(mid, lanes + 0.6, right.sub(left).setY(0).normalize());
    this.items.push((t) => { gusts(t); sock(t); });
  }

  // ---------------------------------------------------------------- soleil

  sun(start, end) {
    const at = this.road.point((start + end) / 2, 3.2);
    const sun = new THREE.Group();
    sun.position.set(at.x, at.y + 1.1, at.z);
    const material = new THREE.MeshBasicMaterial({ color: this.colors.sun });
    sun.add(new THREE.Mesh(new THREE.SphereGeometry(0.22, 16, 12), material));
    const rays = new THREE.Group();
    for (let r = 0; r < 8; r++) {
      const ray = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.035, 0.035), material);
      const a = (r * Math.PI) / 4;
      ray.position.set(Math.cos(a) * 0.36, Math.sin(a) * 0.36, 0);
      ray.rotation.z = a;
      rays.add(ray);
    }
    sun.add(rays);
    this.group.add(sun);
    this.items.push((t, camera) => {
      sun.quaternion.copy(camera.quaternion); // toujours face à la caméra
      rays.rotation.z = t * 0.8;
    });
  }

  update(t, camera) {
    for (const item of this.items) item(t, camera);
  }
}

// ------------------------------------------------------------------ la vue

export function createBoard3D(container, colors) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  container.append(renderer.domElement);
  const labels = new CSS2DRenderer();
  labels.domElement.className = "board3d-labels";
  container.append(labels.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(SKY);
  const camera = new THREE.PerspectiveCamera(40, 2, 0.05, 400);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.maxPolarAngle = Math.PI * 0.47; // jamais sous le sol
  controls.minDistance = 1.5;
  controls.maxDistance = 120;
  controls.screenSpacePanning = false; // on se déplace sur le sol, pas vers le ciel
  // clic gauche = déplacer la caméra, clic molette (ou droit) = changer d'angle, molette = zoom ;
  // au doigt : un doigt déplace, deux doigts zooment et tournent
  controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.ROTATE, RIGHT: THREE.MOUSE.ROTATE };
  controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
  // le clic molette ne lance pas le défilement automatique du navigateur, et le clic droit pas son menu
  renderer.domElement.addEventListener("mousedown", (e) => { if (e.button === 1) e.preventDefault(); });
  renderer.domElement.addEventListener("contextmenu", (e) => e.preventDefault());

  scene.add(new THREE.HemisphereLight(0xdfe9ff, 0x2a4a35, 1.6));
  const sunLight = new THREE.DirectionalLight(0xffffff, 1.8);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  scene.add(sunLight, sunLight.target);

  let road = null, roadGroup = null, ground = null, weather = null, weatherKey = "", sceneId = null;
  const riders = new Map();
  let move = null; // changement de cadrage en cours : {from, to, start}
  let follow = ""; // "" (tout le parcours), "peloton" ou "tete"
  let lastFollowKey = "";
  let handled = false;
  let lastDraw = 0; // le joueur a bougé la caméra lui-même (souris, ＋/－, ⟲ ⟳)

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    labels.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    if (road && !follow && !handled) frameView("", [], true); // la vue d'ensemble suit la taille du cadre
  }
  new ResizeObserver(resize).observe(container);

  // retire un groupe de la scène, et de la page ses étiquettes (CSS2DRenderer ne les enlève pas tout seul)
  function drop(group) {
    scene.remove(group);
    group.traverse((o) => { if (o.isCSS2DObject) o.element.remove(); });
  }

  function setScene(data, id) {
    if (id === sceneId) return;
    sceneId = id;
    if (roadGroup) drop(roadGroup);
    if (ground) scene.remove(ground);
    for (const r of riders.values()) drop(r.group);
    riders.clear();
    if (weather) scene.remove(weather.group);
    weather = null; weatherKey = "";
    road = new Road(data);
    roadGroup = road.build();
    scene.add(roadGroup);
    // numéros de case (tous les 5) et l'arrivée
    for (let s = 0; s < data.n; s += NUMBER_EVERY) addTag(String(s), s, -1.1, "num3d");
    addTag("ARRIVÉE", data.n, 1, "finish3d", 0.7);
    addTag("DÉPART", data.start, 1, "finish3d", 0.7);
    const box = road.bounds(), size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
    const plain = grassTexture().clone(); // la plaine, au-delà du talus : la même pelouse
    plain.repeat.set((size.x + 120) / GRASS_TILE, (size.z + 120) / GRASS_TILE);
    plain.needsUpdate = true;
    ground = new THREE.Mesh(new THREE.PlaneGeometry(size.x + 120, size.z + 120),
                            new THREE.MeshLambertMaterial({ color: TERRAIN_GREEN, map: plain }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(center.x, road.terrain.low - 0.01, center.z);
    ground.receiveShadow = true;
    scene.add(ground);
    const reach = Math.max(size.x, size.z) / 2 + 4;
    sunLight.position.set(center.x - reach * 0.6, reach * 1.6, center.z + reach * 0.8);
    sunLight.target.position.copy(center);
    Object.assign(sunLight.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, far: reach * 5 });
    sunLight.shadow.camera.updateProjectionMatrix();
    scene.fog = new THREE.Fog(SKY, reach * 4, reach * 9);
    lastFollowKey = "";
    handled = false;
    frameView(follow, [], true);
  }

  function addTag(text, s, lane, cls, height = 0.05) {
    const div = document.createElement("div");
    div.className = cls;
    div.textContent = text;
    const tag = new CSS2DObject(div);
    road.point(s, lane, tag.position);
    tag.position.y += height;
    roadGroup.add(tag);
  }

  // le cadrage : tout le parcours, ou un groupe suivi ; la caméra garde l'angle choisi par le joueur
  // la boîte qui contient tous les coureurs (un peu de marge autour, et leur hauteur)
  // vue course : tous les coureurs, et la route sur les 5 prochaines cases devant le premier
  function ridersBox(list) {
    const box = new THREE.Box3(), at = new THREE.Vector3();
    const add = (p, lane) => {
      road.point(p, lane, at);
      box.expandByPoint(at);
      box.expandByPoint(at.clone().setY(at.y + 0.8));
    };
    for (const r of list) add(r.p, r.lane);
    const front = Math.max(...list.map((r) => r.p)), last = road.squares.length - 1;
    for (let p = Math.ceil(front); p <= Math.min(front + RACE_VIEW_AHEAD, last); p++) {
      add(p, 0);
      add(p, road.squares[Math.min(p, last)].lanes - 1);
    }
    return box.expandByScalar(0.9);
  }

  function target(which, list) {
    if (!which || !list.length) return null;
    if (which === "course") return ridersBox(list).getCenter(new THREE.Vector3());
    const sorted = list.slice().sort((a, b) => b.p - a.p);
    const groups = [];
    for (const r of sorted) {
      const g = groups[groups.length - 1];
      if (g && Math.round(g[g.length - 1].p) - Math.round(r.p) <= 1) g.push(r); else groups.push([r]);
    }
    const group = which === "tete" ? groups[0] : groups.reduce((best, g) => (g.length > best.length ? g : best));
    const mid = (group[0].p + group[group.length - 1].p) / 2;
    return road.point(mid, 0.5);
  }

  function frameView(which, list, instant = false) {
    if (!road) return;
    follow = which || "";
    const box = road.bounds();
    const offset = camera.position.clone().sub(controls.target);
    let center, distance;
    const followed = target(follow, list);
    if (followed) {
      center = followed;
      distance = FOLLOW_DISTANCE;
    } else {
      center = box.getCenter(new THREE.Vector3());
    }
    if (instant || offset.lengthSq() < 1e-6) offset.set(0, 1.1, 1); // de face, vu d'en haut à 48°
    if (!followed) distance = fitDistance(box, center, offset);
    // vue course : tous dans le cadre avec la route devant, au plus près (jamais plus près qu'un zoom de suivi)
    else if (follow === "course") distance = Math.max(fitDistance(ridersBox(list), center, offset), FOLLOW_DISTANCE * 0.8);
    offset.setLength(distance);
    const to = { target: center, position: center.clone().add(offset) };
    if (instant) {
      controls.target.copy(to.target);
      camera.position.copy(to.position);
      move = null;
    } else {
      move = { from: { target: controls.target.clone(), position: camera.position.clone() }, to,
               start: performance.now() };
    }
  }

  // tout le parcours dans le cadre : on place une caméra d'essai et on ajuste sa distance jusqu'à ce que les
  // coins du parcours touchent presque les bords de l'image
  function fitDistance(box, center, direction) {
    const probe = camera.clone(), corner = new THREE.Vector3(), dir = direction.clone().normalize();
    let distance = box.getSize(new THREE.Vector3()).length();
    for (let i = 0; i < 5; i++) {
      probe.position.copy(center).addScaledVector(dir, distance);
      probe.lookAt(center);
      probe.updateMatrixWorld();
      let extent = 0;
      for (let k = 0; k < 8; k++) {
        corner.set(k & 1 ? box.max.x : box.min.x, k & 2 ? box.max.y : box.min.y, k & 4 ? box.max.z : box.min.z);
        corner.project(probe);
        extent = Math.max(extent, Math.abs(corner.x), Math.abs(corner.y));
      }
      distance *= extent / FIT_MARGIN;
    }
    return Math.max(distance, 4);
  }

  function zoom(factor) {
    move = null;
    handled = true;
    const offset = camera.position.clone().sub(controls.target).multiplyScalar(1 / factor);
    const length = Math.min(Math.max(offset.length(), controls.minDistance), controls.maxDistance);
    camera.position.copy(controls.target).add(offset.setLength(length));
  }

  function rotate(degrees) {
    move = null;
    handled = true;
    const offset = camera.position.clone().sub(controls.target);
    offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), (degrees * Math.PI) / 180);
    camera.position.copy(controls.target).add(offset);
  }

  // une image : coureurs à leur place (ou en route pendant une animation), météo, cadrage
  // `list` : les coureurs à dessiner (en route pendant une animation) ; `rest` : leurs places au repos, que suit
  // la caméra d'un zoom peloton ou tête de course ; `follow` : la caméra choisie ("", "peloton" ou "tete")
  function draw({ list, rest, follow: which = follow, current, zones, t, animate }) {
    if (!road) return;
    if (which !== follow) { // autre caméra choisie (même pendant le podium) : on recadre
      lastFollowKey = "";
      if (!which) frameView("", rest); else follow = which;
    }
    const now = performance.now(), dt = lastDraw ? Math.min((now - lastDraw) / 1000, 0.1) : 0;
    lastDraw = now;
    // aspiration : celui qui protège un coureur aspiré est le plus proche devant lui
    const protectors = new Set();
    for (const d of list.filter((r) => r.draft)) {
      const ahead = list.filter((r) => !r.draft && r.p > d.p).sort((x, y) => x.p - y.p)[0];
      if (ahead) protectors.add(ahead.name);
    }
    const seen = new Set();
    for (const r of list) {
      let view = riders.get(r.name);
      if (!view) {
        view = new RiderView(r, colors);
        riders.set(r.name, view);
        scene.add(view.group);
      }
      view.place(road, r.p, r.lane, { current: r.name === current, crashed: r.crashed, draft: r.draft, tired: r.tired,
                                      wake: protectors.has(r.name), t, dt });
      seen.add(r.name);
    }
    for (const [name, view] of riders) {
      if (!seen.has(name)) { drop(view.group); riders.delete(name); }
    }
    const key = JSON.stringify(zones);
    if (key !== weatherKey) {
      if (weather) scene.remove(weather.group);
      weather = zones.length ? new WeatherView(road, zones, colors) : null;
      if (weather) scene.add(weather.group);
      weatherKey = key;
    }
    if (weather) weather.update(animate ? t : 0, camera);
    // suivi d'un groupe : quand il avance (nouveau tour), la caméra le suit
    const followKey = follow + "|" + rest.map((r) => r.p).join(",");
    if (follow && followKey !== lastFollowKey) {
      frameView(follow, rest);
      lastFollowKey = followKey;
    }
    if (move) {
      const f = Math.min((performance.now() - move.start) / 1000 / MOVE_TIME, 1);
      const e = f * f * (3 - 2 * f);
      controls.target.lerpVectors(move.from.target, move.to.target, e);
      camera.position.lerpVectors(move.from.position, move.to.position, e);
      if (f >= 1) move = null;
    }
    controls.update();
    renderer.render(scene, camera);
    labels.render(scene, camera);
  }

  controls.addEventListener("start", () => { move = null; handled = true; });

  return {
    get sceneId() { return sceneId; },
    setScene, draw, zoom, rotate, resize,
    frame: (which, list) => { lastFollowKey = ""; handled = false; frameView(which, list); },
  };
}
