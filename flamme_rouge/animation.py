"""Animation des déplacements des coureurs (sans interface).

Le moteur de règles calcule les nouvelles positions d'un seul coup. Pour les voir glisser,
on compare les positions avant et après une phase (`moves_between`), puis `Animation`
donne, à chaque instant, la position intermédiaire de chaque coureur (case fractionnaire).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

# Réglages par défaut (en secondes)
MOVE_DURATION = 0.6  # durée du déplacement d'un coureur pendant la phase de mouvement
MOVE_GAP = 0.08  # pause entre la fin d'un coureur et le départ du suivant
MOVE_TOTAL_MAX = 4.5  # durée maximale de toute la phase de mouvement
MOVE_STAGGER = MOVE_DURATION + MOVE_GAP  # un coureur ne part que quand le précédent est arrivé
SLIPSTREAM_DURATION = 0.7  # tous les coureurs aspirés avancent ensemble
FRAME_MS = 33  # ~30 images par seconde


def ease(t: float) -> float:
    """Départ et arrivée en douceur (0 -> 1)."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


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


@dataclass(frozen=True)
class Animation:
    moves: Sequence[Move]  # dans l'ordre de départ : le premier de la liste bouge en premier
    duration: float = MOVE_DURATION
    stagger: float = 0.0  # 0 = tout le monde bouge en même temps

    @property
    def total(self) -> float:
        if not self.moves:
            return 0.0
        return self.stagger * (len(self.moves) - 1) + self.duration

    def done(self, t: float) -> bool:
        return t >= self.total

    def positions(self, t: float) -> dict:
        """{coureur: (case fractionnaire, couloir fractionnaire)} à l'instant t (en secondes)."""
        result = {}
        for k, move in enumerate(self.moves):
            e = ease((t - k * self.stagger) / self.duration)
            (s0, l0), (s1, l1) = move.start, move.end
            result[move.rider] = (s0 + (s1 - s0) * e, l0 + (l1 - l0) * e)
        return result


def movement_animation(moves: Sequence[Move]) -> Animation:
    """Phase de mouvement : les coureurs partent l'un après l'autre, du plus avancé au plus en retrait."""
    ordered = sorted(moves, key=lambda m: (-m.start[0], m.start[1]))
    # strictement l'un après l'autre : le premier arrive avant que le deuxième ne parte (durée réduite si beaucoup de coureurs)
    duration = min(MOVE_DURATION, MOVE_TOTAL_MAX / max(len(ordered), 1) - MOVE_GAP)
    return Animation(ordered, duration=duration, stagger=duration + MOVE_GAP)


def slipstream_animation(moves: Sequence[Move]) -> Animation:
    """Phase d'aspiration : tous les coureurs aspirés avancent en même temps."""
    return Animation(list(moves), duration=SLIPSTREAM_DURATION, stagger=0.0)
