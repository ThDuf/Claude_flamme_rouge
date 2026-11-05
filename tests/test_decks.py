from collections import Counter

import pytest

from flamme_rouge import ROULEUR, Game, Track
from flamme_rouge.cards import starting_deck
from flamme_rouge.controller import CHOOSE, TurnController
from flamme_rouge.decks import all_decks_text, deck_rows, deck_text


def energy_cards(rider):
    """Toutes les cartes Énergie du coureur, où qu'elles soient."""
    cards = rider.draw_pile + rider.hand + rider.recycle + rider.used
    return [c for c in cards if not c.exhaustion]


def test_fresh_deck_is_all_in_the_draw_pile():
    g = Game(num_teams=2, seed=1)
    for r in g.riders:
        rows = deck_rows(r)
        assert sum(rows["pioche"].values()) == 15
        assert not rows["recyclage"] and not rows["jouées"]
        assert all(n == 3 for n in rows["pioche"].values())


@pytest.mark.parametrize("seed", range(6))
def test_energy_cards_are_never_lost_or_duplicated(seed):
    # Tout au long d'une partie, chaque coureur a toujours exactement ses 15 cartes d'origine.
    g = Game(num_teams=3, seed=seed)
    expected = {r: Counter(starting_deck(r.kind)) for r in g.riders}
    ctl = TurnController(g)
    for _ in range(300):
        if g.finished:
            break
        while ctl.phase == CHOOSE:
            ctl.choose(ctl.hand[0])
            for r in g.riders:  # même en plein milieu du choix des cartes
                assert Counter(energy_cards(r)) == expected[r]
        for _ in range(3):
            ctl.advance()
        for r in g.riders:
            assert Counter(energy_cards(r)) == expected[r]


def test_played_card_goes_to_used_and_the_other_three_to_recycle():
    g = Game(Track("." * 30), num_teams=2, seed=3)
    g.energy_phase(lambda game, r, hand: hand[0])
    for r in g.riders:
        assert len(r.used) == 1 and len(r.recycle) == 3 and len(r.draw_pile) == 11
        assert r.hand == []


def test_hand_is_counted_in_the_draw_pile_while_choosing():
    g = Game(num_teams=2, seed=1)
    ctl = TurnController(g)
    rider = ctl.current_rider
    assert len(rider.hand) == 4 and len(rider.draw_pile) == 11
    assert sum(deck_rows(rider)["pioche"].values()) == 15  # la main n'est pas révélée
    assert "main" in deck_text(rider)


def test_exhaustion_cards_get_their_own_column():
    g = Game(num_teams=2, seed=1)
    r = g.riders[0]
    for other in g.riders[1:]:
        other.position = 10  # le coureur 0 reste seul à l'arrière, avec des cases vides devant lui
    g.apply_exhaustion()
    rows = deck_rows(r)
    assert rows["recyclage"]["F"] == 1
    assert sum(rows["pioche"].values()) == 15


def test_text_lists_every_value_of_the_kind():
    g = Game(num_teams=2, seed=1)
    rouleur = next(r for r in g.riders if r.kind == ROULEUR)
    text = deck_text(rouleur)
    header = text.splitlines()[1].split()
    assert header == ["3", "4", "5", "6", "7", "F", "total"]
    assert text.splitlines()[2].split()[:7] == ["pioche", "3", "3", "3", "3", "3", "·"]


def test_all_decks_text_has_one_block_per_rider():
    g = Game(num_teams=4, seed=1)
    text = all_decks_text(g)
    for r in g.riders:
        assert r.name in text
    assert text.count("pioche") == 2 * len(g.riders)  # une fois dans l'en-tête, une fois dans le tableau
