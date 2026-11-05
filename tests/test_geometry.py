import math

import pytest

from flamme_rouge import Game, Track
from flamme_rouge.geometry import ROAD_WIDTH, finish_edge, layout_squares
from flamme_rouge.track import DEFAULT_LAYOUT, DEFAULT_SHAPE, shape_to_angles


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def inside(point, quad):
    """Point dans un quadrilatère convexe (signe constant du produit vectoriel)."""
    signs = []
    for i in range(4):
        a, b = quad[i], quad[(i + 1) % 4]
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        signs.append(cross > 0)
    return all(signs) or not any(signs)


def test_shape_validation():
    with pytest.raises(ValueError):
        Track("....", shape="SSX")
    with pytest.raises(ValueError):
        Track("....", shape="SSSSS")


def test_shape_defaults():
    assert Track().angles == shape_to_angles(DEFAULT_SHAPE) and len(DEFAULT_SHAPE) == len(DEFAULT_LAYOUT)
    assert Track("." * 10).angles == (0.0,) * 10  # parcours perso : droit tant qu'on ne dit rien
    assert Track("." * 5, "LR").angles == (15.0, -15.0, 0.0, 0.0, 0.0)  # forme plus courte : complétée par du droit
    assert Track("." * 3, [30, 0, -10]).angles == (30.0, 0.0, -10.0)  # angles donnés en degrés
    assert Track().angle(999) == 0.0


def test_start_grid_must_leave_race_squares():
    assert Track("." * 6, start=5).start == 5
    with pytest.raises(ValueError):
        Track("." * 5, start=5)


def test_shape_does_not_change_the_rules():
    # Un parcours courbe et un parcours droit donnent exactement la même partie.
    layout = DEFAULT_LAYOUT
    curved = Game(Track(layout, DEFAULT_SHAPE), num_teams=3, seed=9)
    straight = Game(Track(layout, "S" * len(layout)), num_teams=3, seed=9)
    while not curved.finished:
        curved.play_turn(lambda g, r, hand: hand[0])
        straight.play_turn(lambda g, r, hand: hand[0])
    assert [(r.position, r.lane) for r in curved.riders] == [(r.position, r.lane) for r in straight.riders]
    assert curved.winner.name == straight.winner.name


def test_every_square_has_the_same_size_on_a_straight_road():
    squares = layout_squares(Track("." * 10), extra=2)
    for sq in squares:
        assert dist(sq.lb, sq.rb) == pytest.approx(ROAD_WIDTH)
        assert dist(sq.lb, sq.lf) == pytest.approx(1.0)


def test_squares_are_glued_together_without_gap():
    squares = layout_squares(Track(), extra=10)
    for a, b in zip(squares, squares[1:]):
        assert a.lf == pytest.approx(b.lb) and a.rf == pytest.approx(b.rb)


def test_a_curve_turns_the_road():
    # 6 'L' = virage à 90° vers la gauche : après la route on monte (y augmente).
    sq = layout_squares(Track("." * 20, "L" * 6), extra=0)
    assert sq[-1].center[1] > sq[0].center[1] + 8
    # une seule direction cumulée : les cases du virage sont décalées vers la gauche, pas vers la droite
    assert all(s.center[1] >= -1e-9 for s in sq)


def test_right_curve_goes_the_other_way():
    sq = layout_squares(Track("." * 20, "R" * 6), extra=0)
    assert sq[-1].center[1] < -8


def test_default_track_never_crosses_itself():
    track = Track()
    squares = layout_squares(track)
    centers = [sq.center for sq in squares]
    for i in range(len(centers)):
        for j in range(i + 4, len(centers)):
            assert dist(centers[i], centers[j]) > ROAD_WIDTH + 0.3, (i, j)


def test_lane_centers_are_inside_their_square_and_distinct():
    for sq in layout_squares(Track()):
        right, left = sq.lane_center(0), sq.lane_center(1)
        assert inside(right, sq.corners) and inside(left, sq.corners)
        assert dist(right, left) > ROAD_WIDTH / 4


def test_right_lane_is_on_the_right_of_the_direction_of_travel():
    sq = layout_squares(Track("." * 5), extra=0)[2]  # route vers l'est : la droite est au sud (y < 0)
    assert sq.lane_center(0)[1] < sq.lane_center(1)[1]


def test_finish_edge_is_after_the_last_square():
    track = Track()
    squares = layout_squares(track)
    lb, rb = finish_edge(squares, track)
    assert lb == squares[len(track)].lb and rb == squares[len(track)].rb


def test_curve_squares_turn_the_road_by_their_angle():
    # Un virage serré à gauche (2 cases de 45°) : après lui, la route va vers le nord.
    squares = layout_squares(Track("." * 4, [45, 45, 0, 0]), extra=0)
    lb, rb = squares[2].lb, squares[2].rb
    assert lb[0] - rb[0] == pytest.approx(-ROAD_WIDTH) and lb[1] - rb[1] == pytest.approx(0, abs=1e-9)
    # côté intérieur du virage plus court que l'extérieur (cases en éventail)
    assert dist(squares[0].lb, squares[0].lf) < dist(squares[0].rb, squares[0].rf)
