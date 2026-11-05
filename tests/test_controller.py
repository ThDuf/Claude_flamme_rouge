import pytest

from flamme_rouge import Game, Track
from flamme_rouge.boardview import board_primitives, minimap_primitives, window
from flamme_rouge.controller import (
    CHOOSE,
    EXHAUSTION,
    FINISHED,
    MOVEMENT,
    SLIPSTREAM,
    TurnController,
)


def play_one_turn(ctl, pick=lambda hand: hand[0]):
    while ctl.phase == CHOOSE:
        ctl.choose(pick(ctl.hand))
    assert ctl.phase == MOVEMENT
    ctl.advance()
    assert ctl.phase == SLIPSTREAM
    ctl.advance()
    assert ctl.phase == EXHAUSTION
    ctl.advance()


def test_turn_goes_through_the_phases_in_order():
    ctl = TurnController(Game(num_teams=2, seed=1))
    assert ctl.phase == CHOOSE and ctl.current_rider is ctl.game.riders[0]
    play_one_turn(ctl)
    assert ctl.game.turn == 1
    assert ctl.phase == CHOOSE  # le tour suivant a commencé


def test_each_rider_gets_a_hand_of_four_one_at_a_time():
    ctl = TurnController(Game(num_teams=2, seed=1))
    seen = []
    while ctl.phase == CHOOSE:
        seen.append((ctl.current_rider, len(ctl.hand)))
        ctl.choose(ctl.hand[0])
    assert [r for r, _ in seen] == ctl.game.riders
    assert all(n == 4 for _, n in seen)


def test_nothing_moves_before_advance():
    ctl = TurnController(Game(num_teams=2, seed=1))
    before = [(r.position, r.lane) for r in ctl.game.riders]
    while ctl.phase == CHOOSE:
        ctl.choose(ctl.hand[0])
    assert [(r.position, r.lane) for r in ctl.game.riders] == before


def test_cannot_choose_outside_choose_phase_nor_advance_while_choosing():
    ctl = TurnController(Game(num_teams=2, seed=1))
    with pytest.raises(RuntimeError):
        ctl.advance()
    card = ctl.hand[0]
    while ctl.phase == CHOOSE:
        ctl.choose(ctl.hand[0])
    with pytest.raises(RuntimeError):
        ctl.choose(card)


def test_chosen_card_must_be_in_hand():
    from flamme_rouge import Card

    ctl = TurnController(Game(num_teams=2, seed=1))
    with pytest.raises(ValueError):
        ctl.choose(Card(99))


def test_rider_without_cards_plays_exhaustion_automatically():
    g = Game(num_teams=2, seed=1)
    g.riders[0].draw_pile, g.riders[0].recycle = [], []
    ctl = TurnController(g)
    assert ctl.current_rider is g.riders[1]  # le coureur sans carte est passé automatiquement
    assert ctl.played[g.riders[0]].exhaustion


def test_log_is_drained_once():
    ctl = TurnController(Game(num_teams=2, seed=1))
    assert ctl.drain_log()
    assert ctl.drain_log() == []
    play_one_turn(ctl)
    texts = [line.text for line in ctl.drain_log() if line.heading]
    assert texts[:3] == ["Mouvement", "Aspiration", "Fatigue"]


@pytest.mark.parametrize("teams", [2, 3, 4])
def test_full_game_via_controller_matches_rules(teams):
    ctl = TurnController(Game(num_teams=teams, seed=7))
    for _ in range(300):
        if ctl.phase == FINISHED:
            break
        play_one_turn(ctl)
    assert ctl.phase == FINISHED and ctl.game.winner is not None
    assert any("Victoire" in line.text for line in ctl.drain_log())


def test_same_seed_same_game_as_engine_alone():
    # Le contrôleur et Game.play_turn doivent donner la même partie quand on joue la 1re carte.
    a = Game(num_teams=2, seed=3)
    ctl = TurnController(Game(num_teams=2, seed=3))
    a.play_turn(lambda game, rider, hand: hand[0])
    play_one_turn(ctl)
    assert [(r.position, r.lane) for r in a.riders] == [(r.position, r.lane) for r in ctl.game.riders]


# ------------------------------------------------------------ géométrie du plateau


def test_board_primitives_contain_every_rider():
    g = Game(num_teams=4, seed=1)
    names = {p[3] for p in board_primitives(g) if p[0] == "text"}
    assert {"1R", "1S", "2R", "2S", "3R", "3S", "4R", "4S"} <= names


def test_window_keeps_leader_visible_and_fits_width():
    from flamme_rouge.boardview import BOARD_W, CELL_W, PAD

    g = Game(Track("." * 80), num_teams=2, seed=1)
    g.riders[0].position = 70
    first, last = window(g)
    assert first <= 70 <= last
    assert PAD + (last - first + 1) * CELL_W <= BOARD_W


def test_board_and_minimap_work_at_the_end_of_a_game():
    g = Game(num_teams=3, seed=2)
    while not g.finished:
        g.play_turn()
    assert board_primitives(g, g.winner)
    assert minimap_primitives(g)


# ------------------------------------------------------------------ carte en 2D


def test_map_contains_every_rider_and_stays_on_canvas():
    from flamme_rouge.boardview import BOARD_W, MAP_H, map_primitives

    g = Game(num_teams=4, seed=1)
    for _ in range(40):
        if g.finished:
            break
        prims = map_primitives(g)
        names = {p[3] for p in prims if p[0] == "text"}
        assert {r.name for r in g.riders} <= names  # tous les coureurs sont dessinés
        for p in prims:
            if p[0] == "poly":
                xs, ys = p[1][0::2], p[1][1::2]
                assert -1 <= min(xs) and max(xs) <= BOARD_W + 1
                assert -1 <= min(ys) and max(ys) <= MAP_H + 1
        g.play_turn()


def test_map_window_keeps_leader_and_pack_visible():
    from flamme_rouge.boardview import map_window

    g = Game(Track("." * 80), num_teams=2, seed=1)
    g.riders[0].position = 60
    first, last = map_window(g)
    assert first <= min(r.position for r in g.riders) or last - first + 1 == 26
    assert first <= 60 <= last


def test_map_works_at_the_end_of_a_game():
    from flamme_rouge.boardview import map_primitives

    g = Game(num_teams=3, seed=2)
    while not g.finished:
        g.play_turn()
    assert any(p[0] == "text" and p[3] == "ARRIVÉE" for p in map_primitives(g, g.winner))
