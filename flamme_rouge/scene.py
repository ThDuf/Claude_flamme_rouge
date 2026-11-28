"""La scène du parcours en coordonnées du monde, pour la vue 3D du navigateur (sans interface).

Repère de geometry.py : une case fait 1 de long, x vers la droite, y vers le haut de la carte ; l'altitude
compte en cases de dénivelé (+1 par case de montée, −1 par case de descente, 0 au point le plus bas).
Le navigateur reçoit la scène une fois par course : les coureurs, eux, voyagent dans l'état de la course
(case, file), et `point_on_road` / `SquareGeom.lane_center` suffisent pour les placer sur cette route.
"""
from __future__ import annotations

from .boardview import _surface_fill, elevation
from .geometry import EXTRA_SQUARES, layout_squares
from .iso import ISO_BASE, ISO_LIFT
from .palette import BEYOND_FILL, TERRAIN_FILL
from .track import Track

DIGITS = 3  # millièmes de case : assez fin pour les arcs des virages (un point tous les 5°)


def _point(p) -> list[float]:
    return [round(p[0], DIGITS), round(p[1], DIGITS)]


def edge_altitudes(track: Track, count: int) -> list[float]:
    """Altitude de chaque bord de case (count + 1 valeurs, 0 = point le plus bas) ; plate après l'arrivée.
    Le milieu de la case s est à la moyenne de ses deux bords, comme boardview.road_altitudes."""
    heights = elevation(track)
    low = min(heights)
    n = len(track)
    return [float(heights[min(i, n)] - low) for i in range(count + 1)]


def build_scene(track: Track, extra: int = EXTRA_SQUARES) -> dict:
    """La route : pour chaque case, ses bords gauche et droit (de l'arrière vers l'avant, en arc dans un
    virage), son nombre de files, son terrain et sa couleur ; l'altitude de chaque bord de case.

    Les coins de la case sont le premier et le dernier point de chaque bord : lb = left[0], lf = left[-1],
    rb = right[0], rf = right[-1]."""
    n = len(track)
    squares = layout_squares(track, extra)
    rows = []
    for s, sq in enumerate(squares):
        beyond = s >= n
        kind = "" if beyond else track.kind(s)
        surface = "" if beyond else track.surface(s)
        fill = BEYOND_FILL if beyond else _surface_fill(TERRAIN_FILL[kind], surface)
        rows.append({
            "left": [_point(p) for p in sq.left_path],
            "right": [_point(p) for p in sq.right_path],
            "lanes": sq.lanes,
            "kind": kind,
            "surface": surface,
            "fill": fill,
        })
    return {
        "squares": rows,
        "z": edge_altitudes(track, len(squares)),
        "n": n,  # la ligne d'arrivée est le bord arrière de la case n
        "start": track.start,  # la ligne de départ est le bord arrière de la case `start`
        "lift": ISO_LIFT,  # hauteur d'une case de dénivelé, en longueurs de case
        "base": ISO_BASE,  # niveau du sol sous la route, en cases de dénivelé
    }
