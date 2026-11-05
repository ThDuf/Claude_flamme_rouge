"""Emplacements des fichiers du projet."""
import os

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARCOURS_DIR = os.path.join(PROJECT_DIR, "parcours")  # parcours enregistrés avec l'éditeur
DATA_DIR = os.path.join(PROJECT_DIR, "data")


def ensure_parcours_dir() -> str:
    os.makedirs(PARCOURS_DIR, exist_ok=True)
    return PARCOURS_DIR
