"""Géométrie 2D du parcours (sans tkinter) : où se trouve chaque case sur la carte.

Repère mathématique : x vers la droite, y vers le haut ; la route démarre en (0, 0)
vers l'est. L'interface retourne l'axe y au moment de dessiner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .track import Track

LANE_WIDTH = 0.7  # largeur d'une file, pour une case de longueur 1
ROAD_WIDTH = 2 * LANE_WIDTH  # largeur d'une route ordinaire (2 files)
ARC_STEP_DEGREES = 5  # finesse du dessin des virages : un point tous les 5° le long des bords
EXTRA_SQUARES = 14  # cases dessinées après la ligne d'arrivée (un coureur peut la dépasser)

Point = tuple[float, float]


def _mid(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _avg(*pts: Point) -> Point:
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


@dataclass(frozen=True)
class SquareGeom:
    """Une case = un quadrilatère. 'back' = côté de l'arrière (d'où l'on vient), 'front' = vers l'arrivée."""

    lb: Point  # arrière gauche
    rb: Point  # arrière droit
    rf: Point  # avant droit
    lf: Point  # avant gauche
    # Bords de la route de l'arrière vers l'avant, en arc dans un virage (pour un dessin lisse).
    # Vides : bords droits, de lb à lf et de rb à rf.
    left_edge: tuple[Point, ...] = ()
    right_edge: tuple[Point, ...] = ()
    lanes: int = 2  # nombre de files (1 à 3 avec l'extension Peloton)

    @property
    def corners(self) -> list[Point]:
        return [self.lb, self.rb, self.rf, self.lf]

    @property
    def left_path(self) -> tuple[Point, ...]:
        return self.left_edge or (self.lb, self.lf)

    @property
    def right_path(self) -> tuple[Point, ...]:
        return self.right_edge or (self.rb, self.rf)

    @property
    def middle_path(self) -> tuple[Point, ...]:
        """Ligne au milieu de la route."""
        return tuple(_mid(a, b) for a, b in zip(self.left_path, self.right_path))

    @property
    def lane_lines(self) -> list[tuple[Point, ...]]:
        """Traits entre les files : aucun pour une file, un pour deux, deux pour trois."""
        return [tuple(_lerp(r, l, k / self.lanes) for r, l in zip(self.right_path, self.left_path))
                for k in range(1, self.lanes)]

    @property
    def outline(self) -> list[Point]:
        """Contour à dessiner : comme `corners`, mais les bords suivent l'arc du virage."""
        return [*self.right_path, *reversed(self.left_path)]

    @property
    def center(self) -> Point:
        return _avg(*self.corners)

    def lane_center(self, lane: float) -> Point:
        """Centre de la file : 0 = droite (prioritaire), puis vers la gauche (fractionnaire pendant un changement)."""
        f = (lane + 0.5) / self.lanes
        return _lerp(_mid(self.rb, self.rf), _mid(self.lb, self.lf), f)


def layout_squares(track: Track, extra: int = EXTRA_SQUARES) -> list[SquareGeom]:
    """Les cases du parcours puis `extra` cases droites après la ligne d'arrivée.

    Chaque case est un trapèze : la ligne médiane fait 1 de long, et la route tourne de
    `track.angle(i)` degrés entre le bord arrière et le bord avant de la case (comme les
    cases en éventail d'une tuile de virage). Les bords entre cases sont perpendiculaires à la route."""
    total = len(track) + extra

    # ligne médiane : position et direction de la route à chaque bord entre deux cases
    points: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    for i in range(total):
        x, y, heading = points[-1]
        turn = math.radians(track.angle(i))
        if abs(turn) < 1e-9:
            points.append((x + math.cos(heading), y + math.sin(heading), heading))
        else:  # arc de longueur 1 : on avance selon la corde
            chord = 2 * math.sin(turn / 2) / turn
            points.append((x + chord * math.cos(heading + turn / 2), y + chord * math.sin(heading + turn / 2), heading + turn))

    def side(x: float, y: float, h: float, half: float) -> tuple[Point, Point]:
        return (x - half * math.sin(h), y + half * math.cos(h)), (x + half * math.sin(h), y - half * math.cos(h))

    squares = []
    for i in range(total):
        lanes = track.lanes(i) if i < len(track) else 2
        half = LANE_WIDTH * lanes / 2  # chaque case a la largeur de ses files
        (x0, y0, h0), (x1, y1, h1) = points[i], points[i + 1]
        lb, rb = side(x0, y0, h0, half)
        lf, rf = side(x1, y1, h1, half)
        turn = h1 - h0
        left: tuple[Point, ...] = ()
        right: tuple[Point, ...] = ()
        if abs(turn) >= 1e-9:  # bords échantillonnés le long de l'arc, pour un dessin lisse
            steps = max(2, math.ceil(abs(math.degrees(turn)) / ARC_STEP_DEGREES))
            ls, rs = [], []
            for k in range(steps + 1):
                h = h0 + turn * k / steps
                px = x0 + (math.sin(h) - math.sin(h0)) / turn
                py = y0 - (math.cos(h) - math.cos(h0)) / turn
                lp, rp = side(px, py, h, half)
                ls.append(lp)
                rs.append(rp)
            left, right = tuple(ls), tuple(rs)
        squares.append(SquareGeom(lb=lb, rb=rb, rf=rf, lf=lf, left_edge=left, right_edge=right, lanes=lanes))
    return squares


def start_edge(squares: list[SquareGeom], track: Track) -> tuple[Point, Point]:
    """Extrémités de la ligne de départ (bord arrière de la première case de course)."""
    sq = squares[track.start]
    return sq.lb, sq.rb


def _lerp(a: Point, b: Point, f: float) -> Point:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def point_on_road(squares: list[SquareGeom], progress: float, lane: float = 0.0) -> Point:
    """Point de la route à la case `progress` (fractionnaire : 3.5 = entre la case 3 et la case 4)
    et à la file `lane` (0 = droite, puis vers la gauche ; fractionnaire pendant un changement de file).
    Hors de la route dessinée, la position est ramenée au bout le plus proche."""
    last = len(squares) - 1
    progress = min(max(progress, 0.0), float(last))
    i = min(int(progress), max(last - 1, 0))
    frac = progress - i

    def lane_point(sq: SquareGeom) -> Point:
        return sq.lane_center(lane)

    here = lane_point(squares[i])
    if last == 0:
        return here
    return _lerp(here, lane_point(squares[i + 1]), frac)


def finish_edge(squares: list[SquareGeom], track: Track) -> tuple[Point, Point]:
    """Extrémités de la ligne d'arrivée (bord arrière de la première case après la dernière)."""
    sq = squares[len(track)]
    return sq.lb, sq.rb
