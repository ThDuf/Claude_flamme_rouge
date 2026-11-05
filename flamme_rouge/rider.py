"""Un coureur : position sur le plateau et paquet de cartes."""
import random
from dataclasses import dataclass, field

from .cards import ROULEUR, Card


@dataclass(eq=False)  # eq=False : un coureur est identifié par son identité, pas par ses valeurs
class Rider:
    team: int
    kind: str
    position: int = 0  # index de la case (0 = première case)
    lane: int = 0  # 0 = couloir de droite (prioritaire), 1 = couloir de gauche
    draw_pile: list[Card] = field(default_factory=list)  # pioche (face cachée)
    recycle: list[Card] = field(default_factory=list)  # défausse de recyclage (face visible)
    hand: list[Card] = field(default_factory=list)  # main en cours de choix (vide hors de la phase d'énergie)
    used: list[Card] = field(default_factory=list)  # cartes jouées : retirées définitivement du jeu

    @property
    def name(self) -> str:
        return f"{self.team + 1}{'R' if self.kind == ROULEUR else 'S'}"

    def draw_hand(self, n: int, rng: random.Random) -> list[Card]:
        """Pioche jusqu'à n cartes.

        Si la pioche est vide, on mélange la pile de recyclage pour former une
        nouvelle pioche. S'il n'y a pas assez de cartes au total, on prend ce
        qu'on peut (la main peut être plus petite, voire vide).
        """
        hand: list[Card] = []
        while len(hand) < n:
            if not self.draw_pile:
                if not self.recycle:
                    break
                self.draw_pile = self.recycle
                self.recycle = []
                rng.shuffle(self.draw_pile)
            hand.append(self.draw_pile.pop())
        return hand
