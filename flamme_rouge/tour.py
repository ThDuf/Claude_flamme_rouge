"""Extension Grand Tour : un Tour, c'est-à-dire plusieurs étapes à la suite (sans interface).

Ce module garde ce qui passe d'une étape à l'autre :
  - le paquet de chaque coureur (avec la moitié de sa fatigue, arrondie à l'inférieur, rendue entre deux étapes) ;
  - le temps total, les points de Sprint et de Montagne de chaque coureur (classements et maillots) ;
  - les Points de Tour de chaque équipe (podiums d'étape, jours de repos, bonus de fin de Tour).

Voir docs/extension_grand_tour.md pour la règle.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from .cards import Card, starting_deck
from .game import GHOSTS, TEAM_PLAYER, Game
from .stage import MOUNTAIN, SPRINT, format_time, place_tokens
from .track import Track

PODIUM_POINTS = (3, 2, 1)
YELLOW, GREEN, POLKA = "jaune", "vert", "pois"
JERSEY_NAMES = {YELLOW: "maillot jaune", GREEN: "maillot vert", POLKA: "maillot à pois"}

# Points de Tour bonus à la fin du Tour, selon sa longueur : (général, équipe, sprint, montagne)
BONUS_TABLE = {
    "court": ((3, 2, 1), (1,), (2, 1), (2, 1)),  # 3 à 7 étapes (et toujours à 2 joueurs)
    "moyen": ((4, 3, 2, 1), (2, 1), (3, 2, 1), (3, 2, 1)),  # 8 à 14 étapes
    "long": ((5, 4, 3, 2, 1), (3, 2, 1), (4, 3, 2, 1), (4, 3, 2, 1)),  # 15 à 21 étapes
}

Key = tuple[int, int]  # (équipe, 0 = premier coureur / 1 = second)


@dataclass
class TourStage:
    name: str
    track: Track


@dataclass
class StageResult:
    """Ce qui s'est passé dans une étape terminée."""

    name: str
    order: list[Key]  # ordre d'arrivée
    times: dict[Key, int]  # temps d'étape en secondes
    sprint: dict[Key, int] = field(default_factory=dict)
    mountain: dict[Key, int] = field(default_factory=dict)
    podium: list[Key] = field(default_factory=list)  # 3 premiers : 3, 2, 1 Points de Tour
    rest_day: bool = False
    rest_points: dict[int, int] = field(default_factory=dict)  # Points de Tour du jour de repos, par équipe
    fatigue_returned: dict[Key, int] = field(default_factory=dict)


class Tour:
    def __init__(
        self,
        stages: Sequence[TourStage],
        num_teams: int,
        team_types: Optional[Sequence[str]] = None,
        extensions: Iterable[str] = (),
        rest_after: Iterable[int] = (),
        seed: Optional[int] = None,
    ):
        """`rest_after` : numéros des étapes (1 = première) après lesquelles il y a un jour de repos."""
        if len(stages) < 3:
            raise ValueError("Un Tour compte au moins 3 étapes.")
        self.stages = list(stages)
        self.num_teams = num_teams
        self.team_types = list(team_types or [TEAM_PLAYER] * num_teams)
        self.extensions = frozenset(extensions)
        self.rest_after = frozenset(rest_after)
        self.rng = random.Random(seed)
        self.stage_index = 0  # étape en cours (0 = première)
        self.names: dict[Key, str] = {}
        self.decks: dict[Key, list[Card]] = {}
        self.total_time: dict[Key, int] = {}
        self.sprint: dict[Key, int] = {}
        self.mountain: dict[Key, int] = {}
        self.podium_points = [0] * num_teams
        self.rest_points = [0] * num_teams
        self.results: list[StageResult] = []
        self.jerseys: dict[str, Key] = {}
        self.finished = False

    # ------------------------------------------------------------------ étapes

    @property
    def current(self) -> TourStage:
        return self.stages[self.stage_index]

    def keys(self) -> list[Key]:
        return sorted(self.total_time) if self.total_time else [(t, i) for t in range(self.num_teams) for i in (0, 1)]

    def team_order(self) -> list[int]:
        """Ordre de placement au départ : au hasard pour la 1re étape ; ensuite, l'équipe qui a le moins de Points de
        Tour se place en premier (égalité : celle qui a le coureur le mieux classé au général perd l'égalité)."""
        teams = list(range(self.num_teams))
        if not self.results:
            self.rng.shuffle(teams)
            return teams
        best_gc = {t: min(self.gc_rank(k) for k in self.keys() if k[0] == t) for t in teams}
        return sorted(teams, key=lambda t: (self.tour_points(t, with_bonus=False), -best_gc[t]))

    def start_stage(self, seed: Optional[int] = None, **game_options) -> Game:
        """La partie de l'étape en cours, avec les paquets hérités et les jetons Sprint/Montagne."""
        stage = self.current
        game = Game(stage.track, num_teams=self.num_teams, seed=seed if seed is not None else self.rng.randrange(10**9),
                    extensions=self.extensions, team_types=self.team_types, tour=True, decks=self.decks or None,
                    team_order=self.team_order(), tokens=place_tokens(stage.track), **game_options)
        if not self.names:
            self.names = {game.rider_key(r): r.name for r in game.riders}
        holders = {k: jersey for jersey, k in self.jerseys.items()}
        game.jerseys = {r: holders[game.rider_key(r)] for r in game.riders if game.rider_key(r) in holders}
        return game

    def finish_stage(self, game: Game) -> StageResult:
        """Étape terminée : temps, points, podium, paquets (moitié de la fatigue rendue), maillots, jour de repos."""
        if not game.finished:
            raise RuntimeError("L'étape n'est pas terminée.")
        key = game.rider_key
        order = [key(r) for r in game.arrived]
        result = StageResult(
            name=self.current.name,
            order=order,
            times={key(r): t for r, t in game.stage_time.items()},
            sprint={key(r): p for r, p in game.points[SPRINT].items()},
            mountain={key(r): p for r, p in game.points[MOUNTAIN].items()},
            podium=order[:3],
        )
        for k in order:
            self.total_time[k] = self.total_time.get(k, 0) + result.times[k]
            self.sprint[k] = self.sprint.get(k, 0) + result.sprint.get(k, 0)
            self.mountain[k] = self.mountain.get(k, 0) + result.mountain.get(k, 0)
        for k, points in zip(result.podium, PODIUM_POINTS):
            self.podium_points[k[0]] += points
        # paquets : cartes Énergie jouées rendues, moitié de la fatigue rendue (arrondi à l'inférieur)
        for rider in game.all_riders:
            if game.is_ghost(rider):
                continue
            deck = rider.draw_pile + rider.recycle + rider.hand + [c for c in rider.used if not c.exhaustion]
            result.fatigue_returned[key(rider)] = self._return_fatigue(deck)
            self.decks[key(rider)] = deck
        self.results.append(result)
        self.award_jerseys()
        stage_number = self.stage_index + 1
        if stage_number in self.rest_after and stage_number < len(self.stages):
            self._rest_day(result)
        self.stage_index += 1
        self.finished = self.stage_index >= len(self.stages)
        return result

    @staticmethod
    def _return_fatigue(deck: list[Card]) -> int:
        """Rend la moitié des cartes Fatigue du paquet (arrondi à l'inférieur) ; renvoie combien."""
        fatigue = [c for c in deck if c.exhaustion]
        returned = len(fatigue) // 2
        for card in fatigue[:returned]:
            deck.remove(card)
        return returned

    def _rest_day(self, result: StageResult) -> None:
        """Jour de repos : chaque leader (général, sprint, montagne) rapporte 1 Point de Tour à son équipe ; tous les
        autres coureurs rendent encore la moitié de leur fatigue."""
        result.rest_day = True
        leaders = [self.gc_order()[0]]
        for ranking in (self.sprint_order(), self.mountain_order()):
            if ranking:
                leaders.append(ranking[0])
        for k in leaders:
            self.rest_points[k[0]] += 1
            result.rest_points[k[0]] = result.rest_points.get(k[0], 0) + 1
        for k, deck in self.decks.items():
            if k not in leaders:
                result.fatigue_returned[k] = result.fatigue_returned.get(k, 0) + self._return_fatigue(deck)

    # ------------------------------------------------------------ classements

    def _last_order_rank(self, k: Key) -> int:
        """Rang d'arrivée à la dernière étape : départage toutes les égalités."""
        order = self.results[-1].order if self.results else []
        return order.index(k) if k in order else len(order)

    def gc_order(self) -> list[Key]:
        """Classement général : temps total le plus bas."""
        return sorted(self.total_time, key=lambda k: (self.total_time[k], self._last_order_rank(k)))

    def gc_rank(self, k: Key) -> int:
        order = self.gc_order()
        return order.index(k) if k in order else len(order)

    def sprint_order(self) -> list[Key]:
        return sorted((k for k in self.sprint if self.sprint[k] > 0),
                      key=lambda k: (-self.sprint[k], self._last_order_rank(k)))

    def mountain_order(self) -> list[Key]:
        return sorted((k for k in self.mountain if self.mountain[k] > 0),
                      key=lambda k: (-self.mountain[k], self._last_order_rank(k)))

    def team_time_order(self) -> list[int]:
        """Classement par équipe : temps total des deux coureurs."""
        teams = sorted({k[0] for k in self.total_time})
        def team_time(t: int) -> int:
            return sum(v for k, v in self.total_time.items() if k[0] == t)
        return sorted(teams, key=lambda t: (team_time(t), min(self._last_order_rank(k) for k in self.total_time if k[0] == t)))

    def team_time(self, team: int) -> int:
        return sum(v for k, v in self.total_time.items() if k[0] == team)

    def award_jerseys(self) -> None:
        """Maillots : jaune (général), vert (sprint), à pois (montagne). Un coureur n'en porte qu'un : priorité jaune,
        vert, pois ; s'il mène plusieurs classements, le suivant du classement moins important prend le maillot."""
        self.jerseys = {}
        taken: set[Key] = set()
        for jersey, ranking in ((YELLOW, self.gc_order()), (GREEN, self.sprint_order()), (POLKA, self.mountain_order())):
            holder = next((k for k in ranking if k not in taken), None)
            if holder is not None:
                self.jerseys[jersey] = holder
                taken.add(holder)

    def jersey_of(self, k: Key) -> Optional[str]:
        return next((j for j, holder in self.jerseys.items() if holder == k), None)

    # ------------------------------------------------------------- fin du Tour

    def bonus_table(self) -> tuple:
        players = sum(1 for t in self.team_types if t not in GHOSTS)
        if players <= 2 or len(self.stages) <= 7:
            return BONUS_TABLE["court"]
        return BONUS_TABLE["moyen"] if len(self.stages) <= 14 else BONUS_TABLE["long"]

    def bonus_points(self) -> dict[int, dict[str, int]]:
        """Points de Tour bonus de fin de Tour, par équipe et par classement."""
        gc, team, sprint, mountain = self.bonus_table()
        bonus = {t: {"général": 0, "équipe": 0, "sprint": 0, "montagne": 0} for t in range(self.num_teams)}
        for k, points in zip(self.gc_order(), gc):
            bonus[k[0]]["général"] += points
        for t, points in zip(self.team_time_order(), team):
            bonus[t]["équipe"] += points
        for k, points in zip(self.sprint_order(), sprint):
            bonus[k[0]]["sprint"] += points
        for k, points in zip(self.mountain_order(), mountain):
            bonus[k[0]]["montagne"] += points
        return bonus

    def tour_points(self, team: int, with_bonus: bool = True) -> int:
        """Podiums + jours de repos (+ bonus de fin de Tour quand le Tour est fini)."""
        total = self.podium_points[team] + self.rest_points[team]
        if with_bonus and self.finished:
            total += sum(self.bonus_points()[team].values())
        return total

    def final_ranking(self) -> list[int]:
        """Classement des équipes : le plus de Points de Tour ; égalité : la mieux arrivée à la dernière étape."""
        def best_last(t: int) -> int:
            return min((self._last_order_rank(k) for k in self.keys() if k[0] == t), default=99)
        return sorted(range(self.num_teams), key=lambda t: (-self.tour_points(t), best_last(t)))

    def time_text(self, k: Key) -> str:
        return format_time(self.total_time.get(k, 0))


def rider_deck_size(deck: Sequence[Card]) -> tuple[int, int]:
    """(cartes Énergie, cartes Fatigue) d'un paquet."""
    return sum(not c.exhaustion for c in deck), sum(c.exhaustion for c in deck)


__all__ = ["Tour", "TourStage", "StageResult", "starting_deck", "rider_deck_size"]
