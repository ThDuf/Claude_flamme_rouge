"""Parcours officiels : les cartes étape du jeu, assemblées à partir du catalogue de tuiles.

Une carte étape donne l'ordre des 21 tuiles par une chaîne de lettres (minuscule = côté
d'origine de la tuile, majuscule = côté retourné). Il manque ici la description de chaque
côté de tuile (ligne droite, virage doux ou serré, gauche ou droite, relief), que les
sources en ligne ne donnent pas : elle se renseigne dans `data/tuiles_officielles.json`.
Dès qu'une étape n'a plus aucune lettre manquante, elle devient jouable dans le menu.

Format d'une entrée de `data/tuiles_officielles.json` (la clé est la lettre, majuscule ou minuscule) :
    "g": {"kind": "sharp", "direction": "L", "terrain": "..AAAA"}
  kind      : "start", "finish", "straight", "soft" (virage doux 45°) ou "sharp" (virage serré 90°)
  direction : "L" ou "R" pour un virage, null sinon
  terrain   : une lettre par case, dans le sens de la course : "." plat, "A" montée, "D" descente
Les entrées à null (ou absentes) sont considérées comme inconnues.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

from .tiles import KIND_FINISH, KIND_START, SQUARES_PER_TILE, Tile

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tuiles_officielles.json")

# Les 5 cartes étape retranscrites depuis le règlement officiel (la 6e n'apparaît pas dans les sources).
STAGES = {
    "Avenue Corso Paseo": "abcdefghijklmnopqrstu",  # parcours conseillé pour une première partie
    "Ronde van Wevelgem": "abcmgfteqonLPjkIDHrSu",
    "La Haut Montagne": "abcfimetKGLHJsdopRQNU",
    "La Classicissima": "AebQRNHPcgikDFsLojmtu",
    "Firenze - Milano": "abcgiDHqntmKOLrepJsfu",
}

# Seules certitudes : la tuile a est le départ et la tuile u l'arrivée (leur relief est supposé plat).
BUILT_IN_CATALOG = {
    "a": Tile(KIND_START),
    "A": Tile(KIND_START),
    "u": Tile(KIND_FINISH),
    "U": Tile(KIND_FINISH),
}


@dataclass(frozen=True)
class OfficialStage:
    name: str
    setup: str
    tiles: Optional[tuple[Tile, ...]]  # None tant qu'il manque des tuiles
    missing: tuple[str, ...]  # lettres dont le côté n'est pas encore décrit

    @property
    def available(self) -> bool:
        return self.tiles is not None


def load_catalog(path: str = DATA_FILE) -> dict[str, Tile]:
    """Catalogue des côtés de tuiles connus : valeurs intégrées + fichier de données (s'il existe)."""
    catalog = dict(BUILT_IN_CATALOG)
    if not os.path.exists(path):
        return catalog
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} : le fichier doit contenir un objet JSON.")
    for letter, entry in data.items():
        if letter.startswith("_") or entry is None:
            continue
        if len(letter) != 1 or not letter.isalpha():
            raise ValueError(f"{path} : '{letter}' n'est pas une lettre de tuile.")
        try:
            catalog[letter] = Tile(entry["kind"], entry.get("direction"), entry.get("terrain", "." * SQUARES_PER_TILE))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"{path} : tuile '{letter}' invalide ({exc}).") from exc
    return catalog


def build_stage(name: str, setup: str, catalog: dict[str, Tile]) -> OfficialStage:
    missing = tuple(dict.fromkeys(letter for letter in setup if letter not in catalog))
    tiles = None if missing else tuple(catalog[letter] for letter in setup)
    return OfficialStage(name, setup, tiles, missing)


def official_stages(path: str = DATA_FILE) -> list[OfficialStage]:
    """Les cartes étape, jouables ou non selon le catalogue."""
    catalog = load_catalog(path)
    return [build_stage(name, setup, catalog) for name, setup in STAGES.items()]


def template_catalog() -> dict:
    """Contenu du fichier de données à compléter : une entrée par côté de tuile (a-u, A-U)."""
    template: dict = {
        "_aide": "Remplace chaque null par la description du côté de tuile : "
        '{"kind": "straight|soft|sharp|start|finish", "direction": "L|R|null", "terrain": "......"}. '
        "Voir flamme_rouge/official.py pour le détail du format."
    }
    for letter in "abcdefghijklmnopqrstu":
        for side in (letter, letter.upper()):
            built_in = BUILT_IN_CATALOG.get(side)
            template[side] = (
                {"kind": built_in.kind, "direction": built_in.direction, "terrain": built_in.terrain} if built_in else None
            )
    return template
