"""Logique d'édition d'un parcours en tuiles (sans interface), avec annulation."""
from __future__ import annotations

from typing import Optional, Sequence

from .tiles import Tile

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
