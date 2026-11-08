import pytest

from flamme_rouge.cards import ATTACK, MUSCLE, Card, attack_card
from flamme_rouge.controller import CHOOSE, MOVEMENT, TurnController
from flamme_rouge.extensions import PELOTON
from flamme_rouge.game import TEAM_MUSCLE, TEAM_PELOTON, TEAM_PLAYER, Game
from flamme_rouge.official import official_stages
from flamme_rouge.tiles import KIND_STRAIGHT, Tile, plan_to_track
from flamme_rouge.track import COBBLES, SUPPLY, Track


def place(game, *spots):
    for rider, (pos, lane) in zip(game.riders, spots):
        rider.position, rider.lane = pos, lane


def stage():
    return plan_to_track(official_stages()[0].tiles)


# ------------------------------------------------------------------ équipes


def test_five_and_six_teams_need_the_extension():
    with pytest.raises(ValueError, match="Peloton"):
        Game(stage(), num_teams=5)
    g = Game(stage(), num_teams=6, seed=0, extensions=[PELOTON])
    assert len(g.riders) == 12
    assert all(r.position < g.track.start for r in g.riders)  # tout le monde sur la grille
    assert max(g.track.lanes(s) for s in range(g.track.start)) == 3  # grille élargie (choix documenté)


def test_ghost_teams_need_the_extension_and_only_one_peloton():
    with pytest.raises(ValueError):
        Game(stage(), num_teams=2, team_types=[TEAM_PLAYER, TEAM_MUSCLE])
    with pytest.raises(ValueError):
        Game(stage(), num_teams=3, extensions=[PELOTON], team_types=[TEAM_PELOTON, TEAM_PELOTON, TEAM_PLAYER])


def test_ghost_teams_start_in_front():
    g = Game(stage(), num_teams=3, seed=0, extensions=[PELOTON], team_types=[TEAM_PLAYER, TEAM_MUSCLE, TEAM_PELOTON])
    grid = g.track.start
    peloton = [r for r in g.riders if r.team == 2]
    assert sorted((r.position, r.lane) for r in peloton) == [(grid - 2, 0), (grid - 1, 0)]  # l'un devant l'autre
    muscle = {r.kind: r for r in g.riders if r.team == 1}
    assert muscle["sprinteur"].position > muscle["rouleur"].position  # Sprinteur devant le Rouleur
    player_best = max(r.position for r in g.riders if r.team == 0)
    assert player_best <= min(r.position for r in g.riders if r.team != 0)


def test_peloton_deck_and_attack_card():
    g = Game(stage(), num_teams=2, seed=0, extensions=[PELOTON], team_types=[TEAM_PELOTON, TEAM_PLAYER])
    assert len(g.peloton_pile) == 17 and sum(c.special == ATTACK for c in g.peloton_pile) == 2
    a, b = [r for r in g.riders if r.team == 0]
    g.new_turn_cards()
    assert g.ghost_card(a) is g.ghost_card(b)  # une seule carte pour les deux coureurs
    place(g, (20, 0), (15, 0), (2, 0), (2, 1))
    values = g.card_values({a: attack_card(), b: attack_card(), g.riders[2]: Card(3), g.riders[3]: Card(4)})
    assert values[a] == 2 and values[b] == 9  # tête +2, arrière +9


def test_muscle_card_and_ghosts_never_get_exhausted():
    g = Game(Track("." * 40), num_teams=2, seed=0, extensions=[PELOTON], team_types=[TEAM_MUSCLE, TEAM_PLAYER])
    sprinteur = next(r for r in g.riders if r.team == 0 and r.kind == "sprinteur")
    assert sum(c.special == MUSCLE for c in sprinteur.draw_pile) == 1 and len(sprinteur.draw_pile) == 16
    place(g, (10, 0), (20, 0), (30, 0), (35, 0))  # tout le monde isolé
    exhausted = g.apply_exhaustion()
    assert {r.team for r in exhausted} == {1}


def test_ghost_decks_are_reshuffled_when_empty():
    g = Game(Track("." * 40), num_teams=2, seed=0, extensions=[PELOTON], team_types=[TEAM_MUSCLE, TEAM_PELOTON])
    rider = g.riders[0]
    for _ in range(40):
        g.new_turn_cards()
        assert isinstance(g.ghost_card(rider), Card) and isinstance(g.ghost_card(g.riders[2]), Card)


def test_controller_plays_ghost_teams_by_itself():
    g = Game(stage(), num_teams=3, seed=1, extensions=[PELOTON], team_types=[TEAM_PLAYER, TEAM_PELOTON, TEAM_MUSCLE])
    ctl = TurnController(g)
    assert ctl.phase == CHOOSE and ctl.current_rider.team == 0
    while ctl.phase == CHOOSE:
        ctl.choose(ctl.hand[0])
    assert ctl.phase == MOVEMENT and len(ctl.played) == 6
    ctl.advance()
    assert any("équipe Peloton" in line.text for line in ctl.log)


def test_a_whole_race_with_ghosts_and_six_teams():
    for seed in range(10):
        g = Game(stage(), num_teams=6, seed=seed, extensions=[PELOTON],
                 team_types=[TEAM_PLAYER, TEAM_PELOTON, TEAM_MUSCLE, TEAM_MUSCLE, TEAM_PLAYER, TEAM_PLAYER])
        turns = 0
        while not g.finished and turns < 200:
            g.play_turn()
            turns += 1
        assert g.finished
        for s in {r.position for r in g.riders}:
            assert len(g.riders_at(s)) <= g.lanes(s)  # jamais plus de coureurs que de files


# ------------------------------------------------------------------ pavés et ravitaillement


def cobbled():
    """Départ, droite, droite pavée (provisoire), droite de ravitaillement, droite, arrivée."""
    return [Tile("start"), Tile(KIND_STRAIGHT), Tile(KIND_STRAIGHT, cells="pppppp"),
            Tile(KIND_STRAIGHT, cells="rrrrrr"), Tile(KIND_STRAIGHT), Tile("finish")]


def test_tiles_carry_lanes_and_surface():
    track = plan_to_track(cobbled())
    assert [track.lanes(s) for s in (6, 12, 18, 24)] == [2, 1, 3, 2]
    assert track.surface(12) == COBBLES and track.surface(18) == SUPPLY and track.surface(6) == ""
    assert track.kind(12) == "." and track.kind(18) == "."


def test_cobbles_have_one_lane_and_no_slipstream():
    g = Game(plan_to_track(cobbled()), num_teams=2, seed=0, extensions=[PELOTON])
    place(g, (14, 0), (2, 0), (2, 1), (1, 0))
    g._move(g.riders[1], 12)  # 2 -> 14 : pleine (1 file) -> s'arrête en 13
    assert g.riders[1].position == 13
    place(g, (16, 0), (14, 0), (2, 0), (1, 0))  # 14 -> 16 sur les pavés : pas d'aspiration
    g.apply_slipstream()
    assert g.riders[1].position == 14


def test_supply_zone_has_three_lanes_and_a_minimum_of_four():
    g = Game(plan_to_track(cobbled()), num_teams=2, seed=0, extensions=[PELOTON])
    assert g._effective_value(19, 2) == 4 and g._effective_value(19, 7) == 7
    place(g, (20, 0), (20, 1), (8, 0), (1, 0))
    g._move(g.riders[2], 12)  # 8 -> 20 : 3e file libre
    assert g.riders[2].position == 20 and g.riders[2].lane == 2


def test_leaving_a_three_lane_zone_by_slipstream_keeps_the_extra_rider_back():
    g = Game(plan_to_track(cobbled()), num_teams=2, seed=0, extensions=[PELOTON])
    # trois coureurs côte à côte en 23 (3 files), une case vide en 24 (2 files), un coureur en 25
    place(g, (23, 0), (23, 1), (23, 2), (25, 0))
    moved = g.apply_slipstream()
    at24 = g.riders_at(24)
    assert len(at24) == 2 and {r.lane for r in at24} == {0, 1}
    stayer = g.riders_at(23)
    assert len(stayer) == 1 and stayer[0].lane == 0 and len(moved) == 2


def test_revealed_cards_are_kept_with_who_plays_them():
    g = Game(stage(), num_teams=4, seed=2, extensions=[PELOTON],
             team_types=[TEAM_PLAYER, TEAM_PLAYER, TEAM_PELOTON, TEAM_MUSCLE])
    ctl = TurnController(g, ai_teams={1})
    assert ctl.last_revealed == {} and ctl.last_revealed_turn is None
    while ctl.phase == CHOOSE:
        ctl.choose(ctl.hand[0])
    played = dict(ctl.played)
    ctl.advance()  # mouvement : les cartes sont retournées
    assert ctl.last_revealed == played and ctl.last_revealed_turn == 1
    assert [ctl.controller_of(g.riders[i]) for i in (0, 2, 4, 6)] == ["Joueur", "IA", "Peloton", "Muscle"]
    ctl.advance()
    ctl.advance()  # tour suivant : les cartes du tour 1 restent visibles jusqu'au prochain mouvement
    assert ctl.phase == CHOOSE and ctl.last_revealed_turn == 1
