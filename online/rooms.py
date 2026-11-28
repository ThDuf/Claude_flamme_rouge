"""Parties à distance, sans réseau : salons, joueurs et déroulement d'une course.

Un salon a un code (4 lettres). Le premier joueur l'a créé : il en est l'hôte et règle la partie (parcours,
nombre d'équipes, extensions, qui joue chaque équipe). Les autres le rejoignent avec le code et prennent une
place libre. Au départ, les places « Joueur » restées libres sont jouées par l'IA.

Pendant la course, chaque joueur ne reçoit que ses propres mains. Au début du tour, tous les coureurs piochent en
même temps : chaque joueur choisit les cartes de ses deux coureurs ensemble, sans attendre les autres. Quand
toutes les cartes sont posées, n'importe quel joueur lance le mouvement, l'aspiration et la fatigue.
Les enchères de la variante Échappée restent, elles, une équipe après l'autre.

Chaque changement augmente `version` : un navigateur qui a déjà la version courante ne retélécharge rien.
"""
from __future__ import annotations

import math
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from flamme_rouge.animation import moves_between, snapshot
from flamme_rouge.boardview import (
    BOARD_W, FOLLOW_ALL, FOLLOW_HEAD, FOLLOW_PELOTON, MAP_H, MAX_SCALE, MIN_SCALE, follow_view, map_primitives, map_transform,
    podium_primitives, profile_geometry,
    profile_primitives, road_geometry, track_preview_primitives,
)
from flamme_rouge.catalog import GROUP_MINE, GROUP_PELOTON, Choice, build_choices
from flamme_rouge.decks import deck_summary  # noqa: F401 (aussi importé depuis ce module)
from flamme_rouge.iso import best_angle, projection
from flamme_rouge.scene import build_scene
from flamme_rouge.paths import PARCOURS_DIR
from flamme_rouge.controller import BREAKAWAY, CHOOSE, EXHAUSTION, FINISHED, MOVEMENT, SLIPSTREAM, TurnController
from flamme_rouge.track import BREAKAWAY as BREAKAWAY_TILE
from flamme_rouge.extensions import EXTENSIONS, PELOTON
from flamme_rouge.game import TEAM_MUSCLE, TEAM_PELOTON, TEAM_PLAYER, Game
from flamme_rouge.stage import format_time
from flamme_rouge.tour import JERSEY_NAMES, StageResult, Tour, TourStage
from flamme_rouge.track import Track

TEAM_COLORS = ["rouge", "bleue", "verte", "jaune", "rose", "blanche"]
SEAT_PLAYER, SEAT_AI = "joueur", "ia"  # une place : un joueur (ou l'IA si personne ne la prend), l'IA, ou un fantôme
SEAT_KINDS = {SEAT_PLAYER: "Joueur", SEAT_AI: "IA", TEAM_PELOTON: "Équipe Peloton", TEAM_MUSCLE: "Équipe Muscle"}
PROFILE_H = 100
PREVIEW_W, PREVIEW_H, PREVIEW_PROFILE_H = 700, 300, 110
MAX_ROOMS, MAX_PLAYERS, NAME_MAX = 30, 12, 20
ROOM_IDLE_SECONDS = 6 * 3600  # un salon sans activité depuis 6 h est oublié
CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sans I ni O (confondus avec 1 et 0)
LOG_LINES = 80
MAX_CACHED_VIEWS = 24  # cadrages différents gardés en mémoire pour une même version du salon
SINGLE, TOUR = "course", "tour"  # course unique ou Grand Tour
MIN_TOUR_STAGES, MAX_TOUR_STAGES = 3, 21

PHASE_TITLES = {
    BREAKAWAY: "Enchères de l'échappée",
    CHOOSE: "Choix des cartes",
    MOVEMENT: "Cartes posées",
    SLIPSTREAM: "Mouvement terminé",
    EXHAUSTION: "Aspiration terminée",
    FINISHED: "Arrivée !",
}
ACTION_TEXT = {
    MOVEMENT: "▶ Révéler les cartes : MOUVEMENT",
    SLIPSTREAM: "▶ ASPIRATION",
    EXHAUSTION: "▶ FATIGUE (puis tour suivant)",
}




class OnlineError(Exception):
    """Une demande refusée ; le message s'affiche tel quel chez le joueur."""


@dataclass
class Player:
    token: str
    name: str
    team: Optional[int] = None  # place prise (numéro d'équipe), ou None : spectateur
    # même écran : les autres équipes jouées depuis le même appareil (à tour de rôle, ou main cachée)
    extra: set = field(default_factory=set)

    @property
    def teams(self) -> list[int]:
        """Toutes les équipes de ce joueur, la sienne d'abord."""
        return ([self.team] if self.team is not None else []) + sorted(self.extra - {self.team})

    def owns(self, team: Optional[int]) -> bool:
        return team is not None and (team == self.team or team in self.extra)


def online_choices(parcours_dir: Optional[str] = None) -> list[Choice]:
    """Les parcours jouables, avec une clé sans chemin de fichier (on ne montre pas les dossiers du PC hôte)."""
    out = []
    for c in build_choices(parcours_dir or PARCOURS_DIR):
        if not c.playable:
            continue
        key = f"mine:{c.label}" if c.group == GROUP_MINE else c.key
        out.append(Choice(key, c.label, c.group, c.track, c.tiles))
    return out


def parse_iso(text):
    """« auto » ou un angle (degrés, arrondi au degré) pour la vue 3D ; None (vide ou illisible) : carte plate."""
    if not text:
        return None
    if str(text) == "auto":
        return "auto"
    try:
        angle = float(text)
    except ValueError:
        return None
    return round(angle) % 360 if math.isfinite(angle) else None


def parse_view(text) -> Optional[tuple]:
    """« échelle,x,y » envoyé par le navigateur -> cadrage borné (échelle entre MIN_SCALE et MAX_SCALE), ou None
    (cadrage absent ou illisible : on garde la caméra, sans erreur qui renverrait le joueur à l'accueil)."""
    if not text:
        return None
    try:
        scale, x, y = (float(v) for v in str(text).split(","))
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in (scale, x, y)) or abs(x) > 1e5 or abs(y) > 1e5 or scale <= 0:
        return None
    return round(min(max(scale, MIN_SCALE), MAX_SCALE), 2), round(x, 2), round(y, 2)


def clean_name(name) -> str:
    name = " ".join(str(name or "").split())[:NAME_MAX]
    if not name:
        raise OnlineError("Choisis un nom.")
    return name


@dataclass
class Room:
    code: str
    choices: list[Choice]
    players: dict[str, Player] = field(default_factory=dict)
    host: Optional[str] = None  # jeton de l'hôte
    parcours: str = ""
    teams: int = 2
    extensions: set = field(default_factory=set)
    seats: list[str] = field(default_factory=lambda: [SEAT_PLAYER] * len(TEAM_COLORS))
    breakaway: bool = True  # variante Échappée (seulement avec Peloton et une tuile Échappée sur le parcours)
    mode: str = SINGLE
    tour_stages: list = field(default_factory=list)  # Grand Tour : clés des parcours, dans l'ordre
    rest_after: Optional[int] = None  # Grand Tour : jour de repos après cette étape (1 = la première)
    tour: Optional[Tour] = None
    stage_result: Optional[StageResult] = None  # Grand Tour : l'étape vient de finir, écran des résultats
    game: Optional[Game] = None
    ctl: Optional[TurnController] = None
    ai_teams: frozenset = frozenset()
    last_anim: Optional[dict] = None  # dernier mouvement ou aspiration, rejoué par les navigateurs
    last_fatigue: Optional[dict] = None  # la dernière fatigue : {id, names}, montrée une fois par les navigateurs
    initial_decks: dict = field(default_factory=dict)  # nom du coureur -> son deck au départ (panneau « Deck »)
    scene_id: int = 0  # numéro de la course en cours : la vue 3D ne recharge la route que s'il change
    _scene: Optional[dict] = None
    version: int = 1
    touched: float = field(default_factory=time.monotonic)
    lock: threading.RLock = field(default_factory=threading.RLock)
    _cache: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        keys = [c.key for c in self.choices]
        if not self.parcours:
            self.parcours = "officiel:Avenue Corso Paseo" if "officiel:Avenue Corso Paseo" in keys else keys[0]

    # ------------------------------------------------------------------ outils

    def bump(self) -> None:
        self.version += 1
        self.touched = time.monotonic()
        self._cache.clear()

    def choice(self, key: Optional[str] = None) -> Choice:
        key = key or self.parcours
        for c in self.choices:
            if c.key == key:
                return c
        raise OnlineError("Parcours inconnu.")

    def player(self, token: str) -> Player:
        player = self.players.get(token)
        if player is None:
            raise OnlineError("Tu ne fais pas partie de ce salon (recharge la page pour rejoindre).")
        return player

    def _require_host(self, player: Player) -> None:
        if player.token != self.host:
            raise OnlineError("Seul l'hôte de la partie peut faire ça.")

    def _require_lobby(self) -> None:
        if self.game is not None:
            raise OnlineError("La course est déjà lancée.")

    def owner(self, team: int) -> Optional[Player]:
        return next((p for p in self.players.values() if p.owns(team)), None)

    def team_label(self, team: int) -> str:
        """« Équipe 1 (Alice) », « Équipe 2 (IA) »…"""
        owner = self.owner(team)
        if self.game is not None and self.game.team_types[team] != TEAM_PLAYER:
            who = SEAT_KINDS[self.game.team_types[team]]
        elif owner is not None:
            who = owner.name
        else:
            who = "IA"
        return f"Équipe {team + 1} ({who})"

    # ------------------------------------------------------------------ salon

    def join(self, name) -> Player:
        name = clean_name(name)
        if len(self.players) >= MAX_PLAYERS:
            raise OnlineError("Ce salon est complet.")
        if any(p.name.lower() == name.lower() for p in self.players.values()):
            raise OnlineError("Ce nom est déjà pris dans ce salon.")
        player = Player(secrets.token_urlsafe(18), name)
        self.players[player.token] = player
        if self.host is None:
            self.host = player.token
        if self.game is None:  # on s'assoit d'office à la première place « Joueur » libre
            free = [t for t in range(self.teams) if self.seats[t] == SEAT_PLAYER and self.owner(t) is None]
            if free:
                player.team = free[0]
        self.bump()
        return player

    def take_seat(self, player: Player, team: Optional[int], also: bool = False, drop: bool = False) -> None:
        """Prend la place `team` (None : redevient spectateur et lâche toutes ses places).
        `also` : même écran, la place s'ajoute à celles du joueur ; `drop` : lâche seulement cette place."""
        self._require_lobby()
        if drop:
            if team == player.team:
                player.team = min(player.extra - {team}, default=None)
            player.extra.discard(team)
            player.extra.discard(player.team)
            self.bump()
            return
        if team is not None:
            if not (0 <= team < self.teams) or self.seats[team] != SEAT_PLAYER:
                raise OnlineError("Cette place n'est pas jouable par un joueur.")
            if self.owner(team) not in (None, player):
                raise OnlineError("Cette place est déjà prise.")
        if also and team is not None and player.team is not None:
            if team != player.team:
                player.extra.add(team)
        else:
            player.team = team
            player.extra = set()
        self.bump()

    def breakaway_available(self, track: Optional[Track] = None) -> bool:
        """La variante Échappée demande l'extension Peloton et une tuile Échappée sur le parcours (pour un Tour :
        sur au moins une étape)."""
        if track is None:
            keys = self.tour_stages if self.mode == TOUR else [self.parcours]
            return any(self.breakaway_available(self.choice(k).track) for k in keys)
        return PELOTON in self.extensions and any(track.surface(s) == BREAKAWAY_TILE for s in range(len(track)))

    def configure(self, player: Player, parcours=None, teams=None, extensions=None, seats=None,
                  breakaway=None, mode=None, tour_stages=None, rest_after=None) -> None:
        """L'hôte règle la partie ; les places devenues injouables sont libérées.
        Grand Tour : `mode` = "tour", `tour_stages` = les clés des parcours dans l'ordre, `rest_after` = le numéro
        de l'étape suivie d'un jour de repos (0 : pas de repos)."""
        self._require_host(player)
        self._require_lobby()
        if breakaway is not None:
            self.breakaway = bool(breakaway)
        if mode is not None:
            if mode not in (SINGLE, TOUR):
                raise OnlineError("Type de course inconnu.")
            self.mode = mode
        if tour_stages is not None:
            keys = [self.choice(str(k)).key for k in list(tour_stages)]
            if len(keys) > MAX_TOUR_STAGES:
                raise OnlineError(f"Un Tour compte au plus {MAX_TOUR_STAGES} étapes.")
            self.tour_stages = keys
        if rest_after is not None:
            self.rest_after = int(rest_after) or None
        if self.rest_after is not None and not 1 <= self.rest_after < len(self.tour_stages):
            self.rest_after = None  # le repos se place entre deux étapes
        if parcours is not None:
            choice = self.choice(str(parcours))
            self.parcours = choice.key
        if extensions is not None:
            self.extensions = {e for e in extensions if e in EXTENSIONS}
        played = self.tour_stages if self.mode == TOUR else [self.parcours]
        if any(self.choice(k).group == GROUP_PELOTON for k in played):  # une étape Peloton se joue avec l'extension
            self.extensions.add(PELOTON)
        if teams is not None:
            teams = int(teams)
            if not 2 <= teams <= len(TEAM_COLORS):
                raise OnlineError("De 2 à 6 équipes.")
            self.teams = teams
        if self.teams > 4 and PELOTON not in self.extensions:
            self.extensions.add(PELOTON)  # 5 ou 6 équipes : extension Peloton
        if seats is not None:
            for team, kind in enumerate(list(seats)[: len(TEAM_COLORS)]):
                if kind not in SEAT_KINDS:
                    raise OnlineError("Type de place inconnu.")
                self.seats[team] = kind
        if PELOTON not in self.extensions:  # sans Peloton, pas d'équipe fantôme
            self.seats = [SEAT_PLAYER if s in (TEAM_PELOTON, TEAM_MUSCLE) else s for s in self.seats]
        for p in self.players.values():
            p.extra = {t for t in p.extra if t < self.teams and self.seats[t] == SEAT_PLAYER}
            if p.team is not None and (p.team >= self.teams or self.seats[p.team] != SEAT_PLAYER):
                p.team = min(p.extra, default=None)
            p.extra.discard(p.team)
        self.bump()

    def start(self, player: Player, seed: Optional[int] = None) -> None:
        self._require_host(player)
        self._require_lobby()
        kinds = self.seats[: self.teams]
        if kinds.count(TEAM_PELOTON) > 1:
            raise OnlineError("Il ne peut y avoir qu'une équipe Peloton.")
        if not any(self.owner(t) for t in range(self.teams)):
            raise OnlineError("Personne n'a pris de place : prends une équipe avant de lancer.")
        team_types = [k if k in (TEAM_PELOTON, TEAM_MUSCLE) else TEAM_PLAYER for k in kinds]
        if self.mode == TOUR and len(self.tour_stages) < MIN_TOUR_STAGES:
            raise OnlineError(f"Un Tour compte au moins {MIN_TOUR_STAGES} étapes.")
        self.ai_teams = frozenset(t for t in range(self.teams)
                                  if team_types[t] == TEAM_PLAYER and self.owner(t) is None)
        if self.mode == TOUR:
            stages = [TourStage(self.choice(k).label, self.choice(k).track) for k in self.tour_stages]
            self.tour = Tour(stages, self.teams, team_types, frozenset(self.extensions),
                             {self.rest_after} if self.rest_after else (), seed=seed)
            self._begin(self.tour.start_stage())
        else:
            self.tour = None
            self._begin(Game(self.choice().track, num_teams=self.teams, seed=seed,
                             extensions=frozenset(self.extensions), team_types=team_types))
        self.bump()

    def _begin(self, game: Game) -> None:
        """Une course (ou une étape du Tour) commence."""
        self.game, self.stage_result, self.last_anim, self.last_fatigue = game, None, None, None
        self.scene_id, self._scene = self.scene_id + 1, None
        # avant le contrôleur : il fait déjà piocher (enchères de l'IA, premier tour)
        self.initial_decks = {r.name: deck_summary(r.draw_pile + r.recycle + r.hand) for r in game.riders
                              if not game.is_ghost(r)}
        self.ctl = TurnController(game, self.ai_teams, self.breakaway and self.breakaway_available(game.track),
                                  simultaneous=True)

    def tour_next(self, player: Player, stage: int, screen: str) -> None:
        """Grand Tour : après l'arrivée, l'écran des résultats ; après les résultats, l'étape suivante.
        `stage` et `screen` ("race" ou "results") : ce que le joueur voyait (un deuxième clic ne fait rien)."""
        if self.tour is None or self.ctl is None:
            raise OnlineError("Pas de Grand Tour en cours.")
        if not player.teams:
            raise OnlineError("Les spectateurs ne peuvent pas faire avancer le Tour.")
        if self.stage_result is None:
            if screen != "race" or stage != self.tour.stage_index + 1 or self.ctl.phase != FINISHED:
                return
            self.stage_result = self.tour.finish_stage(self.game)
        else:
            if screen != "results" or stage != len(self.tour.results) or self.tour.finished:
                return
            self._begin(self.tour.start_stage())
        self.bump()

    def back_to_lobby(self, player: Player) -> None:
        self._require_host(player)
        self.game = self.ctl = self.last_anim = self.tour = self.stage_result = None
        self.bump()

    # ------------------------------------------------------------------ course

    def bid_rider(self, player: Player, name: Optional[str]) -> None:
        """Variante Échappée : l'équipe dont c'est le tour choisit le coureur qui tente l'échappée, ou passe."""
        ctl = self._running()
        if ctl.phase != BREAKAWAY or not player.owns(ctl.bid_team) or ctl.bid_rider is not None:
            raise OnlineError("Ce n'est pas à toi de choisir pour l'échappée.")
        rider = None
        if name is not None:
            rider = next((r for r in self.game.riders if r.team == ctl.bid_team and r.name == name), None)
            if rider is None:
                raise OnlineError("Ce coureur n'est pas dans ton équipe.")
        ctl.choose_bid_rider(rider)
        self.bump()

    def play_card(self, player: Player, index: int) -> None:
        """Variante Échappée : la carte misée par l'équipe qui enchérit."""
        ctl = self._running()
        rider = ctl.current_rider
        if ctl.phase != BREAKAWAY or rider is None or not player.owns(rider.team):
            raise OnlineError("Ce n'est pas à toi de miser.")
        if not 0 <= int(index) < len(ctl.hand):
            raise OnlineError("Carte inconnue.")
        ctl.choose(ctl.hand[int(index)])
        self.bump()

    def play_cards(self, player: Player, choices) -> None:
        """Choix simultané : {nom du coureur: numéro de la carte dans sa main}, pour un ou plusieurs coureurs du
        joueur. Tout est vérifié avant de poser quoi que ce soit."""
        ctl = self._running()
        if ctl.phase != CHOOSE or not isinstance(choices, dict) or not choices:
            raise OnlineError("Ce n'est pas le moment de choisir.")
        picks = []
        for name, index in choices.items():
            rider = next((r for r in ctl.hands if r.name == str(name)), None)
            if rider is None or not player.owns(rider.team):
                raise OnlineError(f"{name} n'a pas de carte à choisir.")
            hand = ctl.hands[rider]
            if not 0 <= int(index) < len(hand):
                raise OnlineError("Carte inconnue.")
            picks.append((rider, hand[int(index)]))
        for rider, card in picks:
            ctl.choose_for(rider, card)
        self.bump()

    def advance(self, player: Player, phase: str) -> None:
        """Mouvement, aspiration ou fatigue : n'importe quel joueur assis peut lancer l'étape suivante. `phase` est
        celle que le joueur voyait : si quelqu'un a déjà cliqué, on ne recommence pas."""
        ctl = self._running()
        if not player.teams:
            raise OnlineError("Les spectateurs ne peuvent pas faire avancer la course.")
        if phase != ctl.phase or ctl.phase not in ACTION_TEXT:
            return
        before = snapshot(self.game.riders)
        tired = [r.name for r in self.game.exhaustion_riders()] if phase == EXHAUSTION else []
        ctl.advance()
        self.bump()
        # fatigue : les coureurs qui viennent de prendre une carte Fatigue (la vue 3D les montre une fois, au clic)
        self.last_fatigue = {"id": self.version, "names": tired} if phase == EXHAUSTION else None
        moves = moves_between(before, [r for r in self.game.all_riders if r in before]) \
            if phase in (MOVEMENT, SLIPSTREAM) else []
        # le navigateur rejoue ce déplacement une fois (identifié par la version qui l'a produit)
        self.last_anim = {
            "id": self.version,
            "kind": "movement" if phase == MOVEMENT else "slipstream",
            "moves": [{"name": m.rider.name, "team": m.rider.team, "from": list(m.start), "to": list(m.end)}
                      for m in moves],
        } if moves else None

    def _running(self) -> TurnController:
        if self.ctl is None:
            raise OnlineError("La course n'est pas lancée.")
        return self.ctl

    # ------------------------------------------------------------------ état envoyé au navigateur

    def state(self, player: Player, camera: str = "", view: Optional[tuple] = None, iso=None,
              scene: Optional[str] = None) -> dict:
        """`scene` : la scène 3D que le navigateur a déjà (son `scene_id`, "-" s'il n'en a pas, None sans vue 3D) ;
        la route du parcours choisi (salon) ou de la course part avec l'état seulement s'il ne l'a pas."""
        self.touched = time.monotonic()
        base = {
            "version": self.version,
            "code": self.code,
            "me": {"name": player.name, "team": player.team, "teams": player.teams, "host": player.token == self.host},
            "players": [{"name": p.name, "team": p.team, "teams": p.teams, "host": p.token == self.host}
                        for p in self.players.values()],
        }
        if self.game is None:
            base["lobby"] = self._lobby_state()
            if scene is not None and scene != base["lobby"]["scene_id"]:
                if "scene" not in self._cache:
                    self._cache["scene"] = build_scene(self.choice().track)
                base["lobby"]["scene"] = self._cache["scene"]
        elif self.stage_result is not None:
            base["tour_results"] = self._tour_results_state()
        else:
            base["race"] = self._race_state(player, camera, view, iso)
            if scene is not None and scene != base["race"]["scene_id"]:
                if self._scene is None:
                    self._scene = build_scene(self.game.track)
                base["race"]["scene"] = self._scene
        return base

    def _lobby_state(self) -> dict:
        choice = self.choice()
        if "preview" not in self._cache:
            self._cache["preview"] = {
                "map": track_preview_primitives(choice.track, PREVIEW_W, PREVIEW_H),
                "profile": profile_primitives(choice.track, PREVIEW_W, PREVIEW_PROFILE_H),
            }
        seats = []
        for team in range(self.teams):
            owner = self.owner(team)
            seats.append({"team": team, "color": TEAM_COLORS[team], "kind": self.seats[team],
                          "player": owner.name if owner else None})
        return {
            "parcours": choice.key,
            "parcours_label": choice.label,
            "details": choice.details,
            "teams": self.teams,
            "extensions": sorted(self.extensions),
            "breakaway": self.breakaway,
            "breakaway_available": self.breakaway_available(),
            "seats": seats,
            "preview": self._cache["preview"],
            "preview_size": [PREVIEW_W, PREVIEW_H, PREVIEW_PROFILE_H],
            "mode": self.mode,
            "tour_stages": [{"key": k, "label": self.choice(k).label} for k in self.tour_stages],
            "rest_after": self.rest_after,
            "min_stages": MIN_TOUR_STAGES,
            "max_stages": MAX_TOUR_STAGES,
            "scene_id": f"salon:{choice.key}",  # l'aperçu 3D du parcours choisi
        }

    def _race_state(self, player: Player, camera: str, view: Optional[tuple] = None, iso=None) -> dict:
        """`view` : cadrage libre (échelle, x, y) choisi à la souris dans le navigateur ; sinon la caméra.
        `iso` : vue 3D isométrique — None (carte plate), "auto" (la rotation qui montre le parcours le plus grand)
        ou un angle en degrés."""
        g, ctl = self.game, self.ctl
        rider = ctl.current_rider
        angle = None
        if iso is not None:
            angle = best_angle(g.track, BOARD_W, MAP_H) if iso == "auto" else float(iso) % 360
        proj = projection(g.track, angle) if angle is not None else None
        key = ("race", view if view is not None else camera, angle)
        if key not in self._cache:  # la même image pour tous ceux qui ont le même cadrage
            if len(self._cache) > MAX_CACHED_VIEWS:  # beaucoup de zooms différents : on repart de zéro
                self._cache.clear()
            if view is None:
                view = follow_view(g, camera, proj=proj) if camera in (FOLLOW_PELOTON, FOLLOW_HEAD, FOLLOW_ALL) \
                    else None
            shared = {
                "view": list(view or map_transform(g, proj=proj)),  # le cadrage utilisé : point de départ des zooms
                "iso_angle": angle,
                "map": map_primitives(g, rider, view=view, proj=proj),
                "profile": profile_primitives(g.track, BOARD_W, PROFILE_H, riders=g.riders, weather=g.weather,
                                              jerseys=g.jerseys),
                # pour les animations du navigateur : la route sans coureurs, sa géométrie, celle du profil
                "map_base": map_primitives(g, view=view, draw_riders=False, proj=proj),
                "geo": road_geometry(g, view, proj=proj),
                "profile_geo": profile_geometry(g.track, BOARD_W, PROFILE_H),
                "riders": [{"name": r.name, "team": r.team, "position": r.position, "lane": r.lane,
                            "crashed": r.crashed} for r in g.riders],
                "anim": self.last_anim,
                "fatigue": self.last_fatigue,
                "weather": [{"start": z.start, "end": z.end, "effect": z.effect} for z in g.weather.zones]
                if g.weather else [],
            }
            if ctl.phase == FINISHED:
                names = [self.team_label(t) for t in range(len(g.team_types))]
                shared["podium"] = podium_primitives(g, BOARD_W, MAP_H, 8.0, names)
                # pour revoir la course : le profil sans les coureurs (la page les place selon la relecture) et
                # les positions de chaque coureur à chaque étape (départ, mouvements, aspirations)
                shared["profile_base"] = profile_primitives(g.track, BOARD_W, PROFILE_H, weather=g.weather)
                shared["history"] = [{"label": label, "pos": {r.name: [p, lane] for r, (p, lane) in where.items()}}
                                     for label, where in ctl.history]
            self._cache[key] = shared
        shared = self._cache[key]
        my_hands = [(r, h) for r, h in ctl.hands.items() if player.owns(r.team)] if ctl.phase == CHOOSE else []
        my_hands.sort(key=lambda rh: (player.teams.index(rh[0].team), rh[0].name))
        my_turn = bool(my_hands) or (ctl.phase == BREAKAWAY and rider is not None and player.owns(rider.team))
        bid = None  # variante Échappée : ce que voit l'équipe qui enchérit
        if ctl.phase == BREAKAWAY:
            team = ctl.bid_team
            owner = self.owner(team) if team is not None else None
            if rider is None and team is not None:  # l'équipe choisit son coureur, ou passe
                mine_now = player.owns(team)
                waiting = ("À toi : quel coureur tente l'échappée ?" if mine_now
                           else f"Échappée : {self.team_label(team)} choisit son coureur…")
                if mine_now:
                    bid = {"stage": "rider", "riders": [{"name": r.name, "team": r.team, "kind": r.kind}
                                                        for r in g.riders if r.team == team]}
            elif rider is not None:
                waiting = (f"À toi : enchère {ctl.bid_round} sur 2 pour {rider.name}" if my_turn else
                           f"Échappée : {rider.name} — {owner.name if owner else 'IA'} mise une carte…")
                if my_turn:
                    bid = {"stage": "card", "round": ctl.bid_round}
            else:
                waiting = ""
        elif ctl.phase == CHOOSE:
            late = sorted({(self.owner(r.team).name if self.owner(r.team) else "IA") for r in ctl.hands
                           if not player.owns(r.team)})
            if my_turn:
                waiting = "À toi : choisis une carte pour chacun de tes coureurs"
            else:
                waiting = "En attente de : " + ", ".join(late) if late else ""
        elif ctl.phase in ACTION_TEXT:
            waiting = "Toutes les cartes sont posées." if ctl.phase == MOVEMENT else "Regarde le plateau, puis continue."
        else:
            waiting = ""
        mine = sorted((r for r in g.riders if player.owns(r.team)), key=lambda r: player.teams.index(r.team))
        return {
            "turn": g.turn + 1,
            "phase": ctl.phase,
            "title": PHASE_TITLES.get(ctl.phase, ""),
            "waiting": waiting,
            "action": ACTION_TEXT.get(ctl.phase, ""),
            "can_act": ctl.phase in ACTION_TEXT and bool(player.teams),
            "my_turn": my_turn,
            "bid": bid,
            "rider": {"name": rider.name, "team": rider.team, "position": rider.position} if rider else None,
            "hand": [{"index": i, "label": str(c), "fatigue": c.exhaustion} for i, c in enumerate(ctl.hand)]
            if my_turn and ctl.phase == BREAKAWAY else [],
            # choix simultané : une main par coureur du joueur qui n'a pas encore posé sa carte
            "hands": [{"name": r.name, "team": r.team, "kind": r.kind, "position": r.position,
                       "cards": [{"index": i, "label": str(c), "fatigue": c.exhaustion} for i, c in enumerate(h)]}
                      for r, h in my_hands],
            "decks": [{"name": r.name, "team": r.team, "kind": r.kind, "cards": self.initial_decks.get(r.name, [])}
                      for r in mine if r.name in self.initial_decks],
            "my_riders": [{"name": r.name, "team": r.team, "position": r.position, "draw": len(r.draw_pile), "recycle": len(r.recycle),
                           "fatigue": sum(c.exhaustion for c in r.draw_pile + r.recycle + r.hand)} for r in mine],
            "revealed": [{"name": r.name, "team": r.team, "card": str(c), "who": self._who(r)}
                         for r, c in sorted(ctl.last_revealed.items(), key=lambda rc: (rc[0].team, rc[0].name))],
            "revealed_turn": ctl.last_revealed_turn,
            "log": [{"text": line.text, "team": line.team, "heading": line.heading} for line in ctl.log[-LOG_LINES:]],
            "teams": [self.team_label(t) for t in range(len(g.team_types))],
            "finished": ctl.phase == FINISHED,
            "winner": self._winner_text(),
            "size": [BOARD_W, MAP_H, PROFILE_H],
            "tour": self._tour_race_info(),
            "scene_id": f"course:{self.scene_id}",
            **shared,
        }

    # ------------------------------------------------------------------ Grand Tour

    def _tour_race_info(self) -> Optional[dict]:
        """Pendant une étape : son numéro, les maillots et le haut du général avant l'étape."""
        if self.tour is None:
            return None
        info = self.game.tour_standings or {}
        return {
            "stage": self.tour.stage_index + 1,
            "stages": len(self.tour.stages),
            "name": self.tour.current.name,
            "jerseys": [{"jersey": j, "label": JERSEY_NAMES[j], "name": r.name, "team": r.team, "detail": d}
                        for j, r, d in info.get("jerseys", [])],
            "gc": [{"name": r.name, "team": r.team, "time": t, "gap": gap} for r, t, gap in info.get("gc", [])],
        }

    def _tour_results_state(self) -> dict:
        """Entre deux étapes (et à la fin du Tour) : arrivée, classements, maillots, Points de Tour."""
        tour, result = self.tour, self.stage_result
        names = tour.names

        def rider(k):
            return {"name": names[k], "team": k[0]}

        def gap(value):
            return "+" + format_time(value) if value else ""

        first = result.times[result.order[0]]
        gc = tour.gc_order()
        leader = tour.total_time[gc[0]]
        labels = [self.team_label(t) for t in range(tour.num_teams)]
        notes = []
        if result.rest_day:
            gained = ", ".join(f"{labels[t]} +{p}" for t, p in result.rest_points.items())
            notes.append(f"Jour de repos : les leaders rapportent 1 Point de Tour ({gained}) et les autres "
                         "récupèrent encore.")
        notes.append("Fatigue : chaque coureur a rendu la moitié de ses cartes Fatigue "
                     f"({sum(result.fatigue_returned.values())} au total) ; le reste le suit à l'étape suivante.")
        by_points = sorted(range(tour.num_teams), key=lambda t: -tour.tour_points(t, with_bonus=False))
        out = {
            "stage": len(tour.results),
            "stages": len(tour.stages),
            "name": result.name,
            "finished": tour.finished,
            "next": None if tour.finished else tour.current.name,
            "arrival": [{**rider(k), "time": format_time(result.times[k]), "gap": gap(result.times[k] - first)}
                        for k in result.order],
            "tokens": [{**rider(k), "text": f"sprint +{p}"} for k, p in result.sprint.items()]
            + [{**rider(k), "text": f"montagne +{p}"} for k, p in result.mountain.items()],
            "gc": [{**rider(k), "time": tour.time_text(k), "gap": gap(tour.total_time[k] - leader),
                    "jersey": tour.jersey_of(k)} for k in gc],
            "jerseys": [{"jersey": j, "label": JERSEY_NAMES[j], **rider(k)} for j, k in tour.jerseys.items()],
            "points": [{"team": t, "label": labels[t], "points": tour.tour_points(t, with_bonus=False),
                        "detail": f"podiums {tour.podium_points[t]}"
                        + (f" · repos {tour.rest_points[t]}" if tour.rest_points[t] else "")} for t in by_points],
            "sprint": [{**rider(k), "points": tour.sprint[k]} for k in tour.sprint_order()[:4]],
            "mountain": [{**rider(k), "points": tour.mountain[k]} for k in tour.mountain_order()[:4]],
            "notes": notes,
        }
        if tour.finished:
            bonus = tour.bonus_points()
            ranking = tour.final_ranking()
            out["final"] = {
                "winner": labels[ranking[0]],
                "winner_team": ranking[0],
                "ranking": [{"team": t, "label": labels[t], "points": tour.tour_points(t),
                             "detail": f"podiums {tour.podium_points[t]} · général {bonus[t]['général']} · "
                             f"équipe {bonus[t]['équipe']} · sprint {bonus[t]['sprint']} · "
                             f"montagne {bonus[t]['montagne']}"
                             + (f" · repos {tour.rest_points[t]}" if tour.rest_points[t] else "")}
                            for t in ranking],
            }
        return out

    def _who(self, rider) -> str:
        owner = self.owner(rider.team)
        controller = self.ctl.controller_of(rider)
        return owner.name if controller == "Joueur" and owner else controller

    def _winner_text(self) -> str:
        g = self.game
        if g.winner is None:
            return ""
        return f"Victoire de {g.winner.name} — {self.team_label(g.winner.team)}"


class Lobby:
    """Tous les salons du serveur."""

    def __init__(self, parcours_dir: Optional[str] = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = threading.Lock()
        self.parcours_dir = parcours_dir or PARCOURS_DIR  # parcours enregistrés (« Mes parcours »)
        self._choices: Optional[list[Choice]] = None

    def choices(self) -> list[Choice]:
        if self._choices is None:
            self._choices = online_choices(self.parcours_dir)
        return self._choices

    def refresh_choices(self) -> None:
        """Relit les parcours (un parcours vient d'être enregistré). La liste est modifiée sur place : les salons
        déjà ouverts, qui la partagent, voient aussi le nouveau parcours."""
        fresh = online_choices(self.parcours_dir)
        with self.lock:
            if self._choices is None:
                self._choices = fresh
            else:
                self._choices[:] = fresh

    def create(self, name) -> tuple[Room, Player]:
        clean_name(name)
        with self.lock:
            self._forget_idle()
            if len(self.rooms) >= MAX_ROOMS:
                raise OnlineError("Trop de parties en cours sur ce serveur.")
            code = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
            while code in self.rooms:
                code = "".join(secrets.choice(CODE_LETTERS) for _ in range(4))
            room = Room(code, self.choices())
            self.rooms[code] = room
        with room.lock:
            player = room.join(name)
        return room, player

    def room(self, code) -> Room:
        room = self.rooms.get(str(code or "").strip().upper())
        if room is None:
            raise OnlineError("Aucune partie avec ce code.")
        return room

    def _forget_idle(self) -> None:
        now = time.monotonic()
        for code in [c for c, r in self.rooms.items() if now - r.touched > ROOM_IDLE_SECONDS]:
            del self.rooms[code]

    def parcours_list(self) -> list[dict]:
        return [{"key": c.key, "label": c.label, "group": c.group, "details": c.details} for c in self.choices()]
