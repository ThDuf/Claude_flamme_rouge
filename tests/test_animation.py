import pytest

from flamme_rouge import Game, Track
from flamme_rouge.animation import moves_between, snapshot
from flamme_rouge.geometry import layout_squares, point_on_road


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


def test_a_real_movement_phase_gives_each_move_from_start_to_end():
    g = Game(Track("." * 40), num_teams=3, seed=4)
    played = g.energy_phase(lambda game, r, hand: hand[0])
    before = snapshot(g.riders)
    g.movement_phase(played)
    moves = moves_between(before, g.riders)
    assert moves
    for move in moves:
        assert move.start == before[move.rider] and move.end == (move.rider.position, move.rider.lane)


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


