"""Tuiles de parcours, comme dans la boîte du jeu, et leur assemblage en parcours jouable.

La boîte contient 21 tuiles recto-verso : 1 départ, 1 arrivée, 7 lignes droites,
6 virages doux (45°) et 6 virages serrés (90°). Les virages se retournent pour aller
à gauche ou à droite, et un côté de chaque tuile est plat tandis que l'autre a le plus
souvent des montées ou des descentes.

Les sources ne disent pas combien de cases a une tuile, ni le relief exact de chaque
lettre. Ici une tuile a donc SQUARES_PER_TILE cases (à ajuster si besoin) et son relief
se choisit librement ; les quantités officielles ne donnent que des avertissements.

Convention : la ligne d'arrivée est placée au début de la tuile d'arrivée. Ses cases ne
font pas partie de la course (un coureur y entre en franchissant la ligne).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Sequence

from .geometry import ROAD_WIDTH, layout_squares
from .track import ASCENT, DESCENT, LEFT, NORMAL, RIGHT, STRAIGHT, TURN_STEP_DEGREES, Track

SQUARES_PER_TILE = 6  # À CONFIRMER sur le plateau physique : les sources ne le précisent pas

KIND_START = "start"
KIND_FINISH = "finish"
KIND_STRAIGHT = "straight"
KIND_SOFT = "soft"
KIND_SHARP = "sharp"
KINDS = (KIND_START, KIND_FINISH, KIND_STRAIGHT, KIND_SOFT, KIND_SHARP)

TURN_DEGREES = {KIND_SOFT: 45, KIND_SHARP: 90}
KIND_NAMES = {
    KIND_START: "Départ",
    KIND_FINISH: "Arrivée",
    KIND_STRAIGHT: "Ligne droite",
    KIND_SOFT: "Virage doux",
    KIND_SHARP: "Virage serré",
}

# Contenu de la boîte du jeu de base.
OFFICIAL_MAX = {KIND_START: 1, KIND_FINISH: 1, KIND_STRAIGHT: 7, KIND_SOFT: 6, KIND_SHARP: 6}
OFFICIAL_TOTAL = 21

ERROR = "erreur"
WARNING = "avertissement"

_RELIEF_NAMES = {NORMAL: "plat", ASCENT: "montée", DESCENT: "descente"}


def _relief_profiles() -> dict[str, str]:
    """Reliefs proposés : plat, montée, descente, et les combinaisons moitié/moitié."""
    half = SQUARES_PER_TILE // 2
    profiles: dict[str, str] = {}
    for first in (NORMAL, ASCENT, DESCENT):
        for second in (NORMAL, ASCENT, DESCENT):
            name = _RELIEF_NAMES[first] if first == second else f"{_RELIEF_NAMES[first]} puis {_RELIEF_NAMES[second]}"
            profiles[name] = first * half + second * (SQUARES_PER_TILE - half)
    return profiles


RELIEF_PROFILES = _relief_profiles()
_PROFILE_NAME_BY_TERRAIN = {terrain: name for name, terrain in RELIEF_PROFILES.items()}


@dataclass(frozen=True)
class Tile:
    kind: str
    direction: Optional[str] = None  # LEFT ('L') ou RIGHT ('R'), pour les virages seulement
    terrain: str = NORMAL * SQUARES_PER_TILE  # un caractère par case : '.', 'A' ou 'D'

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Type de tuile inconnu : {self.kind!r}")
        if self.kind in TURN_DEGREES:
            if self.direction not in (LEFT, RIGHT):
                raise ValueError("Un virage va à gauche ('L') ou à droite ('R').")
        elif self.direction is not None:
            raise ValueError("Seuls les virages ont une direction.")
        if len(self.terrain) != SQUARES_PER_TILE or any(c not in (NORMAL, ASCENT, DESCENT) for c in self.terrain):
            raise ValueError(f"Le relief d'une tuile fait {SQUARES_PER_TILE} caractères parmi '.', 'A' et 'D'.")

    @property
    def shape(self) -> str:
        """Forme de la route sur la tuile, une lettre par case ('S', 'L' ou 'R')."""
        n = len(self.terrain)
        if self.kind not in TURN_DEGREES:
            return STRAIGHT * n
        count = TURN_DEGREES[self.kind] // TURN_STEP_DEGREES
        if count > n:
            raise ValueError("Pas assez de cases dans la tuile pour ce virage.")
        chars = [STRAIGHT] * n
        for k in range(count):  # les crans de virage sont répartis régulièrement sur la tuile
            chars[int((k + 0.5) * n / count)] = self.direction
        return "".join(chars)

    @property
    def relief_name(self) -> str:
        return _PROFILE_NAME_BY_TERRAIN.get(self.terrain, "relief personnalisé")

    @property
    def label(self) -> str:
        text = KIND_NAMES[self.kind]
        if self.kind in TURN_DEGREES:
            text += " à gauche" if self.direction == LEFT else " à droite"
        return f"{text} — {self.relief_name}"


def make_tile(kind: str, direction: Optional[str] = None, relief: str = "plat") -> Tile:
    if relief not in RELIEF_PROFILES:
        raise ValueError(f"Relief inconnu : {relief!r}")
    return Tile(kind, direction, RELIEF_PROFILES[relief])


# ---------------------------------------------------------------- assemblage


def finish_index(tiles: Sequence[Tile]) -> Optional[int]:
    """Position de la première tuile d'arrivée, ou None."""
    return next((i for i, t in enumerate(tiles) if t.kind == KIND_FINISH), None)


def tile_ranges(tiles: Sequence[Tile]) -> list[range]:
    """Cases occupées par chaque tuile (toutes les tuiles ont la même taille)."""
    n = SQUARES_PER_TILE
    return [range(i * n, (i + 1) * n) for i in range(len(tiles))]


def full_track(tiles: Sequence[Tile]) -> Track:
    """Toutes les tuiles bout à bout, arrivée comprise (pour dessiner et vérifier la route)."""
    if not tiles:
        raise ValueError("Le parcours est vide.")
    return Track("".join(t.terrain for t in tiles), "".join(t.shape for t in tiles))


def plan_to_track(tiles: Sequence[Tile]) -> Track:
    """Le parcours jouable : les tuiles avant la tuile d'arrivée (dont la ligne marque la fin)."""
    full = full_track(tiles)
    fin = finish_index(tiles)
    race = len(full) if fin is None else fin * SQUARES_PER_TILE
    if race == 0:
        raise ValueError("Il n'y a aucune case de course avant l'arrivée.")
    return Track(full.layout[:race], full.shape[:race])


# ----------------------------------------------------------------- validation


@dataclass(frozen=True)
class Issue:
    level: str  # ERROR ou WARNING
    text: str
    tile: Optional[int] = None  # numéro de la tuile concernée (à partir de 0)


def validate(tiles: Sequence[Tile]) -> list[Issue]:
    """Erreurs (parcours injouable) et avertissements (hors des quantités de la boîte)."""
    if not tiles:
        return [Issue(ERROR, "Le parcours est vide.")]
    issues: list[Issue] = []

    for kind, label, must_be in ((KIND_START, "départ", 0), (KIND_FINISH, "arrivée", len(tiles) - 1)):
        positions = [i for i, t in enumerate(tiles) if t.kind == kind]
        if not positions:
            issues.append(Issue(ERROR, f"Il manque la tuile de {label}."))
        elif len(positions) > 1:
            issues.append(Issue(ERROR, f"Il ne peut y avoir qu'une tuile de {label}.", positions[1]))
        elif positions[0] != must_be:
            place = "première" if kind == KIND_START else "dernière"
            issues.append(Issue(ERROR, f"La tuile de {label} doit être la {place}.", positions[0]))

    for kind in (KIND_STRAIGHT, KIND_SOFT, KIND_SHARP):
        count = sum(t.kind == kind for t in tiles)
        if count > OFFICIAL_MAX[kind]:
            issues.append(
                Issue(WARNING, f"{count} {KIND_NAMES[kind].lower()}s : la boîte n'en contient que {OFFICIAL_MAX[kind]}.")
            )
    if len(tiles) > OFFICIAL_TOTAL:
        issues.append(Issue(WARNING, f"{len(tiles)} tuiles : la boîte n'en contient que {OFFICIAL_TOTAL}."))

    crossing = find_crossing(tiles)
    if crossing:
        a, b = crossing
        issues.append(Issue(ERROR, f"La route se recoupe : les tuiles {a + 1} et {b + 1} se chevauchent.", b))
    return issues


def find_crossing(tiles: Sequence[Tile]) -> Optional[tuple[int, int]]:
    """Premier couple de tuiles dont la route se chevauche, ou None. Les tuiles voisines sont ignorées."""
    squares = layout_squares(full_track(tiles), extra=0)
    centers = [sq.center for sq in squares]
    for j in range(len(centers)):
        for i in range(j - 3):  # on ignore les cases proches le long de la route
            dx, dy = centers[i][0] - centers[j][0], centers[i][1] - centers[j][1]
            if (dx * dx + dy * dy) ** 0.5 < ROAD_WIDTH:
                a, b = i // SQUARES_PER_TILE, j // SQUARES_PER_TILE
                if a != b:
                    return a, b
    return None


def has_errors(issues: Sequence[Issue]) -> bool:
    return any(issue.level == ERROR for issue in issues)


def summary(tiles: Sequence[Tile]) -> str:
    """Ligne de comptage : combien de tuiles de chaque type par rapport à la boîte."""
    count = lambda kind: sum(t.kind == kind for t in tiles)
    return (
        f"{len(tiles)}/{OFFICIAL_TOTAL} tuiles · départ {count(KIND_START)}/1 · arrivée {count(KIND_FINISH)}/1 · "
        f"droites {count(KIND_STRAIGHT)}/{OFFICIAL_MAX[KIND_STRAIGHT]} · doux {count(KIND_SOFT)}/{OFFICIAL_MAX[KIND_SOFT]} · "
        f"serrés {count(KIND_SHARP)}/{OFFICIAL_MAX[KIND_SHARP]}"
    )


# -------------------------------------------------------------- sauvegarde


def plan_to_json(tiles: Sequence[Tile]) -> str:
    data = {
        "version": 1,
        "squares_per_tile": SQUARES_PER_TILE,
        "tiles": [{"kind": t.kind, "direction": t.direction, "terrain": t.terrain} for t in tiles],
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def plan_from_json(text: str) -> list[Tile]:
    """Relit un parcours enregistré. Lève ValueError avec un message clair si le fichier est invalide."""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("tiles"), list):
        raise ValueError("Ce fichier n'est pas un parcours Flamme Rouge.")
    per_tile = data.get("squares_per_tile", SQUARES_PER_TILE)
    if per_tile != SQUARES_PER_TILE:
        raise ValueError(f"Ce parcours a {per_tile} cases par tuile, alors que le programme en utilise {SQUARES_PER_TILE}.")
    tiles = []
    for i, item in enumerate(data["tiles"], 1):
        try:
            tiles.append(Tile(item["kind"], item.get("direction"), item["terrain"]))
        except (KeyError, TypeError) as exc:
            raise ValueError(f"Tuile {i} illisible dans le fichier.") from exc
    return tiles


def load_track_file(path: str) -> Track:
    """Charge un fichier de parcours et le transforme en parcours jouable (erreurs -> ValueError)."""
    with open(path, encoding="utf-8") as handle:
        tiles = plan_from_json(handle.read())
    problems = [issue.text for issue in validate(tiles) if issue.level == ERROR]
    if problems:
        raise ValueError("Parcours injouable : " + " ".join(problems))
    return plan_to_track(tiles)


def example_plan() -> list[Tile]:
    """Un parcours d'exemple avec montées, descentes et virages, sans croisement."""
    t = make_tile
    return [
        t(KIND_START),
        t(KIND_STRAIGHT),
        t(KIND_SHARP, LEFT, "plat puis montée"),
        t(KIND_STRAIGHT, relief="montée"),
        t(KIND_STRAIGHT, relief="montée puis descente"),
        t(KIND_SHARP, RIGHT, "descente"),
        t(KIND_SOFT, RIGHT),
        t(KIND_STRAIGHT),
        t(KIND_SOFT, LEFT, "plat puis montée"),
        t(KIND_STRAIGHT, relief="montée puis descente"),
        t(KIND_STRAIGHT, relief="descente puis plat"),
        t(KIND_SHARP, RIGHT),
        t(KIND_STRAIGHT),
        t(KIND_FINISH),
    ]
