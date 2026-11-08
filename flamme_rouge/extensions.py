"""Extensions du jeu qu'on peut activer depuis le menu.

Une partie garde la liste des extensions choisies (`Game.extensions`).
Météo est programmée (voir weather.py) ; Peloton n'a encore que son interrupteur.
"""
from __future__ import annotations

from typing import Iterable

PELOTON = "peloton"
METEO = "meteo"

# nom interne -> (nom affiché, description courte)
EXTENSIONS = {
    PELOTON: ("Peloton", "5–6 équipes, pavés, ravitaillement, équipes fantômes"),
    METEO: ("Meteo", "vent et pluie sur les lignes droites"),
}

READY: frozenset[str] = frozenset({METEO, PELOTON})  # extensions dont les règles sont programmées


def check_extensions(names: Iterable[str]) -> frozenset[str]:
    """Liste d'extensions validée ; lève ValueError pour un nom inconnu."""
    chosen = frozenset(names)
    unknown = chosen - set(EXTENSIONS)
    if unknown:
        raise ValueError(f"Extension inconnue : {', '.join(sorted(unknown))}.")
    return chosen


def describe(names: Iterable[str]) -> str:
    """Texte court pour l'interface : « jeu de base » ou les extensions choisies."""
    chosen = check_extensions(names)
    if not chosen:
        return "jeu de base"
    return " + ".join(EXTENSIONS[name][0] for name in EXTENSIONS if name in chosen)
