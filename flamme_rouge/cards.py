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


ATTACK = "attaque"  # extension Peloton : carte Attaque de l'équipe Peloton (tête +2, arrière +9)
MUSCLE = "muscle"  # extension Peloton : carte Muscle de l'équipe Muscle (un 5)
ATTACK_FRONT, ATTACK_REAR = 2, 9


@dataclass(frozen=True)
class Card:
    value: int
    exhaustion: bool = False
    special: str = ""  # ATTACK ou MUSCLE pour les cartes des équipes fantômes

    def __str__(self) -> str:
        if self.special == ATTACK:
            return f"A{ATTACK_FRONT}/{ATTACK_REAR}"
        if self.special == MUSCLE:
            return f"{self.value}M"
        return f"{self.value}F" if self.exhaustion else str(self.value)


def starting_deck(kind: str) -> list[Card]:
    """Paquet de départ (non mélangé) d'un coureur."""
    return [Card(v) for v in DECK_VALUES[kind] for _ in range(3)]


def attack_card() -> Card:
    return Card(ATTACK_FRONT, special=ATTACK)


def muscle_card() -> Card:
    return Card(5, special=MUSCLE)


def exhaustion_card() -> Card:
    return Card(EXHAUSTION_VALUE, exhaustion=True)
