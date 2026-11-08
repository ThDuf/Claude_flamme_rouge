"""Géométrie du plateau pour l'interface graphique.

Aucune dépendance à tkinter : les fonctions renvoient des listes de formes à dessiner,
ce qui permet de les tester sans écran. Formats des formes :
  ("rect", x0, y0, x1, y1, remplissage, contour, épaisseur)
  ("oval", x0, y0, x1, y1, remplissage, contour, épaisseur)
  ("line", x0, y0, x1, y1, couleur, épaisseur)
  ("path", [x0, y0, x1, y1, ...], couleur, épaisseur)   ligne brisée (bords de route en virage)
  ("text", x, y, texte, couleur, taille, gras, ancrage)
"""
from __future__ import annotations

import math
import random
import zlib
from typing import Iterable, Optional, Sequence

from .game import Game
from .geometry import EXTRA_SQUARES, finish_edge, layout_squares, point_on_road
from .rider import Rider
from .tiles import KIND_START, Tile, finish_square, full_track, tile_ranges
from .track import ASCENT, BREAKAWAY, COBBLES, DESCENT, NORMAL, SUPPLY, Track
from .weather import CROSSWIND, HEADWIND, RAIN, SHORT as WEATHER_SHORT, SUNNY, TAILWIND, Weather
from .stage import MOUNTAIN as TOKEN_MOUNTAIN, TokenStack, timing_table

from . import palette as pal
from .palette import BEYOND_FILL, LABEL_ON_FILL, TEAM_FILL, TEAM_TEXT, TERRAIN_FILL, TERRAIN_SYMBOL_COLOR

TERRAIN_SYMBOL = {NORMAL: "·", ASCENT: "▲", DESCENT: "▼"}

BOARD_W = 1000
CELL_W = 62
PAD = 64  # marge gauche pour les étiquettes (terrain / droite / gauche)
TOP = 30
ROW_H = 50
BOARD_H = TOP + 3 * ROW_H + 26
MINI_H = 46


def terrain_text(game: Game, square: int) -> str:
    """Symbole d'une case, en texte simple (pour les petites indications)."""
    finish = len(game.track)
    if square < finish:
        return TERRAIN_SYMBOL[game.track.kind(square)]
    return "┃" if square == finish else "░"


def window(game: Game) -> tuple[int, int]:
    """Première et dernière case affichées : on suit le peloton, en gardant le leader visible."""
    finish = len(game.track)
    capacity = (BOARD_W - PAD - 4) // CELL_W
    positions = [r.position for r in game.riders]
    last = max(min(finish + 2, max(positions) + 6), max(positions))
    first = max(0, min(positions) - 1)
    if last - first + 1 > capacity:
        first = max(0, last - capacity + 1)
    last = max(last, min(first + capacity - 1, finish + 2))
    return first, last


def board_primitives(game: Game, current: Optional[Rider] = None) -> list[tuple]:
    finish = len(game.track)
    first, last = window(game)
    prims: list[tuple] = []

    for label, row in (("terrain", 0), ("droite", 1), ("gauche", 2)):
        prims.append(("text", PAD - 8, TOP + row * ROW_H + ROW_H / 2, label, "#607d8b", 10, False, "e"))

    for i, s in enumerate(range(first, last + 1)):
        x0 = PAD + i * CELL_W
        x1 = x0 + CELL_W
        cx = (x0 + x1) / 2
        beyond = s >= finish
        kind = None if beyond else game.track.kind(s)
        fill = BEYOND_FILL if beyond else TERRAIN_FILL[kind]
        for row in range(3):
            prims.append(("rect", x0, TOP + row * ROW_H, x1, TOP + (row + 1) * ROW_H, fill, "#90a4ae", 1))
        if kind is not None:
            prims.append(("text", cx, TOP + ROW_H / 2, TERRAIN_SYMBOL[kind], TERRAIN_SYMBOL_COLOR[kind], 20, True, "center"))
        prims.append(("text", cx, TOP - 12, str(s), "#546e7a", 10, False, "center"))

        for rider in game.riders_at(s):
            cy = TOP + (1 + rider.lane) * ROW_H + ROW_H / 2
            is_current = rider is current
            prims.append((
                "oval", cx - 20, cy - 20, cx + 20, cy + 20, TEAM_FILL[rider.team],
                "#000000" if is_current else "#263238", 4 if is_current else 1,
            ))
            prims.append(("text", cx, cy, rider.name, LABEL_ON_FILL[rider.team], 11, True, "center"))

    if first <= finish <= last + 1:
        x = PAD + (finish - first) * CELL_W
        prims.append(("line", x, TOP - 6, x, TOP + 3 * ROW_H + 6, "#000000", 5))
        prims.append(("text", x, TOP + 3 * ROW_H + 16, "ARRIVÉE", "#000000", 10, True, "center"))
    return prims


MAP_H = 430
MAP_MAX_SCALE = 40  # pixels par unité de longueur (une case = 1)
MAP_MARGIN = 34
MAP_MAX_SQUARES = 26


FULL_VIEW_AFTER_FINISH = 5  # cases grises dessinées après la ligne d'arrivée dans la vue complète


def map_window(game: Game, extra_positions: Iterable[int] = ()) -> tuple[int, int]:
    """Cases affichées en mode zoom : l'arrière du peloton jusqu'un peu devant le leader.

    `extra_positions` ajoute des cases à garder visibles (les départs, pendant une animation)."""
    total = len(game.track) + EXTRA_SQUARES
    positions = [r.position for r in game.riders] + list(extra_positions) or [len(game.track)]
    last = min(max(max(positions) + 5, min(positions) + 12), total - 1)
    first = max(0, min(positions) - 2)
    if last - first + 1 > MAP_MAX_SQUARES:
        first = last - MAP_MAX_SQUARES + 1
    return first, last


def full_window(game: Game, extra_positions: Iterable[int] = ()) -> tuple[int, int]:
    """Tout le parcours, plus quelques cases après la ligne d'arrivée.

    La vue ne s'agrandit que si un coureur dépasse la ligne de plus que ces cases : le zoom reste donc
    identique pendant presque toute la partie."""
    finish = len(game.track)
    furthest = max([r.position for r in game.riders] + list(extra_positions) or [finish])  # Tour : tous arrivés
    after = FULL_VIEW_AFTER_FINISH
    if getattr(game, "tour", False):  # Grand Tour : toute la tuile Chronométrage reste visible
        after = max(after, len(timing_table(game.track)))
    last = max(finish + after - 1, furthest)
    return 0, min(last, finish + EXTRA_SQUARES - 1)


def _grass_stripes(prims: list, width: int, height: int) -> None:
    """Bandes d'herbe tondue, en fond de carte."""
    for x in range(0, width, 120):
        prims.append(("rect", x, 0, min(x + 60, width), height, pal.GRASS_DARK, "", 0))


def _checkered_line(prims: list, squares, finish: int, tr) -> None:
    """Ligne d'arrivée en damier, posée sur le bord avant de la dernière case de course."""
    sq = squares[finish]
    cols, rows = 8, 2
    depth = 0.28  # profondeur du damier, en fraction de case

    def point(u: float, v: float):  # u : de gauche à droite (0..1), v : de l'arrivée vers l'avant (0..depth)
        left = (sq.lb[0] + (sq.lf[0] - sq.lb[0]) * v, sq.lb[1] + (sq.lf[1] - sq.lb[1]) * v)
        right = (sq.rb[0] + (sq.rf[0] - sq.rb[0]) * v, sq.rb[1] + (sq.rf[1] - sq.rb[1]) * v)
        return left[0] + (right[0] - left[0]) * u, left[1] + (right[1] - left[1]) * u

    for r in range(rows):
        for c in range(cols):
            color = "#ffffff" if (r + c) % 2 == 0 else "#111827"
            corners = [point(c / cols, r * depth / rows), point((c + 1) / cols, r * depth / rows),
                       point((c + 1) / cols, (r + 1) * depth / rows), point(c / cols, (r + 1) * depth / rows)]
            prims.append(("poly", [k for p in corners for k in tr(p)], color, color, 1))


def _start_line(prims: list, squares, start: int, tr) -> None:
    """Ligne de départ : un trait blanc sur le bord arrière de la première case de course."""
    sq = squares[start]
    (x0, y0), (x1, y1) = tr(sq.lb), tr(sq.rb)
    prims.append(("line", x0, y0, x1, y1, "#ffffff", 4))


MIN_SCALE = 3.0
MAX_SCALE = 140.0


def map_transform(
    game: Game, zoom: bool = False, window: Optional[tuple[int, int]] = None, width: int = BOARD_W, height: int = MAP_H
) -> tuple[float, float, float]:
    """Cadrage automatique de la carte : (échelle en pixels par case, x et y du centre dans le monde)."""
    squares = layout_squares(game.track)
    first, last = window or (map_window(game) if zoom else full_window(game))
    pts = [p for s in range(first, last + 1) for p in squares[s].corners]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bw, bh = max(xs) - min(xs), max(ys) - min(ys)
    scale = min(
        MAP_MAX_SCALE,
        (width - 2 * MAP_MARGIN) / max(bw, 1e-6),
        (height - 2 * MAP_MARGIN) / max(bh, 1e-6),
    )
    return scale, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def zoom_view(view: tuple[float, float, float], factor: float, px: float, py: float,
              width: int = BOARD_W, height: int = MAP_H) -> tuple[float, float, float]:
    """Nouveau cadrage après un zoom de `factor` centré sur le pixel (px, py) : le point visé ne bouge pas."""
    scale, cx, cy = view
    new_scale = max(MIN_SCALE, min(MAX_SCALE, scale * factor))
    wx, wy = cx + (px - width / 2) / scale, cy - (py - height / 2) / scale
    return new_scale, wx - (px - width / 2) / new_scale, wy + (py - height / 2) / new_scale


def pan_view(view: tuple[float, float, float], dx: float, dy: float) -> tuple[float, float, float]:
    """Cadrage après un glissement de la souris de (dx, dy) pixels."""
    scale, cx, cy = view
    return scale, cx - dx / scale, cy + dy / scale


RELIEF_LIGHT = 0.28  # éclaircissement de la route au point le plus haut du parcours
SHADOW_STEP = 0.9  # pixels d'ombre en plus par case d'altitude (à l'échelle 20 px par case)
CHEVRON_UP = "#6b2a08"  # brun foncé sur l'orange des montées
CHEVRON_DOWN = "#0b3556"  # bleu nuit sur le bleu des descentes


def road_altitudes(track: Track, count: int) -> list[float]:
    """Altitude de dessin de chaque case (0 = point le plus bas), sur `count` cases : au-delà de l'arrivée,
    la route reste à l'altitude de la ligne."""
    heights = elevation(track)
    low = min(heights)
    n = len(track)
    return [((heights[s] + heights[s + 1]) / 2 if s < n else heights[n]) - low for s in range(count)]


def _relief_shadows(prims: list, squares, altitudes: list[float], indices, tr, scale: float) -> None:
    """Ombre portée sous la route, d'autant plus décalée que la case est haute : la route semble sortir du sol
    dans les montées et y redescendre dans les descentes. À dessiner avant la route."""
    unit = max(0.6, min(scale / 20, 2.0))
    for s in indices:
        off = (1.5 + altitudes[s] * SHADOW_STEP) * unit
        pts = [c for p in squares[s].outline for c in tr(p)]
        shifted = [v + (off * 0.6 if i % 2 == 0 else off) for i, v in enumerate(pts)]
        prims.append(("poly", shifted, pal.SHADOW, pal.SHADOW, 1))


def _relief_fill(fill: str, altitude: float, top: float) -> str:
    """Plus la route est haute, plus elle est claire (lumière venue d'en haut)."""
    return _mix(fill, "#ffffff", RELIEF_LIGHT * altitude / top) if top > 0 else fill


def _slope_chevrons(prims: list, squares, square: int, kind: str, tr, width: int) -> None:
    """Chevrons tournés vers l'arrivée : un seul en montée (on grimpe), deux serrés en descente (ça file).

    Repère de point_on_road : la case s va de s − 0,5 à s + 0,5 (s est son centre)."""
    def at(progress: float, lane: float):
        return tr(point_on_road(squares, progress, lane))

    if kind == ASCENT:
        marks = [(square - 0.25, square + 0.25)]
        color = CHEVRON_UP
    else:
        marks = [(square - 0.38, square - 0.05), (square + 0.02, square + 0.35)]
        color = CHEVRON_DOWN
    for back, tip in marks:
        pts = [*at(back, -0.2), *at(tip, 0.5), *at(back, 1.2)]
        prims.append(("path", pts, color, width))


COBBLE_COLOR, COBBLE_STONE, COBBLE_EDGE = "#8b6f47", "#a8916a", "#5c4630"
SUPPLY_COLOR = "#14b8a6"
BREAKAWAY_COLOR = "#d4b84a"  # cases jaunes de la zone d'échappée (tuile 2)
SURFACE_LABEL = {COBBLES: "PAVÉS", SUPPLY: "RAVITO", BREAKAWAY: "ÉCHAPPÉE"}
SURFACE_COLOR = {COBBLES: COBBLE_COLOR, SUPPLY: SUPPLY_COLOR, BREAKAWAY: BREAKAWAY_COLOR}


def _surface_fill(fill: str, surface: str) -> str:
    """Pavés : route brune ; ravitaillement : légère teinte turquoise (extension Peloton)."""
    if surface == COBBLES:
        return _mix(fill, COBBLE_COLOR, 0.6)
    if surface == SUPPLY:
        return _mix(fill, SUPPLY_COLOR, 0.22)
    if surface == BREAKAWAY:
        return _mix(fill, BREAKAWAY_COLOR, 0.45)
    return fill


def _cobble_stones(prims: list, sq, tr, scale: float) -> None:
    """Pavés dessinés sur la case : trois rangées de pierres arrondies."""
    r = max(1.5, 0.08 * scale)
    for u in (0.17, 0.5, 0.83):
        for v in (0.22, 0.5, 0.78):
            back = _lerp_point(sq.rb, sq.lb, v)
            front = _lerp_point(sq.rf, sq.lf, v)
            x, y = tr(_lerp_point(back, front, u))
            prims.append(("oval", x - r, y - r * 0.8, x + r, y + r * 0.8, COBBLE_STONE, COBBLE_EDGE, 1))


def _lerp_point(a, b, f: float):
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def _surface_labels(prims: list, squares, track: Track, indices, tr, scale: float) -> None:
    """Nom de chaque section pavée ou de ravitaillement, posé le long de la route, côté gauche."""
    shown = set(indices)
    s = 0
    while s < len(track):
        surface = track.surface(s)
        if not surface:
            s += 1
            continue
        end = s
        while end < len(track) and track.surface(end) == surface:
            end += 1
        mid = (s + end - 1) // 2
        if mid in shown:
            x, y = tr(point_on_road(squares, mid, squares[mid].lanes + 0.9))
            color = COBBLE_STONE if surface == COBBLES else SURFACE_COLOR[surface]
            prims.append(("text", x, y, SURFACE_LABEL[surface], color, 8 if scale < 15 else 9, True, "center"))
        s = end


JERSEY_GREEN, JERSEY_GREEN_EDGE = "#22c55e", "#14532d"
JERSEY_POLKA, JERSEY_POLKA_DOT, JERSEY_POLKA_EDGE = "#ffffff", "#e11d2e", "#7f1d1d"
JERSEY_YELLOW, JERSEY_YELLOW_EDGE = "#facc15", "#854d0e"
JERSEY_KIND_YELLOW, JERSEY_KIND_GREEN, JERSEY_KIND_POLKA = "jaune", "vert", "pois"  # = tour.YELLOW, GREEN, POLKA
JERSEY_RING = {JERSEY_KIND_YELLOW: JERSEY_YELLOW, JERSEY_KIND_GREEN: JERSEY_GREEN, JERSEY_KIND_POLKA: JERSEY_POLKA_DOT}


TIME_TOKEN_FILL, TIME_TOKEN_EDGE = "#e2e8f0", "#334155"


def time_token_primitives(cx: float, cy: float, r: float, minutes: int) -> list[tuple]:
    """Jeton Temps (Grand Tour) : un petit rond clair marqué du nombre de minutes, « 1' », « 2' »…"""
    return [("oval", cx - r, cy - r, cx + r, cy + r, TIME_TOKEN_FILL, TIME_TOKEN_EDGE, 1),
            ("text", cx, cy, f"{minutes}'", "#0f172a", max(6, int(r * 1.1)), True, "center")]


def worn_jersey_primitives(cx: float, cy: float, radius: float, jersey: str) -> list[tuple]:
    """Grand Tour : le maillot porté par un coureur, en petit, accroché en haut à droite de sa pastille."""
    size = max(13.0, radius * 1.3)
    return jersey_primitives(cx + radius * 0.85, cy - radius * 0.85, size, jersey, None)


def jersey_primitives(cx: float, cy: float, size: float, kind: str, value: Optional[int], dim: bool = False) -> list[tuple]:
    """Petit maillot centré en (cx, cy) : vert pour le Sprint, blanc à pois rouges pour la Montagne, avec au milieu
    la valeur du prochain jeton à gagner. `dim` : pile vide (maillot grisé, sans valeur)."""
    s = size / 2
    # contour d'un maillot vu de face : épaules, manches courtes, col
    shape = [(-0.35, -1.0), (-0.12, -0.82), (0.12, -0.82), (0.35, -1.0), (1.0, -0.62), (0.78, -0.18), (0.55, -0.32),
             (0.55, 1.0), (-0.55, 1.0), (-0.55, -0.32), (-0.78, -0.18), (-1.0, -0.62)]
    points = [c for x, y in shape for c in (cx + x * s, cy + y * s)]
    mountain = kind in (TOKEN_MOUNTAIN, JERSEY_KIND_POLKA)
    fill = JERSEY_POLKA if mountain else JERSEY_GREEN
    edge = JERSEY_POLKA_EDGE if mountain else JERSEY_GREEN_EDGE
    if kind == JERSEY_KIND_YELLOW:
        fill, edge = JERSEY_YELLOW, JERSEY_YELLOW_EDGE
    if dim:
        fill, edge = "#64748b", "#334155"
    prims: list[tuple] = [("poly", points, fill, edge, 2 if size >= 18 else 1)]
    if mountain and not dim:
        r = max(1.2, size * 0.07)
        for dx, dy in ((-0.38, -0.45), (0.38, -0.45), (-0.3, 0.55), (0.3, 0.55), (0.0, 0.05), (-0.62, -0.62),
                       (0.62, -0.62)):
            prims.append(("oval", cx + dx * s - r, cy + dy * s - r, cx + dx * s + r, cy + dy * s + r,
                          JERSEY_POLKA_DOT, "", 0))
    if value is not None and not dim:
        color = "#7f1d1d" if mountain else "#ffffff"
        prims.append(("text", cx, cy + s * 0.12, str(value), color, max(7, int(size * 0.42)), True, "center"))
    return prims


def _token_jerseys(prims: list, squares, tokens, track: Track, shown, tr, scale: float) -> None:
    """Grand Tour : à côté de chaque pile de jetons, un petit maillot avec la valeur du prochain jeton à gagner
    (vert = Sprint, à pois = Montagne), et la suite de la pile en petit."""
    shown = set(shown)
    size = max(16.0, min(30.0, 0.75 * scale))
    for stack in tokens:
        square = min(stack.square, len(squares) - 1)
        if square not in shown:
            continue
        lanes = squares[square].lanes
        x, y = tr(point_on_road(squares, square, lanes + 1.6))
        value = stack.values[0] if stack.values else None
        prims.extend(jersey_primitives(x, y, size, stack.kind, value, dim=not stack.values))
        rest = " · ".join(str(v) for v in stack.values[1:])
        caption = ("puis " + rest) if rest else ("dernier jeton" if stack.values else "plus de jeton")
        prims.append(("text", x, y + size * 0.5 + 8, caption, pal.MUTED, 7, False, "center"))


TIMING_TILE_FILL, TIMING_TILE_EDGE, TIMING_TILE_TEXT = "#0f172a", "#facc15", "#fde68a"


def _timing_tile(prims: list, squares, track: Track, shown, tr, scale: float) -> None:
    """Grand Tour : la tuile Chronométrage écrite dans les cases après la ligne (elles restent vides : les coureurs
    arrivés quittent la piste) : sur chaque case, les secondes que prend un groupe dont le coureur de tête finit là."""
    finish = len(track)
    shown = set(shown)
    font = 7 if scale < 14 else 9 if scale < 24 else 11
    for i, seconds in enumerate(timing_table(track)):
        s = finish + i
        if s not in shown or s >= len(squares):
            continue
        x, y = tr(squares[s].center)
        r = max(6.0, 0.36 * scale)
        prims.append(("oval", x - r, y - r * 0.7, x + r, y + r * 0.7, TIMING_TILE_FILL, TIMING_TILE_EDGE, 1))
        prims.append(("text", x, y, f"+{seconds}", TIMING_TILE_TEXT, font, True, "center"))


def _map_frame(game: Game, zoom: bool, window, width: int, height: int, view):
    """Cadrage de la carte : (cases, première et dernière case dessinées, échelle, passage monde -> pixels)."""
    squares = layout_squares(game.track)
    first, last = window or (map_window(game) if zoom else full_window(game))
    if view is None:
        scale, mx, my = map_transform(game, zoom, window, width, height)
    else:
        scale, mx, my = view
        first, last = 0, min(len(squares) - 1, max([full_window(game)[1]] + [r.position for r in game.riders]))

    def tr(p) -> tuple[float, float]:
        return (width / 2 + (p[0] - mx) * scale, height / 2 - (p[1] - my) * scale)

    return squares, first, last, scale, tr


def _mix(c1: str, c2: str, f: float) -> str:
    """Couleur entre c1 (f = 0) et c2 (f = 1) : sert à simuler la transparence et la profondeur."""
    f = max(0.0, min(1.0, f))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))


def _frac(x: float) -> float:
    return x - math.floor(x)


def map_weather_fx_primitives(
    game: Game,
    t: float,
    zoom: bool = False,
    window: Optional[tuple[int, int]] = None,
    width: int = BOARD_W,
    height: int = MAP_H,
    view: Optional[tuple[float, float, float]] = None,
) -> list[tuple]:
    """Animation de la météo sur la carte, à l'instant `t` (en secondes), dans le même cadrage que map_primitives.

    Pluie : gouttes qui tombent et ronds dans l'eau. Vent arrière / de face : traits qui filent le long de la route,
    vers l'arrivée ou vers le départ. Vent de travers : rafales qui traversent la route sur trois plans (les plus
    proches plus grandes, plus vives et plus rapides) pour donner de la profondeur. Beau temps : un petit soleil."""
    squares, first, last, scale, tr = _map_frame(game, zoom, window, width, height, view)
    px = max(scale, 6.0)  # pixels par case, pour dimensionner les effets
    prims: list[tuple] = []

    def at(progress: float, lane: float) -> tuple[float, float]:
        return tr(point_on_road(squares, progress, lane))

    for k, zone in enumerate(game.weather.zones):
        start, end = max(zone.start, first), min(zone.end, last + 1, len(squares))
        if start >= end:
            continue
        length = end - start
        seed = _frac(k * 0.37)
        if zone.effect == RAIN:
            for d in range(4 * length):
                phase = _frac(d * 0.618 + seed)
                p = start + _frac(d * 0.381 + seed * 3.1) * length
                lane = -0.4 + _frac(d * 0.727 + seed) * 1.8
                x, y = at(p, lane)
                f = _frac(t * 0.9 + phase)
                if f < 0.35:  # la goutte tombe (vue de dessus, en biais vers le bas de l'écran)
                    g = f / 0.35
                    drop = 0.5 * px * (1 - g)
                    prims.append(("line", x - drop * 0.3, y - drop - 3, x - drop * 0.3 + 2, y - drop + 3, FX_RAIN, 1))
                else:  # rond dans l'eau qui s'agrandit et s'efface
                    g = (f - 0.35) / 0.65
                    r = 1.5 + g * 0.22 * px
                    color = _mix(FX_RAIN, pal.TERRAIN_FILL["."], g)
                    prims.append(("oval", x - r, y - r * 0.6, x + r, y + r * 0.6, "", color, 1))
        elif zone.effect in (TAILWIND, HEADWIND):
            direction = 1 if zone.effect == TAILWIND else -1
            color = FX_WIND[zone.effect]
            for d in range(3 * length):
                phase = _frac(d * 0.29 + seed)
                lane = -0.6 + _frac(d * 0.53 + seed) * 2.2
                f = _frac(t * 0.45 + phase)
                head = start + (f if direction > 0 else 1 - f) * length
                tail = head - 0.7 * direction
                if not start <= tail <= end:
                    continue
                (x0, y0), (x1, y1) = at(tail, lane), at(head, lane)
                prims.append(("line", x0, y0, x1, y1, _mix(pal.GRASS, color, 0.5 + 0.5 * math.sin(f * math.pi)), 2))
        elif zone.effect == CROSSWIND:
            color = FX_WIND[CROSSWIND]
            for depth in (0.35, 0.65, 1.0):  # trois plans : du plus loin au plus proche
                for d in range(max(2, int(length * 1.5))):
                    phase = _frac(d * 0.41 + depth * 0.77 + seed)
                    p = start + (d + 0.5) / max(2, int(length * 1.5)) * length
                    f = _frac(t * (0.25 + 0.45 * depth) + phase)
                    lane = 2.6 - f * 4.0  # de la gauche de la route vers la droite
                    streak = 0.35 + 0.6 * depth
                    (x0, y0), (x1, y1) = at(p, lane + streak), at(p, lane)
                    lift = (1 - depth) * 0.18 * px  # les plans lointains un peu plus haut : effet de perspective
                    fade = math.sin(f * math.pi)
                    prims.append(("line", x0, y0 - lift, x1, y1 - lift, _mix(pal.GRASS, color, (0.3 + 0.7 * depth) * fade),
                                  1 if depth < 0.5 else 2 if depth < 0.9 else 3))
        elif zone.effect == SUNNY:
            cx, cy = at(start + length / 2, 2.8)
            r = max(4.0, min(9.0, 0.22 * px))
            prims.append(("oval", cx - r, cy - r, cx + r, cy + r, FX_SUN, FX_SUN, 1))
            for ray in range(8):
                a = t * 0.8 + ray * math.pi / 4
                prims.append(("line", cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2),
                              cx + math.cos(a) * (r + 2 + r * 0.7), cy + math.sin(a) * (r + 2 + r * 0.7), FX_SUN, 2))
    return prims


def map_primitives(
    game: Game,
    current: Optional[Rider] = None,
    positions: Optional[dict] = None,
    zoom: bool = False,
    window: Optional[tuple[int, int]] = None,
    width: int = BOARD_W,
    height: int = MAP_H,
    view: Optional[tuple[float, float, float]] = None,
) -> list[tuple]:
    """La route en 2D, virages compris : le parcours entier, ou un zoom qui suit le peloton.

    `view` = (échelle, x, y) impose un cadrage manuel (zoom à la molette, glissement) ; sinon cadrage automatique.
    `positions` donne, pour une animation, la position intermédiaire de certains coureurs :
    {coureur: (case fractionnaire, couloir fractionnaire)}. Les autres restent à leur place.
    Formes supplémentaires : ("poly", [x0, y0, x1, y1, ...], remplissage, contour, épaisseur).
    """
    track = game.track
    finish = len(track)
    squares, first, last, scale, tr = _map_frame(game, zoom, window, width, height, view)

    def flat(points) -> list[float]:
        return [c for p in points for c in tr(p)]

    number_every = 1 if scale >= 15 else 5  # sur une grande carte, on ne numérote qu'une case sur cinq
    prims: list[tuple] = [("rect", 0, 0, width, height, pal.GRASS, "", 0)]
    _grass_stripes(prims, width, height)

    def visible(s: int) -> bool:
        if view is None:
            return True
        px, py = zip(*(tr(c) for c in squares[s].corners))  # cadrage manuel : rien hors du cadre
        return not (max(px) < -40 or min(px) > width + 40 or max(py) < -40 or min(py) > height + 40)

    shown = [s for s in range(first, last + 1) if visible(s)]
    altitudes = road_altitudes(track, len(squares))
    top = max(altitudes) if altitudes else 0.0
    _relief_shadows(prims, squares, altitudes, shown, tr, scale)
    for s in shown:
        sq = squares[s]
        beyond = s >= finish
        kind = None if beyond else track.kind(s)
        fill = _relief_fill(BEYOND_FILL if beyond else TERRAIN_FILL[kind], altitudes[s], top)
        surface = "" if beyond else track.surface(s)
        prims.append(("poly", flat(sq.outline), _surface_fill(fill, surface), pal.ROAD_OUTLINE, 1))
        if surface == COBBLES and scale >= 10:
            _cobble_stones(prims, sq, tr, scale)
        # lignes blanches sur les bords de la route (en arc dans les virages)
        for path in (sq.left_path, sq.right_path):
            prims.append(("path", flat(path), pal.ROAD_EDGE, 2 if scale >= 12 else 1))
        # traits entre les files (aucun sur les pavés à une file, deux au ravitaillement)
        for path in sq.lane_lines:
            prims.append(("path", flat(path), pal.LANE_LINE, 1))
        cx, cy = tr(sq.center)
        if s % number_every == 0:
            # numéro de case, posé à l'extérieur de la route (côté droit)
            rx, ry = tr(((sq.rb[0] + sq.rf[0]) / 2, (sq.rb[1] + sq.rf[1]) / 2))
            ox, oy = rx - cx, ry - cy
            norm = max((ox * ox + oy * oy) ** 0.5, 1e-6)
            prims.append(("text", rx + ox / norm * 11, ry + oy / norm * 11, str(s), pal.SQUARE_NUMBER, 8, False, "center"))

    if scale >= 9:  # chevrons de pente, au-dessus de toutes les cases
        for s in shown:
            if s < finish and track.kind(s) != NORMAL:
                _slope_chevrons(prims, squares, s, track.kind(s), tr, 3 if scale >= 25 else 2)
    _surface_labels(prims, squares, track, shown, tr, scale)
    if getattr(game, "tokens", None):
        _token_jerseys(prims, squares, game.tokens, track, shown, tr, scale)
    if getattr(game, "tour", False):
        _timing_tile(prims, squares, track, shown, tr, scale)
    if track.start and first <= track.start <= last:
        _start_line(prims, squares, track.start, tr)
    if first <= finish <= last + 1:
        _checkered_line(prims, squares, finish, tr)
        lb, rb = finish_edge(squares, track)
        (x0, y0), (x1, y1) = tr(lb), tr(rb)
        prims.append(("text", (x0 + x1) / 2, min(y0, y1) - 16, "ARRIVÉE", "#ffffff", 10, True, "center"))

    _weather_panels(prims, squares, game.weather, first, last, tr, scale)

    where = {r: (r.position, r.lane) for r in game.riders}
    if positions:
        where.update(positions)
    radius = max(7.5, min(24, 0.32 * scale))
    font_size = 8 if radius < 9 else 9 if radius < 11 else 11 if radius < 16 else 14
    crash_labels: set[int] = set()
    for rider in sorted(game.riders, key=lambda r: where[r][0]):  # ceux de derrière d'abord, devant par-dessus
        progress, lane = where[rider]
        cx, cy = tr(point_on_road(squares, progress, lane))
        is_current = rider is current
        prims.append(("oval", cx - radius + 1.5, cy - radius + 3, cx + radius + 1.5, cy + radius + 3, pal.SHADOW, "", 0))
        if is_current:  # halo doré autour du coureur qui choisit
            prims.append(("oval", cx - radius - 4, cy - radius - 4, cx + radius + 4, cy + radius + 4, "", pal.CURRENT_RING, 3))
        if rider.crashed and rider not in (positions or {}):  # à terre : couché (aplati), cerclé de rouge
            h = radius * 0.6
            prims.append(("oval", cx - radius, cy - h, cx + radius, cy + h, TEAM_FILL[rider.team], pal.CRASH_MARK, 3))
            prims.append(("text", cx, cy, rider.name, LABEL_ON_FILL[rider.team], max(font_size - 1, 7), True, "center"))
            if rider.position not in crash_labels:  # une seule étiquette par case
                crash_labels.add(rider.position)
                lx, ly = tr(point_on_road(squares, rider.position, -1.3))  # côté droit, sous les coureurs
                prims.append(("text", lx, ly, "CHUTE", pal.CRASH_MARK, 8, True, "center"))
            continue
        prims.append(("oval", cx - radius, cy - radius, cx + radius, cy + radius, TEAM_FILL[rider.team], pal.RIDER_OUTLINE, 2))
        prims.append(("text", cx, cy, rider.name, LABEL_ON_FILL[rider.team], font_size, True, "center"))
        jersey = getattr(game, "jerseys", {}).get(rider)
        if jersey:
            prims.extend(worn_jersey_primitives(cx, cy, radius, jersey))
        minutes = getattr(game, "minutes", {}).get(rider, 0) if getattr(game, "tour", False) else 0
        if minutes:  # Grand Tour : jetons Temps d'une minute déjà pris, en bas à gauche de la pastille
            prims.extend(time_token_primitives(cx - radius * 0.85, cy + radius * 0.85, max(6.0, radius * 0.55), minutes))
    return prims


WEATHER_PANEL = (0.12, 0.5)  # bande du panneau météo : de 0,12 à 0,5 case à l'extérieur du bord gauche


def _weather_panels(prims: list, squares, weather: Weather, first: int, last: int, tr, scale: float) -> None:
    """Panneaux météo (extension) : une bande colorée le long du bord gauche de la route (le droit porte les
    numéros de case), et leur nom."""
    for zone in weather.effects:
        shown = [s for s in range(zone.start, zone.end) if first <= s <= last and s < len(squares)]
        if not shown:
            continue
        fill = pal.WEATHER_FILL[zone.effect]
        for s in shown:
            sq = squares[s]
            pts = []
            for edge, other in ((sq.lb, sq.rb), (sq.lf, sq.rf)):
                dx, dy = edge[0] - other[0], edge[1] - other[1]
                norm = max((dx * dx + dy * dy) ** 0.5, 1e-6)
                pts.append([(edge[0] + dx / norm * d, edge[1] + dy / norm * d) for d in WEATHER_PANEL])
            (b0, b1), (f0, f1) = pts
            prims.append(("poly", [c for p in (b0, f0, f1, b1) for c in tr(p)], fill, "#ffffff", 1))
        mid = squares[shown[len(shown) // 2]]
        dx, dy = mid.lb[0] - mid.rb[0], mid.lb[1] - mid.rb[1]
        norm = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        out = 0.9 if scale >= 15 else 1.4
        px, py = tr((mid.lb[0] + dx / norm * out, mid.lb[1] + dy / norm * out))
        prims.append(("text", px, py, WEATHER_SHORT[zone.effect], fill if zone.effect != "pluie" else "#cbd5e1", 8, True, "center"))


PREVIEW_MARGIN = 78  # laisse la place aux étiquettes DÉPART et ARRIVÉE autour de la route
PREVIEW_MAX_SCALE = 60
SELECTED_COLOR = "#ffd24a"


def _preview(
    track: Track,
    finish_square: Optional[int],
    width: int,
    height: int,
    ranges: Optional[Sequence[range]] = None,
    selected: Optional[int] = None,
    start_label: bool = True,
) -> list[tuple]:
    """Dessin d'un parcours entier. `ranges` (cases de chaque tuile) ajoute les pastilles numérotées."""
    squares = layout_squares(track, extra=0)
    # les deux cases du milieu d'une tuile portent sa pastille numérotée
    badge_pairs = [(r[len(r) // 2 - 1], r[len(r) // 2]) for r in ranges or () if len(r) >= 2]
    under_badges = {s for pair in badge_pairs for s in pair}

    pts = [p for sq in squares for p in sq.corners]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bw, bh = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
    scale = min(
        PREVIEW_MAX_SCALE,
        (width - 2 * PREVIEW_MARGIN) / bw,
        (height - 2 * PREVIEW_MARGIN) / bh,
    )
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def tr(p) -> tuple[float, float]:
        return (width / 2 + (p[0] - mx) * scale, height / 2 - (p[1] - my) * scale)

    def flat(points) -> list[float]:
        return [c for p in points for c in tr(p)]

    prims: list[tuple] = [("rect", 0, 0, width, height, pal.GRASS, "", 0)]
    race = Track(track.layout[:finish_square], track.angles[:finish_square], track.start) if finish_square else track
    altitudes = road_altitudes(race, len(squares))
    top = max(altitudes) if altitudes else 0.0
    _relief_shadows(prims, squares, altitudes, range(len(squares)), tr, scale)
    for s, sq in enumerate(squares):
        beyond = finish_square is not None and s >= finish_square
        kind = track.kind(s)
        fill = _relief_fill(BEYOND_FILL if beyond else TERRAIN_FILL[kind], altitudes[s], top)
        surface = "" if beyond else track.surface(s)
        prims.append(("poly", flat(sq.outline), _surface_fill(fill, surface), pal.ROAD_OUTLINE, 1))
        if surface == COBBLES and scale >= 14:
            _cobble_stones(prims, sq, tr, scale)
        for path in (sq.left_path, sq.right_path):
            prims.append(("path", flat(path), pal.ROAD_EDGE, 2 if scale >= 12 else 1))

    if scale >= 9:  # chevrons de pente, au-dessus de toutes les cases (pas sous les pastilles de tuile)
        for s in range(len(squares)):
            beyond = finish_square is not None and s >= finish_square
            if not beyond and track.kind(s) != NORMAL and s not in under_badges:
                _slope_chevrons(prims, squares, s, track.kind(s), tr, 2)

    if ranges:
        if selected is not None and 0 <= selected < len(ranges):
            for s in ranges[selected]:
                prims.append(("poly", flat(squares[s].outline), "", SELECTED_COLOR, 3))
        # numéro de chaque tuile, dans une pastille posée au milieu de la tuile
        for i, (sa, sb) in enumerate(badge_pairs):
            (ax, ay), (bx, by) = tr(squares[sa].center), tr(squares[sb].center)
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            chosen = i == selected
            prims.append(("oval", cx - 10, cy - 10, cx + 10, cy + 10, SELECTED_COLOR if chosen else "#0f172a", "#ffffff", 2))
            prims.append(("text", cx, cy, str(i + 1), "#111827" if chosen else "#ffffff", 9, True, "center"))

    def label_near_edge(square: int, text: str) -> None:
        """Étiquette posée à côté du bord arrière d'une case (côté gauche de la route)."""
        sq = squares[square]
        (lx, ly), (rx, ry) = tr(sq.lb), tr(sq.rb)
        mx_, my_ = (lx + rx) / 2, (ly + ry) / 2
        dx, dy = lx - mx_, ly - my_
        norm = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        x = min(max(lx + dx / norm * 38, 40), width - 40)  # l'étiquette reste toujours dans le cadre
        y = min(max(ly + dy / norm * 38, 14), height - 14)
        prims.append(("text", x, y, text, "#ffffff", 10, True, "center"))

    if start_label:
        if track.start:
            _start_line(prims, squares, track.start, tr)
        label_near_edge(track.start, "DÉPART")
    if finish_square is not None:
        _checkered_line(prims, squares, finish_square, tr)
        label_near_edge(finish_square, "ARRIVÉE")
    return prims


def plan_preview_primitives(tiles: Sequence[Tile], width: int, height: int, selected: Optional[int] = None) -> list[tuple]:
    """Le parcours en tuiles, vu de dessus, pour l'éditeur : tuiles numérotées, tuile sélectionnée entourée."""
    if not tiles:
        return [("text", width / 2, height / 2, "Ajoute des tuiles pour voir le parcours", pal.MUTED, 13, False, "center")]
    return _preview(full_track(tiles), finish_square(tiles), width, height, tile_ranges(tiles), selected,
                    tiles[0].kind == KIND_START)


def track_preview_primitives(track: Track, width: int, height: int) -> list[tuple]:
    """Aperçu d'un parcours quelconque (pour le menu), avec un peu de route après l'arrivée."""
    extended = Track(track.layout + NORMAL * 5, track.angles, track.start)
    return _preview(extended, len(track), width, height)


def minimap_primitives(game: Game) -> list[tuple]:
    """Toute la course en petit, avec un cadre autour de la partie affichée en grand."""
    finish = len(game.track)
    end = max([finish + 3] + [r.position + 1 for r in game.riders])
    x0 = 10
    w = min(18, (BOARD_W - 20) // end)
    prims: list[tuple] = []
    for s in range(end):
        fill = BEYOND_FILL if s >= finish else TERRAIN_FILL[game.track.kind(s)]
        prims.append(("rect", x0 + s * w, 28, x0 + (s + 1) * w, 40, fill, "#90a4ae", 1))
    prims.append(("line", x0 + finish * w, 24, x0 + finish * w, 44, "#000000", 3))
    for r in game.riders:
        cx = x0 + r.position * w + w / 2
        cy = 10 + r.lane * 10
        prims.append(("oval", cx - 5, cy - 5, cx + 5, cy + 5, TEAM_FILL[r.team], "#263238", 1))
    first, last = window(game)
    prims.append(("rect", x0 + first * w, 2, x0 + (last + 1) * w, 44, "", "#455a64", 2))
    return prims


# --------------------------------------------------------------- profil d'une étape

PROFILE_PAD_X = 36
PROFILE_PAD_TOP = 34  # de la place pour le titre au-dessus des badges de col
PROFILE_TITLE_Y, PROFILE_TITLE_BOTTOM = 6, 14  # ligne du titre « Profil : … » et son bas
PROFILE_PAD_BOTTOM = 22
PROFILE_MAX_UNIT = 9  # pixels de hauteur par case de montée
PROFILE_SIZE_JITTER = 0.10  # ±10 % sur la taille des montées et descentes (décor)
PROFILE_BUMP = 0.45  # amplitude des petits accidents, en cases de dénivelé (décor)


def elevation(track: Track) -> list[int]:
    """Altitude relative au début de chaque case (+1 par case de montée, -1 par case de descente) ; longueur n+1."""
    heights = [0]
    for s in range(len(track)):
        kind = track.kind(s)
        heights.append(heights[-1] + (1 if kind == ASCENT else -1 if kind == DESCENT else 0))
    return heights


def cosmetic_elevation(track: Track) -> list[float]:
    """Altitudes « de décor » pour dessiner le profil : purement visuelles, la règle ne s'en sert jamais.

    Chaque montée ou descente est allongée ou raccourcie d'au plus 10 %, et de petits accidents (bosses,
    creux) animent la route. Le résultat ne dépend que du tracé : le profil ne change pas d'un affichage à l'autre."""
    rng = random.Random(zlib.crc32(f"{track.layout}|{track.angles}".encode()))
    n = len(track)
    factor, previous = 1.0, None
    base = [0.0]
    for s in range(n):
        kind = track.kind(s)
        if kind != previous:  # nouvelle montée / descente : sa taille varie de ±10 %
            factor = rng.uniform(1 - PROFILE_SIZE_JITTER, 1 + PROFILE_SIZE_JITTER)
            previous = kind
        step = (1 if kind == ASCENT else -1 if kind == DESCENT else 0) * factor
        base.append(base[-1] + step)
    noise = [rng.uniform(-PROFILE_BUMP, PROFILE_BUMP) for _ in range(n + 1)]
    smooth = [(noise[max(i - 1, 0)] + 2 * noise[i] + noise[min(i + 1, n)]) / 4 for i in range(n + 1)]
    smooth[0] = 0.0
    return [b + w for b, w in zip(base, smooth)]


CLIMB_CATEGORIES = [(10, "HC"), (7, "1"), (5, "2"), (3, "3"), (1, "4")]  # (cases de montée min., nom)
BADGE_FILL = "#e11d2e"
BADGE_ANGLE = 12  # inclinaison des badges de col, en degrés
GROUP_COLORS = {"TÊTE": "#fde047", "TÊTE · PELOTON": "#fde047", "PELOTON": "#ffffff", "LANTERNE ROUGE": "#ff4d4f"}


def climb_category(length: int) -> str:
    """Catégorie d'un col selon son nombre de cases de montée : "4" (petit) à "1", puis "HC" (hors catégorie)."""
    for minimum, name in CLIMB_CATEGORIES:
        if length >= minimum:
            return name
    raise ValueError("Un col a au moins une case de montée.")


def climbs(track: Track) -> list[tuple[int, int, str]]:
    """Les cols du parcours : (première case de montée, case juste après le sommet, catégorie)."""
    found, s, n = [], 0, len(track)
    while s < n:
        if track.kind(s) != ASCENT:
            s += 1
            continue
        end = s
        while end < n and track.kind(end) == ASCENT:
            end += 1
        found.append((s, end, climb_category(end - s)))
        s = end
    return found


def race_groups(riders: Sequence[Rider]) -> list[list[Rider]]:
    """Les groupes de la course, de la tête vers l'arrière : des coureurs sur des cases qui se suivent sans trou."""
    groups: list[list[Rider]] = []
    for rider in sorted(riders, key=lambda r: (-r.position, r.lane)):
        if groups and groups[-1][-1].position - rider.position <= 1:
            groups[-1].append(rider)
        else:
            groups.append([rider])
    return groups


FOLLOW_PELOTON, FOLLOW_HEAD = "peloton", "tete"
FOLLOW_MIN_SQUARES = 14  # un zoom de suivi montre au moins ces cases (sinon la carte serait trop grossie)


def follow_window(game: Game, which: str) -> Optional[tuple[int, int]]:
    """Cases à cadrer pour suivre un groupe : `FOLLOW_PELOTON` (le plus gros groupe, à égalité le plus en avant)
    ou `FOLLOW_HEAD` (la tête de course). None s'il n'y a plus de coureur en course."""
    groups = race_groups(game.riders)
    if not groups:
        return None
    group = groups[0] if which == FOLLOW_HEAD else max(groups, key=len)
    back = min(r.position for r in group)
    front = max(r.position for r in group)
    first, last = max(0, back - 3), front + 6  # un peu de route devant, pour voir où ils vont
    if last - first + 1 < FOLLOW_MIN_SQUARES:
        extra = FOLLOW_MIN_SQUARES - (last - first + 1)
        first = max(0, first - extra // 2)
        last = first + FOLLOW_MIN_SQUARES - 1
    total = len(layout_squares(game.track))
    return max(0, min(first, total - FOLLOW_MIN_SQUARES)), min(last, total - 1)


def follow_view(game: Game, which: str, width: int = BOARD_W, height: int = MAP_H):
    """Cadrage (échelle, x, y) qui suit le peloton ou la tête de course ; None si personne n'est en course."""
    window = follow_window(game, which)
    return None if window is None else map_transform(game, window=window, width=width, height=height)


def group_labels(riders: Sequence[Rider]) -> list[tuple[str, list[Rider]]]:
    """Les groupes à nommer : la tête de course, le peloton (le plus gros groupe) et la lanterne rouge (le dernier)."""
    groups = race_groups(riders)
    if not groups:
        return []
    if len(groups) == 1:
        return [("PELOTON", groups[0])]
    peloton = max(groups, key=len)  # à égalité, le plus en avant
    if len(peloton) < 2:
        peloton = None
    labels = [("TÊTE · PELOTON" if peloton is groups[0] else "TÊTE", groups[0])]
    if peloton is not None and peloton is not groups[0]:
        labels.append(("PELOTON", peloton))
    labels.append(("LANTERNE ROUGE", [groups[-1][-1]]))
    return labels


def _badge_points(cx: float, cy: float, w: float, h: float, r: float, angle: float) -> list[float]:
    """Rectangle aux coins arrondis, incliné de `angle` degrés (sens inverse des aiguilles d'une montre)."""
    corners = [(w / 2 - r, h / 2 - r, 0), (-(w / 2 - r), h / 2 - r, 90), (-(w / 2 - r), -(h / 2 - r), 180), (w / 2 - r, -(h / 2 - r), 270)]
    pts = []
    for ox, oy, start in corners:
        for k in range(5):
            a = math.radians(start + k * 22.5)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    t = math.radians(angle)
    out = []
    for x, y in pts:  # y vers le haut dans ce calcul, vers le bas à l'écran
        rx, ry = x * math.cos(t) - y * math.sin(t), x * math.sin(t) + y * math.cos(t)
        out += [cx + rx, cy - ry]
    return out


def _profile_frame(track: Track, width: int, height: int):
    """Repère du profil : (altitudes de décor, ligne du bas, x d'une case, y d'une altitude, y de la route à une case)."""
    n = len(track)
    heights = cosmetic_elevation(track)  # altitudes de décor ; les chiffres affichés restent ceux du vrai relief
    low, high = min(heights), max(heights)
    plot_w = width - 2 * PROFILE_PAD_X
    plot_h = height - PROFILE_PAD_TOP - PROFILE_PAD_BOTTOM
    unit = min(PROFILE_MAX_UNIT, plot_h / max(high - low, 6))
    base = height - PROFILE_PAD_BOTTOM  # ligne de référence du bas
    sx = plot_w / max(n, 1)

    def x_of(i: float) -> float:
        return PROFILE_PAD_X + i * sx

    def y_of(h: float) -> float:
        return base - (h - low) * unit - 4  # 4 px de socle même à l'altitude minimale

    def y_at(square: float) -> float:
        i = max(0, min(n, int(square)))
        j = min(n, i + 1)
        f = max(0.0, min(1.0, square - i))
        return y_of(heights[i] + (heights[j] - heights[i]) * f)

    return heights, base, x_of, y_of, y_at


FX_RAIN = "#93c5fd"
FX_WIND = {TAILWIND: "#fde68a", HEADWIND: "#bae6fd", CROSSWIND: "#bbf7d0"}
FX_SUN = "#fcd34d"


def weather_fx_primitives(track: Track, weather: Weather, width: int, height: int, t: float) -> list[tuple]:
    """Animation de la météo sur le profil, à l'instant `t` (en secondes) : pluie qui tombe, vent qui souffle
    (vers l'arrivée pour le vent arrière, vers le départ pour le vent de face, en travers pour le vent de travers),
    petit soleil sur les lignes droites « beau temps ». Purement décoratif."""
    n = len(track)
    _heights, _base, x_of, _y_of, y_at = _profile_frame(track, width, height)
    top = PROFILE_PAD_TOP - 6
    prims: list[tuple] = []
    for k, zone in enumerate(weather.zones):
        x0, x1 = x_of(zone.start), x_of(min(zone.end, n))
        w = max(x1 - x0, 1.0)
        seed = (k * 0.37) % 1.0
        if zone.effect == RAIN:  # gouttes en biais qui tombent jusqu'à la route
            for d in range(max(6, int(w / 7))):
                phase = (d * 0.618 + seed) % 1.0
                x = x0 + (d + 0.5) * w / max(6, int(w / 7))
                ground = y_at(zone.start + (x - x0) / w * (min(zone.end, n) - zone.start))
                y = top + ((t * 1.6 + phase) % 1.0) * max(ground - top - 4, 1)
                prims.append(("line", x, y, x - 2, y + 6, FX_RAIN, 1))
        elif zone.effect in FX_WIND:  # traits de vent qui glissent au-dessus de la route
            direction = {TAILWIND: 1, HEADWIND: -1, CROSSWIND: 0}[zone.effect]
            for d in range(4):
                phase = (d * 0.29 + seed) % 1.0
                ground = min(y_at(s + 0.5) for s in range(zone.start, min(zone.end, n)))
                level = ground - 8 - d * 6
                if direction:
                    f = (t * 0.7 + phase) % 1.0
                    x = x0 + (f if direction > 0 else 1 - f) * w
                    tail = x - 10 * direction
                    prims.append(("line", max(min(tail, x1), x0), level, max(min(x, x1), x0), level, FX_WIND[zone.effect], 2))
                    prims.append(("line", x, level, x - 3 * direction, level - 2, FX_WIND[zone.effect], 1))
                else:  # vent de travers : des rafales qui viennent vers nous (elles grossissent et s'éclairent)
                    for g in range(2):
                        f = _frac(t * 0.55 + phase + g * 0.5)
                        cx = x0 + _frac(d * 0.31 + g * 0.47 + seed) * w
                        cy = ground - 10 - _frac(d * 0.59 + g * 0.23) * 22 + f * 8
                        size = 2 + 10 * f
                        color = _mix(pal.CARD, FX_WIND[zone.effect], math.sin(f * math.pi))
                        prims.append(("line", cx - size, cy - size * 0.25, cx + size, cy + size * 0.25, color,
                                      1 if f < 0.4 else 2 if f < 0.75 else 3))
        elif zone.effect == SUNNY:  # petit soleil dont les rayons tournent
            cx = (x0 + x1) / 2
            cy = min(y_at(s + 0.5) for s in range(zone.start, min(zone.end, n))) - 16
            r = 4.5
            prims.append(("oval", cx - r, cy - r, cx + r, cy + r, FX_SUN, FX_SUN, 1))
            for ray in range(8):
                a = t * 0.8 + ray * math.pi / 4
                prims.append(("line", cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2),
                              cx + math.cos(a) * (r + 5), cy + math.sin(a) * (r + 5), FX_SUN, 1))
    return prims


def profile_primitives(
    track: Track,
    width: int,
    height: int,
    marker: Optional[float] = None,
    riders: Optional[Sequence[Rider]] = None,
    weather: Optional[Weather] = None,
    tokens: Optional[Sequence[TokenStack]] = None,
    jerseys: Optional[dict] = None,
) -> list[tuple]:
    """Profil de l'étape (vue de côté) : montées en orange, descentes en bleu, plat en gris, cols catégorisés.

    `marker` (une case, éventuellement fractionnaire) dessine un trait pour situer un coureur.
    `riders` place les coureurs sur le profil et nomme la tête de course, le peloton et la lanterne rouge."""
    n = len(track)
    heights, base, x_of, y_of, y_at = _profile_frame(track, width, height)

    prims: list[tuple] = []
    fills = pal.PROFILE_FILL
    for s in range(n):
        x0, x1 = x_of(s), x_of(s + 1)
        prims.append(("poly", [x0, base, x0, y_of(heights[s]), x1, y_of(heights[s + 1]), x1, base], fills[track.kind(s)], fills[track.kind(s)], 1))
    for s in range(n):  # trait du dessus
        prims.append(("line", x_of(s), y_of(heights[s]), x_of(s + 1), y_of(heights[s + 1]), pal.PROFILE_LINE, 2))
    prims.append(("line", PROFILE_PAD_X, base, x_of(n), base, pal.FAINT, 1))
    step = 10 if n > 40 else 5
    for s in range(0, n + 1, step):
        prims.append(("line", x_of(s), base, x_of(s), base + 4, pal.FAINT, 1))
        prims.append(("text", x_of(s), base + 13, str(s), pal.MUTED, 8, False, "center"))
    if track.start:
        prims.append(("line", x_of(track.start), y_at(track.start) - 8, x_of(track.start), base, "#ffffff", 2))
    prims.append(("line", x_of(n), PROFILE_PAD_TOP - 4, x_of(n), base, "#ffffff", 3))
    prims.append(("text", x_of(n), PROFILE_PAD_TOP - 12, "ARRIVÉE", "#ffffff", 8, True, "center"))
    climb = sum(1 for s in range(n) if track.kind(s) == ASCENT)
    drop = sum(1 for s in range(n) if track.kind(s) == DESCENT)
    title = f"Profil : {climb} cases de montée ▲  ·  {drop} cases de descente ▼"
    if weather:
        title += "  ·  Météo : " + (", ".join(WEATHER_SHORT[z.effect].lower() for z in weather.effects) or "beau temps")
        for zone in weather.effects:  # bande colorée sous l'axe, à l'endroit de chaque panneau
            prims.append(("rect", x_of(zone.start), base + 1, x_of(min(zone.end, n)), base + 5,
                          pal.WEATHER_FILL[zone.effect], "#ffffff", 1))
    for s in range(n):  # extension Peloton : pavés (brun) et ravitaillement (turquoise) sous l'axe
        surface = track.surface(s)
        if surface:
            color = SURFACE_COLOR[surface]
            prims.append(("rect", x_of(s), base + 6, x_of(s + 1), base + 9, color, color, 1))
    if any(track.surface(s) == COBBLES for s in range(n)):
        title += "  ·  pavés"
    if any(track.surface(s) == SUPPLY for s in range(n)):
        title += "  ·  ravitaillement"
    prims.append(("text", PROFILE_PAD_X, PROFILE_TITLE_Y, title, pal.MUTED, 9, True, "w"))
    title_right = PROFILE_PAD_X + 6.5 * len(title)  # largeur approchée du titre (police 9 grasse)

    # badge rouge incliné au sommet de chaque col, avec sa catégorie
    boxes: list[tuple[float, float, float]] = []  # (gauche, droite, milieu en y) des étiquettes déjà posées
    for _first, top, category in climbs(track):
        bw, bh = (24, 15) if category == "HC" else (17, 15)
        cx = x_of(top)
        if top >= n:  # arrivée au sommet : le badge se met à gauche de la ligne d'arrivée
            cx -= bw / 2 + 30  # laisse la place à l'étiquette ARRIVÉE
        t = math.radians(BADGE_ANGLE)
        half_w = (bw * math.cos(t) + bh * math.sin(t)) / 2  # demi-encombrement du badge incliné
        half_h = (bw * math.sin(t) + bh * math.cos(t)) / 2
        cx = min(max(cx, half_w + 2), width - half_w - 2)
        cy = max(y_of(heights[top]) - half_h - 2, half_h + 2)
        if cx - half_w < title_right:  # sous le titre : le badge descend juste en dessous (posé sur le sommet)
            cy = max(cy, PROFILE_TITLE_BOTTOM + half_h + 1)
        boxes.append((cx - half_w, cx + half_w, cy))
        prims.append(("poly", _badge_points(cx, cy, bw, bh, 4, BADGE_ANGLE), BADGE_FILL, "#ffffff", 1))
        prims.append(("text", cx, cy, category, "#ffffff", 7, True, "center", BADGE_ANGLE))

    if marker is not None:
        m = max(0.0, min(float(n), marker))
        prims.append(("line", x_of(m), PROFILE_PAD_TOP, x_of(m), base, pal.ACCENT, 2))
        prims.append(("oval", x_of(m) - 4, PROFILE_PAD_TOP - 4, x_of(m) + 4, PROFILE_PAD_TOP + 4, pal.ACCENT, "#ffffff", 1))

    for stack in tokens or ():  # Grand Tour : petit maillot au-dessus de chaque pile de jetons
        x = min(x_of(min(stack.square, n)) + 22, width - 10)  # à droite du badge de col éventuel
        y = max(12.0, y_at(min(stack.square, n)) - 14)
        prims.extend(jersey_primitives(x, y, 16, stack.kind, stack.values[0] if stack.values else None,
                                       dim=not stack.values))

    if riders:
        # les groupes nommés, écrits au-dessus des coureurs ; une étiquette qui en chevaucherait une autre
        # (ou un badge de col) monte d'un cran
        for name, members in group_labels(riders):
            front, back = members[0].position, members[-1].position
            x0, x1 = x_of(back), x_of(min(front + 1, n))
            color = GROUP_COLORS[name]
            text = f"{name} · {members[0].name}" if name == "LANTERNE ROUGE" else f"{name} ({len(members)})"
            half = len(text) * 2.6 + 4
            mid = min(max((x0 + x1) / 2, half + 2), width - half - 2)
            lo, hi = min(back, n), min(front, n)  # un coureur peut avoir dépassé la ligne d'arrivée
            y = min(y_at(min(p + 0.5, n)) for p in range(lo, hi + 1)) - 26
            while any(abs(y + 3 - by) < 14 and mid - half < bx1 and bx0 < mid + half for bx0, bx1, by in boxes):
                y -= 11
            y = max(y, 6)
            boxes.append((mid - half, mid + half, y))
            prims.append(("line", x0, y + 6, x1, y + 6, color, 2))
            prims.append(("text", mid, y, text, color, 7, True, "center"))
        # chaque coureur : une pastille à la couleur de son équipe, posée sur la route
        for rider in riders:
            x = x_of(min(rider.position + 0.5, n))
            y = y_at(min(rider.position + 0.5, n)) - 5 - 7 * rider.lane
            jersey = (jerseys or {}).get(rider)
            if jersey:  # Grand Tour : un anneau à la couleur du maillot porté
                prims.append(("oval", x - 6.5, y - 6.5, x + 6.5, y + 6.5, "", JERSEY_RING[jersey], 2.5))
            prims.append(("oval", x - 4, y - 4, x + 4, y + 4, TEAM_FILL[rider.team], "#ffffff", 1))
    return prims


# ------------------------------------------------------------ petite carte de tuile

CARD_PAD = 6
CARD_LETTER_W = 18  # bande de gauche qui porte la lettre de la tuile
CARD_MAX_SCALE = 16  # pixels par case : une ligne droite remplit la carte, un virage reste à la même échelle


def tile_card_primitives(tile: Tile, width: int, height: int, selected: bool = False, used: bool = False) -> list[tuple]:
    """Une tuile seule, dessinée en petit pour la palette de l'éditeur : sa forme, son relief, ses lignes."""
    bg = pal.CARD_HI if selected else pal.CARD
    border = SELECTED_COLOR if selected else pal.BORDER
    prims: list[tuple] = [("rect", 1, 1, width - 1, height - 1, bg, border, 3 if selected else 1)]

    track = full_track([tile])
    squares = layout_squares(track, extra=0)
    pts = [p for sq in squares for p in sq.corners]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    area_w, area_h = width - CARD_LETTER_W - 2 * CARD_PAD, height - 2 * CARD_PAD
    scale = min(CARD_MAX_SCALE, area_w / max(max(xs) - min(xs), 1e-6), area_h / max(max(ys) - min(ys), 1e-6))
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    cx0 = CARD_LETTER_W + CARD_PAD + area_w / 2

    def tr(p) -> tuple[float, float]:
        return (cx0 + (p[0] - mx) * scale, height / 2 - (p[1] - my) * scale)

    fin = finish_square([tile])
    for s, sq in enumerate(squares):
        beyond = fin is not None and s >= fin
        fill = BEYOND_FILL if beyond else TERRAIN_FILL[track.kind(s)]
        prims.append(("poly", [c for p in sq.outline for c in tr(p)], fill, pal.ROAD_OUTLINE, 1))
    if track.start:
        _start_line(prims, squares, track.start, tr)
    if fin is not None and fin < len(squares):
        _checkered_line(prims, squares, fin, tr)

    letter_color = pal.FAINT if used else pal.TEXT
    prims.append(("text", CARD_LETTER_W / 2 + 3, height / 2, tile.letter or "?", letter_color, 13, True, "center"))
    if used:
        prims.append(("text", width - 5, height - 9, "posée", pal.MUTED, 7, False, "e"))
    return prims


# ------------------------------------------------------------------ écran de victoire

PODIUM_COLORS = {1: "#f5c542", 2: "#c0c7d1", 3: "#cd7f32"}  # or, argent, bronze
PODIUM_HEIGHTS = {1: 0.42, 2: 0.30, 3: 0.22}  # fraction de la hauteur du cadre
PODIUM_DELAY = {3: 0.0, 2: 0.25, 1: 0.5}  # les marches montent l'une après l'autre : 3e, 2e, puis le vainqueur
RISE_TIME = 0.7
DROP_TIME = 0.45
CONFETTI = 90


def _ease(f: float) -> float:
    """Départ rapide, arrivée en douceur (et un petit rebond à la fin)."""
    f = max(0.0, min(1.0, f))
    return 1 - (1 - f) ** 3 + 0.08 * math.sin(f * math.pi) * (1 - f)


def race_ranking(game: Game) -> list[Rider]:
    """Classement de la course : le plus loin d'abord ; à égalité de case, la file de droite devant.
    Étape de Grand Tour : les coureurs arrivés (dans l'ordre d'arrivée), puis ceux encore en course."""
    still = sorted(game.riders, key=lambda r: (-r.position, r.lane))
    return list(getattr(game, "arrived", [])) + still if getattr(game, "tour", False) else still


def podium_primitives(game: Game, width: int, height: int, t: float, team_names: Optional[Sequence[str]] = None) -> list[tuple]:
    """Écran de victoire à l'instant `t` (en secondes) : les trois marches du podium montent, les coureurs
    se posent dessus, des confettis aux couleurs des équipes tombent en continu.

    `team_names` : comment nommer chaque équipe (par défaut « Équipe n »)."""
    ranking = race_ranking(game)
    everyone = getattr(game, "all_riders", game.riders)
    names = list(team_names or [f"Équipe {i + 1}" for i in range(max(r.team for r in everyone) + 1)])
    prims: list[tuple] = [("rect", 0, 0, width, height, "#0f1a33", "", 0)]
    for x in range(0, width, 90):  # rayons de lumière derrière le podium
        prims.append(("poly", [width / 2, height * 0.15, x, height, x + 45, height], "#14213f", "", 0))

    # confettis (derrière le podium et les coureurs)
    teams = sorted({r.team for r in everyone})
    for i in range(CONFETTI):
        phase = _frac(i * 0.6180339)
        speed = 0.18 + 0.22 * _frac(i * 0.4142)
        x = _frac(i * 0.3819 + 0.11) * width + math.sin(t * 2 + i) * 12
        y = (_frac(t * speed + phase) * 1.2 - 0.1) * height
        a = t * (2 + 3 * _frac(i * 0.27)) + i
        size = 4 + 3 * _frac(i * 0.83)
        color = TEAM_FILL[teams[i % len(teams)]] if i % 3 else "#ffffff"
        dx, dy = math.cos(a) * size, math.sin(a) * size * 0.5
        prims.append(("line", x - dx, y - dy, x + dx, y + dy, color, 3))

    base = height - 30
    block_w = min(150, width / 5)
    centers = {2: width / 2 - block_w * 1.05, 1: width / 2, 3: width / 2 + block_w * 1.05}
    for place in (1, 2, 3):
        if place > len(ranking):
            continue
        rider = ranking[place - 1]
        rise = _ease((t - PODIUM_DELAY[place]) / RISE_TIME)
        top = base - PODIUM_HEIGHTS[place] * height * rise
        cx = centers[place]
        x0, x1 = cx - block_w / 2, cx + block_w / 2
        color = PODIUM_COLORS[place]
        prims.append(("rect", x0 + 6, top + 6, x1 + 6, base, "#0a1226", "", 0))  # ombre
        prims.append(("rect", x0, top, x1, base, color, "#ffffff", 2))
        if rise > 0.35:
            prims.append(("text", cx, (top + base) / 2, str(place), "#1f2937", 30 if place == 1 else 24, True, "center"))
        # le coureur tombe sur sa marche une fois qu'elle est montée
        land = _ease((t - PODIUM_DELAY[place] - RISE_TIME) / DROP_TIME)
        if land <= 0:
            continue
        radius = 26 if place == 1 else 21
        ry = -radius + (top - radius - 6 + radius) * land
        prims.append(("oval", cx - radius, ry - radius, cx + radius, ry + radius, TEAM_FILL[rider.team], "#ffffff", 3))
        prims.append(("text", cx, ry, rider.name, LABEL_ON_FILL[rider.team], 14 if place == 1 else 12, True, "center"))
        if land >= 1:
            label = names[rider.team] if rider.team < len(names) else f"Équipe {rider.team + 1}"
            label_y = top - 2 * radius - (44 if place == 1 else 22)  # au-dessus de la couronne pour le vainqueur
            prims.append(("text", cx, label_y, label, TEAM_TEXT[rider.team], 11, True, "center"))
            if place == 1:  # couronne qui brille au-dessus du vainqueur
                glow = 0.5 + 0.5 * math.sin(t * 4)
                gold = _mix("#b8860b", "#fff3b0", glow)
                ky = ry - radius - 12
                prims.append(("poly", [cx - 16, ky + 8, cx - 16, ky - 6, cx - 8, ky + 1, cx, ky - 10,
                                       cx + 8, ky + 1, cx + 16, ky - 6, cx + 16, ky + 8], gold, "#ffffff", 1))

    winner = ranking[0]
    title_in = _ease((t - PODIUM_DELAY[1] - RISE_TIME - DROP_TIME) / 0.5)
    if title_in > 0:
        size = int(16 + 14 * title_in)
        winner_team = names[winner.team] if winner.team < len(names) else f"Équipe {winner.team + 1}"
        prims.append(("text", width / 2, 38, "VICTOIRE !", "#ffffff", size, True, "center"))
        prims.append(("text", width / 2, 72, f"{winner.name} · {winner_team} · {winner.kind}", TEAM_TEXT[winner.team], 13, True, "center"))
    # le reste du classement, en petit, en bas
    rest = "   ".join(f"{place}. {r.name}" for place, r in enumerate(ranking[3:], 4))
    if rest:
        prims.append(("text", width / 2, height - 12, rest, pal.MUTED, 9, False, "center"))
    prims.append(("text", width - 10, 14, "clic : voir la course", pal.FAINT, 8, False, "e"))
    return prims
