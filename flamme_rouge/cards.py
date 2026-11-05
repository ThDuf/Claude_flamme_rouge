"""Cartes Énergie et Fatigue."""
from dataclasses import dataclass

ROULEUR = "rouleur"
SPRINTEUR = "sprinteur"

EXHAUSTION_VALUE = 2

# 15 cartes par paquet : chaque valeur en 3 exemplaires.
DECK_VALUES = {
    ROULEUR: (3, 4, 5, 6, 7),
    SPRINTEUR: (2, 3, 4, 5, 9),
}


@dataclass(frozen=True)
class Card:
    value: int
    exhaustion: bool = False

    def __str__(self) -> str:
        return f"{self.value}F" if self.exhaustion else str(self.value)


def starting_deck(kind: str) -> list[Card]:
    """Paquet de départ (non mélangé) d'un coureur."""
    return [Card(v) for v in DECK_VALUES[kind] for _ in range(3)]


def exhaustion_card() -> Card:
    return Card(EXHAUSTION_VALUE, exhaustion=True)
