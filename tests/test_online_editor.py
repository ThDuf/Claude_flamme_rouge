"""Éditeur de parcours dans le navigateur : catalogue des tuiles, vérification, ouverture, enregistrement local."""
import json
import os

import pytest

from online.rooms import Lobby, OnlineError
from online.server import Api


def call(api, path, method="POST", **body):
    query = {k: str(v) for k, v in body.items()} if method == "GET" else {}
    return api.handle(method, path, query, {} if method == "GET" else body)


def example(api):
    return call(api, "/api/editor/load", "GET", key="exemple")["tiles"]


def test_catalog_has_the_three_sides_of_the_box():
    cat = call(Api(), "/api/editor/tiles", "GET")
    sides = {s["key"]: s["letters"] for s in cat["sides"]}
    assert len(sides["plat"]) == 21 and len(sides["montagne"]) == 21 and sides["peloton"]
    card = cat["cards"]["b"]
    assert card["prims"] and card["tile"]["letter"] == "b"


def test_check_gives_preview_profile_and_issues():
    api = Api()
    tiles = example(api)
    ok = call(api, "/api/editor/check", tiles=tiles, selected=2)
    assert ok["playable"] and ok["profile"] and ok["preview"] and ok["summary"]
    assert len(ok["labels"]) == len(tiles)
    broken = call(api, "/api/editor/check", tiles=tiles[:-1])  # sans l'arrivée
    assert not broken["playable"] and broken["profile"] is None
    assert any(i["level"] == "error" for i in broken["issues"])
    empty = call(api, "/api/editor/check", tiles=[])
    assert not empty["playable"] and empty["preview"]
    with pytest.raises(OnlineError):
        call(api, "/api/editor/check", tiles=[{"kind": "inconnu"}])
    with pytest.raises(OnlineError):
        call(api, "/api/editor/check", tiles="pas une liste")


def test_open_lists_tracks_made_of_tiles_and_loads_them():
    api = Api()
    listed = call(api, "/api/editor/open", "GET")["parcours"]
    assert listed[0]["key"] == "exemple"
    official = next(p for p in listed if p["key"].startswith("officiel:"))
    loaded = call(api, "/api/editor/load", "GET", key=official["key"])
    assert loaded["label"] == official["label"] and loaded["tiles"]
    with pytest.raises(OnlineError):
        call(api, "/api/editor/load", "GET", key="nulle part")


def test_saving_is_for_the_local_server_only(tmp_path):
    hosted = Api(Lobby(str(tmp_path)))
    with pytest.raises(OnlineError):
        call(hosted, "/api/editor/save", name="Mon tour", tiles=example(hosted))
    assert not os.listdir(tmp_path)


def test_saved_track_appears_in_open_rooms(tmp_path):
    api = Api(Lobby(str(tmp_path)), local=True)
    host = call(api, "/api/create", name="Alice")  # salon déjà ouvert avant l'enregistrement
    tiles = example(api)
    with pytest.raises(OnlineError):  # un parcours injouable ne s'enregistre pas
        call(api, "/api/editor/save", name="Cassé", tiles=tiles[:-1])
    with pytest.raises(OnlineError):
        call(api, "/api/editor/save", name="../", tiles=tiles)
    saved = call(api, "/api/editor/save", name="../Mon/ parcours", tiles=tiles)
    assert saved["saved"] == "Mon parcours" and not saved["replaced"]
    assert os.listdir(tmp_path) == ["Mon parcours.json"]  # pas de chemin : le fichier reste dans le dossier
    with open(tmp_path / "Mon parcours.json", encoding="utf-8") as handle:
        assert len(json.load(handle)["tiles"]) == len(tiles)
    assert call(api, "/api/editor/save", name="Mon parcours", tiles=tiles)["replaced"]
    keys = [p["key"] for p in call(api, "/api/info", "GET")["parcours"]]
    assert saved["key"] in keys
    call(api, "/api/settings", code=host["code"], token=host["token"], parcours=saved["key"])
    lobby = call(api, "/api/state", "GET", code=host["code"], token=host["token"])["lobby"]
    assert lobby["parcours_label"] == "Mon parcours"
