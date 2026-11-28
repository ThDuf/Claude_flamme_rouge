"""Déplacements des coureurs pendant une phase, pour que le navigateur les anime.

Le moteur de règles calcule les nouvelles positions d'un seul coup. On compare les positions avant et après une
phase (`moves_between`) ; le navigateur fait glisser chaque coureur de l'une à l'autre (makeAnimation dans app.js).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Move:
    rider: object
    start: tuple[int, int]  # (case, couloir) avant
    end: tuple[int, int]  # (case, couloir) après


def snapshot(riders: Iterable) -> dict:
    """Positions actuelles : {coureur: (case, couloir)}."""
    return {r: (r.position, r.lane) for r in riders}


def moves_between(before: dict, riders: Iterable) -> list[Move]:
    """Les coureurs dont la case ou le couloir a changé depuis `before`."""
    return [Move(r, before[r], (r.position, r.lane)) for r in riders if before[r] != (r.position, r.lane)]


