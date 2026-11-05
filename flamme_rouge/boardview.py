"""Géométrie du plateau pour l'interface graphique.

Aucune dépendance à tkinter : les fonctions renvoient des listes de formes à dessiner,
ce qui permet de les tester sans écran. Formats des formes :
  ("rect", x0, y0, x1, y1, remplissage, contour, épaisseur)
  ("oval", x0, y0, x1, y1, remplissage, contour, épaisseur)
  ("line", x0, y0, x1, y1, couleur, épaisseur)
  ("text", x, y, texte, couleur, taille, gras, ancrage)
"""
from __future__ import annotations

import random
import zlib
from typing import Iterable, Optional, Sequence

from .game import Game
from .geometry import EXTRA_SQUARES, finish_edge, layout_squares, point_on_road
from .rider import Rider
from .tiles import KIND_START, SQUARES_PER_TILE, Tile, finish_index, full_track, tile_ranges
from .track import ASCENT, DESCENT, NORMAL, Track

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
    positions = [r.position for r in game.riders] + list(extra_positions)
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
    furthest = max([r.position for r in game.riders] + list(extra_positions))
    last = max(finish + FULL_VIEW_AFTER_FINISH - 1, furthest)
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
    squares = layout_squares(track)
    first, last = window or (map_window(game) if zoom else full_window(game))
    if view is None:
        scale, mx, my = map_transform(game, zoom, window, width, height)
    else:
        scale, mx, my = view
        first, last = 0, min(len(squares) - 1, max(full_window(game)[1], max(r.position for r in game.riders)))

    def tr(p) -> tuple[float, float]:
        return (width / 2 + (p[0] - mx) * scale, height / 2 - (p[1] - my) * scale)

    def flat(points) -> list[float]:
        return [c for p in points for c in tr(p)]

    number_every = 1 if scale >= 15 else 5  # sur une grande carte, on ne numérote qu'une case sur cinq
    prims: list[tuple] = [("rect", 0, 0, width, height, pal.GRASS, "", 0)]
    _grass_stripes(prims, width, height)
    for s in range(first, last + 1):
        sq = squares[s]
        if view is not None:  # cadrage manuel : on ne dessine pas ce qui est hors du cadre
            px, py = zip(*(tr(c) for c in sq.corners))
            if max(px) < -40 or min(px) > width + 40 or max(py) < -40 or min(py) > height + 40:
                continue
        beyond = s >= finish
        kind = None if beyond else track.kind(s)
        fill = BEYOND_FILL if beyond else TERRAIN_FILL[kind]
        prims.append(("poly", flat(sq.corners), fill, pal.ROAD_OUTLINE, 1))
        # lignes blanches sur les bords de la route
        for a, b in ((sq.lb, sq.lf), (sq.rb, sq.rf)):
            (ex0, ey0), (ex1, ey1) = tr(a), tr(b)
            prims.append(("line", ex0, ey0, ex1, ey1, pal.ROAD_EDGE, 2 if scale >= 12 else 1))
        # trait séparant les deux couloirs
        mb = ((sq.lb[0] + sq.rb[0]) / 2, (sq.lb[1] + sq.rb[1]) / 2)
        mf = ((sq.lf[0] + sq.rf[0]) / 2, (sq.lf[1] + sq.rf[1]) / 2)
        (x0, y0), (x1, y1) = tr(mb), tr(mf)
        prims.append(("line", x0, y0, x1, y1, pal.LANE_LINE, 1))
        cx, cy = tr(sq.center)
        if kind is not None and kind != NORMAL and scale >= 9:
            prims.append(("text", cx, cy, TERRAIN_SYMBOL[kind], TERRAIN_SYMBOL_COLOR[kind], 13 if scale >= 15 else 9, True, "center"))
        if s % number_every == 0:
            # numéro de case, posé à l'extérieur de la route (côté droit)
            rx, ry = tr(((sq.rb[0] + sq.rf[0]) / 2, (sq.rb[1] + sq.rf[1]) / 2))
            ox, oy = rx - cx, ry - cy
            norm = max((ox * ox + oy * oy) ** 0.5, 1e-6)
            prims.append(("text", rx + ox / norm * 11, ry + oy / norm * 11, str(s), pal.SQUARE_NUMBER, 8, False, "center"))

    if first <= finish <= last + 1:
        _checkered_line(prims, squares, finish, tr)
        lb, rb = finish_edge(squares, track)
        (x0, y0), (x1, y1) = tr(lb), tr(rb)
        prims.append(("text", (x0 + x1) / 2, min(y0, y1) - 16, "ARRIVÉE", "#ffffff", 10, True, "center"))

    where = {r: (r.position, r.lane) for r in game.riders}
    if positions:
        where.update(positions)
    radius = max(7.5, min(24, 0.32 * scale))
    font_size = 8 if radius < 9 else 9 if radius < 11 else 11 if radius < 16 else 14
    for rider in sorted(game.riders, key=lambda r: where[r][0]):  # ceux de derrière d'abord, devant par-dessus
        progress, lane = where[rider]
        cx, cy = tr(point_on_road(squares, progress, lane))
        is_current = rider is current
        prims.append(("oval", cx - radius + 1.5, cy - radius + 3, cx + radius + 1.5, cy + radius + 3, pal.SHADOW, "", 0))
        if is_current:  # halo doré autour du coureur qui choisit
            prims.append(("oval", cx - radius - 4, cy - radius - 4, cx + radius + 4, cy + radius + 4, "", pal.CURRENT_RING, 3))
        prims.append(("oval", cx - radius, cy - radius, cx + radius, cy + radius, TEAM_FILL[rider.team], pal.RIDER_OUTLINE, 2))
        prims.append(("text", cx, cy, rider.name, LABEL_ON_FILL[rider.team], font_size, True, "center"))
    return prims


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
    per_tile = len(ranges[0]) if ranges else 0
    middle = per_tile // 2  # les deux cases du milieu d'une tuile portent sa pastille numérotée

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
    for s, sq in enumerate(squares):
        beyond = finish_square is not None and s >= finish_square
        kind = track.kind(s)
        fill = BEYOND_FILL if beyond else TERRAIN_FILL[kind]
        prims.append(("poly", flat(sq.corners), fill, pal.ROAD_OUTLINE, 1))
        for a, b in ((sq.lb, sq.lf), (sq.rb, sq.rf)):
            (ex0, ey0), (ex1, ey1) = tr(a), tr(b)
            prims.append(("line", ex0, ey0, ex1, ey1, pal.ROAD_EDGE, 2 if scale >= 12 else 1))
        under_badge = bool(ranges) and s % per_tile in (middle - 1, middle)
        if kind != NORMAL and not beyond and scale >= 12 and not under_badge:
            cx, cy = tr(sq.center)
            prims.append(("text", cx, cy, TERRAIN_SYMBOL[kind], TERRAIN_SYMBOL_COLOR[kind], 11, True, "center"))

    if ranges:
        if selected is not None and 0 <= selected < len(ranges):
            for s in ranges[selected]:
                prims.append(("poly", flat(squares[s].corners), "", SELECTED_COLOR, 3))
        # numéro de chaque tuile, dans une pastille posée au milieu de la tuile
        for i, rng in enumerate(ranges):
            (ax, ay), (bx, by) = tr(squares[rng[middle - 1]].center), tr(squares[rng[middle]].center)
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
        label_near_edge(0, "DÉPART")
    if finish_square is not None:
        _checkered_line(prims, squares, finish_square, tr)
        label_near_edge(finish_square, "ARRIVÉE")
    return prims


def plan_preview_primitives(tiles: Sequence[Tile], width: int, height: int, selected: Optional[int] = None) -> list[tuple]:
    """Le parcours en tuiles, vu de dessus, pour l'éditeur : tuiles numérotées, tuile sélectionnée entourée."""
    if not tiles:
        return [("text", width / 2, height / 2, "Ajoute des tuiles pour voir le parcours", pal.MUTED, 13, False, "center")]
    fin = finish_index(tiles)
    finish_square = None if fin is None else fin * SQUARES_PER_TILE
    return _preview(full_track(tiles), finish_square, width, height, tile_ranges(tiles), selected, tiles[0].kind == KIND_START)


def track_preview_primitives(track: Track, width: int, height: int) -> list[tuple]:
    """Aperçu d'un parcours quelconque (pour le menu), avec un peu de route après l'arrivée."""
    extended = Track(track.layout + NORMAL * SQUARES_PER_TILE, track.shape)
    return _preview(extended, len(track), width, height)


def minimap_primitives(game: Game) -> list[tuple]:
    """Toute la course en petit, avec un cadre autour de la partie affichée en grand."""
    finish = len(game.track)
    end = max(finish + 3, max(r.position for r in game.riders) + 1)
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
PROFILE_PAD_TOP = 22
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
    rng = random.Random(zlib.crc32(f"{track.layout}|{track.shape}".encode()))
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


def profile_primitives(track: Track, width: int, height: int, marker: Optional[float] = None) -> list[tuple]:
    """Profil de l'étape (vue de côté) : montées en orange, descentes en bleu, plat en gris.

    `marker` (une case, éventuellement fractionnaire) dessine un trait pour situer un coureur ou le peloton."""
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
    prims.append(("line", x_of(n), PROFILE_PAD_TOP - 4, x_of(n), base, "#ffffff", 3))
    prims.append(("text", x_of(n), PROFILE_PAD_TOP - 12, "ARRIVÉE", "#ffffff", 8, True, "center"))
    climb = sum(1 for s in range(n) if track.kind(s) == ASCENT)
    drop = sum(1 for s in range(n) if track.kind(s) == DESCENT)
    prims.append(("text", PROFILE_PAD_X, 8, f"Profil : {climb} cases de montée ▲  ·  {drop} cases de descente ▼", pal.MUTED, 9, True, "w"))
    if marker is not None:
        m = max(0.0, min(float(n), marker))
        prims.append(("line", x_of(m), PROFILE_PAD_TOP, x_of(m), base, pal.ACCENT, 2))
        prims.append(("oval", x_of(m) - 4, PROFILE_PAD_TOP - 4, x_of(m) + 4, PROFILE_PAD_TOP + 4, pal.ACCENT, "#ffffff", 1))
    return prims
