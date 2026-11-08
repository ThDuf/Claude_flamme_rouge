"""Les 21 tuiles de la boîte (faces a–u et A–U) et les cartes étape officielles.

Chaque face de tuile est décrite par (virage, cases) :
  virage : None pour une ligne droite (ou le départ, l'arrivée),
           sinon (angle en radians, sens) avec sens +1 = à gauche, -1 = à droite ;
  cases  : une lettre par case (CELL_CHARS de tiles.py) : f plat, u montée, d descente,
           s grille de départ, e après la ligne d'arrivée.
Une ligne droite, le départ et l'arrivée font 6 cases ; un virage 2.

Une carte étape donne l'ordre des 21 tuiles par une chaîne de lettres
(minuscule = face plate, majuscule = face montagne).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .tiles import KIND_FINISH, KIND_SHARP, KIND_SOFT, KIND_START, KIND_STRAIGHT, Tile
from .track import LEFT, RIGHT

DEG45 = math.pi / 4
DEG90 = math.pi / 2
GAUCHE, DROITE = +1, -1

# Faces plates (a–u)
TILE_DEFS: dict[str, tuple[Optional[tuple[float, int]], str]] = {
    "a": (None, "sssssf"),  # départ
    "u": (None, "feeeee"),  # arrivée
    **{k: (None, "ffffff") for k in "bcdflmn"},  # 7 lignes droites
    **{k: ((DEG45, GAUCHE), "ff") for k in "hqt"},
    **{k: ((DEG45, DROITE), "ff") for k in "krs"},
    **{k: ((DEG90, GAUCHE), "ff") for k in "egi"},
    **{k: ((DEG90, DROITE), "ff") for k in "jop"},
}

# Faces montagne (A–U), relevées sur les tuiles physiques. Retourner un virage inverse son sens.
MOUNTAIN_DEFS: dict[str, tuple[Optional[tuple[float, int]], str]] = {
    "A": (None, "ssssff"),  # départ
    "U": (None, "uueeee"),  # arrivée : 2 montées puis la ligne
    "B": (None, "ddddff"),
    "C": (None, "fffuuu"),
    "D": (None, "uuuuud"),
    "F": (None, "dddfff"),
    "L": (None, "uuuddd"),
    "M": (None, "ffuuuu"),
    "N": (None, "uuuuuu"),
    "E": ((DEG90, DROITE), "uu"),
    "G": ((DEG90, DROITE), "uu"),
    "I": ((DEG90, DROITE), "ff"),
    "J": ((DEG90, GAUCHE), "ff"),
    "O": ((DEG90, GAUCHE), "uu"),
    "P": ((DEG90, GAUCHE), "dd"),
    "H": ((DEG45, DROITE), "dd"),
    "Q": ((DEG45, DROITE), "uu"),
    "T": ((DEG45, DROITE), "ff"),
    "K": ((DEG45, GAUCHE), "uu"),
    "R": ((DEG45, GAUCHE), "uu"),
    "S": ((DEG45, GAUCHE), "ff"),
}

# Les 6 cartes étape du jeu de base (lettre encadrée sur la carte = face montagne = majuscule).
STAGES = {
    "Avenue Corso Paseo": "abcdefghijklmnopqrstu",  # parcours conseillé pour une première partie
    "Ronde van Wevelgem": "abcmgfteqonLPjkIDHrSu",
    "La Haut Montagne": "abcfimetKGLHJsdopRQNU",
    "La Classicissima": "AebQRNHPcgikDFsLojmtu",
    "Firenze - Milano": "abcgiDHqntmKOLrepJsfu",
    "Ballons Centrale": "AnLHgceqtrMBoipjDFkSu",  # relevée sur la photo des cartes étape
}


def tile_from_def(letter: str, turn: Optional[tuple[float, int]], cells: str) -> Tile:
    if turn is None:
        kind = KIND_START if "s" in cells else KIND_FINISH if "e" in cells else KIND_STRAIGHT
        return Tile(kind, None, cells, letter)
    angle, sens = turn
    kind = KIND_SOFT if math.isclose(angle, DEG45) else KIND_SHARP if math.isclose(angle, DEG90) else None
    if kind is None:
        raise ValueError(f"Tuile {letter} : virage de {math.degrees(angle):.0f}° inconnu.")
    return Tile(kind, LEFT if sens > 0 else RIGHT, cells, letter)


OFFICIAL_TILES: dict[str, Tile] = {
    letter: tile_from_def(letter, turn, cells) for letter, (turn, cells) in {**TILE_DEFS, **MOUNTAIN_DEFS}.items()
}


# Extension Peloton : en attendant la description des 9 tuiles de la boîte, deux tuiles génériques
# (marquées « provisoire » dans l'éditeur) pour poser des pavés et une zone de ravitaillement.
PELOTON_PROVISIONAL: dict[str, Tile] = {
    "P1": Tile(KIND_STRAIGHT, None, "pppppp", "P1"),  # ligne droite pavée, une seule file
    "P2": Tile(KIND_STRAIGHT, None, "rrrrrr", "P2"),  # ligne droite de ravitaillement, trois files
}


def official_tile(letter: str) -> Tile:
    return OFFICIAL_TILES[letter] if letter in OFFICIAL_TILES else PELOTON_PROVISIONAL[letter]


@dataclass(frozen=True)
class OfficialStage:
    name: str
    setup: str
    tiles: Optional[tuple[Tile, ...]]  # None si une lettre est inconnue
    missing: tuple[str, ...]

    @property
    def available(self) -> bool:
        return self.tiles is not None


def build_stage(name: str, setup: str, catalog: dict[str, Tile] = OFFICIAL_TILES) -> OfficialStage:
    missing = tuple(dict.fromkeys(letter for letter in setup if letter not in catalog))
    tiles = None if missing else tuple(catalog[letter] for letter in setup)
    return OfficialStage(name, setup, tiles, missing)


def official_stages() -> list[OfficialStage]:
    return [build_stage(name, setup) for name, setup in STAGES.items()]
