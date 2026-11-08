"""Extension Grand Tour : ce qui se joue pendant une étape d'un Tour (sans interface).

  - jetons Majeur (5/3/1) et Mineur (2/1), côté Sprint ou Montagne, posés à côté d'une case ;
  - tuile Chronométrage : les secondes gagnées selon la case où l'on finit après la ligne ;
  - temps d'étape = minutes (un jeton par tour fini sans avoir passé la ligne) + secondes.

Voir docs/extension_grand_tour.md. Les cartes Étape du Grand Tour donnent l'emplacement des jetons ;
en attendant leur relevé, on les place avec la règle « Création d'étapes » (place_tokens).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .track import ASCENT, Track

SPRINT = "sprint"
MOUNTAIN = "montagne"
MAJOR_VALUES = (5, 3, 1)
MINOR_VALUES = (2, 1)
LONG_CLIMB = 5  # une montée d'au moins 5 cases reçoit les jetons Majeur côté Montagne

# Tuile Chronométrage : secondes selon la case après la ligne (0 = première case après la ligne).
# Plus on finit loin, moins on prend de secondes. VALEURS PROVISOIRES : la règle n'en montre que quelques-unes.
TIMING_FLAT = (50, 40, 30, 20, 10, 0)  # arrivée en plaine (v) : six valeurs
TIMING_MOUNTAIN = (40, 30, 20, 10, 0)  # arrivée en montée (V) : cinq valeurs


@dataclass
class TokenStack:
    """Pile de jetons à côté d'une case : le premier qui y entre ou la dépasse prend le jeton du dessus."""

    square: int
    kind: str  # SPRINT ou MOUNTAIN
    values: list[int] = field(default_factory=list)  # du dessus vers le dessous
    major: bool = True

    @property
    def label(self) -> str:
        return f"{'Majeur' if self.major else 'Mineur'} {'Sprint' if self.kind == SPRINT else 'Montagne'}"


def climbs_of(track: Track) -> list[tuple[int, int]]:
    """Les montées continues : (première case, case juste après la dernière)."""
    runs, s, n = [], 0, len(track)
    while s < n:
        if track.kind(s) != ASCENT:
            s += 1
            continue
        end = s
        while end < n and track.kind(end) == ASCENT:
            end += 1
        runs.append((s, end))
        s = end
    return runs


def place_tokens(track: Track) -> list[TokenStack]:
    """Placement des jetons selon la règle « Création d'étapes » du Grand Tour.

    Jetons Majeur : côté Montagne après la plus longue montée continue d'au moins 5 cases (la plus proche de
    l'arrivée en cas d'égalité ; après la ligne si elle finit sur la ligne), sinon côté Sprint après la ligne.
    Jetons Mineur : côté Sprint après la ligne si les Majeur n'y sont pas ; sinon côté Montagne après la plus
    longue montée restante ; sinon côté Sprint vers le milieu de l'étape."""
    finish = len(track)
    runs = sorted(climbs_of(track), key=lambda r: (r[1] - r[0], r[0]), reverse=True)
    stacks: list[TokenStack] = []
    long = [r for r in runs if r[1] - r[0] >= LONG_CLIMB]
    if long:
        start, end = long[0]
        stacks.append(TokenStack(min(end, finish), MOUNTAIN, list(MAJOR_VALUES), True))
        runs.remove(long[0])
    else:
        stacks.append(TokenStack(finish, SPRINT, list(MAJOR_VALUES), True))
    if stacks[0].square != finish:
        stacks.append(TokenStack(finish, SPRINT, list(MINOR_VALUES), False))
    elif runs:
        start, end = runs[0]
        stacks.append(TokenStack(min(end, finish - 1), MOUNTAIN, list(MINOR_VALUES), False))
    else:
        stacks.append(TokenStack(max(track.start + 1, finish // 2), SPRINT, list(MINOR_VALUES), False))
    return stacks


def finish_seconds(track: Track, beyond: int) -> int:
    """Secondes de la tuile Chronométrage pour un coureur `beyond` cases après la ligne (0 = première case)."""
    table = TIMING_MOUNTAIN if len(track) and track.kind(len(track) - 1) == ASCENT else TIMING_FLAT
    return table[min(max(beyond, 0), len(table) - 1)]


def format_time(seconds: int) -> str:
    """« 1:20 » pour 80 secondes."""
    return f"{seconds // 60}:{seconds % 60:02d}"
