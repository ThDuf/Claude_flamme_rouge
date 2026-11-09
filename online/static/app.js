"use strict";
// Flamme Rouge en ligne : accueil, salon, course. Le serveur envoie l'état ; on le redessine.

const TEAM_FILL = ["#ff4d4f", "#3b82f6", "#22c55e", "#facc15", "#f472b6", "#f1f5f9"];
const TEAM_TEXT = ["#ff7b7d", "#6aa7ff", "#4ade80", "#fde047", "#f9a8d4", "#f8fafc"];
const LABEL_ON_FILL = ["#fff", "#fff", "#000", "#000", "#000", "#000"];
const POLL_MS = 600;
const FONT = '"Segoe UI", system-ui, sans-serif';

const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "style") node.style.cssText = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(child));
  return node;
};

// ------------------------------------------------------------------ réseau

const session = { code: null, token: null, version: 0, camera: "", showPodium: true, info: null, state: null,
                  anim: null, playedAnim: null, animate: true,
                  view: null, // cadrage libre [échelle, x, y] (molette, ＋/－, glisser) ; null = caméra
                  previewing: false }; // un zoom est affiché en attendant le dessin net du serveur

function store(key, value) {
  try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, value); } catch (e) { /* privé */ }
}
function load(key) {
  try { return localStorage.getItem(key); } catch (e) { return null; }
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: session.code, token: session.token, ...body }),
  });
  const data = await res.json().catch(() => ({ error: "Réponse illisible du serveur." }));
  if (!res.ok) throw new Error(data.error || "Erreur.");
  return data;
}

async function get(path, params) {
  const res = await fetch(path + "?" + new URLSearchParams(params));
  const data = await res.json().catch(() => ({ error: "Réponse illisible du serveur." }));
  if (!res.ok) throw Object.assign(new Error(data.error || "Erreur."), { status: res.status });
  return data;
}

function showError(id, err) {
  $(id).textContent = err ? (err.message || String(err)) : "";
}

// ------------------------------------------------------------------ dessin des formes du plateau

const ANCHORS = {
  center: ["center", "middle"], n: ["center", "top"], s: ["center", "bottom"], e: ["right", "middle"],
  w: ["left", "middle"], nw: ["left", "top"], ne: ["right", "top"], sw: ["left", "bottom"], se: ["right", "bottom"],
};

// Le canvas a autant de pixels qu'il en occupe à l'écran (largeur affichée × densité de l'écran) : les formes,
// prévues pour w × h, sont agrandies en vectoriel, donc nettes, au lieu d'être une petite image étirée (floue).
function setupCanvas(canvas, w, h, xf) {
  canvas.style.aspectRatio = `${w} / ${h}`;
  const shown = canvas.clientWidth || w;
  const ratio = (window.devicePixelRatio || 1) * (shown / w);
  const pw = Math.max(1, Math.round(w * ratio)), ph = Math.max(1, Math.round(h * ratio));
  if (canvas.width !== pw || canvas.height !== ph) {
    canvas.width = pw;
    canvas.height = ph;
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, pw, ph);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  if (xf) ctx.transform(xf[0], 0, 0, xf[0], xf[1], xf[2]); // aperçu d'un zoom en attendant le serveur
  return ctx;
}

function finish(ctx, fill, outline, width) {
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (outline && width > 0) { ctx.strokeStyle = outline; ctx.lineWidth = width; ctx.stroke(); }
}

// Même rôle que ui.paint (Tkinter) : rect, oval, poly, path, line, text.
function paint(canvas, shapes, w, h, xf) {
  const ctx = setupCanvas(canvas, w, h, xf);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const s of shapes || []) {
    const kind = s[0];
    if (kind === "rect") {
      const [, x0, y0, x1, y1, fill, outline, width] = s;
      ctx.beginPath();
      ctx.rect(x0, y0, x1 - x0, y1 - y0);
      finish(ctx, fill, outline, width);
    } else if (kind === "oval") {
      const [, x0, y0, x1, y1, fill, outline, width] = s;
      ctx.beginPath();
      ctx.ellipse((x0 + x1) / 2, (y0 + y1) / 2, Math.abs(x1 - x0) / 2, Math.abs(y1 - y0) / 2, 0, 0, Math.PI * 2);
      finish(ctx, fill, outline, width);
    } else if (kind === "poly") {
      const [, pts, fill, outline, width] = s;
      ctx.beginPath();
      for (let i = 0; i < pts.length; i += 2) (i ? ctx.lineTo : ctx.moveTo).call(ctx, pts[i], pts[i + 1]);
      ctx.closePath();
      finish(ctx, fill, outline, width);
    } else if (kind === "path") {
      const [, pts, color, width] = s;
      ctx.beginPath();
      for (let i = 0; i < pts.length; i += 2) (i ? ctx.lineTo : ctx.moveTo).call(ctx, pts[i], pts[i + 1]);
      finish(ctx, "", color, width);
    } else if (kind === "line") {
      const [, x0, y0, x1, y1, color, width] = s;
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      finish(ctx, "", color, width);
    } else if (kind === "text") {
      const [, x, y, text, color, size, bold, anchor, angle] = s;
      const [align, base] = ANCHORS[anchor] || ANCHORS.center;
      ctx.save();
      ctx.translate(x, y);
      if (angle) ctx.rotate((-angle * Math.PI) / 180); // Tk : degrés dans le sens inverse des aiguilles
      ctx.font = `${bold ? "700" : "400"} ${Math.round(size * 1.33)}px ${FONT}`;
      ctx.fillStyle = color;
      ctx.textAlign = align;
      ctx.textBaseline = base;
      const lines = String(text).split("\n");
      const lh = size * 1.33 * 1.2;
      const top = base === "middle" ? -((lines.length - 1) * lh) / 2 : base === "bottom" ? -(lines.length - 1) * lh : 0;
      lines.forEach((line, i) => ctx.fillText(line, 0, top + i * lh));
      ctx.restore();
    }
  }
}

function riderTag(name, team) {
  return el("span", { class: "rider", style: `background:${TEAM_FILL[team]};color:${LABEL_ON_FILL[team]}` }, name);
}

// ------------------------------------------------------------------ écrans

function show(screen) {
  for (const id of ["home", "lobby", "race"]) $(id).classList.toggle("hidden", id !== screen);
}

async function enter(code, token) {
  session.code = code;
  session.token = token;
  session.version = session.seenVersion = 0;
  session.view = null;
  store("fr-session-" + code, token);
  history.replaceState(null, "", "?code=" + code);
  $("room-chip").innerHTML = "";
  $("room-chip").append("Partie ", el("b", {}, code));
  $("room-chip").classList.remove("hidden");
  poll();
}

async function onCreate() {
  showError("home-error", null);
  const name = $("name").value.trim();
  store("fr-name", name);
  try {
    const r = await api("/api/create", { name });
    enter(r.code, r.token);
  } catch (e) { showError("home-error", e); }
}

async function onJoin() {
  showError("home-error", null);
  const name = $("name").value.trim();
  const code = $("code").value.trim().toUpperCase();
  store("fr-name", name);
  try {
    session.code = code;
    const r = await api("/api/join", { name, code });
    enter(r.code, r.token);
  } catch (e) { showError("home-error", e); }
}

let pollTimer = null;
let pollSeq = 0; // seule la réponse à la dernière demande compte (un zoom peut partir pendant une autre demande)
async function poll() {
  clearTimeout(pollTimer);
  const seq = ++pollSeq;
  try {
    const params = { code: session.code, token: session.token, since: session.version, camera: session.camera };
    if (session.view) params.view = session.view.map((v) => v.toFixed(2)).join(",");
    const state = await get("/api/state", params);
    if (seq !== pollSeq) return; // une demande plus récente est partie : elle reprendra la boucle
    if (!state.same) {
      session.previewing = false;
      // dernière version vraiment reçue (un zoom remet `version` à 0 pour forcer un dessin, pas pour rejouer)
      const previousVersion = session.seenVersion || 0;
      const hadRace = !!(session.state && session.state.race && session.state.code === state.code);
      session.version = session.seenVersion = state.version;
      session.state = state;
      render(state, previousVersion, hadRace);
    }
  } catch (e) {
    if (seq !== pollSeq) return;
    if (e.status === 400) { // salon disparu ou jeton inconnu : retour à l'accueil
      store("fr-session-" + session.code, null);
      session.code = session.token = null;
      history.replaceState(null, "", location.pathname);
      $("room-chip").classList.add("hidden");
      show("home");
      showError("home-error", e);
      return;
    }
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

function render(state, previousVersion, hadRace) {
  if (state.lobby) {
    session.anim = null;
    session.view = null; // le prochain parcours repart en vue complète
    show("lobby");
    renderLobby(state);
  } else {
    show("race");
    renderRace(state, previousVersion, hadRace);
  }
}

// ------------------------------------------------------------------ salon

function renderLobby(state) {
  const lobby = state.lobby;
  const host = state.me.host;
  $("subtitle").textContent = "Salon";
  $("lobby-code").textContent = state.code;
  $("share").value = location.origin + location.pathname + "?code=" + state.code;

  const seats = $("seats");
  seats.innerHTML = "";
  for (const seat of lobby.seats) {
    const row = el("div", { class: "seat" }, el("span", { class: "dot", style: `background:${TEAM_FILL[seat.team]}` }),
      el("b", {}, `Équipe ${seat.team + 1}`), el("span", { class: "muted" }, seat.color));
    const who = el("span", { class: "who" });
    if (seat.kind === "joueur") {
      if (seat.player) who.append(seat.player === state.me.name ? el("b", {}, seat.player + " (toi)") : seat.player);
      else who.append(el("span", { class: "muted" }, "libre (sinon IA)"));
    } else {
      who.append(el("span", { class: "muted" }, session.info.seat_kinds[seat.kind]));
    }
    row.append(who);
    if (seat.kind === "joueur" && !seat.player) {
      row.append(el("button", { onclick: () => seatAction(seat.team) }, "Prendre"));
    } else if (seat.player === state.me.name) {
      row.append(el("button", { onclick: () => seatAction(null) }, "Quitter"));
    }
    if (host) {
      const select = el("select", { onchange: (ev) => changeSeat(seat.team, ev.target.value) });
      const kinds = ["joueur", "ia"].concat(lobby.extensions.includes("peloton") ? ["peloton", "muscle"] : []);
      for (const k of kinds) {
        const opt = el("option", { value: k }, session.info.seat_kinds[k]);
        if (k === seat.kind) opt.selected = true;
        select.append(opt);
      }
      row.append(select);
    }
    seats.append(row);
  }
  $("players").textContent = state.players.map((p) => p.name + (p.host ? " (hôte)" : "") +
    (p.team == null ? " · spectateur" : "")).join(", ");

  $("host-settings").classList.toggle("hidden", !host);
  $("guest-settings").textContent = host ? "" :
    `${lobby.parcours_label} · ${lobby.teams} équipes · ` +
    (lobby.extensions.length ? "extensions : " + lobby.extensions.join(", ") : "jeu de base") +
    (lobby.breakaway_available && lobby.breakaway ? " · variante Échappée" : "") +
    " — l'hôte règle la partie.";
  if (host) {
    if (document.activeElement !== $("parcours")) $("parcours").value = lobby.parcours;
    if (document.activeElement !== $("teams")) $("teams").value = String(lobby.teams);
    for (const box of $("extensions").querySelectorAll("input")) box.checked = lobby.extensions.includes(box.value);
    $("breakaway").checked = lobby.breakaway;
  }
  $("breakaway-row").classList.toggle("hidden", !(host && lobby.breakaway_available));
  const [w, h, ph] = lobby.preview_size;
  paint($("preview"), lobby.preview.map, w, h);
  paint($("preview-profile"), lobby.preview.profile, w, ph);
  $("lobby-details").textContent = `${lobby.parcours_label} · ${lobby.details}`;
  $("start").classList.toggle("hidden", !host);
}

function buildSettings() {
  const parcours = $("parcours");
  let group = null;
  let optgroup = null;
  for (const p of session.info.parcours) {
    if (p.group !== group) {
      group = p.group;
      optgroup = el("optgroup", { label: group });
      parcours.append(optgroup);
    }
    optgroup.append(el("option", { value: p.key }, p.label));
  }
  parcours.addEventListener("change", () => settings({ parcours: parcours.value }));
  const teams = $("teams");
  for (let n = 2; n <= 6; n++) teams.append(el("option", { value: n }, `${n} équipes`));
  teams.addEventListener("change", () => settings({ teams: Number(teams.value) }));
  for (const ext of session.info.extensions) {
    const box = el("input", { type: "checkbox", value: ext.key });
    box.addEventListener("change", () => {
      const chosen = [...$("extensions").querySelectorAll("input:checked")].map((b) => b.value);
      settings({ extensions: chosen });
    });
    $("extensions").append(el("label", { class: "ext", title: ext.description }, box, ext.label));
  }
  $("breakaway").addEventListener("change", () => settings({ breakaway: $("breakaway").checked }));
}

async function settings(change) {
  showError("lobby-error", null);
  try { await api("/api/settings", change); poll(); } catch (e) { showError("lobby-error", e); poll(); }
}

async function changeSeat(team, kind) {
  const seats = session.state.lobby.seats.map((s) => s.kind);
  seats[team] = kind;
  settings({ seats });
}

async function seatAction(team) {
  showError("lobby-error", null);
  try { await api("/api/seat", { team }); poll(); } catch (e) { showError("lobby-error", e); }
}

// ------------------------------------------------------------------ animations (mouvement, aspiration, météo)
// Mêmes calculs que flamme_rouge/animation.py et les effets météo de boardview.py : le serveur envoie la géométrie
// de la route (bords droit et gauche de chaque case, en pixels) et celle du profil ; on anime ici, à ~30 images/s.

const MOVE_DURATION = 0.6, MOVE_GAP = 0.08, MOVE_TOTAL_MAX = 4.5, SLIPSTREAM_DURATION = 0.7;
const frac = (x) => x - Math.floor(x);
const ease = (t) => { t = Math.min(Math.max(t, 0), 1); return t * t * (3 - 2 * t); };

function mix(c1, c2, f) { // couleur entre c1 (f = 0) et c2 (f = 1), comme boardview._mix
  f = Math.min(Math.max(f, 0), 1);
  const a = [1, 3, 5].map((i) => parseInt(c1.slice(i, i + 2), 16));
  const b = [1, 3, 5].map((i) => parseInt(c2.slice(i, i + 2), 16));
  return "#" + a.map((x, i) => Math.round(x + (b[i] - x) * f).toString(16).padStart(2, "0")).join("");
}

function roadPoint(road, progress, lane) { // comme geometry.point_on_road + SquareGeom.lane_center
  const last = road.length - 1;
  progress = Math.min(Math.max(progress, 0), last);
  const i = Math.min(Math.floor(progress), Math.max(last - 1, 0));
  const f = progress - i;
  const at = (row) => {
    const [rx, ry, lx, ly, lanes] = row;
    const g = (lane + 0.5) / lanes;
    return [rx + (lx - rx) * g, ry + (ly - ry) * g];
  };
  const here = at(road[i]);
  if (last === 0) return here;
  const next = at(road[i + 1]);
  return [here[0] + (next[0] - here[0]) * f, here[1] + (next[1] - here[1]) * f];
}

function makeAnimation(data) { // comme movement_animation / slipstream_animation
  let moves = data.moves.slice();
  let duration = SLIPSTREAM_DURATION, stagger = 0;
  if (data.kind === "movement") {
    moves.sort((a, b) => b.from[0] - a.from[0] || a.from[1] - b.from[1]); // le plus avancé part en premier
    duration = Math.min(MOVE_DURATION, MOVE_TOTAL_MAX / Math.max(moves.length, 1) - MOVE_GAP);
    stagger = duration + MOVE_GAP;
  }
  return {
    moves, duration, stagger,
    total: moves.length ? stagger * (moves.length - 1) + duration : 0,
    positions(t) {
      const out = {};
      moves.forEach((m, k) => {
        const e = ease((t - k * stagger) / duration);
        out[m.name] = [m.from[0] + (m.to[0] - m.from[0]) * e, m.from[1] + (m.to[1] - m.from[1]) * e];
      });
      return out;
    },
  };
}

function riderShapes(race, positions) { // les pastilles des coureurs, comme dans map_primitives
  const c = session.info.colors;
  const { road, radius, font } = race.geo;
  const where = race.riders.map((r) => ({ r, at: positions[r.name] || [r.position, r.lane] }));
  where.sort((a, b) => a.at[0] - b.at[0]); // ceux de derrière d'abord
  const shapes = [];
  for (const { r, at } of where) {
    const [cx, cy] = roadPoint(road, at[0], at[1]);
    shapes.push(["oval", cx - radius + 1.5, cy - radius + 3, cx + radius + 1.5, cy + radius + 3, c.shadow, "", 0]);
    shapes.push(["oval", cx - radius, cy - radius, cx + radius, cy + radius, TEAM_FILL[r.team], c.rider_outline, 2]);
    shapes.push(["text", cx, cy, r.name, LABEL_ON_FILL[r.team], font, true, "center"]);
  }
  return shapes;
}

function mapWeatherShapes(race, t) { // comme boardview.map_weather_fx_primitives
  const c = session.info.colors, fx = c.effects;
  const { road, first, last, scale } = race.geo;
  const px = Math.max(scale, 6);
  const at = (p, l) => roadPoint(road, p, l);
  const shapes = [];
  race.weather.forEach((zone, k) => {
    const start = Math.max(zone.start, first), end = Math.min(zone.end, last + 1, road.length);
    if (start >= end) return;
    const length = end - start, seed = frac(k * 0.37);
    if (zone.effect === fx.rain) {
      for (let d = 0; d < 4 * length; d++) {
        const phase = frac(d * 0.618 + seed);
        const p = start + frac(d * 0.381 + seed * 3.1) * length;
        const lane = -0.4 + frac(d * 0.727 + seed) * 1.8;
        const [x, y] = at(p, lane);
        const f = frac(t * 0.9 + phase);
        if (f < 0.35) {
          const drop = 0.5 * px * (1 - f / 0.35);
          shapes.push(["line", x - drop * 0.3, y - drop - 3, x - drop * 0.3 + 2, y - drop + 3, c.rain, 1]);
        } else {
          const g = (f - 0.35) / 0.65, r = 1.5 + g * 0.22 * px;
          shapes.push(["oval", x - r, y - r * 0.6, x + r, y + r * 0.6, "", mix(c.rain, c.road, g), 1]);
        }
      }
    } else if (zone.effect === fx.tailwind || zone.effect === fx.headwind) {
      const dir = zone.effect === fx.tailwind ? 1 : -1, color = c.wind[zone.effect];
      for (let d = 0; d < 3 * length; d++) {
        const phase = frac(d * 0.29 + seed), lane = -0.6 + frac(d * 0.53 + seed) * 2.2;
        const f = frac(t * 0.45 + phase);
        const head = start + (dir > 0 ? f : 1 - f) * length, tail = head - 0.7 * dir;
        if (tail < start || tail > end) continue;
        const [x0, y0] = at(tail, lane), [x1, y1] = at(head, lane);
        shapes.push(["line", x0, y0, x1, y1, mix(c.grass, color, 0.5 + 0.5 * Math.sin(f * Math.PI)), 2]);
      }
    } else if (zone.effect === fx.crosswind) {
      const color = c.wind[zone.effect];
      for (const depth of [0.35, 0.65, 1.0]) {
        const count = Math.max(2, Math.floor(length * 1.5));
        for (let d = 0; d < count; d++) {
          const phase = frac(d * 0.41 + depth * 0.77 + seed), p = start + ((d + 0.5) / count) * length;
          const f = frac(t * (0.25 + 0.45 * depth) + phase), lane = 2.6 - f * 4.0, streak = 0.35 + 0.6 * depth;
          const [x0, y0] = at(p, lane + streak), [x1, y1] = at(p, lane);
          const lift = (1 - depth) * 0.18 * px, fade = Math.sin(f * Math.PI);
          shapes.push(["line", x0, y0 - lift, x1, y1 - lift, mix(c.grass, color, (0.3 + 0.7 * depth) * fade),
                       depth < 0.5 ? 1 : depth < 0.9 ? 2 : 3]);
        }
      }
    } else if (zone.effect === fx.sunny) {
      const [cx, cy] = at(start + length / 2, 2.8), r = Math.max(4, Math.min(9, 0.22 * px));
      shapes.push(["oval", cx - r, cy - r, cx + r, cy + r, c.sun, c.sun, 1]);
      for (let ray = 0; ray < 8; ray++) {
        const a = t * 0.8 + (ray * Math.PI) / 4;
        shapes.push(["line", cx + Math.cos(a) * (r + 2), cy + Math.sin(a) * (r + 2),
                     cx + Math.cos(a) * (r + 2 + r * 0.7), cy + Math.sin(a) * (r + 2 + r * 0.7), c.sun, 2]);
      }
    }
  });
  return shapes;
}

function profileWeatherShapes(race, t) { // comme boardview.weather_fx_primitives
  const c = session.info.colors, fx = c.effects;
  const { x0: px0, sx, ys, n, top } = race.profile_geo;
  const xOf = (i) => px0 + i * sx;
  const yAt = (s) => {
    const i = Math.max(0, Math.min(n, Math.floor(s))), j = Math.min(n, i + 1), f = Math.max(0, Math.min(1, s - i));
    return ys[i] + (ys[j] - ys[i]) * f;
  };
  const shapes = [];
  race.weather.forEach((zone, k) => {
    const end = Math.min(zone.end, n), x0 = xOf(zone.start), x1 = xOf(end);
    const w = Math.max(x1 - x0, 1), seed = (k * 0.37) % 1;
    const lowest = () => { let m = Infinity; for (let s = zone.start; s < end; s++) m = Math.min(m, yAt(s + 0.5)); return m; };
    if (zone.effect === fx.rain) {
      const count = Math.max(6, Math.floor(w / 7));
      for (let d = 0; d < count; d++) {
        const phase = (d * 0.618 + seed) % 1, x = x0 + ((d + 0.5) * w) / count;
        const ground = yAt(zone.start + ((x - x0) / w) * (end - zone.start));
        const y = top + ((t * 1.6 + phase) % 1) * Math.max(ground - top - 4, 1);
        shapes.push(["line", x, y, x - 2, y + 6, c.rain, 1]);
      }
    } else if (c.wind[zone.effect]) {
      const dir = zone.effect === fx.tailwind ? 1 : zone.effect === fx.headwind ? -1 : 0, color = c.wind[zone.effect];
      const ground = lowest();
      for (let d = 0; d < 4; d++) {
        const phase = (d * 0.29 + seed) % 1, level = ground - 8 - d * 6;
        if (dir) {
          const f = (t * 0.7 + phase) % 1, x = x0 + (dir > 0 ? f : 1 - f) * w, tail = x - 10 * dir;
          shapes.push(["line", Math.max(Math.min(tail, x1), x0), level, Math.max(Math.min(x, x1), x0), level, color, 2]);
          shapes.push(["line", x, level, x - 3 * dir, level - 2, color, 1]);
        } else {
          for (let g = 0; g < 2; g++) {
            const f = frac(t * 0.55 + phase + g * 0.5), cx = x0 + frac(d * 0.31 + g * 0.47 + seed) * w;
            const cy = ground - 10 - frac(d * 0.59 + g * 0.23) * 22 + f * 8, size = 2 + 10 * f;
            shapes.push(["line", cx - size, cy - size * 0.25, cx + size, cy + size * 0.25,
                         mix(c.card, color, Math.sin(f * Math.PI)), f < 0.4 ? 1 : f < 0.75 ? 2 : 3]);
          }
        }
      }
    } else if (zone.effect === fx.sunny) {
      const cx = (x0 + x1) / 2, cy = lowest() - 16, r = 4.5;
      shapes.push(["oval", cx - r, cy - r, cx + r, cy + r, c.sun, c.sun, 1]);
      for (let ray = 0; ray < 8; ray++) {
        const a = t * 0.8 + (ray * Math.PI) / 4;
        shapes.push(["line", cx + Math.cos(a) * (r + 2), cy + Math.sin(a) * (r + 2),
                     cx + Math.cos(a) * (r + 5), cy + Math.sin(a) * (r + 5), c.sun, 1]);
      }
    }
  });
  return shapes;
}

// ------------------------------------------------------------------ zoom et déplacement de la carte
// Comme boardview.zoom_view / pan_view. Le navigateur agrandit tout de suite ce qu'il a déjà (aperçu), puis
// demande au serveur un dessin net de ce cadrage (numéros de case, chevrons, taille des coureurs).

const MIN_SCALE = 3, MAX_SCALE = 140;

function zoomView([s, cx, cy], f, px, py, W, H) {
  const ns = Math.min(Math.max(s * f, MIN_SCALE), MAX_SCALE);
  const wx = cx + (px - W / 2) / s, wy = cy - (py - H / 2) / s;
  return [ns, wx - (px - W / 2) / ns, wy + (py - H / 2) / ns];
}

function panView([s, cx, cy], dx, dy) {
  return [s, cx - dx / s, cy + dy / s];
}

let viewTimer = null;
function setView(view) {
  const race = session.state && session.state.race;
  if (!race || (race.finished && race.podium && session.showPodium)) return; // pas de zoom sur le podium
  if (session.anim) session.anim = null; // un déplacement en cours s'arrête net
  session.view = view;
  session.camera = "";
  for (const b of $("camera").querySelectorAll("button")) b.classList.remove("on");
  // aperçu : les formes déjà reçues, passées du cadrage dessiné au nouveau
  const [s, cx, cy] = race.view, [ns, ncx, ncy] = view;
  const [w, h] = race.size, k = ns / s;
  const xf = [k, w / 2 - (k * w) / 2 + (cx - ncx) * ns, h / 2 - (k * h) / 2 - (cy - ncy) * ns];
  session.previewing = true;
  paint($("map"), race.map, w, h, xf);
  paint($("map-fx"), [], w, h);
  clearTimeout(viewTimer);
  viewTimer = setTimeout(() => { session.version = 0; poll(); }, 150); // dessin net quand on s'arrête
}

function mapPoint(event) { // position de la souris en coordonnées du plateau (1000 × 430)
  const canvas = $("map"), [w, h] = session.state.race.size;
  const rect = canvas.getBoundingClientRect();
  return [((event.clientX - rect.left) / rect.width) * w, ((event.clientY - rect.top) / rect.height) * h];
}

function currentView() {
  return session.view || session.state.race.view;
}

function setupZoom() {
  const layer = $("map-layer");
  layer.addEventListener("wheel", (event) => {
    if (!session.state || !session.state.race) return;
    event.preventDefault();
    const [px, py] = mapPoint(event), [w, h] = session.state.race.size;
    setView(zoomView(currentView(), event.deltaY < 0 ? 1.25 : 0.8, px, py, w, h));
  }, { passive: false });
  const button = (factor) => () => {
    if (!session.state || !session.state.race) return;
    const [w, h] = session.state.race.size;
    setView(zoomView(currentView(), factor, w / 2, h / 2, w, h));
  };
  $("zoom-in").addEventListener("click", button(1.4));
  $("zoom-out").addEventListener("click", button(1 / 1.4));
  let drag = null;
  layer.addEventListener("pointerdown", (event) => {
    if (!session.state || !session.state.race || event.button !== 0) return;
    drag = { at: mapPoint(event), moved: false };
    layer.setPointerCapture(event.pointerId);
  });
  layer.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const p = mapPoint(event), dx = p[0] - drag.at[0], dy = p[1] - drag.at[1];
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    drag.moved = true;
    drag.at = p;
    layer.classList.add("dragging");
    setView(panView(currentView(), dx, dy));
  });
  const stop = () => { drag = null; layer.classList.remove("dragging"); };
  layer.addEventListener("pointerup", stop);
  layer.addEventListener("pointercancel", stop);
  window.addEventListener("resize", () => { // nouvelle taille d'affichage : on redessine net
    if (!session.state) return;
    if (session.state.race) drawBoard(); else renderLobby(session.state);
  });
}

// Le plateau : la carte complète, ou, pendant un déplacement, la route seule avec les coureurs qui roulent par-dessus.
function drawBoard() {
  const state = session.state;
  if (!state || !state.race) return;
  const race = state.race;
  const [w, h, ph] = race.size;
  const podium = race.finished && race.podium && session.showPodium;
  if (session.anim) paint($("map"), session.anim.race.map_base, w, h);
  else paint($("map"), podium ? race.podium : race.map, w, h);
  paint($("profile"), race.profile, w, ph);
}

function maybeStartAnimation(race, previousVersion, hadRace) {
  const data = race.anim;
  if (!data || data.id === session.playedAnim) return;
  session.playedAnim = data.id;
  // pas de replay au premier chargement (ou après un rechargement) : seulement ce qui vient d'arriver
  if (!hadRace || data.id <= previousVersion || !session.animate) return;
  session.anim = { race, anim: makeAnimation(data), start: performance.now() };
}

let lastFrame = 0;
function frame(now) {
  requestAnimationFrame(frame);
  if (now - lastFrame < 33) return; // ~30 images par seconde
  lastFrame = now;
  const state = session.state;
  if (!state || !state.race || $("race").classList.contains("hidden") || session.previewing) return;
  const race = state.race;
  const [w, h, ph] = race.size;
  const t = now / 1000;
  let mapShapes = [];
  if (session.anim) {
    const a = session.anim;
    const elapsed = (now - a.start) / 1000;
    if (elapsed >= a.anim.total) { // fin du déplacement : la carte complète revient
      session.anim = null;
      drawBoard();
    } else {
      mapShapes = riderShapes(a.race, a.anim.positions(elapsed));
    }
  }
  const podium = race.finished && race.podium && session.showPodium && !session.anim;
  const weather = session.animate && race.weather.length;
  if (weather && !podium) mapShapes = mapShapes.concat(mapWeatherShapes(session.anim ? session.anim.race : race, t));
  paint($("map-fx"), mapShapes, w, h);
  paint($("profile-fx"), weather ? profileWeatherShapes(race, t) : [], w, ph);
}

// ------------------------------------------------------------------ course

function renderRace(state, previousVersion, hadRace) {
  const race = state.race;
  $("subtitle").textContent = race.finished ? "Arrivée" : `Tour ${race.turn}`;
  $("turn").textContent = race.finished ? "ARRIVÉE" : `TOUR ${race.turn}`;
  $("phase-title").textContent = race.title;
  $("waiting").textContent = race.finished ? race.winner : race.waiting;

  if (previousVersion !== undefined) maybeStartAnimation(race, previousVersion, hadRace);
  drawBoard();
  $("toggle-podium").classList.toggle("hidden", !race.finished);
  $("toggle-podium").textContent = session.showPodium ? "Revoir la course" : "Voir le podium";
  $("back-lobby").classList.toggle("hidden", !(race.finished && state.me.host));
  for (const b of $("camera").querySelectorAll("button")) {
    b.classList.toggle("on", !session.view && b.dataset.camera === session.camera);
  }

  // cartes révélées au dernier mouvement
  const rev = $("revealed");
  rev.innerHTML = "";
  if (race.revealed.length) {
    rev.append(`CARTES DU TOUR ${race.revealed_turn}`);
    for (const r of race.revealed) {
      rev.append(el("span", { class: "chip", title: r.who }, riderTag(r.name, r.team), r.card));
    }
  } else {
    rev.append("CARTES JOUÉES : elles apparaîtront ici au premier mouvement");
  }

  // ma main
  const hand = $("hand");
  hand.innerHTML = "";
  if (race.bid && race.bid.stage === "rider") { // variante Échappée : quel coureur tente l'échappée ?
    $("hand-title").textContent = "Échappée : quel coureur la tente ? (2 cartes misées, 2 cartes Fatigue s'il part)";
    const row = el("div", { class: "bid-riders" });
    for (const r of race.bid.riders) {
      row.append(el("button", { class: "primary", onclick: () => bidRider(r.name) }, `${r.name} · ${r.kind}`));
    }
    row.append(el("button", { onclick: () => bidRider(null) }, "Ne pas participer"));
    hand.append(row);
  } else if (race.my_turn) {
    $("hand-title").innerHTML = "";
    if (race.bid && race.bid.stage === "card") {
      $("hand-title").append(`Enchère ${race.bid.round} sur 2 pour `, riderTag(race.rider.name, race.rider.team),
        " : la carte à miser (les autres vont à la défausse)");
    } else {
      $("hand-title").append("À toi : carte de ", riderTag(race.rider.name, race.rider.team),
        ` (case ${race.rider.position})`);
    }
    for (const card of race.hand) {
      hand.append(el("button", { class: card.fatigue ? "fatigue" : "", onclick: () => playCard(card.index) },
        card.label));
    }
  } else {
    $("hand-title").textContent = state.me.team == null ? "Tu regardes la course (spectateur)." :
      race.phase === "choose" || race.phase === "breakaway" ? "En attente des autres joueurs…" :
      "Ta main apparaîtra à ton tour.";
  }
  $("my-riders").textContent = race.my_riders.map((r) =>
    `${r.name} : case ${r.position} · pioche ${r.draw} · recyclage ${r.recycle} · fatigue ${r.fatigue}`).join("   —   ");

  // bouton d'action partagé
  const action = $("action");
  action.textContent = race.finished ? (race.winner || "Course terminée") :
    (race.action || (race.phase === "breakaway" ? "Enchères de l'échappée…" : "Choix des cartes…"));
  action.disabled = !race.can_act;
  action.onclick = () => advance(race.phase);

  // journal
  const log = $("log");
  const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 30;
  log.innerHTML = "";
  for (const line of race.log) {
    const div = el("div", { class: line.heading ? "heading" : "" }, line.text);
    if (line.team != null) div.style.color = TEAM_TEXT[line.team];
    log.append(div);
  }
  if (atBottom) log.scrollTop = log.scrollHeight;
}

async function playCard(index) {
  showError("race-error", null);
  for (const b of $("hand").querySelectorAll("button")) b.disabled = true;
  try { await api("/api/card", { index }); poll(); } catch (e) { showError("race-error", e); poll(); }
}

async function bidRider(name) {
  showError("race-error", null);
  for (const b of $("hand").querySelectorAll("button")) b.disabled = true;
  try { await api("/api/bid_rider", { rider: name }); poll(); } catch (e) { showError("race-error", e); poll(); }
}

async function advance(phase) {
  showError("race-error", null);
  $("action").disabled = true;
  try { await api("/api/advance", { phase }); poll(); } catch (e) { showError("race-error", e); poll(); }
}

// ------------------------------------------------------------------ démarrage

async function start() {
  $("name").value = load("fr-name") || "";
  $("create").addEventListener("click", onCreate);
  $("join").addEventListener("click", onJoin);
  $("code").addEventListener("keydown", (e) => { if (e.key === "Enter") onJoin(); });
  $("copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("share").value); $("copy").textContent = "Copié !"; }
    catch (e) { $("share").select(); }
    setTimeout(() => { $("copy").textContent = "Copier"; }, 1500);
  });
  $("start").addEventListener("click", async () => {
    showError("lobby-error", null);
    try { await api("/api/start", {}); poll(); } catch (e) { showError("lobby-error", e); }
  });
  $("back-lobby").addEventListener("click", async () => {
    try { await api("/api/lobby", {}); poll(); } catch (e) { showError("race-error", e); }
  });
  $("toggle-podium").addEventListener("click", () => {
    session.showPodium = !session.showPodium;
    if (session.state) renderRace(session.state);
  });
  // animations (déplacements, météo) : réglage propre à ce navigateur
  session.animate = load("fr-animate") !== "0";
  const animToggle = $("animate");
  const paintToggle = () => {
    animToggle.classList.toggle("on", session.animate);
    animToggle.textContent = (session.animate ? "✓ " : "") + "Animations";
  };
  paintToggle();
  animToggle.addEventListener("click", () => {
    session.animate = !session.animate;
    store("fr-animate", session.animate ? "1" : "0");
    if (!session.animate && session.anim) { session.anim = null; drawBoard(); }
    paintToggle();
  });
  setupZoom();
  requestAnimationFrame(frame);
  for (const b of $("camera").querySelectorAll("button")) {
    b.addEventListener("click", () => {
      session.camera = b.dataset.camera;
      session.view = null; // une caméra remplace le cadrage libre
      session.version = 0;
      poll();
    });
  }
  try {
    session.info = await get("/api/info", {});
  } catch (e) {
    showError("home-error", "Le serveur ne répond pas.");
    return;
  }
  buildSettings();
  const code = new URLSearchParams(location.search).get("code");
  if (code) {
    $("code").value = code.toUpperCase();
    const token = load("fr-session-" + code.toUpperCase());
    if (token) { enter(code.toUpperCase(), token); return; } // retour dans la partie après un rechargement
  }
  show("home");
}

start();
