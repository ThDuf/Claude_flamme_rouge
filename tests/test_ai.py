from flamme_rouge.ai import ai_chooser, choose_card, destination
from flamme_rouge.cards import Card, exhaustion_card
from flamme_rouge.controller import CHOOSE, MOVEMENT, TurnController
from flamme_rouge.game import Game, random_chooser
from flamme_rouge.official import official_stages
from flamme_rouge.tiles import plan_to_track
from flamme_rouge.track import Track


def place(game, *spots):
    for rider, (pos, lane) in zip(game.riders, spots):
        rider.position, rider.lane = pos, lane


def test_destination_follows_the_rules():
    g = Game(Track("." * 10 + "A" * 10 + "." * 10), num_teams=2, seed=0)
    place(g, (8, 0), (0, 0), (0, 1), (1, 0))
    assert destination(g, g.riders[0], Card(9)) == 13  # montée en vue : plafond de 5
    place(g, (8, 0), (12, 0), (12, 1), (1, 0))
    assert destination(g, g.riders[0], Card(4)) == 11  # case 12 pleine : s'arrête avant


def test_ai_crosses_the_line_as_far_as_possible():
    g = Game(Track("." * 20), num_teams=2, seed=0)
    place(g, (15, 0), (2, 0), (2, 1), (3, 0))
    assert choose_card(g, g.riders[0], [Card(3), Card(6), Card(9)]) == Card(9)


def test_ai_does_not_waste_big_cards_in_a_climb():
    g = Game(Track("." * 4 + "A" * 30), num_teams=2, seed=0)
    place(g, (5, 0), (0, 0), (0, 1), (1, 0))
    assert choose_card(g, g.riders[0], [Card(9), Card(5)]) == Card(5)


def test_ai_plays_exhaustion_in_a_descent():
    g = Game(Track("." * 4 + "D" * 10 + "." * 30), num_teams=2, seed=0)
    place(g, (5, 0), (0, 0), (0, 1), (1, 0))
    assert choose_card(g, g.riders[0], [Card(5), exhaustion_card(), Card(6)]) == exhaustion_card()


def test_ai_chooser_has_the_engine_signature():
    g = Game(seed=3)
    while not g.finished:
        g.play_turn(ai_chooser)
    assert g.winner is not None


def test_controller_plays_ai_teams_by_itself():
    g = Game(plan_to_track(official_stages()[0].tiles), num_teams=3, seed=1)
    ctl = TurnController(g, ai_teams={1, 2})
    assert ctl.phase == CHOOSE and ctl.current_rider.team == 0  # seule l'équipe 1 choisit à l'écran
    while ctl.phase == CHOOSE:
        assert ctl.current_rider.team == 0
        ctl.choose(ctl.hand[0])
    assert ctl.phase == MOVEMENT and len(ctl.played) == 6
    assert sum("(IA) a posé une carte" in line.text for line in ctl.log) == 4

    all_ai = TurnController(Game(seed=2), ai_teams={0, 1})
    assert all_ai.phase == MOVEMENT  # personne ne choisit : on passe directement au mouvement


def test_ai_beats_random_players():
    track = plan_to_track(official_stages()[1].tiles)
    wins = 0
    for seed in range(40):
        g = Game(track, num_teams=2, seed=seed)
        chooser = lambda game, r, h: ai_chooser(game, r, h) if r.team == 0 else random_chooser(game, r, h)
        while not g.finished:
            g.play_turn(chooser)
        wins += g.winner.team == 0
    assert wins >= 28  # au moins 70 % de victoires (environ 95 % mesurés)
