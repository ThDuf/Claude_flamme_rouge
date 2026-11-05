"""Tuiles de parcours, comme dans la boîte du jeu, et leur assemblage en parcours jouable.

La boîte contient 21 tuiles recto-verso (a à u côté plat, A à U côté montagne) :
1 départ, 1 arrivée, 7 lignes droites, 6 virages doux (45°) et 6 virages serrés (90°).
Une ligne droite, le départ et l'arrivée font 6 cases ; un virage en fait 2.

Chaque case d'une tuile est décrite par une lettre (CELL_CHARS) :
  f plat, u montée, d descente,
  s case de la grille de départ (derrière la ligne de départ, plate),
  e case après la ligne d'arrivée (hors course).
Ex. : départ "sssssf" (5 cases de grille puis la ligne de départ), arrivée "feeeee"
(1 case de course puis la ligne d'arrivée).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .geometry import ROAD_WIDTH, layout_squares
from .track import ASCENT, DESCENT, LEFT, NORMAL, RIGHT, Track

KIND_START = "start"
KIND_FINISH = "finish"
KIND_STRAIGHT = "straight"
KIND_SOFT = "soft"
KIND_SHARP = "sharp"
KINDS = (KIND_START, KIND_FINISH, KIND_STRAIGHT, KIND_SOFT, KIND_SHARP)

# Lettres des cases d'une tuile
FLAT, UP, DOWN, START_CELL, FINISH_CELL = "f", "u", "d", "s", "e"
CELL_CHARS = FLAT + UP + DOWN + START_CELL + FINISH_CELL
RACE_CELLS = FLAT + UP + DOWN
CELL_TO_TERRAIN = {FLAT: NORMAL, UP: ASCENT, DOWN: DESCENT, START_CELL: NORMAL, FINISH_CELL: NORMAL}

STRAIGHT_LENGTH = 6
CURVE_LENGTH = 2
TILE_LENGTH = {KIND_START: 6, KIND_FINISH: 6, KIND_STRAIGHT: STRAIGHT_LENGTH, KIND_SOFT: CURVE_LENGTH, KIND_SHARP: CURVE_LENGTH}
DEFAULT_CELLS = {KIND_START: "sssssf", KIND_FINISH: "feeeee"}

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

_RELIEF_NAMES = {FLAT: "plat", UP: "montée", DOWN: "descente"}


def relief_profiles(length: int) -> dict[str, str]:
    """Reliefs proposés pour une tuile de `length` cases : plat, montée, descente et les moitié/moitié."""
    half = length // 2
    profiles: dict[str, str] = {}
    for a in (FLAT, UP, DOWN):
        for b in (FLAT, UP, DOWN):
            name = _RELIEF_NAMES[a] if a == b else f"{_RELIEF_NAMES[a]} puis {_RELIEF_NAMES[b]}"
            profiles[name] = a * half + b * (length - half)
    return profiles


RELIEF_NAMES = list(relief_profiles(STRAIGHT_LENGTH))


def relief_name(cells: str) -> str:
    """Nom du relief des cases de course (les cases de grille et d'après l'arrivée sont ignorées)."""
    race = "".join(c for c in cells if c in RACE_CELLS)
    if not race:
        return "plat"
    for name, profile in relief_profiles(len(race)).items():
        if profile == race:
            return name
    return "relief personnalisé"


@dataclass(frozen=True)
class Tile:
    kind: str
    direction: Optional[str] = None  # LEFT ('L') ou RIGHT ('R'), pour les virages seulement
    cells: str = ""  # une lettre de CELL_CHARS par case ; vide = valeur par défaut du type
    letter: Optional[str] = field(default=None, compare=False)  # lettre de la tuile officielle, s'il y en a une

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"Type de tuile inconnu : {self.kind!r}")
        if not self.cells:
            object.__setattr__(self, "cells", DEFAULT_CELLS.get(self.kind, FLAT * TILE_LENGTH[self.kind]))
        if self.kind in TURN_DEGREES:
            if self.direction not in (LEFT, RIGHT):
                raise ValueError("Un virage va à gauche ('L') ou à droite ('R').")
        elif self.direction is not None:
            raise ValueError("Seuls les virages ont une direction.")
        length = TILE_LENGTH[self.kind]
        if len(self.cells) != length:
            raise ValueError(f"{KIND_NAMES[self.kind]} : la tuile fait {length} cases, pas {len(self.cells)}.")
        pattern = {
            KIND_START: f"{START_CELL}+[{RACE_CELLS}]*",
            KIND_FINISH: f"[{RACE_CELLS}]*{FINISH_CELL}+",
        }.get(self.kind, f"[{RACE_CELLS}]+")
        if not re.fullmatch(pattern, self.cells):
            raise ValueError(
                f"{KIND_NAMES[self.kind]} : cases {self.cells!r} invalides (f plat, u montée, d descente ; "
                "s grille de départ au début du départ ; e après la ligne, à la fin de l'arrivée)."
            )

    @property
    def angles(self) -> tuple[float, ...]:
        """Virage de chaque case, en degrés (positif = à gauche) : un virage est réparti sur ses cases."""
        n = len(self.cells)
        if self.kind not in TURN_DEGREES:
            return (0.0,) * n
        sign = 1 if self.direction == LEFT else -1
        return (sign * TURN_DEGREES[self.kind] / n,) * n

    @property
    def layout(self) -> str:
        """Terrain de chaque case pour les règles ('.', 'A', 'D')."""
        return "".join(CELL_TO_TERRAIN[c] for c in self.cells)

    @property
    def grid_squares(self) -> int:
        return self.cells.count(START_CELL)

    @property
    def relief_name(self) -> str:
        return relief_name(self.cells)

    @property
    def label(self) -> str:
        text = KIND_NAMES[self.kind]
        if self.kind in TURN_DEGREES:
            text += " à gauche" if self.direction == LEFT else " à droite"
        elif self.kind == KIND_START:
            text += f" ({self.grid_squares} places)"
        text = f"{text} — {self.relief_name}"
        return f"{self.letter} · {text}" if self.letter else text


def make_tile(kind: str, direction: Optional[str] = None, relief: str = "plat") -> Tile:
    """Une tuile « libre ». Le départ et l'arrivée gardent leur forme par défaut (relief ignoré)."""
    if kind not in TILE_LENGTH:
        raise ValueError(f"Type de tuile inconnu : {kind!r}")
    if kind in DEFAULT_CELLS:
        return Tile(kind)
    profiles = relief_profiles(TILE_LENGTH[kind])
    if relief not in profiles:
        raise ValueError(f"Relief inconnu : {relief!r}")
    return Tile(kind, direction, profiles[relief])


# ---------------------------------------------------------------- assemblage


def finish_index(tiles: Sequence[Tile]) -> Optional[int]:
    """Position de la première tuile d'arrivée, ou None."""
    return next((i for i, t in enumerate(tiles) if t.kind == KIND_FINISH), None)


def tile_ranges(tiles: Sequence[Tile]) -> list[range]:
    """Cases occupées par chaque tuile."""
    ranges, start = [], 0
    for tile in tiles:
        ranges.append(range(start, start + len(tile.cells)))
        start += len(tile.cells)
    return ranges


def finish_square(tiles: Sequence[Tile]) -> Optional[int]:
    """Première case après la ligne d'arrivée (= nombre de cases avant la ligne), ou None."""
    pos = "".join(t.cells for t in tiles).find(FINISH_CELL)
    return None if pos < 0 else pos


def start_squares(tiles: Sequence[Tile]) -> int:
    """Nombre de cases de la grille de départ (derrière la ligne de départ)."""
    return tiles[0].grid_squares if tiles and tiles[0].kind == KIND_START else 0


def full_track(tiles: Sequence[Tile]) -> Track:
    """Toutes les tuiles bout à bout, cases d'après l'arrivée comprises (pour dessiner et vérifier la route)."""
    if not tiles:
        raise ValueError("Le parcours est vide.")
    layout = "".join(t.layout for t in tiles)
    angles = [a for t in tiles for a in t.angles]
    return Track(layout, angles, min(start_squares(tiles), len(layout) - 1))


def plan_to_track(tiles: Sequence[Tile]) -> Track:
    """Le parcours jouable : la grille de départ et les cases de course, jusqu'à la ligne d'arrivée."""
    if not tiles:
        raise ValueError("Le parcours est vide.")
    full = full_track(tiles)
    fin = finish_square(tiles)
    race = len(full) if fin is None else fin
    start = start_squares(tiles)
    if race <= start:
        raise ValueError("Il n'y a aucune case de course avant l'arrivée.")
    return Track(full.layout[:race], full.angles[:race], start)


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
    tile_of = [i for i, r in enumerate(tile_ranges(tiles)) for _ in r]
    for j in range(len(centers)):
        for i in range(j - 3):  # on ignore les cases proches le long de la route
            dx, dy = centers[i][0] - centers[j][0], centers[i][1] - centers[j][1]
            if (dx * dx + dy * dy) ** 0.5 < ROAD_WIDTH:
                a, b = tile_of[i], tile_of[j]
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


FILE_VERSION = 2


def plan_to_json(tiles: Sequence[Tile]) -> str:
    items = []
    for t in tiles:
        item = {"kind": t.kind, "direction": t.direction, "cells": t.cells}
        if t.letter:
            item["letter"] = t.letter
        items.append(item)
    return json.dumps({"version": FILE_VERSION, "tiles": items}, ensure_ascii=False, indent=2)


def plan_from_json(text: str) -> list[Tile]:
    """Relit un parcours enregistré. Lève ValueError avec un message clair si le fichier est invalide."""
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("tiles"), list):
        raise ValueError("Ce fichier n'est pas un parcours Flamme Rouge.")
    if data.get("version", 1) < FILE_VERSION:
        raise ValueError("Ce parcours vient d'une ancienne version (virages de 6 cases) : recrée-le dans l'éditeur.")
    tiles = []
    for i, item in enumerate(data["tiles"], 1):
        try:
            tiles.append(Tile(item["kind"], item.get("direction"), item["cells"], item.get("letter")))
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
