import pytest

from flamme_rouge.extensions import EXTENSIONS, GRAND_TOUR, METEO, PELOTON, check_extensions, describe
from flamme_rouge.game import Game


def test_known_extensions():
    assert set(EXTENSIONS) == {PELOTON, METEO, GRAND_TOUR}
    assert check_extensions([METEO]) == frozenset({METEO})
    with pytest.raises(ValueError):
        check_extensions(["bidon"])


def test_describe():
    assert describe([]) == "jeu de base"
    assert describe([METEO, PELOTON]) == "Peloton + Meteo"


def test_game_keeps_the_chosen_extensions():
    assert Game(seed=1).extensions == frozenset()
    assert Game(seed=1, extensions=[PELOTON]).extensions == frozenset({PELOTON})
    with pytest.raises(ValueError):
        Game(extensions=["bidon"])
