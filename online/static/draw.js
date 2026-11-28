"use strict";
// Outils partagés par le jeu (app.js) et l'éditeur de parcours (editor.js) : éléments HTML et dessin des formes
// envoyées par le serveur (les mêmes que ui.paint dans la version tkinter).

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
