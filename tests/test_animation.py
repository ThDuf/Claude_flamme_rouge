import pytest

from flamme_rouge import Game, Track
from flamme_rouge.animation import (
    MOVE_DURATION,
    MOVE_STAGGER,
    Animation,
    Move,
    ease,
    moves_between,
    movement_animation,
    slipstream_animation,
    snapshot,
)
from flamme_rouge.cards import Card
from flamme_rouge.geometry import layout_squares, point_on_road


def test_ease_is_smooth_and_bounded():
    assert ease(-1) == 0 and ease(0) == 0 and ease(1) == 1 and ease(5) == 1
    assert ease(0.5) == pytest.approx(0.5)
    values = [ease(i / 20) for i in range(21)]
    assert values == sorted(values)  # toujours croissant
    assert ease(0.1) < 0.1 and ease(0.9) > 0.9  # lent au début et à la fin


def test_moves_between_only_lists_riders_that_moved():
    g = Game(Track("." * 40), num_teams=2, seed=1)
    before = snapshot(g.riders)
    mover = g.riders[3]
    mover.position += 5
    moves = moves_between(before, g.riders)
    assert [m.rider for m in moves] == [mover]
    assert moves[0].start == before[mover] and moves[0].end == (mover.position, mover.lane)


def test_a_lane_change_alone_counts_as_a_move():
    g = Game(Track("." * 40), num_teams=2, seed=1)
    before = snapshot(g.riders)
    g.riders[0].lane = 1 - g.riders[0].lane
    assert len(moves_between(before, g.riders)) == 1


def test_positions_start_at_start_and_finish_at_end():
    rider = object()
    anim = Animation([Move(rider, (3, 0), (9, 1))], duration=1.0)
    assert anim.positions(0.0)[rider] == (3, 0)
    assert anim.positions(1.0)[rider] == (9, 1)
    assert anim.positions(99.0)[rider] == (9, 1)
    mid_case, mid_lane = anim.positions(0.5)[rider]
    assert mid_case == pytest.approx(6) and mid_lane == pytest.approx(0.5)
    assert anim.done(1.0) and not anim.done(0.99)


def test_riders_never_go_backwards_during_the_animation():
    rider = object()
    anim = Animation([Move(rider, (3, 0), (11, 0))], duration=1.0)
    cases = [anim.positions(i / 50)[rider][0] for i in range(60)]
    assert cases == sorted(cases)


def test_movement_goes_front_to_back_with_a_delay():
    front, back = object(), object()
    anim = movement_animation([Move(back, (0, 0), (5, 0)), Move(front, (10, 0), (15, 0))])
    assert [m.rider for m in anim.moves] == [front, back]  # le plus avancé démarre en premier
    assert anim.total == pytest.approx(MOVE_STAGGER + MOVE_DURATION)
    at = anim.positions(MOVE_STAGGER / 2)
    assert at[front][0] > 10  # le premier est déjà parti
    assert at[back] == (0, 0)  # le second attend son tour


def test_slipstream_moves_everyone_together():
    a, b = object(), object()
    anim = slipstream_animation([Move(a, (0, 0), (1, 0)), Move(b, (4, 0), (5, 0))])
    at = anim.positions(0.2)
    assert at[a][0] - 0 == pytest.approx(at[b][0] - 4)


def test_empty_animation_has_no_duration():
    assert Animation([]).total == 0 and Animation([]).done(0)


def test_a_real_movement_phase_can_be_animated_end_to_end():
    g = Game(Track("." * 40), num_teams=3, seed=4)
    played = g.energy_phase(lambda game, r, hand: hand[0])
    before = snapshot(g.riders)
    g.movement_phase(played)
    anim = movement_animation(moves_between(before, g.riders))
    assert anim.moves
    final = anim.positions(anim.total)
    for rider, (case, lane) in final.items():
        assert (case, lane) == (rider.position, rider.lane)


# ------------------------------------------------------------ point sur la route


def test_point_on_road_matches_lane_centers_on_whole_squares():
    squares = layout_squares(Track("." * 10), extra=0)
    for s in (0, 4, 9):
        assert point_on_road(squares, s, 0) == pytest.approx(squares[s].lane_center(0))
        assert point_on_road(squares, s, 1) == pytest.approx(squares[s].lane_center(1))


def test_point_on_road_is_halfway_between_squares_and_lanes():
    squares = layout_squares(Track("." * 10), extra=0)
    a, b = squares[3].lane_center(0), squares[4].lane_center(0)
    assert point_on_road(squares, 3.5, 0) == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
    left, right = squares[3].lane_center(1), squares[3].lane_center(0)
    assert point_on_road(squares, 3, 0.5) == pytest.approx(((left[0] + right[0]) / 2, (left[1] + right[1]) / 2))


def test_point_on_road_clamps_outside_the_road():
    squares = layout_squares(Track("." * 10), extra=0)
    assert point_on_road(squares, -5, 0) == pytest.approx(squares[0].lane_center(0))
    assert point_on_road(squares, 99, 0) == pytest.approx(squares[-1].lane_center(0))


def test_point_on_road_follows_a_curve():
    squares = layout_squares(Track("." * 12, "L" * 6), extra=0)
    points = [point_on_road(squares, i / 4, 0) for i in range(4 * 11)]
    steps = [((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5 for p, q in zip(points, points[1:])]
    assert max(steps) < 0.35 and min(steps) > 0.1  # progression régulière, sans saut


def test_each_rider_starts_only_after_the_previous_one_has_arrived():
    from flamme_rouge.animation import Move, movement_animation

    class R:
        pass

    riders = [R() for _ in range(4)]
    moves = [Move(r, (p, 0), (p + 5, 0)) for r, p in zip(riders, (3, 9, 6, 1))]
    anim = movement_animation(moves)
    assert [m.start[0] for m in anim.moves] == [9, 6, 3, 1]  # le premier de la course part le premier
    assert anim.stagger >= anim.duration  # pas de chevauchement
    t = anim.duration * 0.5  # le leader est à mi-chemin : les autres n'ont pas bougé
    pos = anim.positions(t)
    assert 9 < pos[riders[1]][0] < 14 and pos[riders[2]][0] == 6 and pos[riders[0]][0] == 3 and pos[riders[3]][0] == 1


def test_whole_movement_phase_stays_short_with_many_riders():
    from flamme_rouge.animation import MOVE_TOTAL_MAX, Move, movement_animation

    moves = [Move(object(), (i, 0), (i + 4, 0)) for i in range(8)]
    assert movement_animation(moves).total <= MOVE_TOTAL_MAX + 1e-9
