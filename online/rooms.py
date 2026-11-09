"""Parties à distance, sans réseau : salons, joueurs et déroulement d'une course.

Un salon a un code (4 lettres). Le premier joueur l'a créé : il en est l'hôte et règle la partie (parcours,
nombre d'équipes, extensions, qui joue chaque équipe). Les autres le rejoignent avec le code et prennent une
place libre. Au départ, les places « Joueur » restées libres sont jouées par l'IA.

Pendant la course, chaque joueur ne reçoit que sa propre main ; les coureurs choisissent leur carte chacun à
son tour (comme sur l'écran local), puis n'importe quel joueur lance le mouvement, l'aspiration et la fatigue.

Chaque changement augmente `version` : un navigateur qui a déjà la version courante ne retélécharge rien.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from flamme_rouge.boardview import (
    BOARD_W, FOLLOW_HEAD, FOLLOW_PELOTON, MAP_H, follow_view, map_primitives, podium_primitives, profile_primitives,
    track_preview_primitives,
)
from flamme_rouge.catalog import GROUP_MINE, GROUP_PELOTON, Choice, build_choices
from flamme_rouge.controller import CHOOSE, EXHAUSTION, FINISHED, MOVEMENT, SLIPSTREAM, TurnController
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

PHASE_TITLES = {
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
    game: Optional[Game] = None
    ctl: Optional[TurnController] = None
    ai_teams: frozenset = frozenset()
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

    def configure(self, player: Player, parcours=None, teams=None, extensions=None, seats=None) -> None:
        """L'hôte règle la partie ; les places devenues injouables sont libérées."""
        self._require_host(player)
        self._require_lobby()
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
        self.ctl = TurnController(self.game, self.ai_teams)
        self.bump()

    def back_to_lobby(self, player: Player) -> None:
        self._require_host(player)
        self.game = self.ctl = None
        self.bump()

    # ------------------------------------------------------------------ course

    def play_card(self, player: Player, index: int) -> None:
        ctl = self._running()
        rider = ctl.current_rider
        if ctl.phase != CHOOSE or rider is None or rider.team != player.team:
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
        ctl.advance()
        self.bump()

    def _running(self) -> TurnController:
        if self.ctl is None:
            raise OnlineError("La course n'est pas lancée.")
        return self.ctl

    # ------------------------------------------------------------------ état envoyé au navigateur

    def state(self, player: Player, camera: str = "") -> dict:
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
            base["race"] = self._race_state(player, camera)
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
            "seats": seats,
            "preview": self._cache["preview"],
            "preview_size": [PREVIEW_W, PREVIEW_H, PREVIEW_PROFILE_H],
        }

    def _race_state(self, player: Player, camera: str) -> dict:
        g, ctl = self.game, self.ctl
        rider = ctl.current_rider
        key = ("race", camera)
        if key not in self._cache:  # la même image pour tout le monde (seule la caméra change)
            view = follow_view(g, camera) if camera in (FOLLOW_PELOTON, FOLLOW_HEAD) else None
            shared = {
                "map": map_primitives(g, rider, view=view),
                "profile": profile_primitives(g.track, BOARD_W, PROFILE_H, riders=g.riders, weather=g.weather),
            }
            if ctl.phase == FINISHED:
                names = [self.team_label(t) for t in range(len(g.team_types))]
                shared["podium"] = podium_primitives(g, BOARD_W, MAP_H, 8.0, names)
            self._cache[key] = shared
        shared = self._cache[key]
        my_turn = ctl.phase == CHOOSE and rider is not None and rider.team == player.team
        if ctl.phase == CHOOSE and rider is not None:
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
