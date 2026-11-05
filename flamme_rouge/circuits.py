"""Circuits de base : quatre parcours de 21 tuiles (composition de la boîte), prêts à jouer.

Ce ne sont PAS les cartes étape du jeu (dont le détail tuile par tuile n'est pas disponible dans les sources
textuelles) : ce sont des parcours équivalents, de même taille et de même composition, sans croisement.
"""
from __future__ import annotations

from .tiles import KIND_FINISH, KIND_START, Tile, make_tile

# (nom, description, [(type, direction, relief), ...])
BASE_CIRCUITS = [
    ('Circuit des sprinteurs', 'Presque plat : le peloton file, les sprinteurs sont à la fête.', [
        ('sharp', 'R', 'plat'),
        ('straight', None, 'plat'),
        ('straight', None, 'plat'),
        ('soft', 'R', 'plat'),
        ('straight', None, 'plat'),
        ('soft', 'L', 'plat'),
        ('soft', 'R', 'plat'),
        ('sharp', 'L', 'plat'),
        ('straight', None, 'plat'),
        ('sharp', 'L', 'plat'),
        ('soft', 'R', 'plat'),
        ('sharp', 'R', 'plat'),
        ('sharp', 'R', 'plat'),
        ('soft', 'L', 'plat'),
        ('straight', None, 'plat'),
        ('straight', None, 'plat'),
        ('soft', 'R', 'plat'),
        ('straight', None, 'plat'),
        ('sharp', 'L', 'plat'),
    ]),
    ('Classique', "Quelques bosses, une descente et une dernière côte avant l'arrivée.", [
        ('sharp', 'L', 'plat'),
        ('straight', None, 'plat'),
        ('sharp', 'L', 'plat'),
        ('soft', 'L', 'montée'),
        ('straight', None, 'montée puis descente'),
        ('straight', None, 'descente'),
        ('soft', 'L', 'plat'),
        ('sharp', 'R', 'plat'),
        ('soft', 'L', 'plat'),
        ('straight', None, 'plat'),
        ('sharp', 'R', 'plat'),
        ('straight', None, 'plat puis montée'),
        ('sharp', 'L', 'montée'),
        ('straight', None, 'descente puis plat'),
        ('soft', 'L', 'plat'),
        ('sharp', 'R', 'plat'),
        ('soft', 'R', 'plat'),
        ('soft', 'R', 'plat'),
        ('straight', None, 'plat'),
    ]),
    ('Haute montagne', 'Longues montées et descentes rapides : les rouleurs souffrent.', [
        ('sharp', 'R', 'plat'),
        ('sharp', 'R', 'plat'),
        ('straight', None, 'montée'),
        ('sharp', 'R', 'montée'),
        ('straight', None, 'montée puis descente'),
        ('soft', 'R', 'descente'),
        ('straight', None, 'plat'),
        ('straight', None, 'plat'),
        ('straight', None, 'plat puis montée'),
        ('straight', None, 'montée'),
        ('soft', 'R', 'montée'),
        ('soft', 'L', 'montée puis descente'),
        ('sharp', 'R', 'descente'),
        ('soft', 'L', 'descente puis plat'),
        ('straight', None, 'plat'),
        ('sharp', 'R', 'montée'),
        ('soft', 'L', 'montée puis descente'),
        ('sharp', 'R', 'descente'),
        ('soft', 'L', 'plat'),
    ]),
    ('Vallonné', 'Une succession de petites côtes, beaucoup de virages.', [
        ('sharp', 'L', 'plat'),
        ('straight', None, 'plat puis montée'),
        ('sharp', 'R', 'plat'),
        ('sharp', 'L', 'plat'),
        ('soft', 'L', 'plat'),
        ('soft', 'R', 'plat'),
        ('sharp', 'R', 'plat'),
        ('straight', None, 'descente puis plat'),
        ('soft', 'L', 'plat'),
        ('straight', None, 'plat puis montée'),
        ('straight', None, 'montée puis descente'),
        ('sharp', 'L', 'plat'),
        ('straight', None, 'plat'),
        ('straight', None, 'plat puis montée'),
        ('sharp', 'R', 'plat'),
        ('soft', 'R', 'plat'),
        ('straight', None, 'plat'),
        ('soft', 'R', 'plat'),
        ('soft', 'L', 'plat'),
    ]),
]


def base_circuits() -> list[tuple[str, str, list[Tile]]]:
    """[(nom, description, tuiles)] : départ + 19 tuiles + arrivée."""
    result = []
    for name, description, middle in BASE_CIRCUITS:
        tiles = [make_tile(KIND_START)] + [make_tile(k, d, r) for k, d, r in middle] + [make_tile(KIND_FINISH)]
        result.append((name, description, tiles))
    return result
