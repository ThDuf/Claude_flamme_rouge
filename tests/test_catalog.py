import os
import time

from flamme_rouge.catalog import (
    GROUP_MINE,
    GROUP_BASE,
    GROUP_OFFICIAL,
    MAX_SAVED_FILES,
    build_choices,
    saved_files,
)
from flamme_rouge.tiles import example_plan, make_tile, plan_to_json


def write(path, tiles):
    path.write_text(plan_to_json(tiles), encoding="utf-8")


def test_menu_lists_official_stages_first_then_base_circuits(tmp_path):
    choices = build_choices(str(tmp_path))
    groups = [c.group for c in choices]
    assert groups == [GROUP_OFFICIAL] * 6 + [GROUP_BASE] * 4  # plus de parcours « prêts à jouer » non officiels
    assert choices[0].key == "officiel:Avenue Corso Paseo"


def test_official_stages_are_listed_and_playable(tmp_path):
    official = [c for c in build_choices(str(tmp_path)) if c.group == GROUP_OFFICIAL]
    assert [c.label for c in official][0] == "Avenue Corso Paseo" and len(official) == 6
    assert all(c.playable for c in official)
    assert official[0].details.endswith("21 tuiles")


def test_saved_files_are_listed_newest_first(tmp_path):
    old, new = tmp_path / "ancien.json", tmp_path / "recent.json"
    write(old, example_plan())
    time.sleep(0.02)
    write(new, example_plan())
    os.utime(old, (1, 1))
    assert [os.path.basename(p) for p in saved_files(str(tmp_path))] == ["recent.json", "ancien.json"]
    mine = [c for c in build_choices(str(tmp_path)) if c.group == GROUP_MINE]
    assert [c.label for c in mine] == ["recent", "ancien"] and all(c.playable for c in mine)


def test_invalid_files_are_listed_with_the_reason(tmp_path):
    write(tmp_path / "sans_arrivee.json", [make_tile("start"), make_tile("straight")])
    (tmp_path / "casse.json").write_text("pas du json", encoding="utf-8")
    mine = {c.label: c for c in build_choices(str(tmp_path)) if c.group == GROUP_MINE}
    assert not mine["sans_arrivee"].playable and "arrivée" in mine["sans_arrivee"].details
    assert not mine["casse"].playable and "illisible" in mine["casse"].details


def test_extra_files_are_added_once(tmp_path):
    other = tmp_path / "ailleurs" / "mon_parcours.json"
    other.parent.mkdir()
    write(other, example_plan())
    choices = build_choices(str(tmp_path / "vide"), extra_files=[str(other), str(other)])
    assert [c.label for c in choices if c.group == GROUP_MINE] == ["mon_parcours"]


def test_only_the_most_recent_files_are_listed(tmp_path):
    for i in range(MAX_SAVED_FILES + 5):
        write(tmp_path / f"p{i:02d}.json", example_plan())
        os.utime(tmp_path / f"p{i:02d}.json", (i + 1, i + 1))
    mine = [c for c in build_choices(str(tmp_path)) if c.group == GROUP_MINE]
    assert len(mine) == MAX_SAVED_FILES and mine[0].label == f"p{MAX_SAVED_FILES + 4:02d}"


def test_missing_parcours_folder_is_fine(tmp_path):
    assert all(c.group != GROUP_MINE for c in build_choices(str(tmp_path / "nexiste_pas")))


def test_every_playable_choice_can_really_be_raced():
    from flamme_rouge import Game

    for choice in build_choices():
        if choice.playable:
            game = Game(choice.track, num_teams=2, seed=1)
            while not game.finished:
                game.play_turn()
            assert game.winner is not None
