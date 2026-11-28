"""Logique d'édition d'un parcours en tuiles (sans interface), avec annulation."""
from __future__ import annotations

from typing import Optional, Sequence

from .official import OFFICIAL_TILES, PELOTON_TILES
from .tiles import KIND_FINISH, KIND_SHARP, KIND_SOFT, KIND_START, KIND_STRAIGHT, Tile

UNDO_LIMIT = 100


class PlanEditor:
    def __init__(self, tiles: Optional[Sequence[Tile]] = None):
        self.tiles: list[Tile] = list(tiles or [])
        self.selected: Optional[int] = None
        self._undo: list[tuple[list[Tile], Optional[int]]] = []

    # ------------------------------------------------------------------ outils

    def _remember(self) -> None:
        self._undo.append((list(self.tiles), self.selected))
        del self._undo[:-UNDO_LIMIT]

    def _need_selection(self) -> int:
        if self.selected is None:
            raise ValueError("Aucune tuile sélectionnée.")
        return self.selected

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    # --------------------------------------------------------------- sélection

    def select(self, index: Optional[int]) -> None:
        if index is not None and not 0 <= index < len(self.tiles):
            raise IndexError(f"Pas de tuile numéro {index + 1}.")
        self.selected = index

    # ---------------------------------------------------------------- édition

    def append(self, tile: Tile) -> None:
        """Ajoute la tuile à la fin du parcours et la sélectionne."""
        self._remember()
        self.tiles.append(tile)
        self.selected = len(self.tiles) - 1

    def insert_after(self, tile: Tile) -> None:
        """Insère la tuile juste après la tuile sélectionnée et la sélectionne."""
        index = self._need_selection()
        self._remember()
        self.tiles.insert(index + 1, tile)
        self.selected = index + 1

    def replace(self, tile: Tile) -> None:
        index = self._need_selection()
        self._remember()
        self.tiles[index] = tile

    def remove(self) -> None:
        """Supprime la tuile sélectionnée ; la sélection passe à la tuile voisine."""
        index = self._need_selection()
        self._remember()
        del self.tiles[index]
        self.selected = min(index, len(self.tiles) - 1) if self.tiles else None

    def move(self, delta: int) -> None:
        """Déplace la tuile sélectionnée vers le départ (delta < 0) ou vers l'arrivée (delta > 0)."""
        index = self._need_selection()
        target = index + delta
        if not 0 <= target < len(self.tiles):
            return
        self._remember()
        self.tiles[index], self.tiles[target] = self.tiles[target], self.tiles[index]
        self.selected = target

    def clear(self) -> None:
        if not self.tiles:
            return
        self._remember()
        self.tiles = []
        self.selected = None

    def load(self, tiles: Sequence[Tile]) -> None:
        """Remplace tout le parcours (ouverture d'un fichier, exemple...)."""
        self._remember()
        self.tiles = list(tiles)
        self.selected = None

    def undo(self) -> None:
        if not self._undo:
            return
        self.tiles, self.selected = self._undo.pop()


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
