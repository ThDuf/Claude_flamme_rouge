"""La scène du parcours pour la vue 3D : coins des cases, altitudes, terrain."""
import pytest

from flamme_rouge.boardview import road_altitudes
from flamme_rouge.geometry import EXTRA_SQUARES, layout_squares
from flamme_rouge.iso import projection
from flamme_rouge.official import official_stages
from flamme_rouge.scene import _too_close, build_scene
from flamme_rouge.tiles import plan_to_track
from flamme_rouge.track import Track


def test_roads_never_overlap():
    # La Haut Montagne : après l'arrivée, la route repartirait au-dessus de l'épingle des cases 32 à 35
    for stage in official_stages():
        track = plan_to_track(stage.tiles)
        rows = build_scene(track)["squares"]
        squares = layout_squares(track)[:len(rows)]
        assert len(rows) > len(track)  # la case du damier est toujours là
        for j in range(len(squares)):
            assert not any(_too_close(squares[j], squares[i]) for i in range(j - 3)), (stage.name, j)
    cut = build_scene(plan_to_track(official_stages()[2].tiles))
    assert len(cut["squares"]) < cut["n"] + EXTRA_SQUARES and len(cut["z"]) == len(cut["squares"]) + 1


def test_corners_match_the_squares_of_the_map():
    track = plan_to_track(official_stages()[0].tiles)
    scene = build_scene(track)
    squares = layout_squares(track)
    assert len(scene["squares"]) <= len(squares) == len(track) + EXTRA_SQUARES
    for row, sq in zip(scene["squares"], squares):
        assert row["left"][0] == pytest.approx(sq.lb, abs=1e-3) and row["left"][-1] == pytest.approx(sq.lf, abs=1e-3)
        assert row["right"][0] == pytest.approx(sq.rb, abs=1e-3) and row["right"][-1] == pytest.approx(sq.rf, abs=1e-3)
        assert len(row["left"]) == len(sq.left_path) and row["lanes"] == sq.lanes
    turns = [row for row in scene["squares"] if len(row["left"]) > 2]
    assert turns  # les virages arrivent en arc, pas en ligne droite


def test_altitudes_follow_the_profile():
    track = Track("." * 5 + "A" * 4 + "D" * 2 + "." * 3)
    scene = build_scene(track)
    z = scene["z"]
    assert len(z) == len(scene["squares"]) + 1
    assert z[:12] == [0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 3, 2]
    assert all(v == z[len(track)] for v in z[len(track):])  # plate après l'arrivée
    # le milieu d'une case est à la moyenne de ses bords, comme le relief de la carte et la vue isométrique
    middles = [(a + b) / 2 for a, b in zip(z, z[1:])]
    assert middles == pytest.approx(road_altitudes(track, len(scene["squares"])))
    assert z == projection(track, 45).edges


def test_terrain_and_lines():
    track = Track("." * 5 + "A" * 4 + "D" * 2 + "." * 3, start=2)
    scene = build_scene(track)
    rows = scene["squares"]
    assert [r["kind"] for r in rows[4:12]] == list(".AAAADD.")
    assert rows[len(track)]["kind"] == "" and rows[len(track)]["fill"] != rows[0]["fill"]  # au-delà de l'arrivée
    assert scene["n"] == len(track) and scene["start"] == 2


def test_the_profile_for_the_3d_view():
    from flamme_rouge.boardview import climbs, cosmetic_elevation, profile_title
    track = plan_to_track(official_stages()[2].tiles)
    profile = build_scene(track)["profile"]
    assert len(profile["heights"]) == len(track) + 1
    assert profile["heights"] == pytest.approx(cosmetic_elevation(track), abs=1e-3)  # le même relief que le profil 2D
    assert profile["climbs"] == [list(c) for c in climbs(track)] and profile["climbs"]
    assert set(profile["fills"]) == {".", "A", "D"}
    assert profile_title(track).startswith("Profil : ")
