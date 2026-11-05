"""Le parcours : une suite de cases, chacune avec un terrain et un angle de virage.

Terrain (règles) : '.' plat, 'A' montée, 'D' descente.
Virage (dessin seulement) : de combien de degrés la route tourne sur la case
(positif = vers la gauche, négatif = vers la droite). Les virages n'ont aucun effet sur les règles.

Les `start` premières cases forment la grille de départ : elles sont derrière la ligne
de départ, et c'est là que les coureurs sont placés au début de la course.
"""
from __future__ import annotations

from typing import Optional, Sequence, Union

NORMAL = "."
ASCENT = "A"
DESCENT = "D"

STRAIGHT = "S"
LEFT = "L"
RIGHT = "R"

TURN_STEP_DEGREES = 15  # dans une forme écrite en lettres, un 'L' ou un 'R' tourne de 15°

# Parcours d'exemple (50 cases) : plat, une montée suivie d'une descente, etc.
DEFAULT_LAYOUT = "." * 8 + "A" * 4 + "D" * 3 + "." * 20 + "A" * 3 + "D" * 3 + "." * 9

# Un parcours en S qui ne se recoupe pas et qui finit loin du départ.
DEFAULT_SHAPE = (
    "S" * 6  # 0-5    départ, vers l'est
    + "L" * 6  # 6-11   virage à gauche : on part vers le nord
    + "S" * 6  # 12-17
    + "R" * 6  # 18-23  virage à droite : retour vers l'est
    + "S" * 6  # 24-29
    + "R" * 6  # 30-35  virage à droite : vers le sud
    + "S" * 4  # 36-39
    + "L" * 6  # 40-45  virage à gauche : repart vers l'est
    + "S" * 4  # 46-49  arrivée
)

Shape = Union[str, Sequence[float]]


def shape_to_angles(shape: str) -> tuple[float, ...]:
    """Forme en lettres ('S', 'L', 'R') -> angle de chaque case en degrés."""
    if any(c not in (STRAIGHT, LEFT, RIGHT) for c in shape):
        raise ValueError("Une forme ne contient que 'S', 'L' et 'R'.")
    step = {STRAIGHT: 0.0, LEFT: TURN_STEP_DEGREES, RIGHT: -TURN_STEP_DEGREES}
    return tuple(float(step[c]) for c in shape)


class Track:
    """La ligne d'arrivée se situe juste après la dernière case : un coureur dont la
    position est >= len(track) l'a franchie. Les cases au-delà de la ligne sont
    considérées comme plates et droites.
    """

    def __init__(
        self,
        layout: str = DEFAULT_LAYOUT,
        shape: Optional[Shape] = None,
        start: int = 0,
        straights: Optional[Sequence[tuple[int, int]]] = None,
    ):
        if not layout or any(c not in (NORMAL, ASCENT, DESCENT) for c in layout):
            raise ValueError("Un parcours ne contient que '.', 'A' et 'D' (et n'est pas vide).")
        if shape is None:
            # Le parcours par défaut a ses virages ; un parcours personnalisé est droit
            # tant qu'on ne précise pas sa forme.
            shape = DEFAULT_SHAPE if layout == DEFAULT_LAYOUT else ""
        angles = shape_to_angles(shape) if isinstance(shape, str) else tuple(float(a) for a in shape)
        if len(angles) > len(layout):
            raise ValueError("La forme ne peut pas être plus longue que le parcours.")
        if not 0 <= start < len(layout):
            raise ValueError("La grille de départ doit laisser au moins une case de course.")
        self.layout = layout
        self.angles = angles + (0.0,) * (len(layout) - len(angles))
        self.start = start  # nombre de cases de la grille de départ (derrière la ligne de départ)
        # lignes droites (hors départ et arrivée), quand le parcours est fait de tuiles : [(première case, fin)]
        self.straights = None if straights is None else tuple(tuple(s) for s in straights)

    def __len__(self) -> int:
        return len(self.layout)

    def kind(self, square: int) -> str:
        if 0 <= square < len(self.layout):
            return self.layout[square]
        return NORMAL

    def angle(self, square: int) -> float:
        """Virage de la case, en degrés (positif = à gauche). Droit hors du parcours."""
        if 0 <= square < len(self.angles):
            return self.angles[square]
        return 0.0
