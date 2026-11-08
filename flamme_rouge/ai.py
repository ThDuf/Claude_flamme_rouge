"""IA qui joue une équipe : pour chaque coureur, elle choisit la carte à poser parmi sa main.

Elle ne triche pas : elle ne regarde que sa main, le parcours (relief, météo) et la position
actuelle des coureurs, comme un joueur autour de la table.

Pour chaque carte, elle estime la case d'arrivée (montée, descente, relève après une chute,
cases pleines) puis donne une note :
  + les cases gagnées ;
  - le prix de la carte : une grosse carte dépensée tôt manque pour le sprint final
    (ce prix baisse à l'approche de l'arrivée) ;
  - le gâchis : une grosse carte plafonnée à 5 en montée ;
  + jouer une carte Fatigue (elle quitte le jeu), surtout quand elle ne coûte rien (descente) ;
  + finir juste derrière un coureur (pas de fatigue) ou à une case d'un groupe (aspiration) ;
  + franchir la ligne, le plus loin possible.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .cards import Card

if TYPE_CHECKING:
    from .game import Game
    from .rider import Rider

SPRINT_ZONE = 20  # à moins de 20 cases de l'arrivée, on ne garde plus ses grosses cartes
CARD_COST = 0.1  # prix d'un point de carte loin de l'arrivée (réglé en simulant des centaines de courses)
WASTE_COST = 0.6  # par point de carte perdu (plafond de montée)
EXHAUSTION_BONUS = 1.5  # se débarrasser d'une carte Fatigue
SHELTER_BONUS = 1.2  # un coureur juste devant : pas de carte Fatigue en fin de tour
SLIPSTREAM_BONUS = 1.6  # une case vide puis un coureur : aspiration probable
FINISH_BONUS = 100.0


def destination(game: "Game", rider: "Rider", card: Card) -> int:
    """Case où le coureur finirait avec cette carte, si personne d'autre ne bougeait."""
    start = rider.position
    wanted = start + game._effective_value(start, card.value, rider.crashed)
    target = next((s - 1 for s in range(start + 1, wanted + 1) if game.is_blocked(s, exclude=rider)), wanted)
    while target > start and game.is_full(target, exclude=rider):
        target -= 1
    return target


def score(game: "Game", rider: "Rider", card: Card) -> float:
    """Note d'une carte pour ce coureur (plus c'est haut, mieux c'est)."""
    finish = len(game.track)
    dest = destination(game, rider, card)
    gained = dest - rider.position
    if dest >= finish:  # on franchit la ligne : le plus loin possible gagne
        return FINISH_BONUS + dest
    effective = game._effective_value(rider.position, card.value, rider.crashed)
    distance_left = finish - rider.position
    urgency = max(0.0, min(1.0, (distance_left - 4) / SPRINT_ZONE))  # 1 loin de l'arrivée, 0 tout près
    value = gained
    value -= CARD_COST * urgency * (0 if card.exhaustion else card.value)
    value -= WASTE_COST * max(0, card.value - effective) * (0 if card.exhaustion else 1)
    if card.exhaustion:
        value += EXHAUSTION_BONUS
    others = [r for r in game.riders if r is not rider]
    occupied = {r.position for r in others}
    if dest + 1 in occupied:
        value += SHELTER_BONUS
    elif dest + 2 in occupied and not game.no_slipstream(dest):
        value += SLIPSTREAM_BONUS
    return value


def choose_card(game: "Game", rider: "Rider", hand: list[Card]) -> Card:
    """La meilleure carte de la main ; à égalité, la plus petite (on garde les grosses)."""
    return max(hand, key=lambda c: (round(score(game, rider, c), 6), -c.value, c.exhaustion))


BID_HIGH = 6  # variante Échappée : l'IA ne mise une grosse carte que si elle en a une d'au moins 6


def breakaway_rider(game: "Game", team: int) -> "Rider":
    """Variante Échappée : l'IA tente l'échappée avec son Rouleur (paquet régulier, utile devant)."""
    riders = [r for r in game.riders if r.team == team]
    return next((r for r in riders if r.kind == "rouleur"), riders[0])


def bid_card(hand: list[Card]) -> Card:
    """Mise de l'IA : sa plus grosse carte si elle vaut au moins 6 (elle joue pour gagner), sinon sa plus petite
    (elle garde ses cartes pour la course)."""
    best = max(hand, key=lambda c: c.value)
    return best if best.value >= BID_HIGH else min(hand, key=lambda c: c.value)


def ai_chooser(game: "Game", rider: "Rider", hand: list[Card]) -> Card:
    """Même signature que les autres « choosers » du moteur (voir game.Chooser)."""
    return choose_card(game, rider, hand)
