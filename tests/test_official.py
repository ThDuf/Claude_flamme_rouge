import json

import pytest

from flamme_rouge.official import (
    BUILT_IN_CATALOG,
    DATA_FILE,
    STAGES,
    build_stage,
    load_catalog,
    official_stages,
    template_catalog,
)
from flamme_rouge.tiles import (
    SQUARES_PER_TILE,
    Tile,
    make_tile,
    plan_to_track,
    validate,
)


def test_every_stage_uses_each_of_the_21_tiles_exactly_once():
    # Vérifie la retranscription des chaînes du règlement (la casse indique le côté retourné).
    for name, setup in STAGES.items():
        assert len(setup) == 21, name
        assert sorted(setup.lower()) == list("abcdefghijklmnopqrstu"), name


def test_avenue_corso_paseo_is_the_beginner_track_in_alphabetical_order():
    assert STAGES["Avenue Corso Paseo"] == "abcdefghijklmnopqrstu"


def test_every_stage_starts_with_a_and_ends_with_u():
    for name, setup in STAGES.items():
        assert setup[0] in "aA" and setup[-1] in "uU", name


def test_stages_are_unavailable_until_tiles_are_described():
    stages = official_stages()
    assert [s.name for s in stages] == list(STAGES)
    assert all(not s.available for s in stages)  # seules a et u sont connues
    assert "b" in stages[0].missing and "a" not in stages[0].missing


def test_shipped_template_file_matches_the_template():
    with open(DATA_FILE, encoding="utf-8") as handle:
        assert json.load(handle) == template_catalog()
    assert len([k for k in template_catalog() if not k.startswith("_")]) == 42


def test_a_complete_catalog_makes_a_stage_playable(tmp_path):
    # Faux catalogue : toutes les tuiles du milieu sont des lignes droites plates.
    data = {c: {"kind": "straight", "direction": None, "terrain": "." * SQUARES_PER_TILE}
            for c in "bcdefghijklmnopqrst"}
    path = tmp_path / "tuiles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    stage = official_stages(str(path))[0]
    assert stage.available and stage.missing == ()
    assert len(stage.tiles) == 21
    track = plan_to_track(stage.tiles)
    assert len(track) == 20 * SQUARES_PER_TILE
    # 19 droites : la boîte n'en a que 7, ce qui n'est qu'un avertissement
    assert all(issue.level == "avertissement" for issue in validate(stage.tiles))


def test_uppercase_and_lowercase_sides_are_distinct_entries(tmp_path):
    data = {"g": {"kind": "sharp", "direction": "L", "terrain": ".." + "A" * (SQUARES_PER_TILE - 2)},
            "G": {"kind": "straight", "direction": None, "terrain": "." * SQUARES_PER_TILE}}
    path = tmp_path / "t.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    catalog = load_catalog(str(path))
    assert catalog["g"].kind == "sharp" and catalog["G"].kind == "straight"
    assert catalog["a"] == BUILT_IN_CATALOG["a"]  # les valeurs intégrées restent


def test_null_and_help_entries_are_ignored(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"_aide": "texte", "b": None}), encoding="utf-8")
    assert set(load_catalog(str(path))) == set(BUILT_IN_CATALOG)


def test_bad_data_gives_a_clear_error(tmp_path):
    for bad in ({"b": {"kind": "bidon"}}, {"bb": {"kind": "straight"}}, {"b": {"direction": "L"}}, [1, 2]):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(bad), encoding="utf-8")
        with pytest.raises(ValueError):
            load_catalog(str(path))


def test_missing_data_file_falls_back_to_built_in(tmp_path):
    assert load_catalog(str(tmp_path / "absent.json")) == BUILT_IN_CATALOG


def test_build_stage_reports_missing_letters_once_each():
    stage = build_stage("x", "abbc", {"a": make_tile("start")})
    assert stage.missing == ("b", "c") and not stage.available
