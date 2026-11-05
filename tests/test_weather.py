import random

from flamme_rouge.cards import Card
from flamme_rouge.controller import TurnController
from flamme_rouge.extensions import METEO
from flamme_rouge.game import Game
from flamme_rouge.official import official_stages
from flamme_rouge.tiles import plan_to_track
from flamme_rouge.track import Track
from flamme_rouge.weather import (
    CROSSWIND,
    EFFECTS,
    HEADWIND,
    RAIN,
    SUNNY,
    TAILWIND,
    Weather,
    WeatherZone,
    draw_weather,
    straight_segments,
)


def card(value):
    return Card(value)


def place(game, *spots):
    """Place les coureurs : (case, file) dans l'ordre de game.riders ; les autres loin derrière."""
    for rider, (pos, lane) in zip(game.riders, spots):
        rider.position, rider.lane = pos, lane


def test_official_stage_has_seven_straights_for_the_tokens():
    track = plan_to_track(official_stages()[0].tiles)
    segments = straight_segments(track)
    assert len(segments) == 7 and all(b - a == 6 for a, b in segments)
    assert all(a >= track.start + 1 and b <= len(track) - 1 for a, b in segments)  # ni départ ni arrivée


def test_draw_weather_uses_13_tokens_one_per_straight():
    track = plan_to_track(official_stages()[0].tiles)
    seen = set()
    for seed in range(200):
        zones = draw_weather(track, random.Random(seed))
        assert len(zones) == 7  # un jeton par ligne droite, « beau temps » compris
        effects = [z.effect for z in zones if z.effect != SUNNY]
        assert len(effects) == len(set(effects)) <= 4  # chaque effet au plus une fois
        assert all((z.start, z.end) in straight_segments(track) for z in zones)
        seen.update(effects)
    assert seen == set(EFFECTS)


def test_weather_only_with_the_extension():
    track = plan_to_track(official_stages()[0].tiles)
    assert not Game(track, seed=1).weather
    assert any(Game(track, seed=s, extensions=[METEO]).weather for s in range(10))


def test_tailwind_and_headwind_change_the_hand_size():
    g = Game(Track("." * 30), num_teams=2, seed=0,
             weather=[WeatherZone(0, 2, TAILWIND), WeatherZone(2, 4, HEADWIND)])
    place(g, (0, 0), (2, 0), (5, 0), (5, 1))
    assert [g.hand_size(r) for r in g.riders] == [5, 3, 4, 4]
    assert [len(g.draw_hand_for(r)) for r in g.riders] == [5, 3, 4, 4]


def test_crosswind_cancels_slipstream_given_and_received():
    for zone in (WeatherZone(10, 12, CROSSWIND), WeatherZone(7, 9, CROSSWIND)):
        g = Game(Track("." * 30), num_teams=2, seed=0, weather=[zone])
        place(g, (10, 0), (8, 0), (3, 0), (3, 1))  # 8 -> 10 : 1 case vide entre les deux
        g.apply_slipstream()
        assert g.riders[1].position == 8  # devant ou derrière dans le vent : pas d'aspiration
    g = Game(Track("." * 30), num_teams=2, seed=0)
    place(g, (10, 0), (8, 0), (3, 0), (3, 1))
    g.apply_slipstream()
    assert g.riders[1].position == 9  # sans vent : aspiré


def test_rain_crash_when_blocked():
    g = Game(Track("." * 30), num_teams=2, seed=0, weather=[WeatherZone(6, 12, RAIN)])
    place(g, (12, 0), (12, 1), (7, 0), (1, 0))
    g.crashed_this_turn = []
    g._move(g.riders[2], card(5))  # vise 12, pleine : s'arrête en 11, sous la pluie -> chute
    assert g.riders[2].position == 11 and g.riders[2].crashed
    assert g.crashed_this_turn == [g.riders[2]]


def test_rain_without_blocking_is_harmless():
    g = Game(Track("." * 30), num_teams=2, seed=0, weather=[WeatherZone(6, 12, RAIN)])
    place(g, (20, 0), (20, 1), (5, 0), (1, 0))
    g._move(g.riders[2], card(5))  # 5 -> 10, case libre : pas de chute
    assert g.riders[2].position == 10 and not g.riders[2].crashed


def test_blocked_but_not_in_rain_does_not_crash():
    g = Game(Track("." * 30), num_teams=2, seed=0, weather=[WeatherZone(20, 26, RAIN)])
    place(g, (12, 0), (12, 1), (7, 0), (1, 0))
    g._move(g.riders[2], card(5))
    assert g.riders[2].position == 11 and not g.riders[2].crashed


def test_square_with_two_crashed_riders_is_blocked_and_chain_crash():
    g = Game(Track("." * 30), num_teams=2, seed=0, weather=[WeatherZone(6, 12, RAIN)])
    place(g, (10, 0), (10, 1), (5, 0), (1, 0))
    g.riders[0].crashed = g.riders[1].crashed = True
    assert g.is_blocked(10)
    g._move(g.riders[2], card(9))  # voudrait aller en 14 : la case 10 barre la route
    assert g.riders[2].position == 9 and g.riders[2].crashed  # 9 est sous la pluie : chute en chaîne
    # une seule file à terre : la case se traverse
    g2 = Game(Track("." * 30), num_teams=2, seed=0, weather=[WeatherZone(6, 12, RAIN)])
    place(g2, (10, 0), (3, 0), (5, 0), (1, 0))
    g2.riders[0].crashed = True
    g2._move(g2.riders[2], card(9))
    assert g2.riders[2].position == 14 and not g2.riders[2].crashed


def test_crashed_rider_gives_and_gets_no_slipstream():
    g = Game(Track("." * 30), num_teams=2, seed=0)
    place(g, (10, 0), (8, 0), (3, 0), (3, 1))
    g.riders[0].crashed = True
    g.apply_slipstream()
    assert g.riders[1].position == 8


def test_standing_up_costs_two_after_descent_and_before_climb_cap():
    g = Game(Track("..DDDD" + "." * 10 + "A" * 10 + "." * 10), num_teams=2, seed=0)
    assert g._effective_value(2, 2, crashed=True) == 3  # descente : 2 -> 5, puis -2
    assert g._effective_value(0, 2, crashed=True) == 0  # une carte 2 : se relève sans avancer
    assert g._effective_value(14, 7, crashed=True) == 5  # montée : 7 - 2 = 5, plafond 5
    assert g._effective_value(14, 6, crashed=True) == 4
    place(g, (8, 0), (20, 0), (30, 0), (30, 1))
    g.riders[0].crashed = True
    g._move(g.riders[0], card(4))
    assert g.riders[0].position == 10 and not g.riders[0].crashed


def test_controller_logs_wind_and_crash():
    g = Game(Track("." * 40), num_teams=2, seed=0, weather=[WeatherZone(0, 4, TAILWIND)])
    ctl = TurnController(g)
    texts = [line.text for line in ctl.log]
    assert any("vent arrière, pioche 5 cartes" in t for t in texts)
    assert len(ctl.hand) in (4, 5)


def test_a_whole_meteo_race_finishes():
    track = plan_to_track(official_stages()[1].tiles)
    for seed in range(20):
        g = Game(track, num_teams=4, seed=seed, extensions=[METEO])
        turns = 0
        while not g.finished and turns < 200:
            g.play_turn()
            turns += 1
        assert g.finished


def test_weather_lookup():
    w = Weather([WeatherZone(3, 5, RAIN)])
    assert w.at(3) == RAIN and w.at(5) is None and w.is_rain(4) and not w.blocks_slipstream(4)
    assert bool(w) and not Weather()


def test_weather_is_drawn_on_the_map_and_the_profile():
    from flamme_rouge import palette as pal
    from flamme_rouge.boardview import map_primitives, profile_primitives

    zones = [WeatherZone(6, 12, RAIN), WeatherZone(18, 24, TAILWIND)]
    g = Game(plan_to_track(official_stages()[0].tiles), num_teams=2, seed=0, weather=zones)
    g.riders[0].crashed = True
    prims = map_primitives(g)
    panels = [p for p in prims if p[0] == "poly" and p[2] in pal.WEATHER_FILL.values()]
    assert len(panels) == 12  # une bande par case des deux lignes droites
    texts = {p[3] for p in prims if p[0] == "text"}
    assert {"PLUIE", "VENT +1", "CHUTE"} <= texts
    profile = profile_primitives(g.track, 1000, 100, riders=g.riders, weather=g.weather)
    assert any("Météo : pluie, vent +1" in p[3] for p in profile if p[0] == "text")
    assert len([p for p in profile if p[0] == "rect" and p[5] in pal.WEATHER_FILL.values()]) == 2


def test_sunny_straights_have_no_effect():
    w = Weather([WeatherZone(3, 9, SUNNY), WeatherZone(9, 15, RAIN)])
    assert [z.effect for z in w.effects] == [RAIN]
    assert w.hand_size(4, 4) == 4 and not w.blocks_slipstream(4) and not w.is_rain(4)


def test_weather_animation_on_the_profile():
    from flamme_rouge.boardview import FX_RAIN, FX_SUN, FX_WIND, weather_fx_primitives

    track = plan_to_track(official_stages()[0].tiles)
    w = Weather([WeatherZone(6, 12, RAIN), WeatherZone(18, 24, TAILWIND), WeatherZone(26, 32, HEADWIND),
                 WeatherZone(42, 48, CROSSWIND), WeatherZone(54, 60, SUNNY)])
    a, b = weather_fx_primitives(track, w, 1000, 100, 0.0), weather_fx_primitives(track, w, 1000, 100, 0.4)
    colors = {p[5] for p in a if p[0] == "line"} | {p[5] for p in a if p[0] == "oval"}
    assert {FX_RAIN, FX_SUN} | set(FX_WIND.values()) <= colors
    assert a != b  # ça bouge
    for p in a + b:  # tout reste dans le cadre du profil
        if p[0] == "line":
            assert 0 <= min(p[1], p[3]) and max(p[1], p[3]) <= 1000 and 0 <= min(p[2], p[4]) and max(p[2], p[4]) <= 100
    # le vent arrière va vers l'arrivée, le vent de face vers le départ
    def head_x(prims, color):
        return [p[3] for p in prims if p[0] == "line" and p[5] == color and p[6] == 2][0]
    c = weather_fx_primitives(track, w, 1000, 100, 0.1)  # assez tôt pour qu'aucun trait ne reparte du bord
    assert head_x(c, FX_WIND[TAILWIND]) > head_x(a, FX_WIND[TAILWIND])
    assert head_x(c, FX_WIND[HEADWIND]) < head_x(a, FX_WIND[HEADWIND])
    assert weather_fx_primitives(track, Weather(), 1000, 100, 0.0) == []
