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
const RIDER_SCALE = 1.5; // les coureurs un peu plus grands que nature : on les voit de loin

const lerp = (a, b, f) => a + (b - a) * f;
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
        if (s < n) { // les côtés jusqu'au sol (pas après l'arrivée : la route peut y passer au-dessus d'une autre)
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

const parts = {
  wheel: new THREE.TorusGeometry(0.085, 0.014, 6, 18),
  frame: new THREE.BoxGeometry(0.24, 0.02, 0.02),
  body: new THREE.CapsuleGeometry(0.05, 0.13, 4, 8),
  leg: new THREE.CapsuleGeometry(0.022, 0.12, 3, 6),
  head: new THREE.SphereGeometry(0.045, 12, 10),
  shadow: new THREE.CircleGeometry(0.16, 20),
  ring: new THREE.RingGeometry(0.2, 0.25, 28),
};

function riderModel(fill) {
  const team = new THREE.MeshLambertMaterial({ color: fill });
  const dark = new THREE.MeshLambertMaterial({ color: WHEEL });
  const metal = new THREE.MeshLambertMaterial({ color: FRAME });
  const skin = new THREE.MeshLambertMaterial({ color: SKIN });
  const bike = new THREE.Group(); // tourné vers +x (le sens de la course)
  for (const x of [-0.12, 0.12]) {
    const w = new THREE.Mesh(parts.wheel, dark);
    w.position.set(x, 0.1, 0);
    bike.add(w);
  }
  const frame = new THREE.Mesh(parts.frame, metal);
  frame.position.set(0, 0.17, 0);
  bike.add(frame);
  const body = new THREE.Mesh(parts.body, team); // penché sur le guidon
  body.position.set(0.0, 0.29, 0);
  body.rotation.z = -1.0;
  bike.add(body);
  for (const z of [-0.035, 0.035]) {
    const leg = new THREE.Mesh(parts.leg, team);
    leg.position.set(-0.04, 0.2, z);
    leg.rotation.z = 0.35;
    bike.add(leg);
  }
  const head = new THREE.Mesh(parts.head, skin);
  head.position.set(0.1, 0.36, 0);
  bike.add(head);
  bike.traverse((o) => { o.castShadow = true; });
  return bike;
}

class RiderView {
  constructor(r, colors) {
    this.group = new THREE.Group();
    this.bike = riderModel(colors.fill[r.team]);
    this.bike.scale.setScalar(RIDER_SCALE);
    this.group.add(this.bike);
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
  }

  place(road, p, lane, current, crashed) {
    road.point(p, lane, this.group.position);
    const a = road.point(p - 0.25, lane), b = road.point(p + 0.25, lane);
    this.group.rotation.y = Math.atan2(-(b.z - a.z), b.x - a.x);
    this.bike.rotation.x = crashed ? Math.PI / 2 : 0; // à terre : couché sur le côté
    this.bike.position.y = crashed ? 0.05 : 0;
    this.ring.visible = current || crashed;
    this.ring.material.color.set(crashed ? CRASH_MARK : CURRENT_RING);
    this.tag.classList.toggle("crashed", crashed);
  }
}

// ------------------------------------------------------------------ la météo

class WeatherView {
  constructor(road, zones, colors) {
    this.road = road;
    this.colors = colors;
    this.group = new THREE.Group();
    this.items = [];
    const fx = colors.effects;
    zones.forEach((zone, k) => {
      const start = zone.start, end = Math.min(zone.end, road.squares.length);
      if (start >= end) return;
      if (zone.effect === fx.rain) this.rain(start, end, k);
      else if (zone.effect === fx.tailwind || zone.effect === fx.headwind) {
        this.wind(start, end, zone.effect === fx.tailwind ? 1 : -1, colors.wind[zone.effect]);
      } else if (zone.effect === fx.crosswind) this.crosswind(start, end, colors.wind[zone.effect]);
      else if (zone.effect === fx.sunny) this.sun(start, end);
    });
  }

  lines(count, color) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(new Float32Array(count * 6), 3));
    const seg = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.85 }));
    seg.frustumCulled = false;
    this.group.add(seg);
    return g.attributes.position;
  }

  rain(start, end, k) {
    const count = Math.round(14 * (end - start));
    const drops = Array.from({ length: count }, (_, d) => ({
      p: start + ((d * 0.381 + k * 0.37) % 1) * (end - start), lane: -0.4 + ((d * 0.727) % 1) * 2.8,
      phase: (d * 0.618) % 1,
    }));
    const attr = this.lines(count, this.colors.rain);
    const at = new THREE.Vector3();
    this.items.push((t) => {
      drops.forEach((d, i) => {
        this.road.point(d.p, d.lane, at);
        const y = at.y + 1.6 * (1 - ((t * 0.9 + d.phase) % 1));
        attr.setXYZ(2 * i, at.x, y + 0.12, at.z);
        attr.setXYZ(2 * i + 1, at.x + 0.02, y, at.z);
      });
      attr.needsUpdate = true;
    });
  }

  wind(start, end, dir, color) {
    const count = Math.round(4 * (end - start));
    const streaks = Array.from({ length: count }, (_, d) => ({
      lane: -0.6 + ((d * 0.53) % 1) * 3, phase: (d * 0.29) % 1, h: 0.15 + ((d * 0.71) % 1) * 0.5 }));
    const attr = this.lines(count, color);
    const a = new THREE.Vector3(), b = new THREE.Vector3();
    this.items.push((t) => {
      streaks.forEach((s, i) => {
        const f = (t * 0.45 + s.phase) % 1;
        const head = start + (dir > 0 ? f : 1 - f) * (end - start);
        const tail = Math.min(Math.max(head - 0.8 * dir, start), end);
        this.road.point(tail, s.lane, a);
        this.road.point(head, s.lane, b);
        attr.setXYZ(2 * i, a.x, a.y + s.h, a.z);
        attr.setXYZ(2 * i + 1, b.x, b.y + s.h, b.z);
      });
      attr.needsUpdate = true;
    });
  }

  crosswind(start, end, color) {
    const count = Math.round(3 * (end - start));
    const streaks = Array.from({ length: count }, (_, d) => ({
      p: start + ((d + 0.5) / count) * (end - start), phase: (d * 0.41) % 1, h: 0.1 + ((d * 0.37) % 1) * 0.5 }));
    const attr = this.lines(count, color);
    const a = new THREE.Vector3(), b = new THREE.Vector3();
    this.items.push((t) => {
      streaks.forEach((s, i) => {
        const lane = 3 - ((t * 0.5 + s.phase) % 1) * 4.5; // de la gauche vers la droite de la route
        this.road.point(s.p, lane + 0.7, a);
        this.road.point(s.p, lane, b);
        attr.setXYZ(2 * i, a.x, a.y + s.h, a.z);
        attr.setXYZ(2 * i + 1, b.x, b.y + s.h, b.z);
      });
      attr.needsUpdate = true;
    });
  }

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

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    renderer.domElement.style.width = "100%";
    renderer.domElement.style.height = "100%";
    labels.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);

  function setScene(data, id) {
    if (id === sceneId) return;
    sceneId = id;
    if (roadGroup) scene.remove(roadGroup);
    if (ground) scene.remove(ground);
    for (const r of riders.values()) scene.remove(r.group);
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
  function target(which, list) {
    if (!which || !list.length) return null;
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
      const size = box.getSize(new THREE.Vector3());
      const fit = Math.max(size.x / camera.aspect, size.z) / 2 / Math.tan((camera.fov * Math.PI) / 360);
      distance = Math.max(fit * 1.05, 6);
    }
    if (instant || offset.lengthSq() < 1e-6) offset.set(0, 1.1, 1); // de face, vu d'en haut à 48°
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

  function zoom(factor) {
    move = null;
    const offset = camera.position.clone().sub(controls.target).multiplyScalar(1 / factor);
    const length = Math.min(Math.max(offset.length(), controls.minDistance), controls.maxDistance);
    camera.position.copy(controls.target).add(offset.setLength(length));
  }

  function rotate(degrees) {
    move = null;
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
    const seen = new Set();
    for (const r of list) {
      let view = riders.get(r.name);
      if (!view) {
        view = new RiderView(r, colors);
        riders.set(r.name, view);
        scene.add(view.group);
      }
      view.place(road, r.p, r.lane, r.name === current, r.crashed);
      seen.add(r.name);
    }
    for (const [name, view] of riders) {
      if (!seen.has(name)) { scene.remove(view.group); riders.delete(name); }
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

  controls.addEventListener("start", () => { move = null; });

  return {
    get sceneId() { return sceneId; },
    setScene, draw, zoom, rotate, resize,
    frame: (which, list) => { lastFollowKey = ""; frameView(which, list); },
  };
}
