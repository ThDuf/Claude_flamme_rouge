"""Éditeur de parcours dans le navigateur : ce que le serveur calcule pour lui (sans état).

La page garde le parcours en cours (liste de tuiles) et l'envoie à chaque modification ; le serveur renvoie
l'aperçu, le profil, le comptage et les erreurs, avec les mêmes fonctions que l'éditeur de bureau.
Enregistrer dans le dossier `parcours/` n'est possible que sur un serveur local (python main.py) : sur Render,
la page propose de télécharger le fichier à la place.
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from flamme_rouge.boardview import plan_preview_primitives, profile_primitives, tile_card_primitives
from flamme_rouge.official import official_tile
from flamme_rouge.plan import FLAT_SIDE, MOUNTAIN_SIDE, PELOTON_SIDE, letter_for_tile, side_letters
from flamme_rouge.tiles import (
    ERROR, FILE_VERSION, Tile, example_plan, has_errors, plan_from_json, plan_to_json, plan_to_track, summary,
    validate,
)

from .rooms import Lobby, OnlineError

CARD_W, CARD_H = 96, 50
PREVIEW_W, PREVIEW_H, PROFILE_H = 700, 470, 110
MAX_TILES = 80
NAME_MAX = 40
SIDES = [(FLAT_SIDE, "Plates a–u"), (MOUNTAIN_SIDE, "Montagne A–U"), (PELOTON_SIDE, "Peloton")]
EXAMPLE_KEY = "exemple"


def tile_json(tile: Tile) -> dict:
    item = {"kind": tile.kind, "direction": tile.direction, "cells": tile.cells}
    if tile.letter:
        item["letter"] = tile.letter
    return item


def parse_tiles(items) -> list[Tile]:
    """Les tuiles envoyées par la page (même format que les fichiers .json)."""
    if not isinstance(items, list):
        raise OnlineError("Parcours illisible.")
    if len(items) > MAX_TILES:
        raise OnlineError(f"Au plus {MAX_TILES} tuiles.")
    try:
        return plan_from_json(json.dumps({"version": FILE_VERSION, "tiles": items}))
    except ValueError as exc:
        raise OnlineError(str(exc)) from exc


def catalog() -> dict:
    """Les tuiles de la boîte, face par face, avec leur petite carte dessinée."""
    sides, cards = [], {}
    for side, label in SIDES:
        letters = side_letters(side)
        sides.append({"key": side, "label": label, "letters": letters})
        for letter in letters:
            tile = official_tile(letter)
            cards[letter] = {"tile": tile_json(tile), "label": tile.label,
                             "prims": tile_card_primitives(tile, CARD_W, CARD_H)}
    return {"sides": sides, "cards": cards, "card_size": [CARD_W, CARD_H]}


def check(items, selected: Optional[int] = None) -> dict:
    """Aperçu, profil (si le parcours est jouable), comptage et messages du parcours en cours."""
    tiles = parse_tiles(items)
    if selected is not None and not (isinstance(selected, int) and 0 <= selected < len(tiles)):
        selected = None
    issues = validate(tiles)
    playable = not has_errors(issues)
    return {
        "preview": plan_preview_primitives(tiles, PREVIEW_W, PREVIEW_H, selected),
        "profile": profile_primitives(plan_to_track(tiles), PREVIEW_W, PROFILE_H) if playable else None,
        "size": [PREVIEW_W, PREVIEW_H, PROFILE_H],
        "summary": summary(tiles),
        "issues": [{"level": "error" if i.level == ERROR else "warning", "text": i.text} for i in issues],
        "playable": playable,
        "labels": [t.label for t in tiles],
        "letters": [letter_for_tile(t) for t in tiles],
    }


def openable(lobby: Lobby) -> list[dict]:
    """Les parcours qu'on peut ouvrir dans l'éditeur : l'exemple, puis tous ceux du salon faits de tuiles."""
    out = [{"key": EXAMPLE_KEY, "label": "Parcours d'exemple", "group": "Exemple"}]
    out += [{"key": c.key, "label": c.label, "group": c.group} for c in lobby.choices() if c.tiles]
    return out


def load(lobby: Lobby, key: str) -> dict:
    if key == EXAMPLE_KEY:
        return {"label": "exemple", "tiles": [tile_json(t) for t in example_plan()]}
    choice = next((c for c in lobby.choices() if c.key == key and c.tiles), None)
    if choice is None:
        raise OnlineError("Parcours inconnu.")
    return {"label": choice.label, "tiles": [tile_json(t) for t in choice.tiles]}


def clean_file_name(name) -> str:
    """Un nom de fichier sûr : lettres, chiffres, espaces, tirets ; pas de chemin."""
    name = re.sub(r"[^\w \-'àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ]", "", str(name or ""), flags=re.UNICODE)
    name = " ".join(name.split())[:NAME_MAX].strip(" .")
    if not name:
        raise OnlineError("Choisis un nom pour le parcours.")
    return name


def save(lobby: Lobby, name, items) -> dict:
    """Enregistre le parcours dans `parcours/` (serveur local seulement) ; il apparaît dans « Mes parcours »."""
    tiles = parse_tiles(items)
    if has_errors(validate(tiles)):
        raise OnlineError("Ce parcours a des erreurs : corrige-les avant de l'enregistrer.")
    name = clean_file_name(name)
    folder = lobby.parcours_dir
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name + ".json")
    existed = os.path.exists(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(plan_to_json(tiles))
    lobby.refresh_choices()
    return {"saved": name, "replaced": existed, "key": f"mine:{name}"}
