"""Affichage texte du plateau, en couleurs si le terminal le permet."""
from __future__ import annotations

import os
import shutil
import sys

from .game import Game
from .rider import Rider
from .track import ASCENT, DESCENT, NORMAL

USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if USE_COLOR and os.name == "nt":
    os.system("")  # active les codes de couleur dans la console Windows

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
FINISH = "\033[1;97m"
ORANGE = "\033[38;5;208m"
CYAN = "\033[36m"
# Une couleur par équipe : rouge, bleu, vert, jaune.
TEAM_COLORS = ["\033[1;91m", "\033[1;94m", "\033[1;92m", "\033[1;93m", "\033[1;95m", "\033[1;97m"]
TERRAIN = {NORMAL: ("·", DIM), ASCENT: ("▲", ORANGE), DESCENT: ("▼", CYAN)}

CELL = 5  # largeur d'une case à l'écran
LABEL_W = 8  # largeur de la colonne d'étiquettes (terrain, droite, gauche...)


def paint(text: str, code: str) -> str:
    return f"{code}{text}{RESET}" if USE_COLOR else text


def rider_tag(rider: Rider) -> str:
    return paint(rider.name, TEAM_COLORS[rider.team])


def _terrain_parts(game: Game, square: int) -> tuple[str, str]:
    finish = len(game.track)
    if square < finish:
        return TERRAIN[game.track.kind(square)]
    if square == finish:
        return "┃", FINISH
    return "░", DIM  # après la ligne d'arrivée


def terrain_symbol(game: Game, square: int) -> str:
    sym, code = _terrain_parts(game, square)
    return paint(sym, code)


def legend() -> str:
    return (
        f"{paint('▲', ORANGE)} montée (max 5)   {paint('▼', CYAN)} descente (min 5)   "
        f"{paint('┃', FINISH)} ligne d'arrivée   {paint('●', BOLD)} coureur (vue d'ensemble)"
    )


def _window(game: Game, first: int | None, last: int | None) -> tuple[int, int]:
    """Portion du parcours à afficher : de l'arrière du peloton jusqu'un peu devant le leader,
    réduite si le terminal est trop étroit (on garde alors le leader visible)."""
    cols = shutil.get_terminal_size((100, 24)).columns
    capacity = max(8, (cols - LABEL_W - 2) // (CELL + 1))
    positions = [r.position for r in game.riders]
    if last is None:
        last = max(min(len(game.track) + 2, max(positions) + 6), max(positions))
    if first is None:
        first = max(0, min(positions) - 1)
    first = max(0, min(first, last))
    if last - first + 1 > capacity:
        first = max(0, last - capacity + 1)
    return first, last


def render(game: Game, first: int | None = None, last: int | None = None) -> str:
    """Le plateau en cases : une ligne de terrain, puis les deux couloirs."""
    first, last = _window(game, first, last)
    squares = list(range(first, last + 1))
    finish = len(game.track)

    def sep(s: int) -> str:
        return paint("┃", FINISH) if s == finish else "│"

    def row(label: str, cells: list[str]) -> str:
        return label.ljust(LABEL_W) + "".join(sep(s) + c for s, c in zip(squares, cells)) + "│"

    def lane_cell(s: int, lane: int) -> str:
        for r in game.riders_at(s):
            if r.lane == lane:
                return paint(r.name.center(CELL), TEAM_COLORS[r.team])
        return " " * CELL

    terrain_cells = []
    for s in squares:
        sym, code = _terrain_parts(game, s)
        terrain_cells.append(paint(sym.center(CELL), code))

    bar = "─" * CELL
    pad = " " * LABEL_W
    return "\n".join(
        [
            pad + "┌" + "┬".join(bar for _ in squares) + "┐",
            row("terrain", terrain_cells),
            pad + "├" + "┼".join(bar for _ in squares) + "┤",
            row("droite", [lane_cell(s, 0) for s in squares]),
            row("gauche", [lane_cell(s, 1) for s in squares]),
            pad + "└" + "┴".join(bar for _ in squares) + "┘",
            "case".ljust(LABEL_W) + " " + " ".join(str(s).center(CELL) for s in squares),
        ]
    )


def minimap(game: Game) -> str:
    """Toute la course sur une ligne : une case = un caractère."""
    end = max(len(game.track) + 3, max(r.position for r in game.riders) + 1)
    chars = []
    for s in range(end):
        here = game.riders_at(s)
        if here:
            r = min(here, key=lambda r: r.lane)
            chars.append(paint("●", TEAM_COLORS[r.team]))
        else:
            chars.append(terrain_symbol(game, s))
    return "course".ljust(LABEL_W) + "".join(chars)


def standings(game: Game) -> str:
    order = sorted(game.riders, key=lambda r: (-r.position, r.lane))
    parts = [f"{i}. {rider_tag(r)} (case {r.position})" for i, r in enumerate(order, 1)]
    return "Classement : " + "   ".join(parts)


def board_view(game: Game) -> str:
    return "\n".join([minimap(game), "", render(game), "", standings(game)])
