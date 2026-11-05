from flamme_rouge.catalog import GROUP_BASE, build_choices
from flamme_rouge.circuits import base_circuits
from flamme_rouge.tiles import ERROR, KIND_SHARP, KIND_SOFT, KIND_STRAIGHT, validate


def test_four_base_circuits_with_the_box_composition_and_no_error():
    circuits = base_circuits()
    assert len(circuits) == 4
    for name, _desc, tiles in circuits:
        assert len(tiles) == 21, name
        assert [sum(t.kind == k for t in tiles) for k in (KIND_STRAIGHT, KIND_SOFT, KIND_SHARP)] == [7, 6, 6]
        assert [i for i in validate(tiles) if i.level == ERROR] == [], name


def test_base_circuits_are_in_the_menu_and_playable(tmp_path):
    choices = [c for c in build_choices(str(tmp_path)) if c.group == GROUP_BASE]
    assert len(choices) == 4 and all(c.playable for c in choices)
