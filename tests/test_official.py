import math

import pytest

from flamme_rouge.game import Game
from flamme_rouge.official import (
    MOUNTAIN_DEFS,
    OFFICIAL_TILES,
    STAGES,
    TILE_DEFS,
    build_stage,
    official_stages,
    official_tile,
    tile_from_def,
)
from flamme_rouge.tiles import (
    KIND_FINISH,
    KIND_SHARP,
    KIND_SOFT,
    KIND_START,
    KIND_STRAIGHT,
    OFFICIAL_MAX,
    finish_square,
    make_tile,
    plan_to_track,
    validate,
)
from flamme_rouge.track import ASCENT, LEFT, RIGHT


def test_every_stage_uses_each_of_the_21_tiles_exactly_once():
    # Vérifie la retranscription des chaînes du règlement (la casse indique le côté retourné).
    for name, setup in STAGES.items():
        assert len(setup) == 21, name
        assert sorted(setup.lower()) == list("abcdefghijklmnopqrstu"), name


def test_avenue_corso_paseo_is_the_beginner_track_in_alphabetical_order():
    assert STAGES["Avenue Corso Paseo"] == "abcdefghijklmnopqrstu"


def test_every_stage_starts_with_a_and_ends_with_u():
    for name, setup in STAGES.items():
        assert setup[0] in "aA" and setup[-1] in "uU", name


def test_all_42_faces_are_described():
    assert set(TILE_DEFS) == set("abcdefghijklmnopqrstu")
    assert set(MOUNTAIN_DEFS) == set("ABCDEFGHIJKLMNOPQRSTU")
    assert len(OFFICIAL_TILES) == 42


def test_each_side_of_the_box_matches_the_official_quantities():
    for letters in ("abcdefghijklmnopqrstu", "ABCDEFGHIJKLMNOPQRSTU"):
        kinds = [OFFICIAL_TILES[c].kind for c in letters]
        for kind, count in OFFICIAL_MAX.items():
            assert kinds.count(kind) == count, (letters, kind)


def test_both_faces_of_a_tile_have_the_same_shape_and_turning_flips_the_direction():
    for lower in "abcdefghijklmnopqrstu":
        a, b = official_tile(lower), official_tile(lower.upper())
        assert a.kind == b.kind, lower
        if a.direction:
            assert {a.direction, b.direction} == {LEFT, RIGHT}, lower


def test_tile_lengths_curves_are_two_squares():
    for tile in OFFICIAL_TILES.values():
        assert len(tile.cells) == (2 if tile.kind in (KIND_SOFT, KIND_SHARP) else 6)


def test_start_and_finish_faces():
    assert official_tile("a").grid_squares == 5 and official_tile("A").grid_squares == 4
    u, U = official_tile("u"), official_tile("U")
    assert u.cells == "feeeee" and U.cells == "uueeee"
    assert U.layout[:2] == ASCENT * 2


def test_tile_from_def_rejects_unknown_angles():
    with pytest.raises(ValueError):
        tile_from_def("x", (math.radians(30), 1), "ff")
    assert tile_from_def("x", None, "sssssf").kind == KIND_START
    assert tile_from_def("x", None, "feeeee").kind == KIND_FINISH
    assert tile_from_def("x", None, "ffffff").kind == KIND_STRAIGHT


def test_all_official_stages_are_playable_and_do_not_cross():
    stages = official_stages()
    assert [s.name for s in stages] == list(STAGES)
    for stage in stages:
        assert stage.available, stage.name
        assert validate(stage.tiles) == [], stage.name


def test_official_stage_lengths():
    # 6 cases de départ + 7 droites de 6 + 12 virages de 2 + 1 case avant l'arrivée (u)
    track = plan_to_track(official_stages()[0].tiles)
    assert track.start == 5
    assert len(track) == 6 + 7 * 6 + 12 * 2 + 1
    classicissima = plan_to_track(build_stage("x", STAGES["La Classicissima"]).tiles)
    assert classicissima.start == 4


def test_riders_start_on_the_grid_behind_the_line():
    track = plan_to_track(official_stages()[0].tiles)
    game = Game(track, num_teams=4, seed=1)
    assert sorted({r.position for r in game.riders}) == [1, 2, 3, 4]
    assert all(r.position < track.start for r in game.riders)


def test_mountain_finish_is_two_squares_of_climb_before_the_line():
    tiles = build_stage("x", STAGES["La Haut Montagne"]).tiles
    track = plan_to_track(tiles)
    assert track.layout.endswith(ASCENT * 2)
    assert finish_square(tiles) == len(track)


def test_build_stage_reports_missing_letters_once_each():
    stage = build_stage("x", "abbc", {"a": make_tile("start")})
    assert stage.missing == ("b", "c") and not stage.available


def test_the_six_stage_cards_of_the_base_game():
    # Relevé sur les cartes étape de la boîte (lettre encadrée = face montagne).
    assert len(STAGES) == 6
    assert STAGES["Ballons Centrale"] == "AnLHgceqtrMBoipjDFkSu"
