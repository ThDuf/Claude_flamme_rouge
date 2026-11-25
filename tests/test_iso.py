import pytest

from flamme_rouge.boardview import CYCLIST_WHEEL, _map_frame, map_primitives, map_transform, road_geometry
from flamme_rouge.game import Game
from flamme_rouge.geometry import point_on_road
from flamme_rouge.iso import ISO_LIFT, best_angle, projection
from flamme_rouge.official import official_stages
from flamme_rouge.tiles import plan_to_track
from flamme_rouge.track import Track


def official(i):
    return plan_to_track(official_stages()[i].tiles)


def test_climbs_rise_on_screen():
    track = Track("." * 5 + "A" * 4 + "." * 5)
    p = projection(track, 45)
    assert p.edges[:10] == [0, 0, 0, 0, 0, 0, 1, 2, 3, 4]
    assert p.z_at(2) == 0 and p.z_at(9) == 4 and p.z_at(6.5) == pytest.approx(2.0)
    flat, high = p.squares[2].center, p.squares[10].center
    assert p(high)[1] - p(high, 0)[1] == pytest.approx(4 * ISO_LIFT)  # soulevé de 4 cases de dénivelé
    assert p.z(flat) == 0


def test_the_altitude_of_a_square_ignores_the_road_after_the_finish():
    # La Haut Montagne : la route après l'arrivée (altitude 14) passe au-dessus de l'épingle des cases 32 à 35
    track = official(2)
    p = projection(track, 150)
    for s in range(31, 36):
        assert all(p.z(q, s) == 0 for q in p.squares[s].outline)
        assert all(p.z(q) == 0 for q in p.squares[s].outline)


def test_best_angle_keeps_an_isometric_look_and_fills_the_frame():
    for i in range(len(official_stages())):
        angle = best_angle(official(i))
        assert angle % 90 in (30, 45, 60)
    track = official(2)
    fit = lambda a: map_transform(Game(track, num_teams=2, seed=0), proj=projection(track, a))[0]  # noqa: E731
    assert fit(best_angle(track)) >= fit(45)


def test_3d_map_has_walls_pawns_and_matches_the_browser_geometry():
    track = official(2)
    g = Game(track, num_teams=3, seed=1)
    proj = projection(track, best_angle(track))
    flat = map_primitives(g)
    iso = map_primitives(g, g.riders[0], proj=proj)
    assert len(iso) > len(flat)  # les côtés du plateau
    wheels = [p for p in iso if p[0] == "oval" and p[5] == "" and p[6] == CYCLIST_WHEEL]
    assert len(wheels) == 2 * len(g.riders)  # chaque coureur : un petit cycliste, deux roues
    labels = {p[3] for p in iso if p[0] == "text"}
    assert {r.name for r in g.riders} <= labels  # son nom au-dessus de la tête
    # la géométrie envoyée au navigateur place les coureurs comme le serveur
    squares, *_rest, tr = _map_frame(g, False, None, 1000, 430, None, proj)
    road = road_geometry(g, proj=proj)["road"]
    for progress, lane in ((0, 0), (12, 1), (40.5, 0.5), (70, 1)):
        expected = tr.at(point_on_road(squares, progress, lane), proj.z_at(progress))
        last = len(road) - 1
        i = min(int(progress), last - 1)
        f = progress - i

        def at(row):
            rx, ry, lx, ly, lanes = row
            k = (lane + 0.5) / lanes
            return rx + (lx - rx) * k, ry + (ly - ry) * k

        (x0, y0), (x1, y1) = at(road[i]), at(road[i + 1])
        assert x0 + (x1 - x0) * f == pytest.approx(expected[0], abs=1e-6)
        assert y0 + (y1 - y0) * f == pytest.approx(expected[1], abs=1e-6)
