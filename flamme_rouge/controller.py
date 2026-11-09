"""Déroulement d'un tour étape par étape, sans aucune interface.

Une interface (texte ou graphique) n'a qu'à appeler :
  - (variante Échappée) choose_bid_rider(coureur ou None) puis choose(carte) tant que phase == BREAKAWAY ;
  - choose(carte) tant que phase == CHOOSE ;
  - advance() pour passer à la phase suivante (mouvement, aspiration, fatigue).
Les événements à afficher s'accumulent dans `log` (voir drain_log).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .ai import bid_card, breakaway_rider, choose_card
from .cards import ATTACK, Card
from .game import BID_ROUNDS, Game
from .stage import format_time
from .track import DESCENT
from .rider import Rider

BREAKAWAY = "breakaway"  # variante Échappée : enchères avant le premier tour
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
    if card.special:
        return {"attaque": "Attaque (2 / 9)", "muscle": "5 (Muscle)"}[card.special]
    return f"{card.value} (fatigue)" if card.exhaustion else str(card.value)


class TurnController:
    def __init__(self, game: Game, ai_teams: Iterable[int] = (), breakaway: bool = False):
        """`ai_teams` : numéros des équipes jouées par l'IA (0 = première équipe) ; leurs cartes sont choisies seules.
        `breakaway` : variante Échappée (extension Peloton), seulement si le parcours a une tuile Échappée."""
        self.game = game
        self.ai_teams = frozenset(ai_teams)
        # cartes révélées au dernier mouvement (toutes les équipes) et numéro de ce tour : pour les afficher
        self.last_revealed: dict[Rider, Card] = {}
        self.last_revealed_turn: Optional[int] = None
        self.phase = CHOOSE
        self.log: list[LogLine] = []
        self._drained = 0
        self.played: dict[Rider, Card] = {}
        self.index = 0  # coureur en train de choisir
        self.hand: list[Card] = []
        # variante Échappée : équipes qui peuvent enchérir (pas les fantômes), équipe en cours, coureur choisi, mises
        self.bid_teams = [t for t in range(len(game.team_types))
                          if not game.is_ghost(next(r for r in game.riders if r.team == t))]
        self.bid_index = 0
        self.bid_rider: Optional[Rider] = None
        self.bids: dict[Rider, list[Card]] = {}
        self.breakaway_winners: list[Rider] = []
        if breakaway and game.breakaway_squares():
            self._start_breakaway()
        else:
            self._begin_turn()

    @property
    def current_rider(self) -> Optional[Rider]:
        if self.phase == CHOOSE:
            return self.game.riders[self.index]
        if self.phase == BREAKAWAY:
            return self.bid_rider
        return None

    # ------------------------------------------------------- variante Échappée

    @property
    def bid_team(self) -> Optional[int]:
        """Équipe qui enchérit en ce moment (variante Échappée)."""
        if self.phase != BREAKAWAY or self.bid_index >= len(self.bid_teams):
            return None
        return self.bid_teams[self.bid_index]

    @property
    def bid_round(self) -> int:
        """Numéro de l'enchère en cours pour le coureur choisi (1 ou 2)."""
        return len(self.bids.get(self.bid_rider, [])) + 1 if self.bid_rider else 1

    def _start_breakaway(self) -> None:
        self.phase = BREAKAWAY
        self.log.append(LogLine("ÉCHAPPÉE : ENCHÈRES", heading=True))
        self._next_bidder()

    def _next_bidder(self) -> None:
        """Passe à l'équipe suivante ; l'IA enchérit toute seule ; à la fin, on résout l'échappée."""
        while self.bid_index < len(self.bid_teams):
            team = self.bid_teams[self.bid_index]
            if team not in self.ai_teams:
                return  # un joueur choisit son coureur (ou passe) à l'écran
            rider = breakaway_rider(self.game, team)
            self.log.append(LogLine(f"{rider.name} (IA) tente l'échappée", team))
            self.bids[rider] = []
            for _ in range(BID_ROUNDS):
                hand = self.game.draw_bid_hand(rider)
                self.bids[rider].append(self.game.put_bid(rider, hand, bid_card(hand)) if hand else Card(0))
            self.bid_index += 1
        self._resolve_breakaway()

    def choose_bid_rider(self, rider: Optional[Rider]) -> None:
        """Le joueur choisit le coureur qui tente l'échappée, ou None pour ne pas participer."""
        team = self.bid_team
        if team is None:
            raise RuntimeError("Ce n'est pas le moment des enchères.")
        if rider is None:
            self.log.append(LogLine(f"Équipe {team + 1} ne participe pas à l'échappée", team))
            self.bid_index += 1
            self._next_bidder()
            return
        if rider.team != team:
            raise ValueError("Ce coureur n'est pas de l'équipe qui enchérit.")
        self.bid_rider = rider
        self.bids[rider] = []
        self.log.append(LogLine(f"{rider.name} tente l'échappée", team))
        self.hand = self.game.draw_bid_hand(rider)
        if not self.hand:
            self._bid(None)

    def _bid(self, card: Optional[Card]) -> None:
        rider = self.bid_rider
        self.bids[rider].append(self.game.put_bid(rider, self.hand, card) if card is not None else Card(0))
        if len(self.bids[rider]) < BID_ROUNDS:
            self.hand = self.game.draw_bid_hand(rider)
            if not self.hand:
                self._bid(None)
            return
        self.bid_rider, self.hand = None, []
        self.bid_index += 1
        self._next_bidder()

    def _resolve_breakaway(self) -> None:
        g = self.game
        for rider, cards in sorted(self.bids.items(), key=lambda kv: -sum(c.value for c in kv[1])):
            total = sum(c.value for c in cards)
            self.log.append(LogLine(f"{rider.name} mise {' + '.join(str(c.value) for c in cards)} = {total}", rider.team))
        self.breakaway_winners = g.resolve_breakaway(self.bids) if self.bids else []
        for rider in self.breakaway_winners:
            self.log.append(LogLine(f"{rider.name} part en échappée (case {rider.position}) : 2 cartes Fatigue", rider.team))
        if self.bids and not self.breakaway_winners:
            self.log.append(LogLine("Pas de tuile Échappée sur ce parcours : personne ne part."))
        if not self.bids:
            self.log.append(LogLine("Personne n'a tenté l'échappée."))
        self.bids = {}
        self._begin_turn()

    def controller_of(self, rider: Rider) -> str:
        """Qui joue ce coureur : « Joueur », « IA », « Peloton » ou « Muscle »."""
        if self.game.is_ghost(rider):
            return self.game.team_type(rider).capitalize()
        return "IA" if rider.team in self.ai_teams else "Joueur"

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
        self.game.new_turn_cards()
        self._draw_next()

    def _draw_next(self) -> None:
        riders = self.game.riders
        while self.index < len(riders):
            rider = riders[self.index]
            if self.game.is_ghost(rider):  # équipe fantôme (Peloton, Muscle) : sa carte sera retournée au mouvement
                self.played[rider] = self.game.ghost_card(rider)
                self.index += 1
                continue
            hand = self.game.draw_hand_for(rider)
            size = self.game.hand_size(rider)
            if size != 4:
                wind = "vent arrière" if size > 4 else "vent de face"
                self.log.append(LogLine(f"{rider.name} : {wind}, pioche {size} cartes", rider.team))
            if hand and rider.team in self.ai_teams:  # l'IA choisit tout de suite, sans montrer sa main
                card = choose_card(self.game, rider, hand)
                self.played[rider] = self.game.play_from_hand(rider, hand, card)
                self.log.append(LogLine(f"{rider.name} (IA) a posé une carte (face cachée)", rider.team))
                self.index += 1
                continue
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
        if self.phase == BREAKAWAY and self.bid_rider is not None:  # carte misée pour l'échappée
            if card not in self.hand:
                raise ValueError(f"{card} n'est pas dans la main.")
            self._bid(card)
            return
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
        crashed_before = {r: r.crashed for r in g.riders}
        self.last_revealed = dict(self.played)  # les cartes sont retournées : tout le monde les voit
        self.last_revealed_turn = g.turn + 1
        g.movement_phase(self.played)
        self.log.append(LogLine("Mouvement", heading=True))
        for r in order:
            card = self.played[r]
            value = g.last_values.get(r, card.value)  # carte Attaque : 2 en tête, 9 derrière
            effective = g._effective_value(start[r], value, crashed_before[r])
            plain = g._effective_value(start[r], value)
            notes = []
            if g.is_ghost(r):
                notes.append(f"équipe {g.team_type(r).capitalize()}")
            if card.special == ATTACK:
                notes.append(f"ATTAQUE : {value}")
            if crashed_before[r]:
                notes.append("se relève : −2")
            if plain > value:
                notes.append("descente : 5 minimum" if g.track.kind(start[r]) == DESCENT else "ravitaillement : 4 minimum")
            elif plain < value:
                notes.append("montée : plafonné à 5" if plain <= 5 else f"montée : s'arrête au pied ({plain})")
            if r.position - start[r] < effective:
                notes.append("bloqué : s'arrête avant")
            if r in g.crashed_this_turn:
                notes.append("CHUTE sous la pluie")
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
        if g.tour:  # Grand Tour : jetons pris, arrivées avec leur temps
            for rider, stack, value in g.last_tokens:
                self.log.append(LogLine(f"{rider.name} prend le jeton {stack.label} : {value} point(s)", rider.team))
            if g.last_arrivals:
                self.log.append(LogLine("Arrivées", heading=True))
                for rider in g.last_arrivals:
                    place = g.arrived.index(rider) + 1
                    self.log.append(LogLine(f"{place}. {rider.name} : {format_time(g.stage_time[rider])}", rider.team))
        if g.finished and g.tour:
            self.phase = FINISHED
            self.log.append(LogLine("ÉTAPE TERMINÉE", heading=True))
            w = g.winner
            self.log.append(LogLine(f"Victoire d'étape : {w.name} (équipe {w.team + 1}) en {format_time(g.stage_time[w])}", w.team))
        elif g.finished:
            self.phase = FINISHED
            w = g.winner
            self.log.append(LogLine("ARRIVÉE", heading=True))
            self.log.append(
                LogLine(f"Victoire de l'équipe {w.team + 1} avec le {w.kind} {w.name} "
                        f"(case {w.position}) au tour {g.turn} !", w.team)
            )
        else:
            self._begin_turn()
