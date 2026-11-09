import pytest

from flamme_rouge import ROULEUR, SPRINTEUR, Card, Game, Track
from flamme_rouge.cards import exhaustion_card, starting_deck


def key(rider):
    return f"{rider.team}{'r' if rider.kind == ROULEUR else 's'}"


def make(layout, positions, teams=2):
    """Crée une partie où les coureurs listés sont placés ('0r' = rouleur de l'équipe 0).
    Les autres sont envoyés très loin derrière pour ne pas gêner."""
    g = Game(Track(layout), num_teams=teams, seed=1)
    far = -100
    for r in g.riders:
        if key(r) in positions:
            r.position = positions[key(r)]
        else:
            r.position = far
            far -= 10
    count = {}
    for r in g.riders:
        r.lane = count.get(r.position, 0)
        count[r.position] = r.lane + 1
    return g


def rider(g, k):
    return next(r for r in g.riders if key(r) == k)


def move(g, values):
    played = {r: Card(values.get(key(r), 0)) for r in g.riders}
    g.movement_phase(played)


# ------------------------------------------------------------------ paquets


def test_decks():
    rouleur = sorted(c.value for c in starting_deck(ROULEUR))
    sprinteur = sorted(c.value for c in starting_deck(SPRINTEUR))
    assert rouleur == [3] * 3 + [4] * 3 + [5] * 3 + [6] * 3 + [7] * 3
    assert sprinteur == [2] * 3 + [3] * 3 + [4] * 3 + [5] * 3 + [9] * 3


def test_draw_reshuffles_recycle_when_pile_runs_out():
    g = make("." * 10, {})
    r = rider(g, "0r")
    r.draw_pile = [Card(3), Card(4)]
    r.recycle = [Card(5), Card(6), Card(7)]
    hand = r.draw_hand(4, g.rng)
    assert len(hand) == 4
    assert len(r.draw_pile) == 1 and r.recycle == []


def test_draw_takes_what_it_can():
    g = make("." * 10, {})
    r = rider(g, "0r")
    r.draw_pile, r.recycle = [Card(3)], []
    assert r.draw_hand(4, g.rng) == [Card(3)]


# ----------------------------------------------------------- phase d'énergie


def test_energy_phase_plays_one_and_recycles_three():
    g = Game(Track("." * 30), num_teams=2, seed=3)
    played = g.energy_phase(lambda game, r, hand: hand[0])
    for r in g.riders:
        assert not played[r].exhaustion
        assert len(r.recycle) == 3 and len(r.draw_pile) == 11
        assert len(r.draw_pile) + len(r.recycle) + 1 == 15


def test_energy_phase_without_cards_plays_exhaustion_card():
    g = Game(Track("." * 30), num_teams=2, seed=3)
    r = g.riders[0]
    r.draw_pile, r.recycle = [], []
    played = g.energy_phase(lambda game, rr, hand: hand[0])
    assert played[r] == exhaustion_card()


def test_chooser_must_pick_from_hand():
    g = Game(Track("." * 30), num_teams=2, seed=3)
    with pytest.raises(ValueError):
        g.energy_phase(lambda game, r, hand: Card(99))


# ----------------------------------------------------------------- mouvement


def test_simple_move():
    g = make("." * 20, {"0r": 0})
    move(g, {"0r": 5})
    assert rider(g, "0r").position == 5


def test_cannot_end_on_full_square():
    g = make("." * 20, {"0r": 0, "1r": 6, "1s": 6})
    move(g, {"0r": 6})
    assert rider(g, "0r").position == 5


def test_can_pass_through_full_square():
    g = make("." * 20, {"0r": 0, "1r": 3, "1s": 3})
    move(g, {"0r": 7})
    assert rider(g, "0r").position == 7


def test_riders_move_front_to_back():
    # Le coureur de devant libère la case visée par celui de derrière.
    g = make("." * 20, {"0r": 0, "1r": 4, "1s": 4})
    move(g, {"1r": 3, "1s": 3, "0r": 4})
    assert rider(g, "0r").position == 4


def test_ascent_caps_movement_when_passing_through():
    g = make("...AA........", {"0r": 0})
    move(g, {"0r": 7})
    assert rider(g, "0r").position == 5


def test_ascent_caps_movement_when_starting_on_it():
    g = make("AA.........", {"0r": 0})
    move(g, {"0r": 7})
    assert rider(g, "0r").position == 5


def test_a_big_card_still_reaches_the_foot_of_a_far_climb():
    # montée à la 8e case : un 9 avance jusqu'à la case juste avant la montée (7), pas seulement de 5
    g = make("." * 8 + "AAAA" + "." * 10, {"0r": 0})
    move(g, {"0r": 9})
    assert rider(g, "0r").position == 7
    assert g._effective_value(0, 9) == 7 and g._effective_value(0, 7) == 7  # le 7 n'entre pas dans la montée
    assert g._effective_value(2, 9) == 5  # montée à la 6e case : on ne peut pas aller plus loin que 5
    assert g._effective_value(8, 9) == 5  # départ en montée : 5 au plus


def test_ascent_out_of_reach_does_not_cap():
    g = make("....A......", {"0r": 0})
    move(g, {"0r": 3})
    assert rider(g, "0r").position == 3


def test_descent_gives_minimum_five():
    g = make("D.........", {"0r": 0})
    move(g, {"0r": 2})
    assert rider(g, "0r").position == 5


def test_passing_a_descent_does_not_give_bonus():
    g = make(".D........", {"0r": 0})
    move(g, {"0r": 2})
    assert rider(g, "0r").position == 2


def test_descent_replaces_exhaustion_card_value():
    g = make("D.........", {"0r": 0})
    played = {r: Card(0) for r in g.riders}
    played[rider(g, "0r")] = exhaustion_card()
    g.movement_phase(played)
    assert rider(g, "0r").position == 5


# ----------------------------------------------------------------- aspiration


def test_slipstream_with_one_empty_square():
    g = make("." * 20, {"0r": 0, "1r": 2})
    g.apply_slipstream()
    assert rider(g, "0r").position == 1


def test_no_slipstream_with_two_empty_squares():
    g = make("." * 20, {"0r": 0, "1r": 3})
    g.apply_slipstream()
    assert rider(g, "0r").position == 0


def test_no_slipstream_when_already_adjacent():
    g = make("." * 20, {"0r": 0, "1r": 1})
    g.apply_slipstream()
    assert rider(g, "0r").position == 0


def test_slipstream_chains():
    # 0 / 2 / 4 : le plus en arrière aspire deux fois, celui du milieu une fois.
    g = make("." * 20, {"0r": 0, "1r": 2, "0s": 4})
    g.apply_slipstream()
    assert (rider(g, "0r").position, rider(g, "1r").position, rider(g, "0s").position) == (2, 3, 4)


def test_whole_pack_slipstreams_together():
    g = make("." * 20, {"0r": 0, "0s": 1, "1r": 3})
    g.apply_slipstream()
    assert (rider(g, "0r").position, rider(g, "0s").position) == (1, 2)


def test_rider_on_ascent_cannot_give_slipstream():
    g = make("...A......", {"0r": 1, "1r": 3})
    g.apply_slipstream()
    assert rider(g, "0r").position == 1


def test_rider_on_ascent_cannot_receive_slipstream():
    g = make(".A........", {"0r": 1, "1r": 3})
    g.apply_slipstream()
    assert rider(g, "0r").position == 1


# --------------------------------------------------------------------- fatigue


def test_exhaustion_for_rider_with_empty_square_ahead():
    g = make("." * 20, {"0r": 5, "1r": 6})
    g.apply_exhaustion()
    assert rider(g, "1r").recycle == [exhaustion_card()]
    assert rider(g, "0r").recycle == []  # quelqu'un devant lui, même si le couloir est libre


def test_exhaustion_when_gap_of_two():
    g = make("." * 20, {"0r": 0, "1r": 3})
    g.apply_exhaustion()
    assert rider(g, "0r").recycle == [exhaustion_card()]


# ----------------------------------------------------------------- arrivée


def test_winner_is_furthest_past_the_line():
    g = make("." * 5, {"0r": 4, "1r": 3})
    move(g, {"0r": 3, "1r": 5})
    g.end_phase()
    assert g.finished
    assert key(g.winner) == "1r"


def test_not_finished_before_the_line():
    g = make("." * 10, {"0r": 0})
    move(g, {"0r": 5})
    g.end_phase()
    assert not g.finished and g.winner is None


# ---------------------------------------------------------- parties simulées


@pytest.mark.parametrize("teams", [2, 3, 4])
@pytest.mark.parametrize("seed", range(10))
def test_random_games_finish_and_keep_invariants(teams, seed):
    g = Game(num_teams=teams, seed=seed)
    for _ in range(300):
        if g.finished:
            break
        before = {r: r.position for r in g.riders}
        g.play_turn()
        spots = [(r.position, r.lane) for r in g.riders]
        assert len(set(spots)) == len(spots), "deux coureurs sur le même couloir"
        assert all(len(g.riders_at(r.position)) <= 2 for r in g.riders)
        assert all(r.position >= before[r] for r in g.riders), "un coureur a reculé"
    assert g.finished and g.winner is not None
