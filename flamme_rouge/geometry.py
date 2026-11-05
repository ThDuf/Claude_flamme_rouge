"""Géométrie 2D du parcours (sans tkinter) : où se trouve chaque case sur la carte.

Repère mathématique : x vers la droite, y vers le haut ; la route démarre en (0, 0)
vers l'est. L'interface retourne l'axe y au moment de dessiner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .track import Track

ROAD_WIDTH = 1.4  # largeur de la route (2 couloirs), pour une case de longueur 1
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

    @property
    def corners(self) -> list[Point]:
        return [self.lb, self.rb, self.rf, self.lf]

    @property
    def center(self) -> Point:
        return _avg(*self.corners)

    def lane_center(self, lane: int) -> Point:
        """Centre du couloir : 0 = droite (prioritaire), 1 = gauche."""
        mb, mf = _mid(self.lb, self.rb), _mid(self.lf, self.rf)
        if lane == 0:
            return _avg(self.rb, self.rf, mf, mb)
        return _avg(mb, mf, self.lf, self.lb)


def layout_squares(track: Track, extra: int = EXTRA_SQUARES) -> list[SquareGeom]:
    """Les cases du parcours puis `extra` cases droites après la ligne d'arrivée.

    Chaque case est un trapèze : la ligne médiane fait 1 de long, et la route tourne de
    `track.angle(i)` degrés entre le bord arrière et le bord avant de la case (comme les
    cases en éventail d'une tuile de virage). Les bords entre cases sont perpendiculaires à la route."""
    total = len(track) + extra
    half = ROAD_WIDTH / 2

    edges: list[tuple[Point, Point]] = []
    heading = 0.0  # direction de la route au bord courant, en radians
    x = y = 0.0

    def edge() -> tuple[Point, Point]:
        left = (x - half * math.sin(heading), y + half * math.cos(heading))
        right = (x + half * math.sin(heading), y - half * math.cos(heading))
        return left, right

    edges.append(edge())
    for i in range(total):
        turn = math.radians(track.angle(i))
        if abs(turn) < 1e-9:
            x += math.cos(heading)
            y += math.sin(heading)
        else:  # arc de longueur 1 : on avance selon la corde
            chord = 2 * math.sin(turn / 2) / turn
            x += chord * math.cos(heading + turn / 2)
            y += chord * math.sin(heading + turn / 2)
        heading += turn
        edges.append(edge())

    return [
        SquareGeom(lb=edges[i][0], rb=edges[i][1], rf=edges[i + 1][1], lf=edges[i + 1][0])
        for i in range(total)
    ]


def start_edge(squares: list[SquareGeom], track: Track) -> tuple[Point, Point]:
    """Extrémités de la ligne de départ (bord arrière de la première case de course)."""
    sq = squares[track.start]
    return sq.lb, sq.rb


def _lerp(a: Point, b: Point, f: float) -> Point:
    return (a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)


def point_on_road(squares: list[SquareGeom], progress: float, lane: float = 0.0) -> Point:
    """Point de la route à la case `progress` (fractionnaire : 3.5 = entre la case 3 et la case 4)
    et au couloir `lane` (0 = droite, 1 = gauche, entre les deux pendant un changement de couloir).
    Hors de la route dessinée, la position est ramenée au bout le plus proche."""
    last = len(squares) - 1
    progress = min(max(progress, 0.0), float(last))
    i = min(int(progress), max(last - 1, 0))
    frac = progress - i

    def lane_point(sq: SquareGeom) -> Point:
        return _lerp(sq.lane_center(0), sq.lane_center(1), lane)

    here = lane_point(squares[i])
    if last == 0:
        return here
    return _lerp(here, lane_point(squares[i + 1]), frac)


def finish_edge(squares: list[SquareGeom], track: Track) -> tuple[Point, Point]:
    """Extrémités de la ligne d'arrivée (bord arrière de la première case après la dernière)."""
    sq = squares[len(track)]
    return sq.lb, sq.rb
