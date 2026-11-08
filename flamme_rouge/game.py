"""Moteur de règles de Flamme Rouge (sans aucune interface)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

from .cards import (
    ATTACK,
    ATTACK_FRONT,
    ATTACK_REAR,
    ROULEUR,
    SPRINTEUR,
    Card,
    attack_card,
    exhaustion_card,
    muscle_card,
    starting_deck,
)
from .extensions import METEO, PELOTON, check_extensions
from .rider import Rider
from .track import ASCENT, BREAKAWAY, COBBLES, DESCENT, SUPPLY, Track
from .weather import Weather, WeatherZone, draw_weather
from .stage import MOUNTAIN, SPRINT, TokenStack, finish_seconds

HAND_SIZE = 4
MOUNTAIN_SPEED = 5  # plafond en montée ET minimum en descente
SUPPLY_SPEED = 4  # extension Peloton : minimum quand on part d'une zone de ravitaillement
MAX_PER_SQUARE = 2  # files d'une case ordinaire (voir Track.lanes pour les autres)
CRASH_PENALTY = 2  # extension Météo : un coureur qui se relève avance de 2 cases de moins
BASE_MAX_TEAMS, PELOTON_MAX_TEAMS = 4, 6
BID_ROUNDS = 2  # variante Échappée : deux enchères par coureur
BREAKAWAY_FATIGUE = 2  # cartes Fatigue prises par chaque échappé

# Qui joue une équipe (l'IA, elle, joue avec les règles d'un joueur : voir controller.py)
TEAM_PLAYER = "joueur"
TEAM_PELOTON = "peloton"  # extension Peloton : équipe fantôme à un seul paquet (+ 2 cartes Attaque)
TEAM_MUSCLE = "muscle"  # extension Peloton : équipe fantôme qui retourne la carte du dessus
GHOSTS = (TEAM_PELOTON, TEAM_MUSCLE)

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
    crashed: list[str] = field(default_factory=list)  # chutes sous la pluie (extension Météo)


class Game:
    def __init__(
        self,
        track: Optional[Track] = None,
        num_teams: int = 2,
        seed: Optional[int] = None,
        extensions: Iterable[str] = (),
        weather: Optional[Sequence[WeatherZone]] = None,
        team_types: Optional[Sequence[str]] = None,
        tour: bool = False,
        decks: Optional[dict[tuple[int, int], list[Card]]] = None,
        team_order: Optional[Sequence[int]] = None,
        tokens: Optional[Sequence[TokenStack]] = None,
    ):
        """`weather` impose la météo (sinon, avec l'extension Météo, elle est tirée au hasard).
        `team_types` : pour chaque équipe, TEAM_PLAYER (défaut), TEAM_PELOTON ou TEAM_MUSCLE (extension Peloton).

        Grand Tour : `tour` = étape d'un Tour (l'étape continue jusqu'à ce que tout le monde ait passé la ligne,
        avec temps, jetons Sprint/Montagne et podium) ; `decks` = paquet de chaque coureur (clé : équipe,
        numéro du coureur dans l'équipe) hérité des étapes précédentes ; `team_order` = ordre dans lequel les
        équipes se placent au départ ; `tokens` = piles de jetons Majeur/Mineur."""
        self.extensions = check_extensions(extensions)
        max_teams = PELOTON_MAX_TEAMS if PELOTON in self.extensions else BASE_MAX_TEAMS
        if not 2 <= num_teams <= max_teams:
            if num_teams <= PELOTON_MAX_TEAMS and max_teams == BASE_MAX_TEAMS:
                raise ValueError("Le jeu de base se joue de 2 à 4 équipes (5 et 6 avec l'extension Peloton).")
            raise ValueError(f"On joue de 2 à {max_teams} équipes.")
        self.team_types = list(team_types or [TEAM_PLAYER] * num_teams)
        if len(self.team_types) != num_teams or any(t not in (TEAM_PLAYER, *GHOSTS) for t in self.team_types):
            raise ValueError("Il faut un type (joueur, peloton ou muscle) par équipe.")
        if any(t in GHOSTS for t in self.team_types) and PELOTON not in self.extensions:
            raise ValueError("Les équipes Peloton et Muscle viennent de l'extension Peloton.")
        if self.team_types.count(TEAM_PELOTON) > 1:
            raise ValueError("Il ne peut y avoir qu'une équipe Peloton.")
        self.track = track or Track()
        self.rng = random.Random(seed)
        self.turn = 0
        self.finished = False
        self.winner: Optional[Rider] = None

        self.riders: list[Rider] = []
        self.peloton_pile: list[Card] = []  # paquet commun de l'équipe Peloton
        self.peloton_discard: list[Card] = []
        for team, kind_of_team in enumerate(self.team_types):
            for kind in (ROULEUR, SPRINTEUR):
                if kind_of_team == TEAM_PELOTON:  # deux rouleurs, un seul paquet (ci-dessous)
                    rider = Rider(team=team, kind=ROULEUR, label=f"{team + 1}P{1 if kind == ROULEUR else 2}")
                else:
                    deck = starting_deck(kind)
                    if kind_of_team == TEAM_MUSCLE and kind == SPRINTEUR:
                        deck.append(muscle_card())
                    rider = Rider(team=team, kind=kind, draw_pile=deck)
                    self.rng.shuffle(rider.draw_pile)
                self.riders.append(rider)
            if kind_of_team == TEAM_PELOTON:
                self.peloton_pile = starting_deck(ROULEUR) + [attack_card(), attack_card()]
                self.rng.shuffle(self.peloton_pile)
        if decks:  # Grand Tour : chaque coureur garde son paquet d'une étape à l'autre (fatigue comprise)
            for rider in self.riders:
                if self.rider_key(rider) in decks and not self.is_ghost(rider):
                    rider.draw_pile = list(decks[self.rider_key(rider)])
                    self.rng.shuffle(rider.draw_pile)
        self.team_order = list(team_order) if team_order is not None else list(range(num_teams))
        self._place_riders()
        # Grand Tour
        self.tour = tour
        self.all_riders: list[Rider] = list(self.riders)  # tous les coureurs, même ceux déjà arrivés
        self.arrived: list[Rider] = []  # ordre d'arrivée de l'étape
        self.minutes: dict[Rider, int] = {r: 0 for r in self.riders}  # jetons Temps d'une minute
        self.stage_time: dict[Rider, int] = {}  # temps d'étape en secondes, à l'arrivée
        self.tokens = [TokenStack(t.square, t.kind, list(t.values), t.major) for t in (tokens or [])]
        self.points: dict[str, dict[Rider, int]] = {SPRINT: {}, MOUNTAIN: {}}
        self.jerseys: dict[Rider, str] = {}  # Grand Tour : maillot porté (jaune, vert, pois), posé par le Tour
        self.last_tokens: list[tuple[Rider, TokenStack, int]] = []  # jetons pris au dernier tour
        self.last_arrivals: list[Rider] = []  # coureurs arrivés au dernier tour
        self.turn_start: dict[Rider, int] = {r: r.position for r in self.riders}
        if weather is None:
            weather = draw_weather(self.track, self.rng) if METEO in self.extensions else ()
        self.weather = Weather(weather)
        self.crashed_this_turn: list[Rider] = []  # chutes du dernier mouvement
        self.stood_up_this_turn: list[Rider] = []  # coureurs qui se sont relevés au dernier mouvement
        self.last_values: dict[Rider, int] = {}  # valeur jouée par chaque coureur au dernier mouvement
        self._peloton_card: Optional[Card] = None  # carte du Peloton pour le tour en cours

    # --------------------------------------------------------------- mise en place

    def _place_riders(self) -> None:
        """Placement au départ : les places les plus proches de la ligne d'abord (case par case, file de droite
        d'abord). Les équipes fantômes se placent avant les joueurs : le Peloton l'un devant l'autre, puis
        Muscle (Sprinteur devant le Rouleur). Sans grille de départ, on remplit les premières cases du parcours.

        Si la grille ne suffit pas (5–6 équipes), ses cases reçoivent une 3e file (choix faute de règle)."""
        grid = self.track.start
        if grid:
            capacity = sum(self.track.lanes(s) for s in range(grid))
            if capacity < len(self.riders):
                lanes = [max(self.track.lanes(s), 3) if s < grid else self.track.lanes(s) for s in range(len(self.track))]
                self.track = self.track.with_lanes(lanes)
                capacity = sum(self.track.lanes(s) for s in range(grid))
            if capacity < len(self.riders):
                raise ValueError(f"La grille de départ n'a que {capacity} places pour {len(self.riders)} coureurs.")
            squares = list(range(grid - 1, -1, -1))
        else:
            squares = list(range(len(self.track)))
        slots = [(s, lane) for s in squares for lane in range(self.track.lanes(s))]
        taken: set[tuple[int, int]] = set()

        def put(rider: Rider, slot: tuple[int, int]) -> None:
            rider.position, rider.lane = slot
            taken.add(slot)

        def free() -> list[tuple[int, int]]:
            return [s for s in slots if s not in taken]

        peloton = [r for r in self.riders if self.team_types[r.team] == TEAM_PELOTON]
        if peloton:  # l'un devant l'autre, dans la file de droite, au plus près de la ligne
            column = [s for s in free() if s[1] == 0]
            for rider, slot in zip(peloton, column):
                put(rider, slot)
        for team, kind_of_team in enumerate(self.team_types):
            if kind_of_team == TEAM_MUSCLE:
                pair = sorted((r for r in self.riders if r.team == team), key=lambda r: r.kind != SPRINTEUR)
                for rider in pair:
                    put(rider, free()[0])
        for team in self.team_order:  # Grand Tour : l'équipe qui a le moins de Points de Tour se place d'abord
            for rider in self.riders:
                if rider.team == team and self.team_types[team] == TEAM_PLAYER:
                    put(rider, free()[0])

    # ------------------------------------------------------------------ outils

    def rider_key(self, rider: Rider) -> tuple[int, int]:
        """Identité d'un coureur d'une étape à l'autre : (équipe, 0 pour le premier coureur, 1 pour le second)."""
        team = [r for r in getattr(self, "all_riders", self.riders) if r.team == rider.team]
        return rider.team, team.index(rider)

    def riders_at(self, square: int, exclude: Optional[Rider] = None) -> list[Rider]:
        return [r for r in self.riders if r.position == square and r is not exclude]

    def lanes(self, square: int) -> int:
        """Files de la case (2, ou de 1 à 3 avec l'extension Peloton)."""
        return self.track.lanes(square)

    def team_type(self, rider: Rider) -> str:
        return self.team_types[rider.team]

    def is_ghost(self, rider: Rider) -> bool:
        """Coureur d'une équipe fantôme (Peloton ou Muscle) : il retourne une carte, sans choisir."""
        return self.team_types[rider.team] in GHOSTS

    # ------------------------------------------------- 0. Variante Échappée (extension Peloton)

    def breakaway_squares(self) -> list[int]:
        """Cases de la zone d'échappée (tuile 2), de l'avant vers l'arrière ; vide sans tuile Échappée."""
        return sorted((s for s in range(len(self.track)) if self.track.surface(s) == BREAKAWAY), reverse=True)

    def breakaway_winners_count(self) -> int:
        """Un échappé de 2 à 4 équipes, deux à 5–6 équipes."""
        return 2 if len(self.team_types) >= 5 else 1

    def draw_bid_hand(self, rider: Rider) -> list[Card]:
        """Enchère : 4 cartes du paquet du coureur choisi (les autres retourneront à la défausse)."""
        hand = rider.draw_hand(HAND_SIZE, self.rng)
        rider.hand = list(hand)
        return hand

    def put_bid(self, rider: Rider, hand: list[Card], card: Card) -> Card:
        """Pose la carte misée (mise de côté) et défausse les autres cartes de la main."""
        if card not in hand:
            raise ValueError(f"{card} n'est pas dans la main de {rider.name} : {hand}")
        rest = list(hand)
        rest.remove(card)
        rider.recycle.extend(rest)
        rider.hand = []
        return card

    def resolve_breakaway(self, bids: dict[Rider, list[Card]]) -> list[Rider]:
        """Fin des enchères : le ou les meilleurs totaux partent dans la zone d'échappée (le plus haut à droite).
        Égalité : le coureur le plus en arrière, puis le plus à gauche, l'emporte.

        Les échappés retirent leurs cartes misées du jeu et prennent 2 cartes Fatigue dans leur défausse ; les
        autres défaussent leurs mises. Puis le paquet de chaque enchérisseur est remélangé avec sa défausse."""
        ranked = sorted(bids, key=lambda r: (-sum(c.value for c in bids[r]), r.position, -r.lane))
        winners = ranked[: self.breakaway_winners_count()] if self.breakaway_squares() else []
        for rider, cards in bids.items():
            if rider in winners:
                rider.used.extend(cards)
                rider.recycle.extend(exhaustion_card() for _ in range(BREAKAWAY_FATIGUE))
            else:
                rider.recycle.extend(cards)
            rider.draw_pile.extend(rider.recycle)
            rider.recycle = []
            self.rng.shuffle(rider.draw_pile)
        slots = [(s, lane) for s in self.breakaway_squares() for lane in range(self.lanes(s))]
        for rider, (square, lane) in zip(winners, slots):
            rider.position, rider.lane = square, lane
        return winners

    # ------------------------------------------------------------- 1. Énergie

    def energy_phase(self, chooser: Optional[Chooser] = None) -> dict[Rider, Card]:
        """Chaque coureur pioche 4 cartes, en joue 1 et recycle les 3 autres.

        Pour chaque équipe, on traite le rouleur puis le sprinteur (les règles
        autorisent l'ordre inverse : à ajouter plus tard). On ne pioche pour le
        2e coureur qu'après avoir choisi la carte du 1er. Les équipes fantômes retournent leur carte.
        """
        chooser = chooser or random_chooser
        played: dict[Rider, Card] = {}
        self.new_turn_cards()
        for rider in self.riders:
            if self.is_ghost(rider):
                played[rider] = self.ghost_card(rider)
                continue
            hand = self.draw_hand_for(rider)
            card = chooser(self, rider, hand) if hand else None
            played[rider] = self.play_from_hand(rider, hand, card)
        return played

    def new_turn_cards(self) -> None:
        """Début de la phase Énergie : l'équipe Peloton retournera une nouvelle carte."""
        self._peloton_card = None

    def ghost_card(self, rider: Rider) -> Card:
        """Carte d'un coureur fantôme : la carte du dessus de son paquet (une seule pour toute l'équipe Peloton).

        Paquet vide : on remélange les cartes déjà retournées (la règle ne dit rien ; choix pour finir la course)."""
        if self.team_type(rider) == TEAM_PELOTON:
            if self._peloton_card is None:
                if not self.peloton_pile:
                    self.peloton_pile, self.peloton_discard = self.peloton_discard, []
                    self.rng.shuffle(self.peloton_pile)
                self._peloton_card = self.peloton_pile.pop()
                self.peloton_discard.append(self._peloton_card)
            rider.hand = []
            return self._peloton_card
        if not rider.draw_pile:
            rider.draw_pile, rider.recycle = rider.recycle, []
            self.rng.shuffle(rider.draw_pile)
        card = rider.draw_pile.pop()
        rider.recycle.append(card)
        rider.hand = []
        return card

    def hand_size(self, rider: Rider) -> int:
        """4 cartes ; 5 ou 3 si le coureur commence le tour dans un vent arrière ou de face (Météo)."""
        return self.weather.hand_size(rider.position, HAND_SIZE)

    def draw_hand_for(self, rider: Rider) -> list[Card]:
        """Pioche la main de 4 cartes (moins s'il n'en reste pas assez ; vent : 5 ou 3)."""
        hand = rider.draw_hand(self.hand_size(rider), self.rng)
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

    def _effective_value(self, start: int, value: int, crashed: bool = False) -> int:
        """Descente (minimum 5), ravitaillement (minimum 4), relève après une chute (−2), puis montée (maximum 5)."""
        if self.track.kind(start) == DESCENT:
            value = max(value, MOUNTAIN_SPEED)
        if self.track.surface(start) == SUPPLY:
            value = max(value, SUPPLY_SPEED)
        if crashed:
            value = max(value - CRASH_PENALTY, 0)
        # Montée : plafond de 5 si on démarre sur, entre dans, ou traverse une case de montée.
        if any(self.track.kind(s) == ASCENT for s in range(start, start + value + 1)):
            value = min(value, MOUNTAIN_SPEED)
        return value

    def is_full(self, square: int, exclude: Optional[Rider] = None) -> bool:
        return len(self.riders_at(square, exclude=exclude)) >= self.lanes(square)

    def is_blocked(self, square: int, exclude: Optional[Rider] = None) -> bool:
        """Case barrée par une chute : toutes ses files ont un coureur à terre (extension Météo)."""
        here = self.riders_at(square, exclude=exclude)
        return len(here) >= self.lanes(square) and all(r.crashed for r in here)

    def _free_lane(self, square: int, exclude: Optional[Rider] = None) -> int:
        """La file libre la plus à droite (0 = droite) de la case."""
        used = {r.lane for r in self.riders_at(square, exclude=exclude)}
        return next((lane for lane in range(self.lanes(square)) if lane not in used), 0)

    def card_values(self, played: dict[Rider, Card]) -> dict[Rider, int]:
        """Valeur de la carte de chaque coureur. Carte Attaque (équipe Peloton) : le coureur de tête
        de l'équipe avance de 2, celui de derrière de 9."""
        values = {r: c.value for r, c in played.items()}
        for team, kind_of_team in enumerate(self.team_types):
            if kind_of_team != TEAM_PELOTON:
                continue
            pair = [r for r in played if r.team == team]
            if pair and played[pair[0]].special == ATTACK:
                pair.sort(key=lambda r: (-r.position, r.lane))
                values[pair[0]] = ATTACK_FRONT
                for rear in pair[1:]:
                    values[rear] = ATTACK_REAR
        return values

    def _move(self, rider: Rider, value: int) -> None:
        start = rider.position
        was_crashed = rider.crashed
        rider.crashed = False  # un coureur à terre se relève au moment de son mouvement
        if was_crashed:
            self.stood_up_this_turn.append(rider)
        wanted = start + self._effective_value(start, value, was_crashed)
        # Une case barrée par une chute ne se traverse pas : on s'arrête avant.
        target = next((s - 1 for s in range(start + 1, wanted + 1) if self.is_blocked(s, exclude=rider)), wanted)
        # On peut traverser une case pleine mais pas s'y arrêter : on recule
        # jusqu'à la première case avec de la place (au pire, sa case de départ).
        while target > start and self.is_full(target, exclude=rider):
            target -= 1
        rider.lane = self._free_lane(target, exclude=rider) if target != start else rider.lane
        rider.position = target
        if target == start:  # resté sur place (ou relevé sans avancer) : file de droite si elle est libre
            rider.lane = self._free_lane(start, exclude=rider)
        # Pluie : bloqué par d'autres coureurs et arrêté sous la pluie -> chute.
        if target < wanted and self.weather.is_rain(target):
            rider.crashed = True
            self.crashed_this_turn.append(rider)

    def movement_phase(self, played: dict[Rider, Card]) -> None:
        """Les coureurs avancent un par un, du premier au dernier."""
        order = sorted(self.riders, key=lambda r: (-r.position, r.lane))
        self.turn_start = {r: r.position for r in self.riders}
        self.crashed_this_turn, self.stood_up_this_turn = [], []
        self.last_values = self.card_values(played)
        for rider in order:
            self._move(rider, self.last_values[rider])

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
        Extension Météo : pareil pour une case de vent de travers ou une case avec un coureur à terre.
        Extension Peloton : pareil sur les pavés ; et si la case de devant a moins de files (sortie d'une
        zone de ravitaillement), les coureurs des files de droite avancent d'abord, les autres restent.
        """
        moved: list[Rider] = []
        while True:
            packs = self._packs()
            to_shift: set[int] = set()
            for rear, front in zip(packs, packs[1:]):
                gap_square = rear[-1] + 1
                if front[0] - rear[-1] - 1 != 1:
                    continue
                if self.no_slipstream(front[0]):  # ne peut pas donner
                    continue
                if self.no_slipstream(gap_square) or any(self.no_slipstream(s) for s in rear):  # ne peut pas recevoir
                    continue
                to_shift.update(rear)
            if not to_shift:
                return moved
            shifted = False
            for square in sorted(to_shift, reverse=True):  # de l'avant vers l'arrière
                for rider in sorted(self.riders_at(square), key=lambda r: r.lane):  # file de droite d'abord
                    if self.is_full(square + 1):
                        continue
                    rider.lane = self._free_lane(square + 1)
                    rider.position = square + 1
                    shifted = True
                    if rider not in moved:
                        moved.append(rider)
                for stayer in sorted(self.riders_at(square), key=lambda r: r.lane):  # ceux restés : vers la droite
                    stayer.lane = self._free_lane(square, exclude=stayer)
            if not shifted:
                return moved

    def no_slipstream(self, square: int) -> bool:
        """Une case qui ne donne ni ne reçoit d'aspiration : montée, pavés, vent de travers, coureur à terre."""
        return (
            self.track.kind(square) == ASCENT
            or self.track.surface(square) == COBBLES
            or self.weather.blocks_slipstream(square)
            or any(r.crashed for r in self.riders_at(square))
        )

    def apply_exhaustion(self) -> list[Rider]:
        """Fatigue : un coureur dont la case devant lui est entièrement vide reçoit une carte Fatigue (2).
        Les équipes fantômes (Peloton, Muscle) n'en prennent jamais."""
        exhausted = [r for r in self.riders if not self.riders_at(r.position + 1) and not self.is_ghost(r)
                     and not (self.tour and r.position >= len(self.track))]  # Grand Tour : pas pour les arrivés
        for rider in exhausted:
            rider.recycle.append(exhaustion_card())
        return exhausted

    def check_finish(self) -> None:
        if self.tour:
            self._tour_end_of_turn()
            return
        crossed = [r for r in self.riders if r.position >= len(self.track)]
        if crossed:
            self.finished = True
            # Le plus loin gagne ; à égalité de case, le couloir de droite est devant
            # (hypothèse à vérifier dans le livret).
            self.winner = max(crossed, key=lambda r: (r.position, -r.lane))

    # ------------------------------------------------------------ Grand Tour

    def _take_tokens(self) -> None:
        """Jetons Majeur/Mineur : chaque coureur qui est entré sur la case d'une pile ou l'a dépassée ce tour-ci
        en prend un ; le plus avancé en fin de tour prend le plus haut."""
        self.last_tokens = []
        for stack in self.tokens:
            takers = [r for r in self.riders if self.turn_start.get(r, r.position) < stack.square <= r.position]
            for rider in sorted(takers, key=lambda r: (-r.position, r.lane)):
                if not stack.values:
                    break
                value = stack.values.pop(0)
                self.points[stack.kind][rider] = self.points[stack.kind].get(rider, 0) + value
                self.last_tokens.append((rider, stack, value))

    def _tour_end_of_turn(self) -> None:
        """Fin de tour d'une étape de Tour (après l'aspiration et la fatigue) : jetons, puis les coureurs qui ont
        passé la ligne prennent leur temps (secondes de la tuile Chronométrage selon le coureur de tête de leur
        groupe) et quittent la piste ; les autres prennent un jeton d'une minute si quelqu'un est déjà arrivé."""
        self._take_tokens()
        finish = len(self.track)
        crossed = sorted((r for r in self.riders if r.position >= finish), key=lambda r: (-r.position, r.lane))
        self.last_arrivals = crossed
        if crossed:
            packs = self._packs()
            for rider in crossed:
                pack = next(p for p in packs if rider.position in p)
                front = max(pack)
                self.stage_time[rider] = self.minutes[rider] * 60 + finish_seconds(self.track, front - finish)
            self.arrived.extend(crossed)
            self.riders = [r for r in self.riders if r not in crossed]
        if self.arrived:
            for rider in self.riders:
                self.minutes[rider] += 1
        if not self.riders:
            self.finished = True
            self.winner = self.arrived[0]

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
            crashed=[r.name for r in self.crashed_this_turn],
        )
