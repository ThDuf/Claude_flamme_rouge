"""Contenu des decks de chaque coureur, en texte (utilisé par le mode texte et par la fenêtre graphique).

Pour chaque coureur on affiche, valeur par valeur :
  - pioche    : cartes pas encore tirées (la main en cours de choix y est comptée, pour ne pas la révéler) ;
  - recyclage : cartes écartées, face visible, qui seront remélangées quand la pioche sera vide ;
  - jouées    : cartes déjà jouées, retirées définitivement du jeu.
La colonne F compte les cartes Fatigue (valeur 2) reçues.
"""
from __future__ import annotations

from collections import Counter

from .cards import DECK_VALUES, Card
from .game import Game
from .rider import Rider

LABEL_W = 10
COL_W = 4


def _counts(cards: list[Card]) -> Counter:
    return Counter("F" if c.exhaustion else c.value for c in cards)


def deck_rows(rider: Rider) -> dict[str, Counter]:
    """Nombre de cartes par valeur ("F" pour la fatigue), pour chaque zone du deck."""
    return {
        "pioche": _counts(rider.draw_pile + rider.hand),
        "recyclage": _counts(rider.recycle),
        "jouées": _counts(rider.used),
    }


def deck_text(rider: Rider) -> str:
    rows = deck_rows(rider)
    columns: list = list(DECK_VALUES[rider.kind]) + ["F"]
    totals = {zone: sum(counter.values()) for zone, counter in rows.items()}

    lines = [
        f"{rider.name} — {rider.kind} (équipe {rider.team + 1}) : "
        f"{totals['pioche']} en pioche · {totals['recyclage']} en recyclage · {totals['jouées']} jouées",
        " " * (2 + LABEL_W) + "".join(str(c).rjust(COL_W) for c in columns) + "   total".rjust(8),
    ]
    for zone, counter in rows.items():
        cells = "".join((str(counter[c]) if counter[c] else "·").rjust(COL_W) for c in columns)
        lines.append(f"  {zone.ljust(LABEL_W)}{cells}{str(totals[zone]).rjust(8)}")
    if rider.hand:
        lines.append(f"  (la main de {len(rider.hand)} cartes en cours de choix est comptée dans la pioche)")
    return "\n".join(lines)


def all_decks_text(game: Game) -> str:
    return "\n\n".join(deck_text(r) for r in game.riders)
