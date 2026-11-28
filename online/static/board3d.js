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
const GROUND = "#1f5a3b";
const ROAD_EDGE = "#e2e8f0", LANE_LINE = "#64748b", SQUARE_LINE = "#2a3444";
const CURRENT_RING = "#fde047", CRASH_MARK = "#ff4d4f";
const WHEEL = "#1e293b", FRAME = "#cbd5e1", SKIN = "#f1c27d";
const WALL_SHADE = 0.55; // les côtés de la route, plus sombres que le dessus
const LINE_LIFT = 0.006; // les traits flottent juste au-dessus de la route (pas de scintillement)
const START_DEPTH = 0.14; // largeur de la ligne de départ blanche, en fraction de case
const NUMBER_EVERY = 5; // numéro de case tous les 5 (et à l'arrivée)
const FOLLOW_DISTANCE = 7; // distance de la caméra au groupe suivi, en cases
const MOVE_TIME = 0.6; // durée d'un changement de cadrage, en secondes
const FIT_MARGIN = 0.92; // vue d'ensemble : le parcours occupe 92 % du cadre
const RIDER_SCALE = 1.5; // les coureurs un peu plus grands que nature : on les voit de loin
const DUST_BITS = 40;
const TIRED = "#ef4444"; // phase de fatigue : le maillot vire au rouge, un halo rouge pulse autour du coureur // grains du nuage de poussière d'une chute

const lerp = (a, b, f) => a + (b - a) * f;
const rnd = (seed) => { const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const lerp2 = (p, q, f) => [lerp(p[0], q[0], f), lerp(p[1], q[1], f)];

function shade(hex, f) {
  return new THREE.Color(hex).multiplyScalar(f);
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
    const h = last === 0 ? this.mid[0] : lerp(this.mid[i], this.mid[i + 1], f);
    return out.set(x, h * this.lift, -y);
  }

  // hauteur de la route au point `k` (0 à m − 1) d'un bord de la case s
  heightAt(s, k, m) {
    return lerp(this.z[s], this.z[s + 1], m > 1 ? k / (m - 1) : 0) * this.lift;
  }

  build() {
    const group = new THREE.Group();
    const top = [], topColors = [], walls = [], wallColors = [], edges = [], lanes = [], cross = [];
    const ground = this.data.base * this.lift;
    const v = (x, y, h) => [x, h, -y];
    const n = this.data.n;
    this.squares.forEach((sq, s) => {
      const { left, right } = sq, m = left.length;
      const fill = new THREE.Color(sq.fill), wall = shade(sq.fill, WALL_SHADE);
      for (let k = 0; k < m - 1; k++) {
        const h0 = this.heightAt(s, k, m), h1 = this.heightAt(s, k + 1, m);
        const l0 = v(...left[k], h0), r0 = v(...right[k], h0), l1 = v(...left[k + 1], h1), r1 = v(...right[k + 1], h1);
        top.push(...r0, ...l0, ...l1, ...r0, ...l1, ...r1);
        for (let t = 0; t < 6; t++) topColors.push(fill.r, fill.g, fill.b);
        { // les côtés jusqu'au sol (scene.py coupe la route d'après l'arrivée avant qu'elle passe sur une autre)
          for (const [p0, ha, p1, hb] of [[left[k], h0, left[k + 1], h1], [right[k], h0, right[k + 1], h1]]) {
            const a = v(...p0, ha), b = v(...p1, hb), a0 = v(...p0, ground), b0 = v(...p1, ground);
            walls.push(...a, ...a0, ...b0, ...a, ...b0, ...b);
            for (let t = 0; t < 6; t++) wallColors.push(wall.r, wall.g, wall.b);
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
      const { left, right } = this.squares[s], m = left.length;
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
const POSES = { // hanche et épaules, dans le repère du vélo
  rouleur: { hip: [-0.035, 0.245], shoulder: [0.072, 0.34] },
  sprinteur: { hip: [-0.03, 0.235], shoulder: [0.088, 0.3] },
  danseuse: { hip: [0.015, 0.29], shoulder: [0.105, 0.35] },
  descente: { hip: [-0.025, 0.245], shoulder: [0.098, 0.268] },
};
const SHORTS = "#111827";
const DUST = "#eadcb8";
const Y_AXIS = new THREE.Vector3(0, 1, 0), Z_AXIS = new THREE.Vector3(0, 0, 1);

const parts = {
  wheel: new THREE.TorusGeometry(WHEEL_R, 0.012, 6, 22),
  spoke: new THREE.BoxGeometry(WHEEL_R * 2, 0.006, 0.006),
  tube: new THREE.CylinderGeometry(0.009, 0.009, 1, 6),
  limb: new THREE.CylinderGeometry(0.019, 0.016, 1, 8),
  joint: new THREE.SphereGeometry(0.02, 8, 6),
  torso: new THREE.CapsuleGeometry(0.05, 0.12, 4, 10),
  band: new THREE.TorusGeometry(0.05, 0.013, 6, 18),
  head: new THREE.SphereGeometry(0.04, 14, 10),
  helmet: new THREE.SphereGeometry(0.048, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2),
  glasses: new THREE.BoxGeometry(0.018, 0.014, 0.07),
  crank: new THREE.BoxGeometry(CRANK, 0.008, 0.008),
  pedal: new THREE.BoxGeometry(0.03, 0.008, 0.03),
  shadow: new THREE.CircleGeometry(0.16, 20),
  ring: new THREE.RingGeometry(0.2, 0.25, 28),
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
    this.pose = { hip: [...this.base.hip], shoulder: [...this.base.shoulder] };
    const lambert = (color) => new THREE.MeshLambertMaterial({ color });
    const team = lambert(fill), skin = lambert(SKIN), dark = lambert(WHEEL), metal = lambert(FRAME);
    // maillot à deux couleurs : bande claire pour le rouleur, foncée pour le sprinteur
    const band = lambert(this.sprinter ? fill.clone().multiplyScalar(0.5) : fill.clone().lerp(new THREE.Color("#ffffff"), 0.6));
    const shorts = lambert(SHORTS);
    this.teamMat = team;
    this.teamColor = fill.clone();

    this.group = new THREE.Group(); // à la place du coureur sur la route, tourné vers l'arrivée
    this.model = new THREE.Group(); // à l'échelle des coureurs
    this.model.scale.setScalar(RIDER_SCALE);
    this.group.add(this.model);
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

    // le coureur : buste, bande du maillot, tête, casque, lunettes, bras, jambes
    this.torso = new THREE.Mesh(parts.torso, team);
    this.torso.userData.width = this.sprinter ? 1.18 : 1;
    this.band = new THREE.Mesh(parts.band, band);
    this.head = new THREE.Group();
    this.head.add(new THREE.Mesh(parts.head, skin));
    const helmet = new THREE.Mesh(parts.helmet, team);
    helmet.position.y = 0.004;
    helmet.scale.set(1.15, 0.9, 0.95);
    const glasses = new THREE.Mesh(parts.glasses, dark);
    glasses.position.set(0.036, 0.004, 0);
    this.head.add(helmet, glasses);
    this.body.add(this.torso, this.band, this.head);
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
    this.group.add(shadow);
    this.ring = new THREE.Mesh(parts.ring, new THREE.MeshBasicMaterial({ color: CURRENT_RING, side: THREE.DoubleSide }));
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.position.y = LINE_LIFT * 3;
    this.group.add(this.ring);
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
    this.group.add(this.pulse);

    this.crank = rnd(r.name.length + r.team) * Math.PI * 2;
    this.wheel = 0;
    this.last = null;
  }

  // une image : place, posture, pédalage ; `draft` : aspiré en ce moment ; `wake` : il protège quelqu'un
  place(road, p, lane, { current, crashed, draft, wake, tired, t, dt }) {
    road.point(p, lane, this.group.position);
    const a = road.point(p - 0.25, lane), b = road.point(p + 0.25, lane);
    this.group.rotation.y = Math.atan2(-(b.z - a.z), b.x - a.x);
    const moved = this.last ? this.last.distanceTo(this.group.position) : 0;
    this.last = (this.last || new THREE.Vector3()).copy(this.group.position);
    const moving = moved > 1e-4 && !crashed;
    const square = road.squares[Math.min(Math.max(Math.round(p), 0), road.squares.length - 1)];
    // en danseuse dans les montées, même à l'arrêt (on voit qui grimpe) ; recroquevillé en descente quand il roule
    const target = square.kind === "A" ? POSES.danseuse : moving && square.kind === "D" ? POSES.descente : this.base;
    const k = Math.min(1, dt * 6); // la posture change en douceur
    for (const key of ["hip", "shoulder"]) {
      this.pose[key][0] = lerp(this.pose[key][0], target[key][0], k);
      this.pose[key][1] = lerp(this.pose[key][1], target[key][1], k);
    }
    const travel = moved / RIDER_SCALE;
    if (moving && square.kind !== "D") this.crank -= travel * CADENCE; // en descente : roue libre
    if (moving) this.wheel -= travel / WHEEL_R;
    this.wheels.forEach((w) => { w.rotation.z = this.wheel; });
    this.crankSet.rotation.z = this.crank;
    // en danseuse, le vélo se balance d'un côté à l'autre au rythme des pédales
    const rock = moving && square.kind === "A" ? Math.sin(this.crank) * 0.12 : 0;
    this.pose3d(rock);

    this.fall(crashed, t);
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
    const chest = v(...hip).lerp(v(...shoulder), 0.62);
    this.band.position.copy(chest);
    this.band.quaternion.setFromUnitVectors(Z_AXIS, v(shoulder[0] - hip[0], shoulder[1] - hip[1]).normalize());
    this.band.scale.setScalar(this.torso.userData.width);
    const neck = v(shoulder[0] - hip[0], shoulder[1] - hip[1]).normalize();
    this.head.position.set(shoulder[0] + neck.x * 0.05 + 0.012, shoulder[1] + neck.y * 0.05 + 0.02, 0);
    this.head.rotation.z = -0.25;
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
// filent dans le sens du vent, des feuilles et de la poussière emportées, et une manche à air au bord de la
// route, tourné dans le sens du vent (dans le dos, de face ou de travers).

const RAIN_PER_SQUARE = 55; // gouttes par case
const RAIN_TOP = 2.6; // hauteur d'où tombent les gouttes, en cases
const RAIN_STREAK = 0.22; // longueur d'une goutte
const RAIN_SLANT = 0.12; // biais des gouttes (un peu de vent)
const SPLASH_PER_SQUARE = 14;
const WET_COLOR = "#1d3b5c";
const CLOUD_COLOR = "#5d6b80";
const GUST_PER_SQUARE = 5; // rubans de vent par case
const GUST_POINTS = 12; // points le long d'un ruban
const LEAF_PER_SQUARE = 4;
const SOCK_POLE = 1.5, SOCK_LENGTH = 0.85, SOCK_MOUTH = 0.13, SOCK_TIP = 0.06; // la manche à air, en cases
const SOCK_STRIPES = 5; // bandes rouges et blanches
const LEAF_COLORS = ["#c9a227", "#a16207", "#84cc16", "#d6c7a1"];


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
      m.position.set(at.x, at.y + RAIN_TOP + 0.25 + rnd(i * 3 + k) * 0.25, at.z);
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
                                                                          opacity: 0.8, depthWrite: false }));
    lines.frustumCulled = false;
    this.group.add(lines);
    // les éclaboussures : des anneaux qui s'élargissent et s'effacent dans la couleur de la route
    const splashes = Math.round(SPLASH_PER_SQUARE * length);
    const ring = new THREE.RingGeometry(0.03, 0.045, 16);
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

  // des feuilles et de la poussière emportées, qui tourbillonnent un peu
  leaves(count, place) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
    const tint = new Float32Array(count * 3), c = new THREE.Color();
    for (let i = 0; i < count; i++) {
      c.set(LEAF_COLORS[i % LEAF_COLORS.length]);
      tint.set([c.r, c.g, c.b], i * 3);
    }
    g.setAttribute("color", new THREE.BufferAttribute(tint, 3));
    const points = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.11, vertexColors: true }));
    points.frustumCulled = false;
    this.group.add(points);
    const bits = Array.from({ length: count }, (_, d) => ({
      phase: rnd(d * 59), speed: 0.18 + rnd(d * 61) * 0.18, lane: rnd(d * 67), wob: rnd(d * 71) * 6 }));
    const at = new THREE.Vector3();
    return (t) => {
      const pos = g.attributes.position;
      bits.forEach((s, i) => {
        const life = (t * s.speed + s.phase) % 1;
        place(s, life, 0.5, t, at);
        at.y += 0.05 + Math.abs(Math.sin(t * 4 + s.wob)) * 0.35 * Math.sin(Math.PI * life);
        pos.setXYZ(i, at.x, at.y, at.z);
      });
      pos.needsUpdate = true;
    };
  }

  // une manche à air au bord de la route : un mât, un anneau, et la manche rayée rouge et blanc, gonflée,
  // tournée dans le sens du vent (`dir` : vecteur au sol) ; elle ondule et se balance un peu
  windsock(p, lane, dir) {
    const foot = this.road.point(p, lane);
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
    const leafAlong = (s, life, u, t, out) => {
      const p = dir > 0 ? start + life * length : end - life * length;
      return road.point(p, -1 + s.lane * (lanes + 2) + Math.sin(t * 2 + s.wob) * 0.3, out);
    };
    const leaves = this.leaves(Math.round(LEAF_PER_SQUARE * length), leafAlong);
    const a = road.point(start + 0.5, 0), b = road.point(start + 1.5, 0);
    const tangent = b.sub(a).setY(0).normalize().multiplyScalar(dir);
    const sock = this.windsock(start + 0.5, -1.4, tangent);
    this.items.push((t) => { gusts(t); leaves(t); sock(t); });
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
    const leafAcross = (s, life, u, t, out) => road.point(start + s.lane * length + Math.sin(t * 2 + s.wob) * 0.2,
                                                          far - life * (far - near), out);
    const leaves = this.leaves(Math.round(LEAF_PER_SQUARE * length), leafAcross);
    const mid = start + Math.min(0.5, length / 2);
    const left = road.point(mid, lanes), right = road.point(mid, 0);
    const sock = this.windsock(mid, lanes + 0.6, right.sub(left).setY(0).normalize());
    this.items.push((t) => { gusts(t); leaves(t); sock(t); });
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
    ground = new THREE.Mesh(new THREE.PlaneGeometry(size.x + 60, size.z + 60),
                            new THREE.MeshLambertMaterial({ color: GROUND }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(center.x, data.base * data.lift - 0.002, center.z);
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
  function ridersBox(list) {
    const box = new THREE.Box3(), at = new THREE.Vector3();
    for (const r of list) {
      road.point(r.p, r.lane, at);
      box.expandByPoint(at);
      box.expandByPoint(at.clone().setY(at.y + 0.8));
    }
    return box.expandByScalar(0.9);
  }

  function target(which, list) {
    if (!which || !list.length) return null;
    if (which === "coureurs") return ridersBox(list).getCenter(new THREE.Vector3());
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
    // vue coureurs : tous dans le cadre, au plus près (jamais plus près qu'un zoom de suivi)
    else if (follow === "coureurs") distance = Math.max(fitDistance(ridersBox(list), center, offset), FOLLOW_DISTANCE * 0.8);
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
