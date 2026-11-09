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

const session = { code: null, token: null, version: 0, camera: "", showPodium: true, info: null, state: null };

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

function setupCanvas(canvas, w, h) {
  const ratio = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(w * ratio) || canvas.height !== Math.round(h * ratio)) {
    canvas.width = Math.round(w * ratio);
    canvas.height = Math.round(h * ratio);
  }
  canvas.style.aspectRatio = `${w} / ${h}`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return ctx;
}

function finish(ctx, fill, outline, width) {
  if (fill) { ctx.fillStyle = fill; ctx.fill(); }
  if (outline && width > 0) { ctx.strokeStyle = outline; ctx.lineWidth = width; ctx.stroke(); }
}

// Même rôle que ui.paint (Tkinter) : rect, oval, poly, path, line, text.
function paint(canvas, shapes, w, h) {
  const ctx = setupCanvas(canvas, w, h);
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
  session.version = 0;
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
async function poll() {
  clearTimeout(pollTimer);
  try {
    const state = await get("/api/state", { code: session.code, token: session.token, since: session.version,
                                            camera: session.camera });
    if (!state.same) {
      session.version = state.version;
      session.state = state;
      render(state);
    }
  } catch (e) {
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

function render(state) {
  if (state.lobby) { show("lobby"); renderLobby(state); } else { show("race"); renderRace(state); }
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
    " — l'hôte règle la partie.";
  if (host) {
    if (document.activeElement !== $("parcours")) $("parcours").value = lobby.parcours;
    if (document.activeElement !== $("teams")) $("teams").value = String(lobby.teams);
    for (const box of $("extensions").querySelectorAll("input")) box.checked = lobby.extensions.includes(box.value);
  }
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

// ------------------------------------------------------------------ course

function renderRace(state) {
  const race = state.race;
  const [w, h, ph] = race.size;
  $("subtitle").textContent = race.finished ? "Arrivée" : `Tour ${race.turn}`;
  $("turn").textContent = race.finished ? "ARRIVÉE" : `TOUR ${race.turn}`;
  $("phase-title").textContent = race.title;
  $("waiting").textContent = race.finished ? race.winner : race.waiting;

  const podium = race.finished && race.podium && session.showPodium;
  paint($("map"), podium ? race.podium : race.map, w, h);
  paint($("profile"), race.profile, w, ph);
  $("toggle-podium").classList.toggle("hidden", !race.finished);
  $("toggle-podium").textContent = session.showPodium ? "Revoir la course" : "Voir le podium";
  $("back-lobby").classList.toggle("hidden", !(race.finished && state.me.host));
  for (const b of $("camera").querySelectorAll("button")) b.classList.toggle("on", b.dataset.camera === session.camera);

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
  if (race.my_turn) {
    $("hand-title").innerHTML = "";
    $("hand-title").append("À toi : carte de ", riderTag(race.rider.name, race.rider.team),
      ` (case ${race.rider.position})`);
    for (const card of race.hand) {
      hand.append(el("button", { class: card.fatigue ? "fatigue" : "", onclick: () => playCard(card.index) },
        card.label));
    }
  } else {
    $("hand-title").textContent = state.me.team == null ? "Tu regardes la course (spectateur)." :
      race.phase === "choose" ? "En attente des autres joueurs…" : "Ta main apparaîtra à ton tour.";
  }
  $("my-riders").textContent = race.my_riders.map((r) =>
    `${r.name} : case ${r.position} · pioche ${r.draw} · recyclage ${r.recycle} · fatigue ${r.fatigue}`).join("   —   ");

  // bouton d'action partagé
  const action = $("action");
  action.textContent = race.finished ? (race.winner || "Course terminée") : (race.action || "Choix des cartes…");
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
  for (const b of $("camera").querySelectorAll("button")) {
    b.addEventListener("click", () => { session.camera = b.dataset.camera; session.version = 0; poll(); });
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
