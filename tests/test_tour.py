import pytest

from flamme_rouge.ai import ai_chooser
from flamme_rouge.cards import Card, exhaustion_card
from flamme_rouge.controller import FINISHED, TurnController
from flamme_rouge.game import Game
from flamme_rouge.official import official_stages
from flamme_rouge.stage import (
    MAJOR_VALUES,
    MOUNTAIN,
    SPRINT,
    TIMING_FLAT,
    TIMING_MOUNTAIN,
    TokenStack,
    finish_seconds,
    format_time,
    place_tokens,
)
from flamme_rouge.tiles import plan_to_track
from flamme_rouge.tour import GREEN, POLKA, YELLOW, Tour, TourStage
from flamme_rouge.track import Track


def official(i):
    return plan_to_track(official_stages()[i].tiles)


def place(game, *spots):
    for rider, (pos, lane) in zip(game.riders, spots):
        rider.position, rider.lane = pos, lane


# ------------------------------------------------------------------ jetons et chrono


def test_tokens_follow_the_stage_creation_rules():
    flat = Track("." * 40)
    assert [(t.square, t.kind, t.major) for t in place_tokens(flat)] == [(40, SPRINT, True), (20, SPRINT, False)]
    climb = Track("." * 10 + "A" * 6 + "." * 10 + "A" * 2 + "." * 10)
    assert [(t.square, t.kind, t.major) for t in place_tokens(climb)] == [(16, MOUNTAIN, True), (38, SPRINT, False)]
    summit = Track("." * 10 + "A" * 3 + "." * 10 + "A" * 7)  # longue montée qui finit sur la ligne
    assert [(t.square, t.kind, t.major) for t in place_tokens(summit)] == [(30, MOUNTAIN, True), (13, MOUNTAIN, False)]
    assert place_tokens(flat)[0].values == list(MAJOR_VALUES)


def test_timing_tile_and_time_format():
    assert finish_seconds(Track("." * 10), 0) == TIMING_FLAT[0] and finish_seconds(Track("." * 10), 99) == 0
    assert finish_seconds(Track("." * 8 + "AA"), 1) == TIMING_MOUNTAIN[1]
    assert format_time(80) == "1:20" and format_time(0) == "0:00"


# ------------------------------------------------------------------ une étape de Tour


def test_a_tour_stage_goes_on_until_everyone_has_finished():
    g = Game(official(0), num_teams=3, seed=4, tour=True, tokens=place_tokens(official(0)))
    while not g.finished:
        g.play_turn(ai_chooser)
    assert len(g.arrived) == 6 and not g.riders and g.winner is g.arrived[0]
    assert set(g.stage_time) == set(g.all_riders)
    assert g.stage_time[g.arrived[0]] == min(g.stage_time.values())


def test_finish_times_groups_and_minutes():
    g = Game(Track("." * 20), num_teams=2, seed=0, tour=True)
    # deux coureurs passent la ligne ensemble (groupe), un autre seul plus loin derrière, un pas encore arrivé
    place(g, (24, 0), (23, 0), (21, 0), (10, 0))
    g.turn_start = {r: r.position for r in g.riders}
    g.check_finish()
    a, b, c, d = g.all_riders
    assert g.arrived == [a, b, c]
    assert g.stage_time[a] == g.stage_time[b] == finish_seconds(g.track, 4)  # le groupe prend le temps de sa tête
    assert g.stage_time[c] == finish_seconds(g.track, 1)
    assert g.riders == [d] and g.minutes[d] == 1  # pas arrivé : un jeton d'une minute
    d.position = 22
    g.check_finish()
    assert g.finished and g.stage_time[d] == 60 + finish_seconds(g.track, 2)


def test_finished_riders_get_no_fatigue():
    g = Game(Track("." * 20), num_teams=2, seed=0, tour=True)
    place(g, (25, 0), (12, 0), (5, 0), (5, 1))
    exhausted = g.apply_exhaustion()
    assert g.riders[0] not in exhausted and g.riders[1] in exhausted


def test_tokens_go_to_the_most_advanced_first():
    g = Game(Track("." * 30), num_teams=2, seed=0, tour=True, tokens=[TokenStack(10, SPRINT, [5, 3, 1], True)])
    place(g, (8, 0), (9, 0), (4, 0), (2, 0))
    g.turn_start = {r: r.position for r in g.riders}
    place(g, (12, 0), (14, 0), (10, 0), (6, 0))
    g.check_finish()
    a, b, c, d = g.all_riders
    assert g.points[SPRINT] == {b: 5, a: 3, c: 1} and d not in g.points[SPRINT]
    assert g.tokens[0].values == []


def test_controller_logs_arrivals_and_tokens():
    g = Game(official(0), num_teams=2, seed=1, tour=True, tokens=place_tokens(official(0)))
    ctl = TurnController(g, ai_teams={0, 1})
    while ctl.phase != FINISHED:
        ctl.advance()
    texts = [line.text for line in ctl.log]
    assert "ÉTAPE TERMINÉE" in texts and any(t.startswith("1. ") for t in texts)
    assert any("prend le jeton" in t for t in texts)


# ------------------------------------------------------------------ le Tour


def make_tour(n=3, teams=3, **kw):
    stages = [TourStage(s.name, plan_to_track(s.tiles)) for s in official_stages()[:n]]
    return Tour(stages, teams, seed=1, **kw)


def run_stage(tour):
    g = tour.start_stage()
    while not g.finished:
        g.play_turn(ai_chooser)
    return g, tour.finish_stage(g)


def test_a_tour_needs_three_stages():
    with pytest.raises(ValueError):
        make_tour(2)


def test_half_of_the_fatigue_is_returned_between_stages():
    deck = [Card(5)] + [exhaustion_card()] * 5
    assert Tour._return_fatigue(deck) == 2 and sum(c.exhaustion for c in deck) == 3
    tour = make_tour()
    g, result = run_stage(tour)
    for rider in g.all_riders:
        k = g.rider_key(rider)
        energy = sum(not c.exhaustion for c in tour.decks[k])
        assert energy == 15  # toutes les cartes Énergie jouées reviennent
        fatigue_before = sum(c.exhaustion for c in rider.draw_pile + rider.recycle + rider.hand)
        assert sum(c.exhaustion for c in tour.decks[k]) == fatigue_before - fatigue_before // 2


def test_decks_and_times_carry_over_and_the_tour_ends_with_bonus():
    tour = make_tour(3, rest_after={2})
    results = [run_stage(tour)[1] for _ in range(3)]
    assert tour.finished and len(tour.results) == 3
    assert results[1].rest_day and not results[0].rest_day and not results[2].rest_day
    assert sum(tour.rest_points) == 3  # un PT pour chacun des 3 leaders (général, sprint, montagne)
    assert sum(tour.podium_points) == 3 * 6  # 3 + 2 + 1 par étape
    k = tour.gc_order()[0]
    assert tour.total_time[k] == sum(r.times[k] for r in results)
    bonus = tour.bonus_points()
    assert sum(b["général"] for b in bonus.values()) == 6 and sum(b["équipe"] for b in bonus.values()) == 1
    ranking = tour.final_ranking()
    points = [tour.tour_points(t) for t in ranking]
    assert points == sorted(points, reverse=True)


def test_jerseys_one_per_rider_with_priority():
    tour = make_tour()
    tour.total_time = {(0, 0): 10, (0, 1): 20, (1, 0): 30, (1, 1): 40}
    tour.sprint = {(0, 0): 9, (1, 0): 5}
    tour.mountain = {(0, 0): 7, (1, 1): 2}
    tour.award_jerseys()
    assert tour.jerseys == {YELLOW: (0, 0), GREEN: (1, 0), POLKA: (1, 1)}  # (0, 0) mène tout mais garde le jaune


def test_bonus_table_depends_on_length():
    assert make_tour(3).bonus_table()[0] == (3, 2, 1)
    stages = [TourStage("x", Track("." * 30))] * 9
    assert Tour(stages, 3).bonus_table()[0] == (4, 3, 2, 1)
    assert Tour(stages, 2).bonus_table()[0] == (3, 2, 1)  # à 2 joueurs : toujours la colonne courte


def test_team_order_after_the_first_stage():
    tour = make_tour()
    assert sorted(tour.team_order()) == [0, 1, 2]
    run_stage(tour)
    order = tour.team_order()
    points = [tour.tour_points(t, with_bonus=False) for t in order]
    assert points == sorted(points)  # le moins de Points de Tour se place d'abord


def test_jersey_markers_show_the_next_token_on_the_map_and_profile():
    from flamme_rouge.boardview import (
        JERSEY_GREEN, JERSEY_POLKA, jersey_primitives, map_primitives, profile_primitives)

    track = official(3)  # La Classicissima : un col (Montagne) et l'arrivée (Sprint)
    g = Game(track, num_teams=2, seed=0, tour=True, tokens=place_tokens(track))
    kinds = {s.kind for s in g.tokens}
    assert kinds == {SPRINT, MOUNTAIN}
    fills = lambda prims: [p[2] for p in prims if p[0] == "poly"]
    texts = lambda prims: [p[3] for p in prims if p[0] == "text"]
    prims = map_primitives(g)
    assert JERSEY_GREEN in fills(prims) and JERSEY_POLKA in fills(prims)
    first = g.tokens[0]
    assert str(first.values[0]) in texts(prims) and "puis " + " · ".join(map(str, first.values[1:])) in texts(prims)
    first.values.clear()  # pile vide : maillot grisé
    assert "plus de jeton" in texts(map_primitives(g))
    profile = profile_primitives(track, 1000, 100, riders=g.riders, tokens=g.tokens)
    assert JERSEY_GREEN in fills(profile)
    assert fills(jersey_primitives(50, 50, 20, SPRINT, 5))[0] == JERSEY_GREEN
    assert "5" in texts(jersey_primitives(50, 50, 20, MOUNTAIN, 5))
    assert Game(track, num_teams=2, seed=0).tokens == []  # pas de jetons hors Grand Tour


def test_token_wins_and_arrivals_explain_themselves():
    g = Game(Track("." * 20), num_teams=2, seed=0, tour=True, tokens=[TokenStack(10, SPRINT, [5, 3, 1], True)])
    place(g, (8, 0), (9, 0), (4, 0), (2, 0))
    g.turn_start = {r: r.position for r in g.riders}
    place(g, (12, 0), (14, 0), (10, 0), (6, 0))
    g.check_finish()
    a, b, c, _d = g.all_riders
    assert [(w.rider, w.value, w.rank, w.takers) for w in g.token_log] == [(b, 5, 1, 3), (a, 3, 2, 3), (c, 1, 3, 3)]
    assert "case 10" in g.token_log[0].reason() and "+5 point(s) de Sprint" in g.token_log[0].reason()
    assert "le plus avancé des 3" in g.token_log[0].reason()
    g.turn_start = {r: r.position for r in g.riders}
    place(g, (23, 0), (22, 0), (21, 0), (10, 0))  # a, b et c passent la ligne ensemble
    g.check_finish()
    arrival = g.arrival_log[c]
    assert arrival.leader is a and arrival.seconds == finish_seconds(g.track, 3) and arrival.minutes == 0
    assert "en tête de son groupe" in arrival.reason() and format_time(arrival.time) in arrival.reason()
    assert g.minutes[_d] == 1  # pas encore arrivé : un jeton Temps


def test_timing_tile_and_time_tokens_on_the_map():
    from flamme_rouge.boardview import TIME_TOKEN_FILL, map_primitives
    from flamme_rouge.stage import timing_table

    track = official(0)
    g = Game(track, num_teams=2, seed=0, tour=True)
    texts = [p[3] for p in map_primitives(g) if p[0] == "text"]
    assert all(f"+{s}" in texts for s in timing_table(track))
    g.minutes[g.riders[0]] = 2
    prims = map_primitives(g)
    assert any(p[0] == "oval" and p[5] == TIME_TOKEN_FILL for p in prims) and "2'" in [p[3] for p in prims if p[0] == "text"]
    assert "+50" not in [p[3] for p in map_primitives(Game(track, num_teams=2, seed=0)) if p[0] == "text"]


def test_follow_camera_frames_the_head_or_the_peloton():
    from flamme_rouge.boardview import FOLLOW_HEAD, FOLLOW_MIN_SQUARES, FOLLOW_PELOTON, follow_view, follow_window

    g = Game(Track("." * 60), num_teams=3, seed=0)
    place(g, (30, 0), (29, 0), (12, 0), (11, 0), (11, 1), (10, 0))  # 2 devant, 4 derrière
    head, peloton = follow_window(g, FOLLOW_HEAD), follow_window(g, FOLLOW_PELOTON)
    assert head[0] <= 29 and head[1] >= 30 + 5 and head[1] - head[0] + 1 >= FOLLOW_MIN_SQUARES
    assert peloton[0] <= 10 and peloton[1] >= 12 and peloton[1] < 29
    assert follow_view(g, FOLLOW_HEAD)[1] > follow_view(g, FOLLOW_PELOTON)[1]  # la tête est plus loin sur la route
    g.riders.clear()
    assert follow_window(g, FOLLOW_HEAD) is None


def test_jersey_holders_wear_them_on_the_next_stage():
    from flamme_rouge.boardview import JERSEY_RING, JERSEY_YELLOW, map_primitives, profile_primitives

    tour = make_tour()
    assert tour.start_stage().jerseys == {}  # 1re étape : personne n'a encore de maillot
    tour = make_tour()
    run_stage(tour)
    g = tour.start_stage()
    worn = {g.rider_key(r): j for r, j in g.jerseys.items()}
    assert worn == {k: j for j, k in tour.jerseys.items()} and YELLOW in worn.values()
    fills = [p[2] for p in map_primitives(g) if p[0] == "poly"]
    assert JERSEY_YELLOW in fills
    profile = profile_primitives(g.track, 1000, 100, riders=g.riders, jerseys=g.jerseys)
    assert any(p[0] == "oval" and p[6] == JERSEY_RING[YELLOW] for p in profile)
