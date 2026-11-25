"""Vue 3D isométrique du plateau (sans interface).

La carte 2D (geometry.py) est vue de biais : on la tourne de `angle` degrés autour de la verticale, on l'incline
(`tilt` : le fond s'écrase vers le haut de l'écran) et on soulève chaque point de l'altitude réelle de la route
(+1 par case de montée, −1 par case de descente) fois `lift`. Les montées grimpent donc vraiment à l'écran.

Une `Projection` transforme un point du monde (x, y) en un point « écran-monde » (u, v), dans les mêmes unités
que la carte plate : le cadrage, le zoom et le déplacement (boardview.map_transform, zoom_view, pan_view)
s'appliquent ensuite sans changement. Pour l'ordre de dessin (du fond vers l'avant), `depth` donne la distance
au spectateur : plus elle est grande, plus c'est loin, donc à dessiner d'abord.
"""
from __future__ import annotations

import math
from typing import Optional

from .geometry import layout_squares
from .track import ASCENT, DESCENT, Track

ISO_ANGLE = 45  # rotation par défaut (degrés) : la vue « isométrique » classique
ISO_TILT = 0.55  # écrasement de la profondeur (1 = vue du dessus, 0 = vue de profil)
ISO_LIFT = 0.32  # hauteur d'une case de dénivelé, en longueurs de case
ISO_BASE = -0.6  # niveau du sol sous la route (en cases de dénivelé) : l'épaisseur du plateau


class Projection:
    def __init__(self, track: Track, angle: float = ISO_ANGLE, tilt: float = ISO_TILT, lift: float = ISO_LIFT):
        self.track, self.angle, self.tilt, self.lift = track, angle % 360, tilt, lift
        self.squares = layout_squares(track)
        a = math.radians(self.angle)
        self._cos, self._sin = math.cos(a), math.sin(a)
        # altitude de chaque bord de case (0 = départ de la case 0), puis plate après l'arrivée
        heights = [0.0]
        for s in range(len(track)):
            kind = track.kind(s)
            heights.append(heights[-1] + (1 if kind == ASCENT else -1 if kind == DESCENT else 0))
        low = min(heights)
        n = len(track)
        self.edges = [heights[min(i, n)] - low for i in range(len(self.squares) + 1)]
        # grille des centres de case, pour retrouver vite la case sous un point quelconque
        self._grid: dict[tuple[int, int], list[int]] = {}
        # pour chaque case : milieu du bord arrière, axe (arrière -> avant) et demi-largeur
        self._axes = []
        for s, sq in enumerate(self.squares):
            cx, cy = sq.center
            self._grid.setdefault((math.floor(cx), math.floor(cy)), []).append(s)
            bx, by = (sq.lb[0] + sq.rb[0]) / 2, (sq.lb[1] + sq.rb[1]) / 2
            fx, fy = (sq.lf[0] + sq.rf[0]) / 2, (sq.lf[1] + sq.rf[1]) / 2
            half = math.dist(sq.lb, sq.rb) / 2
            self._axes.append((bx, by, fx - bx, fy - by, half))
        self._memo: dict[tuple[float, float], float] = {}

    # ------------------------------------------------------------------ altitudes

    def z_at(self, progress: float) -> float:
        """Altitude au milieu de la route à la case `progress` (fractionnaire, comme point_on_road : la case s
        est à son milieu)."""
        last = len(self.squares) - 1
        p = min(max(progress, 0.0), float(last))
        i = min(int(p), max(last - 1, 0))
        f = p - i
        mid = lambda s: (self.edges[s] + self.edges[s + 1]) / 2  # noqa: E731
        return mid(i) + (mid(min(i + 1, last)) - mid(i)) * f

    def _locate(self, s: int, x: float, y: float) -> tuple[float, float]:
        """(écart à la case s : 0 si le point est dessus, position t de 0 à 1 de l'arrière vers l'avant)."""
        bx, by, ax, ay, half = self._axes[s]
        length2 = max(ax * ax + ay * ay, 1e-9)
        t = ((x - bx) * ax + (y - by) * ay) / length2
        lateral = abs((x - bx) * ay - (y - by) * ax) / math.sqrt(length2)
        miss = max(0.0, t - 1.0, -t) * 1.5 + max(0.0, lateral - half * 1.3)  # l'arc d'un virage déborde un peu
        return miss, t

    def _square_under(self, x: float, y: float) -> tuple[int, float]:
        """La case sous le point (et la position t sur elle). Dans une épingle, deux bouts de route se frôlent :
        on prend la case dont le point est vraiment sur la chaussée, pas seulement le centre le plus proche."""
        gx, gy = math.floor(x), math.floor(y)
        best = None
        for radius in (2, 4):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    for s in self._grid.get((gx + dx, gy + dy), ()):
                        miss, t = self._locate(s, x, y)
                        if s > len(self.track) + 6:  # la route après l'arrivée peut croiser le parcours : en dernier
                            miss += 2.0
                        cx, cy = self.squares[s].center
                        score = (round(miss, 3), (cx - x) ** 2 + (cy - y) ** 2)
                        if best is None or score < best[0]:
                            best = (score, s, t)
            if best is not None:
                return best[1], best[2]
        s = min(range(len(self.squares)), key=lambda k: self._locate(k, x, y)[0])
        return s, self._locate(s, x, y)[1]

    def z(self, p, square: Optional[int] = None) -> float:
        """Altitude de la route sous le point `p` : sa case, entre son bord arrière et son bord avant
        (continu d'une case à l'autre, puisque deux cases voisines partagent le même bord). `square` : la case à
        laquelle le point appartient, quand on la connaît (bords et lignes d'une case) ; sinon on la cherche."""
        key = (round(p[0], 3), round(p[1], 3), square)
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        s = None
        if square is not None and 0 <= square < len(self.squares):
            miss, t = self._locate(square, p[0], p[1])
            if miss <= 1.0:
                s = square
        if s is None:
            s, t = self._square_under(p[0], p[1])
        t = min(max(t, 0.0), 1.0)
        value = self.edges[s] + (self.edges[s + 1] - self.edges[s]) * t
        if len(self._memo) < 200_000:
            self._memo[key] = value
        return value

    # ------------------------------------------------------------------ projection

    def ground(self, p) -> tuple[float, float]:
        """Le point tourné : (droite-gauche à l'écran, profondeur avant l'inclinaison)."""
        x, y = p
        return x * self._cos - y * self._sin, x * self._sin + y * self._cos

    def depth(self, p) -> float:
        """Plus c'est grand, plus c'est loin du spectateur (à dessiner en premier)."""
        return self.ground(p)[1]

    def __call__(self, p, z: Optional[float] = None, square: Optional[int] = None) -> tuple[float, float]:
        """Point du monde -> point écran-monde (u, v), v vers le haut comme sur la carte plate."""
        u, w = self.ground(p)
        if z is None:
            z = self.z(p, square)
        return u, w * self.tilt + z * self.lift


_CACHE: dict[tuple, Projection] = {}
_BEST: dict[tuple, float] = {}


def best_angle(track: Track, width: int = 1000, height: int = 430) -> float:
    """La rotation (30°, 45° ou 60° par rapport à un axe, pour garder l'allure isométrique) qui montre le parcours
    le plus grand dans un cadre width × height ; à peu près égales, on préfère la plus proche de 45°."""
    key = (id(track), width, height)
    if key in _BEST and _CACHE.get((id(track), float(ISO_ANGLE))) is not None:
        return _BEST[key]
    base = projection(track, ISO_ANGLE)
    corners = [(c, base.z(c)) for sq in base.squares[: len(track) + 6] for c in sq.corners]
    best = (0.0, 0.0, ISO_ANGLE)
    for angle in range(15, 360, 15):
        if angle % 90 not in (30, 45, 60):
            continue
        a = math.radians(angle)
        cos, sin = math.cos(a), math.sin(a)
        us, vs = [], []
        for (x, y), z in corners:
            u, w = x * cos - y * sin, (x * sin + y * cos) * ISO_TILT
            us.append(u)
            vs += [w + z * ISO_LIFT, w + ISO_BASE * ISO_LIFT]
        scale = min(width / max(max(us) - min(us), 1e-6), height / max(max(vs) - min(vs), 1e-6))
        near45 = -abs(angle % 90 - 45)
        score = (round(scale, 1), near45)
        if score > best[:2]:
            best = (*score, float(angle))
    _BEST[key] = best[2]
    return best[2]


def projection(track: Track, angle: float = ISO_ANGLE) -> Projection:
    """La projection d'un parcours (gardée en mémoire : elle retient les altitudes déjà calculées)."""
    key = (id(track), round(angle % 360, 3))
    hit = _CACHE.get(key)
    if hit is None or hit.track is not track:
        if len(_CACHE) > 32:
            _CACHE.clear()
        hit = _CACHE[key] = Projection(track, angle)
    return hit
