"""Parties à distance, sans réseau : salons, joueurs et déroulement d'une course.

Un salon a un code (4 lettres). Le premier joueur l'a créé : il en est l'hôte et règle la partie (parcours,
nombre d'équipes, extensions, qui joue chaque équipe). Les autres le rejoignent avec le code et prennent une
place libre. Au départ, les places « Joueur » restées libres sont jouées par l'IA.

Pendant la course, chaque joueur ne reçoit que sa propre main ; les coureurs choisissent leur carte chacun à
son tour (comme sur l'écran local), puis n'importe quel joueur lance le mouvement, l'aspiration et la fatigue.

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
    BOARD_W, FOLLOW_HEAD, FOLLOW_PELOTON, MAP_H, MAX_SCALE, MIN_SCALE, follow_view, map_primitives, map_transform,
    podium_primitives, profile_geometry,
    profile_primitives, road_geometry, track_preview_primitives,
)
from flamme_rouge.catalog import GROUP_MINE, GROUP_PELOTON, Choice, build_choices
from flamme_rouge.controller import BREAKAWAY, CHOOSE, EXHAUSTION, FINISHED, MOVEMENT, SLIPSTREAM, TurnController
from flamme_rouge.track import BREAKAWAY as BREAKAWAY_TILE
from flamme_rouge.extensions import EXTENSIONS, PELOTON
from flamme_rouge.game import TEAM_MUSCLE, TEAM_PELOTON, TEAM_PLAYER, Game

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


def online_choices() -> list[Choice]:
    """Les parcours jouables, avec une clé sans chemin de fichier (on ne montre pas les dossiers du PC hôte)."""
    out = []
    for c in build_choices():
        if not c.playable:
            continue
        key = f"mine:{c.label}" if c.group == GROUP_MINE else c.key
        out.append(Choice(key, c.label, c.group, c.track, c.tiles))
    return out


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
    game: Optional[Game] = None
    ctl: Optional[TurnController] = None
    ai_teams: frozenset = frozenset()
    last_anim: Optional[dict] = None  # dernier mouvement ou aspiration, rejoué par les navigateurs
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
        return next((p for p in self.players.values() if p.team == team), None)

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

    def take_seat(self, player: Player, team: Optional[int]) -> None:
        self._require_lobby()
        if team is not None:
            if not (0 <= team < self.teams) or self.seats[team] != SEAT_PLAYER:
                raise OnlineError("Cette place n'est pas jouable par un joueur.")
            if self.owner(team) not in (None, player):
                raise OnlineError("Cette place est déjà prise.")
        player.team = team
        self.bump()

    def breakaway_available(self) -> bool:
        """La variante Échappée demande l'extension Peloton et une tuile Échappée sur le parcours."""
        track = self.choice().track
        return PELOTON in self.extensions and any(track.surface(s) == BREAKAWAY_TILE for s in range(len(track)))

    def configure(self, player: Player, parcours=None, teams=None, extensions=None, seats=None,
                  breakaway=None) -> None:
        """L'hôte règle la partie ; les places devenues injouables sont libérées."""
        self._require_host(player)
        self._require_lobby()
        if breakaway is not None:
            self.breakaway = bool(breakaway)
        if parcours is not None:
            choice = self.choice(str(parcours))
            self.parcours = choice.key
        if extensions is not None:
            self.extensions = {e for e in extensions if e in EXTENSIONS}
        if self.choice().group == GROUP_PELOTON:  # une étape Peloton se joue avec l'extension
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
            if p.team is not None and (p.team >= self.teams or self.seats[p.team] != SEAT_PLAYER):
                p.team = None
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
        self.game = Game(self.choice().track, num_teams=self.teams, seed=seed, extensions=frozenset(self.extensions),
                         team_types=team_types)
        self.ai_teams = frozenset(t for t in range(self.teams)
                                  if team_types[t] == TEAM_PLAYER and self.owner(t) is None)
        self.ctl = TurnController(self.game, self.ai_teams, self.breakaway and self.breakaway_available())
        self.bump()

    def back_to_lobby(self, player: Player) -> None:
        self._require_host(player)
        self.game = self.ctl = self.last_anim = None
        self.bump()

    # ------------------------------------------------------------------ course

    def bid_rider(self, player: Player, name: Optional[str]) -> None:
        """Variante Échappée : l'équipe dont c'est le tour choisit le coureur qui tente l'échappée, ou passe."""
        ctl = self._running()
        if ctl.phase != BREAKAWAY or ctl.bid_team != player.team or ctl.bid_rider is not None:
            raise OnlineError("Ce n'est pas à toi de choisir pour l'échappée.")
        rider = None
        if name is not None:
            rider = next((r for r in self.game.riders if r.team == player.team and r.name == name), None)
            if rider is None:
                raise OnlineError("Ce coureur n'est pas dans ton équipe.")
        ctl.choose_bid_rider(rider)
        self.bump()

    def play_card(self, player: Player, index: int) -> None:
        """Une carte : pour le coureur qui choisit (tour normal), ou la mise de l'échappée."""
        ctl = self._running()
        rider = ctl.current_rider
        if ctl.phase not in (CHOOSE, BREAKAWAY) or rider is None or rider.team != player.team:
            raise OnlineError("Ce n'est pas à toi de choisir.")
        if not 0 <= int(index) < len(ctl.hand):
            raise OnlineError("Carte inconnue.")
        ctl.choose(ctl.hand[int(index)])
        self.bump()

    def advance(self, player: Player, phase: str) -> None:
        """Mouvement, aspiration ou fatigue : n'importe quel joueur assis peut lancer l'étape suivante. `phase` est
        celle que le joueur voyait : si quelqu'un a déjà cliqué, on ne recommence pas."""
        ctl = self._running()
        if player.team is None:
            raise OnlineError("Les spectateurs ne peuvent pas faire avancer la course.")
        if phase != ctl.phase or ctl.phase not in ACTION_TEXT:
            return
        before = snapshot(self.game.riders)
        ctl.advance()
        self.bump()
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

    def state(self, player: Player, camera: str = "", view: Optional[tuple] = None) -> dict:
        self.touched = time.monotonic()
        base = {
            "version": self.version,
            "code": self.code,
            "me": {"name": player.name, "team": player.team, "host": player.token == self.host},
            "players": [{"name": p.name, "team": p.team, "host": p.token == self.host} for p in self.players.values()],
        }
        if self.game is None:
            base["lobby"] = self._lobby_state()
        else:
            base["race"] = self._race_state(player, camera, view)
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
        }

    def _race_state(self, player: Player, camera: str, view: Optional[tuple] = None) -> dict:
        """`view` : cadrage libre (échelle, x, y) choisi à la souris dans le navigateur ; sinon la caméra."""
        g, ctl = self.game, self.ctl
        rider = ctl.current_rider
        key = ("race", view) if view is not None else ("race", camera)
        if key not in self._cache:  # la même image pour tous ceux qui ont le même cadrage
            if len(self._cache) > MAX_CACHED_VIEWS:  # beaucoup de zooms différents : on repart de zéro
                self._cache.clear()
            if view is None:
                view = follow_view(g, camera) if camera in (FOLLOW_PELOTON, FOLLOW_HEAD) else None
            shared = {
                "view": list(view or map_transform(g)),  # le cadrage utilisé : point de départ des zooms
                "map": map_primitives(g, rider, view=view),
                "profile": profile_primitives(g.track, BOARD_W, PROFILE_H, riders=g.riders, weather=g.weather),
                # pour les animations du navigateur : la route sans coureurs, sa géométrie, celle du profil
                "map_base": map_primitives(g, view=view, draw_riders=False),
                "geo": road_geometry(g, view),
                "profile_geo": profile_geometry(g.track, BOARD_W, PROFILE_H),
                "riders": [{"name": r.name, "team": r.team, "position": r.position, "lane": r.lane}
                           for r in g.riders],
                "anim": self.last_anim,
                "weather": [{"start": z.start, "end": z.end, "effect": z.effect} for z in g.weather.zones]
                if g.weather else [],
            }
            if ctl.phase == FINISHED:
                names = [self.team_label(t) for t in range(len(g.team_types))]
                shared["podium"] = podium_primitives(g, BOARD_W, MAP_H, 8.0, names)
            self._cache[key] = shared
        shared = self._cache[key]
        my_turn = ctl.phase in (CHOOSE, BREAKAWAY) and rider is not None and rider.team == player.team
        bid = None  # variante Échappée : ce que voit l'équipe qui enchérit
        if ctl.phase == BREAKAWAY:
            team = ctl.bid_team
            owner = self.owner(team) if team is not None else None
            if rider is None and team is not None:  # l'équipe choisit son coureur, ou passe
                mine_now = team == player.team
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
        elif ctl.phase == CHOOSE and rider is not None:
            who = self.owner(rider.team)
            waiting = ("À toi : choisis la carte de " + rider.name) if my_turn else \
                f"{rider.name} — {who.name if who else 'IA'} choisit sa carte…"
        elif ctl.phase in ACTION_TEXT:
            waiting = "Toutes les cartes sont posées." if ctl.phase == MOVEMENT else "Regarde le plateau, puis continue."
        else:
            waiting = ""
        mine = [r for r in g.riders if r.team == player.team]
        return {
            "turn": g.turn + 1,
            "phase": ctl.phase,
            "title": PHASE_TITLES.get(ctl.phase, ""),
            "waiting": waiting,
            "action": ACTION_TEXT.get(ctl.phase, ""),
            "can_act": ctl.phase in ACTION_TEXT and player.team is not None,
            "my_turn": my_turn,
            "bid": bid,
            "rider": {"name": rider.name, "team": rider.team, "position": rider.position} if rider else None,
            "hand": [{"index": i, "label": str(c), "fatigue": c.exhaustion} for i, c in enumerate(ctl.hand)]
            if my_turn else [],
            "my_riders": [{"name": r.name, "position": r.position, "draw": len(r.draw_pile), "recycle": len(r.recycle),
                           "fatigue": sum(c.exhaustion for c in r.draw_pile + r.recycle + r.hand)} for r in mine],
            "revealed": [{"name": r.name, "team": r.team, "card": str(c), "who": self._who(r)}
                         for r, c in sorted(ctl.last_revealed.items(), key=lambda rc: (rc[0].team, rc[0].name))],
            "revealed_turn": ctl.last_revealed_turn,
            "log": [{"text": line.text, "team": line.team, "heading": line.heading} for line in ctl.log[-LOG_LINES:]],
            "teams": [self.team_label(t) for t in range(len(g.team_types))],
            "finished": ctl.phase == FINISHED,
            "winner": self._winner_text(),
            "size": [BOARD_W, MAP_H, PROFILE_H],
            **shared,
        }

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

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}
        self.lock = threading.Lock()
        self._choices: Optional[list[Choice]] = None

    def choices(self) -> list[Choice]:
        if self._choices is None:
            self._choices = online_choices()
        return self._choices

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
