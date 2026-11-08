from flamme_rouge import Game, Track
from flamme_rouge.palette import TEAM_FILL
from flamme_rouge.boardview import (
    BOARD_W,
    MAP_H,
    full_window,
    map_primitives,
    map_window,
    track_preview_primitives,
)
from flamme_rouge.tiles import example_plan, plan_to_track


def rider_labels(prims):
    return [p for p in prims if p[0] == "text" and p[3] in {"1R", "1S", "2R", "2S", "3R", "3S", "4R", "4S"}]


def squares_drawn(prims):
    return [p for p in prims if p[0] == "poly" and p[2] != "" and p[3] == "#364152"]  # cases de route (pas le damier)


def test_full_view_shows_the_whole_track_from_start_to_finish():
    g = Game(num_teams=2, seed=1)
    first, last = full_window(g)
    assert first == 0 and last >= len(g.track)  # jusqu'à la ligne d'arrivée et un peu au-delà
    prims = map_primitives(g)
    assert len(squares_drawn(prims)) == last + 1
    assert any(p[0] == "text" and p[3] == "ARRIVÉE" for p in prims)


def test_full_view_does_not_change_while_riders_stay_on_the_race():
    g = Game(num_teams=2, seed=1)
    before = len(squares_drawn(map_primitives(g)))
    for r in g.riders:
        r.position += 20  # toujours avant l'arrivée
    assert len(squares_drawn(map_primitives(g))) == before  # pas de saut de zoom pendant la partie


def test_full_view_only_grows_when_a_rider_goes_far_past_the_line():
    g = Game(num_teams=2, seed=1)
    normal = full_window(g)
    g.riders[0].position = len(g.track) + 2  # un peu après la ligne : déjà couvert par les cases grises
    assert full_window(g) == normal
    g.riders[0].position = len(g.track) + 8  # un grand dépassement : la vue s'étend pour le garder visible
    assert full_window(g)[1] == len(g.track) + 8


def test_zoom_shows_fewer_squares_than_the_full_view():
    g = Game(num_teams=2, seed=1)
    assert len(squares_drawn(map_primitives(g, zoom=True))) < len(squares_drawn(map_primitives(g)))
    first, last = map_window(g)
    assert last - first + 1 == len(squares_drawn(map_primitives(g, zoom=True)))


def test_zoom_window_can_be_widened_to_cover_an_animation():
    g = Game(Track("." * 80), num_teams=2, seed=1)
    for r in g.riders:
        r.position = 40
    plain = map_window(g)
    widened = map_window(g, extra_positions=[20])
    assert widened[0] < plain[0]
    assert widened[0] <= 20 and widened[1] >= 40  # le départ (20) et l'arrivée (40) restent visibles


def test_animated_positions_move_the_drawn_rider():
    g = Game(Track("." * 40), num_teams=2, seed=1)
    rider = g.riders[0]

    def centre(prims):
        oval = [p for p in prims if p[0] == "oval" and p[5] == TEAM_FILL[0] and p[6] == "#ffffff"]  # ovales de l'équipe 1 (rouge)
        return [(p[1] + p[3]) / 2 for p in oval]

    start = centre(map_primitives(g, positions={rider: (3.0, 0.0)}))
    later = centre(map_primitives(g, positions={rider: (9.0, 0.0)}))
    assert start != later and max(later) > max(start)  # la piste va vers la droite : l'ovale a avancé


def test_all_riders_are_drawn_even_while_animated():
    g = Game(num_teams=4, seed=1)
    prims = map_primitives(g, positions={g.riders[0]: (2.5, 0.5)})
    assert {p[3] for p in rider_labels(prims)} == {r.name for r in g.riders}


def test_views_stay_on_the_canvas_on_every_track_and_mode():
    for track in (Track(), plan_to_track(example_plan())):
        g = Game(track, num_teams=3, seed=2)
        for zoom in (False, True):
            for p in map_primitives(g, zoom=zoom):
                if p[0] == "poly":
                    xs, ys = p[1][0::2], p[1][1::2]
                    assert -1 <= min(xs) and max(xs) <= BOARD_W + 1 and -1 <= min(ys) and max(ys) <= MAP_H + 1


def test_track_preview_for_the_menu():
    for track in (Track(), plan_to_track(example_plan())):
        prims = track_preview_primitives(track, 560, 400)
        assert len(squares_drawn(prims)) > len(track)  # la route + un peu au-delà de l'arrivée
        texts = {p[3] for p in prims if p[0] == "text"}
        assert {"DÉPART", "ARRIVÉE"} <= texts
        for p in squares_drawn(prims):
            xs, ys = p[1][0::2], p[1][1::2]
            assert -1 <= min(xs) and max(xs) <= 561 and -1 <= min(ys) and max(ys) <= 401


def test_manual_view_zooms_in_on_the_point_under_the_cursor():
    from flamme_rouge.boardview import map_transform, pan_view, zoom_view

    g = Game(num_teams=2, seed=1)
    view = map_transform(g)
    zoomed = zoom_view(view, 2.0, 700, 100)
    assert abs(zoomed[0] - 2 * view[0]) < 1e-9
    # le point du monde sous le curseur ne bouge pas
    def world(v, px, py):
        return v[1] + (px - BOARD_W / 2) / v[0], v[2] - (py - MAP_H / 2) / v[0]
    assert all(abs(a - b) < 1e-9 for a, b in zip(world(view, 700, 100), world(zoomed, 700, 100)))
    moved = pan_view(zoomed, 50, 0)  # glisser vers la droite : on voit ce qui est à gauche
    assert moved[1] < zoomed[1]
    assert zoom_view(view, 1e-6, 10, 10)[0] >= 3.0 and zoom_view(view, 1e6, 10, 10)[0] <= 140.0


def test_map_with_manual_view_draws_less_when_zoomed_in_and_keeps_all_riders():
    from flamme_rouge.boardview import map_transform, zoom_view

    g = Game(num_teams=2, seed=1)
    auto = map_primitives(g, view=map_transform(g))
    zoomed = map_primitives(g, view=zoom_view(map_transform(g), 5.0, 100, 100))
    assert len(squares_drawn(zoomed)) < len(squares_drawn(auto))
    assert {p[3] for p in rider_labels(zoomed)} == {r.name for r in g.riders}


def test_elevation_profile_follows_the_terrain_and_marks_the_finish():
    from flamme_rouge.boardview import elevation, profile_primitives

    track = Track("..AAA..DDD.")
    assert elevation(track) == [0, 0, 0, 1, 2, 3, 3, 3, 2, 1, 0, 0]
    prims = profile_primitives(track, 560, 130, marker=4.5)
    texts = {p[3] for p in prims if p[0] == "text"}
    assert "ARRIVÉE" in texts and any("3 cases de montée" in t and "3 cases de descente" in t for t in texts)
    for p in prims:
        if p[0] == "poly":
            assert -1 <= min(p[1][0::2]) and max(p[1][0::2]) <= 561 and -1 <= min(p[1][1::2]) and max(p[1][1::2]) <= 131


def test_profile_of_every_base_circuit_fits_in_its_canvas():
    from flamme_rouge.boardview import profile_primitives
    from flamme_rouge.circuits import base_circuits
    from flamme_rouge.tiles import plan_to_track

    for _name, _d, tiles in base_circuits():
        for p in profile_primitives(plan_to_track(tiles), 560, 130):
            if p[0] == "poly":
                assert -1 <= min(p[1][1::2]) and max(p[1][1::2]) <= 131


def test_cosmetic_profile_is_stable_bumpy_and_within_ten_percent():
    from flamme_rouge.boardview import cosmetic_elevation, elevation, profile_primitives

    track = Track("." * 10 + "A" * 12 + "." * 8 + "D" * 12 + "." * 10)
    first, second = cosmetic_elevation(track), cosmetic_elevation(track)
    assert first == second  # même tracé, même dessin à chaque image
    real = elevation(track)
    assert first != [float(h) for h in real]  # des accidents sont ajoutés
    # la vraie montée de 12 cases reste entre 90 % et 110 % (plus les accidents, qui font moins d'une case)
    assert 12 * 0.9 - 1 <= first[22] - first[10] <= 12 * 1.1 + 1
    assert max(abs(first[i + 1] - first[i]) for i in range(10)) < 1.0  # le plat reste presque plat
    texts = {p[3] for p in profile_primitives(track, 560, 130) if p[0] == "text"}
    assert any("12 cases de montée" in t and "12 cases de descente" in t for t in texts)  # les chiffres sont vrais


def test_climb_categories_grow_with_the_climb():
    from flamme_rouge.boardview import climb_category, climbs

    assert [climb_category(n) for n in (1, 2, 3, 4, 5, 6, 7, 9, 10, 12)] == [
        "4", "4", "3", "3", "2", "2", "1", "1", "HC", "HC"]
    track = Track("..AAA..DDD.." + "A" * 12)
    assert climbs(track) == [(2, 5, "3"), (12, 24, "HC")]


def test_profile_shows_a_red_badge_at_each_summit():
    from flamme_rouge.boardview import BADGE_FILL, profile_primitives

    prims = profile_primitives(Track("..AAAAAAA..DDD....AA"), 560, 130)
    badges = [p for p in prims if p[0] == "poly" and p[2] == BADGE_FILL]
    texts = [p for p in prims if p[0] == "text" and len(p) == 9]
    assert len(badges) == 2 and [t[3] for t in texts] == ["1", "4"]
    assert all(len(t) == 9 and t[8] != 0 for t in texts)  # texte incliné comme le badge


def test_race_groups_and_their_names():
    from flamme_rouge.boardview import group_labels, race_groups

    g = Game(Track("." * 40), num_teams=4, seed=0)
    for rider, pos in zip(g.riders, (20, 19, 10, 10, 9, 8, 8, 2)):
        rider.position = pos
    groups = race_groups(g.riders)
    assert [[r.position for r in grp] for grp in groups] == [[20, 19], [10, 10, 9, 8, 8], [2]]
    labels = group_labels(g.riders)
    assert [(name, len(m)) for name, m in labels] == [("TÊTE", 2), ("PELOTON", 5), ("LANTERNE ROUGE", 1)]
    for rider in g.riders:
        rider.position = 5
    assert [name for name, _ in group_labels(g.riders)] == ["PELOTON"]
    for rider, pos in zip(g.riders, (20, 20, 19, 18, 18, 17, 5, 4)):
        rider.position = pos
    assert [(name, len(m)) for name, m in group_labels(g.riders)] == [("TÊTE · PELOTON", 6), ("LANTERNE ROUGE", 1)]


def test_profile_during_the_race_places_riders_and_groups():
    from flamme_rouge.boardview import profile_primitives

    g = Game(Track("." * 10 + "A" * 6 + "D" * 4 + "." * 20), num_teams=2, seed=0)
    for rider, pos in zip(g.riders, (30, 12, 12, 3)):
        rider.position = pos
    prims = profile_primitives(g.track, 1000, 100, riders=g.riders)
    texts = {p[3] for p in prims if p[0] == "text"}
    assert {"TÊTE (1)", "PELOTON (2)"} <= texts and any(t.startswith("LANTERNE ROUGE") for t in texts)
    dots = [p for p in prims if p[0] == "oval"]
    assert len(dots) == len(g.riders)
    g.riders[0].position = 45  # au-delà de la ligne d'arrivée
    assert profile_primitives(g.track, 1000, 100, riders=g.riders)


def test_relief_shadows_grow_with_altitude_and_slopes_get_chevrons():
    from flamme_rouge import palette as pal
    from flamme_rouge.boardview import CHEVRON_DOWN, CHEVRON_UP, map_primitives, road_altitudes

    track = Track("." * 6 + "A" * 4 + "D" * 2 + "." * 6)
    assert road_altitudes(track, 20)[:12] == [0, 0, 0, 0, 0, 0, 0.5, 1.5, 2.5, 3.5, 3.5, 2.5]
    g = Game(track, num_teams=2, seed=0)
    prims = map_primitives(g)
    shadows = [p for p in prims if p[0] == "poly" and p[2] == pal.SHADOW]
    assert len(shadows) >= len(track)
    ups = [p for p in prims if p[0] == "path" and p[2] == CHEVRON_UP]
    downs = [p for p in prims if p[0] == "path" and p[2] == CHEVRON_DOWN]
    assert len(ups) == 4 and len(downs) == 2 * 2  # un chevron par case de montée, deux par case de descente


def test_victory_podium_animation():
    from flamme_rouge.boardview import PODIUM_COLORS, podium_primitives, race_ranking

    g = Game(seed=1)
    while not g.finished:
        g.play_turn()
    ranking = race_ranking(g)
    assert ranking[0] is g.winner
    start, end = podium_primitives(g, 1000, 430, 0.0), podium_primitives(g, 1000, 430, 4.0)
    blocks = lambda prims: {p[5]: p for p in prims if p[0] == "rect" and p[5] in PODIUM_COLORS.values()}
    assert blocks(start)[PODIUM_COLORS[1]][2] == blocks(start)[PODIUM_COLORS[1]][4]  # au début, les marches sont à plat
    gold, silver, bronze = (blocks(end)[PODIUM_COLORS[k]] for k in (1, 2, 3))
    assert gold[2] < silver[2] < bronze[2]  # à la fin : la plus haute marche pour le vainqueur
    assert silver[1] < gold[1] < bronze[1]  # 2e à gauche, 1er au milieu, 3e à droite
    texts = [p[3] for p in end if p[0] == "text"]
    assert "VICTOIRE !" in texts and ranking[0].name in texts and "VICTOIRE !" not in [p[3] for p in start if p[0] == "text"]
    names = podium_primitives(g, 1000, 430, 4.0, ["Équipe 1", "Équipe 2 · IA"])
    assert any(p[0] == "text" and "Équipe 2 · IA" in p[3] for p in names) or ranking[0].team == 0
    confetti = lambda prims: [p for p in prims if p[0] == "line" and p[6] == 3]
    assert len(confetti(start)) == 90 and confetti(start) != confetti(podium_primitives(g, 1000, 430, 0.1))
