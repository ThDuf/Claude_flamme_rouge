"""Liste des parcours proposés par le menu (sans interface) : prêts à jouer, officiels, enregistrés."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from .circuits import base_circuits
from .official import official_stages
from .paths import PARCOURS_DIR
from .tiles import ERROR, Tile, plan_from_json, plan_to_track, validate
from .track import Track

GROUP_BASE = "Circuits de base"
GROUP_OFFICIAL = "Parcours officiels"
GROUP_MINE = "Mes parcours"

MAX_SAVED_FILES = 12  # le menu ne liste que les plus récents ; « Ouvrir un fichier » donne accès aux autres


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    group: str
    track: Optional[Track] = None
    tiles: Optional[tuple] = None  # les tuiles, quand le parcours en est fait
    problem: Optional[str] = None  # pourquoi on ne peut pas le jouer

    @property
    def playable(self) -> bool:
        return self.track is not None and self.problem is None

    @property
    def details(self) -> str:
        if not self.playable:
            return self.problem or "Parcours indisponible."
        text = f"{len(self.track)} cases de course"
        return text + (f" · {len(self.tiles)} tuiles" if self.tiles else "")


def choice_from_tiles(key: str, label: str, group: str, tiles: Sequence[Tile]) -> Choice:
    """Un parcours en tuiles, jouable seulement s'il n'a aucune erreur."""
    errors = [issue.text for issue in validate(tiles) if issue.level == ERROR]
    if errors:
        return Choice(key, label, group, tiles=tuple(tiles), problem=" ".join(errors))
    return Choice(key, label, group, plan_to_track(tiles), tuple(tiles))


def choice_from_file(path: str) -> Choice:
    label = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, encoding="utf-8") as handle:
            tiles = plan_from_json(handle.read())
    except (OSError, ValueError) as exc:
        return Choice(path, label, GROUP_MINE, problem=f"Fichier illisible : {exc}")
    return choice_from_tiles(path, label, GROUP_MINE, tiles)


def saved_files(parcours_dir: str = PARCOURS_DIR) -> list[str]:
    """Les fichiers .json enregistrés, du plus récent au plus ancien."""
    paths = glob.glob(os.path.join(parcours_dir, "*.json"))
    return sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)


def build_choices(
    parcours_dir: str = PARCOURS_DIR,
    extra_files: Iterable[str] = (),
) -> list[Choice]:
    """Les parcours du menu : les étapes officielles d'abord, puis les circuits de base et les parcours enregistrés."""
    choices: list[Choice] = []
    for stage in official_stages():
        if stage.available:
            choices.append(choice_from_tiles(f"officiel:{stage.name}", stage.name, GROUP_OFFICIAL, stage.tiles))
        else:
            problem = f"Tuiles inconnues : {', '.join(stage.missing)}."
            choices.append(Choice(f"officiel:{stage.name}", stage.name, GROUP_OFFICIAL, problem=problem))
    for name, description, tiles in base_circuits():
        choices.append(choice_from_tiles(f"base:{name}", name, GROUP_BASE, tiles))

    paths = saved_files(parcours_dir)[:MAX_SAVED_FILES]
    for path in extra_files:
        if path not in paths:
            paths.append(path)
    choices.extend(choice_from_file(path) for path in paths)
    return choices
