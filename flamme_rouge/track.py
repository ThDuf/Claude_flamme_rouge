"""Le parcours : une suite de cases, chacune avec un terrain et une forme.

Terrain (règles) : '.' plat, 'A' montée, 'D' descente.
Forme (dessin seulement) : 'S' tout droit, 'L' la route tourne un cran à gauche,
'R' un cran à droite. Les virages n'ont aucun effet sur les règles.
"""

NORMAL = "."
ASCENT = "A"
DESCENT = "D"

STRAIGHT = "S"
LEFT = "L"
RIGHT = "R"

TURN_STEP_DEGREES = 15  # un 'L' ou un 'R' fait tourner la route de 15° ; 6 d'affilée = virage à 90°

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


class Track:
    """La ligne d'arrivée se situe juste après la dernière case : un coureur dont la
    position est >= len(track) l'a franchie. Les cases au-delà de la ligne sont
    considérées comme plates et droites.
    """

    def __init__(self, layout: str = DEFAULT_LAYOUT, shape: str | None = None):
        if not layout or any(c not in (NORMAL, ASCENT, DESCENT) for c in layout):
            raise ValueError("Un parcours ne contient que '.', 'A' et 'D' (et n'est pas vide).")
        if shape is None:
            # Le parcours par défaut a ses virages ; un parcours personnalisé est droit
            # tant qu'on ne précise pas sa forme.
            shape = DEFAULT_SHAPE if layout == DEFAULT_LAYOUT else STRAIGHT * len(layout)
        if len(shape) > len(layout):
            raise ValueError("La forme ne peut pas être plus longue que le parcours.")
        if any(c not in (STRAIGHT, LEFT, RIGHT) for c in shape):
            raise ValueError("Une forme ne contient que 'S', 'L' et 'R'.")
        self.layout = layout
        self.shape = shape.ljust(len(layout), STRAIGHT)

    def __len__(self) -> int:
        return len(self.layout)

    def kind(self, square: int) -> str:
        if 0 <= square < len(self.layout):
            return self.layout[square]
        return NORMAL

    def turn(self, square: int) -> str:
        if 0 <= square < len(self.shape):
            return self.shape[square]
        return STRAIGHT
