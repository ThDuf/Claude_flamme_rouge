"""Éditeur de parcours : la palette des tuiles de la boîte (l'édition elle-même est dans online/static/editor.js)."""
from __future__ import annotations

from .official import OFFICIAL_TILES, PELOTON_TILES
from .tiles import KIND_FINISH, KIND_SHARP, KIND_SOFT, KIND_START, KIND_STRAIGHT

# ------------------------------------------------------------------ palette des tuiles de la boîte

FLAT_SIDE, MOUNTAIN_SIDE, PELOTON_SIDE = "plat", "montagne", "peloton"
_KIND_ORDER = {KIND_START: 0, KIND_FINISH: 1, KIND_STRAIGHT: 2, KIND_SOFT: 3, KIND_SHARP: 4}


def side_letters(side: str) -> list[str]:
    """Les 21 lettres d'une face de la boîte, rangées par type : départ, arrivée, droites, virages doux, serrés."""
    if side == PELOTON_SIDE:
        return list(PELOTON_TILES)
    letters = "abcdefghijklmnopqrstu" if side == FLAT_SIDE else "ABCDEFGHIJKLMNOPQRSTU"
    return sorted(letters, key=lambda c: (_KIND_ORDER[OFFICIAL_TILES[c].kind], OFFICIAL_TILES[c].direction or "", c))


def letter_for_tile(tile) -> str | None:
    """Lettre officielle d'une tuile du parcours (une tuile « libre » identique à une face officielle compte)."""
    if tile.letter in OFFICIAL_TILES or tile.letter in PELOTON_TILES:
        return tile.letter
    return next((letter for letter, official in OFFICIAL_TILES.items() if official == tile), None)
