"""Extension Météo : tirage des jetons et effet de chaque météo (sans interface).

Règles (voir docs/extension_meteo.md) :
  - 13 jetons (4 effets, un de chaque, et 9 « beau temps ») ; un jeton tiré au hasard
    par ligne droite, hors départ et arrivée ;
  - vent de travers : sur la tuile, pas d'aspiration reçue ni donnée ;
  - vent arrière / de face : qui commence le tour sur la tuile pioche 5 / 3 cartes ;
  - pluie : qui finit son mouvement sur la tuile après avoir été bloqué chute.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence

from .track import Track

CROSSWIND = "travers"
TAILWIND = "arriere"
HEADWIND = "face"
RAIN = "pluie"
SUNNY = "soleil"  # jeton « beau temps » : aucun effet (on le garde pour l'afficher)
EFFECTS = (CROSSWIND, TAILWIND, HEADWIND, RAIN)
SUNNY_TOKENS = 9

NAMES = {CROSSWIND: "Vent de travers", TAILWIND: "Vent arrière", HEADWIND: "Vent de face", RAIN: "Pluie", SUNNY: "Beau temps"}
SHORT = {CROSSWIND: "TRAVERS", TAILWIND: "VENT +1", HEADWIND: "VENT −1", RAIN: "PLUIE"}
HAND_CHANGE = {TAILWIND: +1, HEADWIND: -1}

STRAIGHT_CHUNK = 6  # longueur d'une ligne droite, pour découper un parcours qui n'est pas fait de tuiles


@dataclass(frozen=True)
class WeatherZone:
    start: int  # première case
    end: int  # case juste après la dernière
    effect: str

    def __contains__(self, square: int) -> bool:
        return self.start <= square < self.end


def straight_segments(track: Track) -> list[tuple[int, int]]:
    """Les lignes droites qui peuvent recevoir un jeton (hors départ et arrivée).

    Un parcours fait de tuiles les connaît (`track.straights`). Sinon, on découpe les portions
    droites en tronçons de 6 cases, sans compter le premier et le dernier (départ, arrivée)."""
    if track.straights is not None:
        return list(track.straights)
    chunks: list[tuple[int, int]] = []
    s, n = 0, len(track)
    while s < n:
        if track.angle(s) != 0:
            s += 1
            continue
        end = s
        while end < n and track.angle(end) == 0:
            end += 1
        for k in range(s, end - STRAIGHT_CHUNK + 1, STRAIGHT_CHUNK):
            chunks.append((k, k + STRAIGHT_CHUNK))
        s = end
    return chunks[1:-1]


def draw_weather(track: Track, rng: random.Random) -> list[WeatherZone]:
    """Mise en place : les 13 jetons mélangés, un par ligne droite (les « beau temps » sont gardés, sans effet)."""
    tokens: list[str] = list(EFFECTS) + [SUNNY] * SUNNY_TOKENS
    rng.shuffle(tokens)
    return [WeatherZone(a, b, effect) for (a, b), effect in zip(straight_segments(track), tokens)]


class Weather:
    """La météo d'une partie : quel effet sur quelle case."""

    def __init__(self, zones: Sequence[WeatherZone] = ()):
        self.zones = list(zones)  # toutes les lignes droites tirées, « beau temps » compris

    @property
    def effects(self) -> list[WeatherZone]:
        """Les zones qui ont un effet (sans les « beau temps »)."""
        return [z for z in self.zones if z.effect != SUNNY]

    def at(self, square: int) -> Optional[str]:
        return next((z.effect for z in self.zones if square in z), None)

    def hand_size(self, square: int, base: int) -> int:
        return base + HAND_CHANGE.get(self.at(square), 0)

    def blocks_slipstream(self, square: int) -> bool:
        return self.at(square) == CROSSWIND

    def is_rain(self, square: int) -> bool:
        return self.at(square) == RAIN

    def __bool__(self) -> bool:
        """Vrai si la partie se joue avec la météo (même s'il ne fait que beau)."""
        return bool(self.zones)
