"""Moteur de règles de Flamme Rouge (sans aucune interface)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

from .cards import ROULEUR, SPRINTEUR, Card, exhaustion_card, starting_deck
from .rider import Rider
from .track import ASCENT, DESCENT, Track

HAND_SIZE = 4
MOUNTAIN_SPEED = 5  # plafond en montée ET minimum en descente
MAX_PER_SQUARE = 2  # 2 couloirs par case

# Un "chooser" choisit la carte à jouer parmi la main. C'est le point d'entrée
# pour brancher plus tard une interface humaine ou une IA.
Chooser = Callable[["Game", Rider, "list[Card]"], Card]


def random_chooser(game: "Game", rider: Rider, hand: list[Card]) -> Card:
    return game.rng.choice(hand)


@dataclass
class TurnReport:
    turn: int
    played: dict[str, Card] = field(default_factory=dict)
    slipstreamed: list[str] = field(default_factory=list)
    exhausted: list[str] = field(default_factory=list)


class Game:
    def __init__(self, track: Optional[Track] = None, num_teams: int = 2, seed: Optional[int] = None):
        if not 2 <= num_teams <= 4:
            raise ValueError("Le jeu de base se joue de 2 à 4 équipes.")
        self.track = track or Track()
        self.rng = random.Random(seed)
        self.turn = 0
        self.finished = False
        self.winner: Optional[Rider] = None

        self.riders: list[Rider] = []
        for team in range(num_teams):
            for kind in (ROULEUR, SPRINTEUR):
                rider = Rider(team=team, kind=kind, draw_pile=starting_deck(kind))
                self.rng.shuffle(rider.draw_pile)
                self.riders.append(rider)
        # Placement initial simplifié : 2 coureurs par case de départ.
        # (Plus tard : laisser chaque joueur choisir son emplacement.)
        for i, rider in enumerate(self.riders):
            rider.position = i // MAX_PER_SQUARE
            rider.lane = i % MAX_PER_SQUARE

    # ------------------------------------------------------------------ outils

    def riders_at(self, square: int, exclude: Optional[Rider] = None) -> list[Rider]:
        return [r for r in self.riders if r.position == square and r is not exclude]

    # ------------------------------------------------------------- 1. Énergie

    def energy_phase(self, chooser: Optional[Chooser] = None) -> dict[Rider, Card]:
        """Chaque coureur pioche 4 cartes, en joue 1 et recycle les 3 autres.

        Pour chaque équipe, on traite le rouleur puis le sprinteur (les règles
        autorisent l'ordre inverse : à ajouter plus tard). On ne pioche pour le
        2e coureur qu'après avoir choisi la carte du 1er.
        """
        chooser = chooser or random_chooser
        played: dict[Rider, Card] = {}
        for rider in self.riders:
            hand = self.draw_hand_for(rider)
            card = chooser(self, rider, hand) if hand else None
            played[rider] = self.play_from_hand(rider, hand, card)
        return played

    def draw_hand_for(self, rider: Rider) -> list[Card]:
        """Pioche la main de 4 cartes (moins s'il n'en reste pas assez)."""
        hand = rider.draw_hand(HAND_SIZE, self.rng)
        rider.hand = list(hand)  # copie : sert à afficher le contenu du deck pendant le choix
        return hand

    def play_from_hand(self, rider: Rider, hand: list[Card], card: Optional[Card]) -> Card:
        """Joue `card` parmi `hand` et recycle les autres.

        Si la main est vide (plus aucune carte Énergie), le coureur joue une carte Fatigue.
        Ces deux méthodes permettent à une interface de demander la carte au joueur
        entre la pioche et la pose, sans bloquer le moteur.
        """
        if not hand:
            rider.hand = []
            return exhaustion_card()
        if card not in hand:
            raise ValueError(f"{card} n'est pas dans la main de {rider.name} : {hand}")
        rest = list(hand)
        rest.remove(card)
        rider.recycle.extend(rest)  # les 3 autres vont dans la pile de recyclage
        rider.used.append(card)  # la carte jouée est retirée du jeu (on la garde pour l'affichage)
        rider.hand = []
        return card

    # ------------------------------------------------------------ 2. Mouvement

    def _effective_value(self, start: int, value: int) -> int:
        """Applique les règles de descente (minimum 5) puis de montée (maximum 5)."""
        if self.track.kind(start) == DESCENT:
            value = max(value, MOUNTAIN_SPEED)
        # Montée : plafond de 5 si on démarre sur, entre dans, ou traverse une case de montée.
        if any(self.track.kind(s) == ASCENT for s in range(start, start + value + 1)):
            value = min(value, MOUNTAIN_SPEED)
        return value

    def _move(self, rider: Rider, card: Card) -> None:
        start = rider.position
        target = start + self._effective_value(start, card.value)
        # On peut traverser une case pleine mais pas s'y arrêter : on recule
        # jusqu'à la première case avec de la place (au pire, sa case de départ).
        while target > start and len(self.riders_at(target, exclude=rider)) >= MAX_PER_SQUARE:
            target -= 1
        others = self.riders_at(target, exclude=rider)
        rider.position = target
        rider.lane = 0 if not any(o.lane == 0 for o in others) else 1

    def movement_phase(self, played: dict[Rider, Card]) -> None:
        """Les coureurs avancent un par un, du premier au dernier."""
        order = sorted(self.riders, key=lambda r: (-r.position, r.lane))
        for rider in order:
            self._move(rider, played[rider])

    # ---------------------------------------------------------------- 3. Fin

    def _packs(self) -> list[list[int]]:
        """Groupes (packs) de cases occupées consécutives, de l'arrière vers l'avant."""
        occupied = sorted({r.position for r in self.riders})
        packs = [[occupied[0]]]
        for square in occupied[1:]:
            if square == packs[-1][-1] + 1:
                packs[-1].append(square)
            else:
                packs.append([square])
        return packs

    def apply_slipstream(self) -> list[Rider]:
        """Aspiration : un pack séparé du pack de devant par exactement 1 case vide avance d'1 case.

        Tous les packs éligibles avancent en même temps, et on recommence jusqu'à
        ce que plus personne ne puisse aspirer (un coureur peut donc aspirer
        plusieurs fois). Un coureur sur une case de montée ne donne ni ne reçoit d'aspiration.

        Hypothèse à vérifier : si la case vide visée est elle-même une montée, le pack n'aspire pas.
        """
        moved: list[Rider] = []
        while True:
            packs = self._packs()
            to_shift: set[int] = set()
            for rear, front in zip(packs, packs[1:]):
                gap_square = rear[-1] + 1
                if front[0] - rear[-1] - 1 != 1:
                    continue
                if self.track.kind(front[0]) == ASCENT:  # ne peut pas donner
                    continue
                if self.track.kind(gap_square) == ASCENT or any(
                    self.track.kind(s) == ASCENT for s in rear
                ):  # ne peut pas recevoir
                    continue
                to_shift.update(rear)
            if not to_shift:
                return moved
            for rider in self.riders:
                if rider.position in to_shift:
                    rider.position += 1
                    if rider not in moved:
                        moved.append(rider)

    def apply_exhaustion(self) -> list[Rider]:
        """Fatigue : un coureur dont la case devant lui est entièrement vide reçoit une carte Fatigue (2)."""
        exhausted = [r for r in self.riders if not self.riders_at(r.position + 1)]
        for rider in exhausted:
            rider.recycle.append(exhaustion_card())
        return exhausted

    def check_finish(self) -> None:
        crossed = [r for r in self.riders if r.position >= len(self.track)]
        if crossed:
            self.finished = True
            # Le plus loin gagne ; à égalité de case, le couloir de droite est devant
            # (hypothèse à vérifier dans le livret).
            self.winner = max(crossed, key=lambda r: (r.position, -r.lane))

    def end_phase(self) -> tuple[list[Rider], list[Rider]]:
        """Les cartes jouées sont déjà retirées du jeu ; puis aspiration, fatigue, vérification de l'arrivée."""
        slipstreamed = self.apply_slipstream()
        exhausted = self.apply_exhaustion()
        self.check_finish()
        return slipstreamed, exhausted

    # ----------------------------------------------------------------- Un tour

    def play_turn(self, chooser: Optional[Chooser] = None) -> TurnReport:
        if self.finished:
            raise RuntimeError("La partie est terminée.")
        played = self.energy_phase(chooser)
        self.movement_phase(played)
        slipstreamed, exhausted = self.end_phase()
        self.turn += 1
        return TurnReport(
            turn=self.turn,
            played={r.name: c for r, c in played.items()},
            slipstreamed=[r.name for r in slipstreamed],
            exhausted=[r.name for r in exhausted],
        )
