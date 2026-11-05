"""Déroulement d'un tour étape par étape, sans aucune interface.

Une interface (texte ou graphique) n'a qu'à appeler :
  - choose(carte) tant que phase == CHOOSE ;
  - advance() pour passer à la phase suivante (mouvement, aspiration, fatigue).
Les événements à afficher s'accumulent dans `log` (voir drain_log).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .cards import Card
from .game import Game
from .rider import Rider

CHOOSE = "choose"  # chaque coureur choisit sa carte
MOVEMENT = "movement"  # cartes posées, prêt pour le mouvement
SLIPSTREAM = "slipstream"  # mouvement fait, prêt pour l'aspiration
EXHAUSTION = "exhaustion"  # aspiration faite, prêt pour la fatigue
FINISHED = "finished"


@dataclass
class LogLine:
    text: str
    team: Optional[int] = None  # équipe concernée (pour la couleur)
    heading: bool = False


def describe(card: Card) -> str:
    return f"{card.value} (fatigue)" if card.exhaustion else str(card.value)


class TurnController:
    def __init__(self, game: Game):
        self.game = game
        self.phase = CHOOSE
        self.log: list[LogLine] = []
        self._drained = 0
        self.played: dict[Rider, Card] = {}
        self.index = 0  # coureur en train de choisir
        self.hand: list[Card] = []
        self._begin_turn()

    @property
    def current_rider(self) -> Optional[Rider]:
        if self.phase == CHOOSE:
            return self.game.riders[self.index]
        return None

    def drain_log(self) -> list[LogLine]:
        """Les lignes ajoutées depuis le dernier appel."""
        new = self.log[self._drained :]
        self._drained = len(self.log)
        return new

    # ------------------------------------------------------------ choix des cartes

    def _begin_turn(self) -> None:
        self.log.append(LogLine(f"TOUR {self.game.turn + 1}", heading=True))
        self.played = {}
        self.index = 0
        self.phase = CHOOSE
        self._draw_next()

    def _draw_next(self) -> None:
        riders = self.game.riders
        while self.index < len(riders):
            rider = riders[self.index]
            hand = self.game.draw_hand_for(rider)
            if hand:
                self.hand = hand
                return
            # Plus de cartes Énergie : une carte Fatigue est jouée automatiquement.
            self.played[rider] = self.game.play_from_hand(rider, hand, None)
            self.log.append(LogLine(f"{rider.name} n'a plus de cartes : carte Fatigue jouée", rider.team))
            self.index += 1
        self.hand = []
        self.phase = MOVEMENT

    def choose(self, card: Card) -> None:
        if self.phase != CHOOSE:
            raise RuntimeError("Ce n'est pas le moment de choisir une carte.")
        rider = self.game.riders[self.index]
        self.played[rider] = self.game.play_from_hand(rider, self.hand, card)
        self.log.append(LogLine(f"{rider.name} a posé une carte (face cachée)", rider.team))
        self.index += 1
        self._draw_next()

    # --------------------------------------------------------------------- phases

    def advance(self) -> None:
        if self.phase == MOVEMENT:
            self._movement()
        elif self.phase == SLIPSTREAM:
            self._slipstream()
        elif self.phase == EXHAUSTION:
            self._exhaustion()
        else:
            raise RuntimeError("Rien à faire à cette étape.")

    def _movement(self) -> None:
        g = self.game
        order = sorted(g.riders, key=lambda r: (-r.position, r.lane))  # du premier au dernier
        start = {r: r.position for r in g.riders}
        g.movement_phase(self.played)
        self.log.append(LogLine("Mouvement", heading=True))
        for r in order:
            card = self.played[r]
            effective = g._effective_value(start[r], card.value)
            notes = []
            if effective > card.value:
                notes.append("descente : 5 minimum")
            elif effective < card.value:
                notes.append("montée : plafonné à 5")
            if r.position - start[r] < effective:
                notes.append("case pleine : s'arrête avant")
            note = f" ({', '.join(notes)})" if notes else ""
            self.log.append(
                LogLine(f"{r.name} joue {describe(card)} : case {start[r]} → {r.position}{note}", r.team)
            )
        self.phase = SLIPSTREAM

    def _slipstream(self) -> None:
        g = self.game
        before = {r: r.position for r in g.riders}
        moved = g.apply_slipstream()
        self.log.append(LogLine("Aspiration", heading=True))
        if moved:
            for r in sorted(moved, key=lambda r: -r.position):
                gain = r.position - before[r]
                self.log.append(LogLine(f"{r.name} aspiré : case {before[r]} → {r.position} (+{gain})", r.team))
        else:
            self.log.append(LogLine("Personne n'est aspiré."))
        self.phase = EXHAUSTION

    def _exhaustion(self) -> None:
        g = self.game
        exhausted = g.apply_exhaustion()
        self.log.append(LogLine("Fatigue", heading=True))
        if exhausted:
            for r in exhausted:
                self.log.append(LogLine(f"{r.name} reçoit une carte Fatigue (2)", r.team))
        else:
            self.log.append(LogLine("Personne n'est fatigué."))
        g.check_finish()
        g.turn += 1
        if g.finished:
            self.phase = FINISHED
            w = g.winner
            self.log.append(LogLine("ARRIVÉE", heading=True))
            self.log.append(
                LogLine(f"Victoire de l'équipe {w.team + 1} avec le {w.kind} {w.name} "
                        f"(case {w.position}) au tour {g.turn} !", w.team)
            )
        else:
            self._begin_turn()
