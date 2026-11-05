import json

import pytest

from flamme_rouge import Game
from flamme_rouge.plan import PlanEditor
from flamme_rouge.tiles import (
    ERROR,
    KIND_FINISH,
    KIND_SHARP,
    KIND_SOFT,
    KIND_START,
    KIND_STRAIGHT,
    RELIEF_PROFILES,
    SQUARES_PER_TILE,
    WARNING,
    Tile,
    example_plan,
    find_crossing,
    finish_index,
    full_track,
    has_errors,
    load_track_file,
    make_tile,
    plan_from_json,
    plan_to_json,
    plan_to_track,
    summary,
    tile_ranges,
    validate,
)
from flamme_rouge.track import ASCENT, DESCENT, LEFT, RIGHT

N = SQUARES_PER_TILE


def simple(*kinds):
    """Départ, les tuiles données (droites ou ('sharp','L')...), arrivée."""
    tiles = [make_tile(KIND_START)]
    for k in kinds:
        tiles.append(make_tile(k) if isinstance(k, str) else make_tile(k[0], k[1]))
    tiles.append(make_tile(KIND_FINISH))
    return tiles


# ----------------------------------------------------------------------- Tile


def test_tile_validation():
    with pytest.raises(ValueError):
        Tile("bidon")
    with pytest.raises(ValueError):
        Tile(KIND_SHARP)  # un virage a besoin d'une direction
    with pytest.raises(ValueError):
        Tile(KIND_STRAIGHT, LEFT)  # une droite n'a pas de direction
    with pytest.raises(ValueError):
        Tile(KIND_STRAIGHT, terrain="..")  # mauvaise longueur
    with pytest.raises(ValueError):
        Tile(KIND_STRAIGHT, terrain="X" * N)
    with pytest.raises(ValueError):
        make_tile(KIND_STRAIGHT, relief="volcan")


def test_turn_tiles_turn_by_the_right_angle():
    # 15° par 'L' ou 'R' : un virage doux fait 45° (3 crans), un virage serré 90° (6 crans).
    assert make_tile(KIND_SOFT, LEFT).shape.count("L") == 3
    assert make_tile(KIND_SHARP, RIGHT).shape.count("R") == 6
    assert make_tile(KIND_STRAIGHT).shape == "S" * N
    assert make_tile(KIND_START).shape == "S" * N and make_tile(KIND_FINISH).shape == "S" * N


def test_relief_profiles():
    assert RELIEF_PROFILES["plat"] == "." * N
    assert RELIEF_PROFILES["montée"] == "A" * N and RELIEF_PROFILES["descente"] == "D" * N
    mixed = RELIEF_PROFILES["montée puis descente"]
    assert mixed == "A" * (N // 2) + "D" * (N - N // 2)
    assert len(RELIEF_PROFILES) == 9
    assert make_tile(KIND_STRAIGHT, relief="montée puis descente").relief_name == "montée puis descente"
    assert Tile(KIND_STRAIGHT, terrain="A" + "." * (N - 1)).relief_name == "relief personnalisé"


def test_labels_are_readable():
    assert make_tile(KIND_SOFT, LEFT, "montée").label == "Virage doux à gauche — montée"
    assert make_tile(KIND_START).label == "Départ — plat"


# ------------------------------------------------------------------ assemblage


def test_finish_tile_is_not_part_of_the_race():
    tiles = simple(KIND_STRAIGHT, KIND_STRAIGHT)  # départ + 2 droites + arrivée
    assert finish_index(tiles) == 3
    assert len(plan_to_track(tiles)) == 3 * N
    assert len(full_track(tiles)) == 4 * N


def test_track_carries_terrain_and_shape_of_each_tile():
    tiles = [
        make_tile(KIND_START),
        make_tile(KIND_STRAIGHT, relief="montée"),
        make_tile(KIND_SHARP, LEFT, "descente"),
        make_tile(KIND_FINISH),
    ]
    track = plan_to_track(tiles)
    assert track.layout == "." * N + "A" * N + "D" * N
    assert track.shape == "S" * (2 * N) + "L" * 6 if N == 6 else True
    assert track.kind(N) == ASCENT and track.kind(2 * N) == DESCENT
    assert track.turn(2 * N + 1) == LEFT


def test_plan_without_finish_uses_every_tile():
    tiles = [make_tile(KIND_START), make_tile(KIND_STRAIGHT)]
    assert len(plan_to_track(tiles)) == 2 * N


def test_plan_with_only_a_finish_tile_cannot_be_played():
    with pytest.raises(ValueError):
        plan_to_track([make_tile(KIND_FINISH)])
    with pytest.raises(ValueError):
        plan_to_track([])


def test_tile_ranges_cover_all_squares_once():
    tiles = simple(KIND_STRAIGHT, KIND_STRAIGHT)
    ranges = tile_ranges(tiles)
    assert [s for r in ranges for s in r] == list(range(len(tiles) * N))


def test_an_assembled_track_can_be_raced_with_the_real_rules():
    for seed in range(3):
        game = Game(plan_to_track(example_plan()), num_teams=3, seed=seed)
        while not game.finished:
            game.play_turn()
        assert game.winner is not None


# ------------------------------------------------------------------ validation


def test_example_plan_is_valid_and_within_official_limits():
    issues = validate(example_plan())
    assert issues == []


def test_empty_plan_is_an_error():
    assert [i.level for i in validate([])] == [ERROR]


def test_missing_start_and_finish():
    texts = " ".join(i.text for i in validate([make_tile(KIND_STRAIGHT)]))
    assert "départ" in texts and "arrivée" in texts


def test_start_must_be_first_and_finish_last():
    tiles = [make_tile(KIND_STRAIGHT), make_tile(KIND_START), make_tile(KIND_FINISH), make_tile(KIND_STRAIGHT)]
    texts = [i.text for i in validate(tiles)]
    assert any("première" in t for t in texts) and any("dernière" in t for t in texts)


def test_two_starts_is_an_error():
    tiles = [make_tile(KIND_START), make_tile(KIND_START), make_tile(KIND_FINISH)]
    assert any("qu'une tuile de départ" in i.text for i in validate(tiles))


def test_official_quantities_only_warn():
    tiles = simple(*([KIND_STRAIGHT] * 8))  # 8 droites : la boîte en contient 7
    issues = validate(tiles)
    assert [i.level for i in issues] == [WARNING]
    assert not has_errors(issues)


def test_total_over_21_warns():
    tiles = simple(*([KIND_STRAIGHT] * 7), *[(KIND_SOFT, LEFT)] * 6, *[(KIND_SHARP, RIGHT)] * 6, KIND_STRAIGHT)
    assert len(tiles) == 22  # 20 tuiles de course + départ + arrivée
    assert any("22 tuiles" in i.text for i in validate(tiles) if i.level == WARNING)


def test_a_loop_is_detected_as_crossing():
    loop = [make_tile(KIND_START)] + [make_tile(KIND_SHARP, LEFT)] * 4 + [make_tile(KIND_STRAIGHT), make_tile(KIND_FINISH)]
    assert find_crossing(loop) is not None
    issues = validate(loop)
    assert has_errors(issues) and any("recoupe" in i.text for i in issues)


def test_s_bend_does_not_cross():
    tiles = simple((KIND_SHARP, LEFT), (KIND_SHARP, RIGHT), (KIND_SHARP, RIGHT), (KIND_SHARP, LEFT))
    assert find_crossing(tiles) is None


def test_summary_counts():
    text = summary(example_plan())
    assert text.startswith("14/21 tuiles") and "départ 1/1" in text and "droites 7/7" in text


# ----------------------------------------------------------------- sauvegarde


def test_json_roundtrip():
    tiles = example_plan()
    assert plan_from_json(plan_to_json(tiles)) == tiles


def test_json_rejects_garbage():
    with pytest.raises(ValueError):
        plan_from_json("pas du json")
    with pytest.raises(ValueError):
        plan_from_json("[]")
    with pytest.raises(ValueError):
        plan_from_json(json.dumps({"tiles": [{"kind": "straight"}]}))  # relief manquant
    with pytest.raises(ValueError):
        plan_from_json(json.dumps({"squares_per_tile": 99, "tiles": []}))


def test_load_track_file(tmp_path):
    good = tmp_path / "ok.json"
    good.write_text(plan_to_json(example_plan()), encoding="utf-8")
    assert len(load_track_file(str(good))) == (len(example_plan()) - 1) * N

    bad = tmp_path / "bad.json"
    bad.write_text(plan_to_json([make_tile(KIND_STRAIGHT)]), encoding="utf-8")
    with pytest.raises(ValueError, match="injouable"):
        load_track_file(str(bad))


# -------------------------------------------------------------------- éditeur


def test_editor_append_insert_replace_remove():
    ed = PlanEditor()
    a, b, c = make_tile(KIND_START), make_tile(KIND_STRAIGHT), make_tile(KIND_FINISH)
    ed.append(a)
    ed.append(c)
    assert ed.selected == 1
    ed.select(0)
    ed.insert_after(b)
    assert ed.tiles == [a, b, c] and ed.selected == 1
    ed.replace(make_tile(KIND_SOFT, LEFT))
    assert ed.tiles[1].kind == KIND_SOFT
    ed.remove()
    assert ed.tiles == [a, c] and ed.selected == 1
    ed.select(0)
    ed.remove()
    ed.remove()
    assert ed.tiles == [] and ed.selected is None


def test_editor_move():
    ed = PlanEditor(simple(KIND_STRAIGHT))
    ed.select(1)
    ed.move(-1)
    assert ed.tiles[0].kind == KIND_STRAIGHT and ed.selected == 0
    ed.move(-1)  # déjà en tête : rien ne se passe
    assert ed.selected == 0
    ed.move(+1)
    assert ed.selected == 1 and ed.tiles[1].kind == KIND_STRAIGHT


def test_editor_needs_a_selection_for_selection_actions():
    ed = PlanEditor(simple())
    for action in (lambda: ed.replace(make_tile(KIND_STRAIGHT)), ed.remove, lambda: ed.move(1),
                   lambda: ed.insert_after(make_tile(KIND_STRAIGHT))):
        with pytest.raises(ValueError):
            action()
    with pytest.raises(IndexError):
        ed.select(99)


def test_editor_undo_restores_tiles_and_selection():
    ed = PlanEditor(simple(KIND_STRAIGHT))
    original = list(ed.tiles)
    ed.select(1)
    ed.remove()
    ed.append(make_tile(KIND_SOFT, RIGHT))
    ed.clear()
    assert ed.tiles == []
    ed.undo()
    ed.undo()
    ed.undo()
    assert ed.tiles == original
    ed.undo()  # rien à annuler : sans effet
    assert ed.tiles == original and not ed.can_undo


def test_editor_load_is_undoable():
    ed = PlanEditor(simple())
    ed.load(example_plan())
    assert len(ed.tiles) == 14 and ed.selected is None
    ed.undo()
    assert len(ed.tiles) == 2


# ---------------------------------------------------------------------- aperçu


def test_preview_draws_every_square_and_numbers_every_tile():
    from flamme_rouge.boardview import plan_preview_primitives

    tiles = example_plan()
    prims = plan_preview_primitives(tiles, 640, 520, selected=3)
    polys = [p for p in prims if p[0] == "poly" and p[2] != "" and p[3] == "#364152"]
    assert len(polys) == len(tiles) * N
    numbers = {p[3] for p in prims if p[0] == "text"}
    assert {str(i) for i in range(1, len(tiles) + 1)} <= numbers
    assert {"DÉPART", "ARRIVÉE"} <= numbers
    outlines = [p for p in prims if p[0] == "poly" and p[2] == ""]
    assert len(outlines) == N  # seule la tuile sélectionnée est entourée


def test_preview_stays_on_canvas_and_handles_edge_cases():
    from flamme_rouge.boardview import plan_preview_primitives

    for tiles in (example_plan(), [make_tile(KIND_START)], simple(*([KIND_STRAIGHT] * 15))):
        for p in plan_preview_primitives(tiles, 640, 520):
            if p[0] == "poly":
                xs, ys = p[1][0::2], p[1][1::2]
                assert -1 <= min(xs) and max(xs) <= 641 and -1 <= min(ys) and max(ys) <= 521
    empty = plan_preview_primitives([], 640, 520)
    assert empty[0][0] == "text" and "tuiles" in empty[0][3]
