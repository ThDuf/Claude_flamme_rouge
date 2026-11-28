"use strict";
// Éditeur de parcours : la page garde le parcours (liste de tuiles, sélection, annulation, comme
// flamme_rouge/plan.py) ; le serveur dessine l'aperçu et vérifie le parcours à chaque modification.

const UNDO_LIMIT = 100;
const ed = {
  catalog: null, // tuiles de la boîte : faces, petites cartes
  side: "plat", pick: "b", // face affichée, tuile choisie dans la palette
  tiles: [], selected: null, undo: [],
  check: null, // dernière réponse du serveur (aperçu, profil, messages)
  local: false, // serveur sur ce PC : on peut enregistrer dans « Mes parcours »
  name: "", // nom du parcours ouvert (proposé pour l'enregistrer)
  saved: [], // noms de « Mes parcours » (pour prévenir avant de remplacer un fichier)
};

async function edGet(path, params = {}) {
  const res = await fetch(path + "?" + new URLSearchParams(params));
  const data = await res.json().catch(() => ({ error: "Réponse illisible du serveur." }));
  if (!res.ok) throw new Error(data.error || "Erreur.");
  return data;
}

async function edPost(path, body) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" },
                                  body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({ error: "Réponse illisible du serveur." }));
  if (!res.ok) throw new Error(data.error || "Erreur.");
  return data;
}

function showEditorError(err) {
  $("editor-error").textContent = err ? (err.message || String(err)) : "";
}

// ------------------------------------------------------------------ édition (comme PlanEditor)

function remember() {
  ed.undo.push([ed.tiles.slice(), ed.selected]);
  if (ed.undo.length > UNDO_LIMIT) ed.undo.shift();
}

function pickedTile() {
  return { ...ed.catalog.cards[ed.pick].tile };
}

const actions = {
  append() { remember(); ed.tiles.push(pickedTile()); ed.selected = ed.tiles.length - 1; },
  insert() {
    if (ed.selected == null) return actions.append();
    remember(); ed.tiles.splice(ed.selected + 1, 0, pickedTile()); ed.selected += 1;
  },
  replace() { if (ed.selected == null) return; remember(); ed.tiles[ed.selected] = pickedTile(); },
  remove() {
    if (ed.selected == null) return;
    remember();
    ed.tiles.splice(ed.selected, 1);
    ed.selected = ed.tiles.length ? Math.min(ed.selected, ed.tiles.length - 1) : null;
  },
  move(delta) {
    if (ed.selected == null) return;
    const target = ed.selected + delta;
    if (target < 0 || target >= ed.tiles.length) return;
    remember();
    [ed.tiles[ed.selected], ed.tiles[target]] = [ed.tiles[target], ed.tiles[ed.selected]];
    ed.selected = target;
  },
  clear() {
    if (!ed.tiles.length || !confirm("Effacer tout le parcours ? (tu pourras annuler)")) return;
    remember(); ed.tiles = []; ed.selected = null;
  },
  load(tiles, name) { remember(); ed.tiles = tiles.slice(); ed.selected = null; ed.name = name || ""; },
  undo() { if (ed.undo.length) [ed.tiles, ed.selected] = ed.undo.pop(); },
};

function act(name, ...args) {
  showEditorError(null);
  actions[name](...args);
  refresh();
}

// ------------------------------------------------------------------ affichage

function sideOf(letter) {
  return ed.catalog.sides.find((s) => s.letters.includes(letter)).key;
}

function renderPalette() {
  const sides = $("sides");
  sides.innerHTML = "";
  for (const s of ed.catalog.sides) {
    sides.append(el("button", { class: s.key === ed.side ? "on" : "",
      onclick: () => { ed.side = s.key; renderPalette(); } }, s.label));
  }
  const used = new Set(((ed.check && ed.check.letters) || []).filter(Boolean).map((l) => l.toLowerCase()));
  const [w, h] = ed.catalog.card_size;
  const palette = $("palette");
  palette.innerHTML = "";
  const side = ed.catalog.sides.find((s) => s.key === ed.side);
  for (const letter of side.letters) {
    const card = ed.catalog.cards[letter];
    const canvas = el("canvas", { width: w, height: h, title: card.label });
    const box = el("button", {
      class: "tile-card" + (letter === ed.pick ? " picked" : "") + (used.has(letter.toLowerCase()) ? " used" : ""),
      "aria-label": `Tuile ${letter} : ${card.label}`,
      onclick: () => { ed.pick = letter; renderPalette(); },
      ondblclick: () => { ed.pick = letter; act("insert"); },
    }, canvas);
    palette.append(box);
    paint(canvas, card.prims, w, h);
  }
  if (ed.side === "peloton") {
    palette.append(el("p", { class: "muted small" }, "Tuiles Peloton 1 à 9 (cases provisoires, faces non distinguées)."));
  }
}

function renderPlan() {
  const list = $("plan");
  list.innerHTML = "";
  const labels = (ed.check && ed.check.labels) || [];
  ed.tiles.forEach((tile, i) => {
    const item = el("li", { class: i === ed.selected ? "selected" : "", tabindex: "0",
      onclick: () => selectTile(i),
      onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectTile(i); } } },
    labels[i] || tile.letter || tile.kind);
    list.append(item);
  });
  if (!ed.tiles.length) list.append(el("p", { class: "muted small" }, "Le parcours est vide : pose une tuile de départ."));
  const sel = list.querySelector(".selected");
  if (sel) sel.scrollIntoView({ block: "nearest" });
  const has = ed.selected != null;
  for (const id of ["insert", "replace", "up", "down", "remove"]) $(id).disabled = !has;
  $("undo").disabled = !ed.undo.length;
  $("clear").disabled = !ed.tiles.length;
}

function selectTile(i) {
  ed.selected = i;
  // la palette reprend la tuile choisie : pratique pour la remplacer par une variante
  const letter = ed.check && ed.check.letters ? ed.check.letters[i] : null;
  if (letter && ed.catalog.cards[letter]) { ed.pick = letter; ed.side = sideOf(letter); }
  refresh();
}

function renderCheck() {
  const c = ed.check;
  if (!c) return;
  const [w, h, ph] = c.size;
  paint($("preview"), c.preview, w, h);
  $("profile").classList.toggle("hidden", !c.profile);
  if (c.profile) paint($("profile"), c.profile, w, ph);
  $("summary").textContent = c.summary;
  const issues = $("issues");
  issues.innerHTML = "";
  for (const i of c.issues) issues.append(el("div", { class: i.level }, (i.level === "error" ? "✖ " : "⚠ ") + i.text));
  if (!c.issues.length) issues.append(el("div", { class: "ok" }, "✔ Parcours valide, conforme au contenu de la boîte."));
  $("save").disabled = !c.playable;
  $("download").disabled = !ed.tiles.length;
}

let checkSeq = 0;
async function refresh() {
  renderPlan();
  renderPalette();
  const seq = ++checkSeq;
  try {
    const result = await edPost("/api/editor/check", { tiles: ed.tiles, selected: ed.selected });
    if (seq !== checkSeq) return; // une modification plus récente est partie
    ed.check = result;
    renderPlan();
    renderPalette();
    renderCheck();
  } catch (e) { showEditorError(e); }
}

// ------------------------------------------------------------------ fichiers

async function fillOpenList() {
  const data = await edGet("/api/editor/open");
  ed.local = data.local;
  ed.saved = data.parcours.filter((p) => p.group === "Mes parcours").map((p) => p.label.toLowerCase());
  const select = $("open");
  select.innerHTML = "";
  select.append(el("option", { value: "" }, "— choisis un parcours —"));
  let group = null, optgroup = null;
  for (const p of data.parcours) {
    if (p.group !== group) { group = p.group; optgroup = el("optgroup", { label: group }); select.append(optgroup); }
    optgroup.append(el("option", { value: p.key }, p.label));
  }
  $("save-box").classList.toggle("hidden", !ed.local);
  $("save-note").textContent = ed.local ?
    "Les parcours enregistrés apparaissent dans le salon, rubrique « Mes parcours » (dossier parcours/ de ce PC)." :
    "Sur le site en ligne, télécharge le fichier ; « Importer » le rouvre ici. Pour le jouer dans un salon, " +
    "lance le jeu sur ton PC (python main.py) et enregistre-le.";
}

async function openTrack(key) {
  if (!key) return;
  showEditorError(null);
  try {
    const data = await edGet("/api/editor/load", { key });
    act("load", data.tiles, data.label === "exemple" ? "" : data.label);
    $("save-name").value = ed.name;
  } catch (e) { showEditorError(e); }
  $("open").value = "";
}

function importFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      if (!data || !Array.isArray(data.tiles)) throw new Error("Ce fichier n'est pas un parcours Flamme Rouge.");
      if ((data.version || 1) < 2) throw new Error("Ce parcours vient d'une ancienne version : recrée-le dans l'éditeur.");
      act("load", data.tiles, file.name.replace(/\.json$/i, ""));
      $("save-name").value = ed.name;
    } catch (e) { showEditorError(e); }
  };
  reader.readAsText(file);
  $("import-file").value = "";
}

function download() {
  const text = JSON.stringify({ version: 2, tiles: ed.tiles }, null, 2);
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const name = ($("save-name").value.trim() || ed.name || "mon_parcours").replace(/[\\/:*?"<>|]/g, "");
  const a = el("a", { href: url, download: name + ".json" });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function save() {
  showEditorError(null);
  const name = $("save-name").value.trim();
  if (!name) { showEditorError("Choisis un nom pour le parcours."); $("save-name").focus(); return; }
  if (ed.saved.includes(name.toLowerCase()) && !confirm(`« ${name} » existe déjà dans « Mes parcours ». Le remplacer ?`)) return;
  try {
    const r = await edPost("/api/editor/save", { name, tiles: ed.tiles });
    ed.name = r.saved;
    $("save-name").value = r.saved;
    $("save-note").textContent = `« ${r.saved} » ${r.replaced ? "remplacé" : "enregistré"} : il est dans le salon, ` +
      "rubrique « Mes parcours » (un salon déjà ouvert le voit en rechargeant sa page).";
    await fillOpenList().catch(() => {});
  } catch (e) { showEditorError(e); }
}

// ------------------------------------------------------------------ démarrage

async function startEditor() {
  $("append").addEventListener("click", () => act("append"));
  $("insert").addEventListener("click", () => act("insert"));
  $("replace").addEventListener("click", () => act("replace"));
  $("up").addEventListener("click", () => act("move", -1));
  $("down").addEventListener("click", () => act("move", 1));
  $("remove").addEventListener("click", () => act("remove"));
  $("undo").addEventListener("click", () => act("undo"));
  $("clear").addEventListener("click", () => act("clear"));
  $("open").addEventListener("change", () => openTrack($("open").value));
  $("import").addEventListener("click", () => $("import-file").click());
  $("import-file").addEventListener("change", () => importFile($("import-file").files[0]));
  $("download").addEventListener("click", download);
  $("save").addEventListener("click", save);
  try {
    ed.catalog = await edGet("/api/editor/tiles");
    await fillOpenList();
    const example = await edGet("/api/editor/load", { key: "exemple" });
    ed.tiles = example.tiles;
  } catch (e) {
    showEditorError("Le serveur ne répond pas.");
    return;
  }
  refresh();
}

startEditor();
