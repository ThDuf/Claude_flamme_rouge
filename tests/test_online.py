import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from flamme_rouge.controller import CHOOSE, FINISHED
from online.rooms import OnlineError
from online.server import Api, make_handler


def call(api, path, method="POST", **body):
    query = {k: str(v) for k, v in body.items()} if method == "GET" else {}
    return api.handle(method, path, query, {} if method == "GET" else body)


def lobby_of_two(api):
    host = call(api, "/api/create", name="Alice")
    code = host["code"]
    guest = call(api, "/api/join", code=code, name="Bob")
    return code, host["token"], guest["token"]


def test_room_creation_seats_and_settings():
    api = Api()
    code, alice, bob = lobby_of_two(api)
    state = call(api, "/api/state", "GET", code=code, token=alice)
    assert state["me"] == {"name": "Alice", "team": 0, "host": True}
    seats = state["lobby"]["seats"]
    assert [s["player"] for s in seats] == ["Alice", "Bob"]
    assert "map" in state["lobby"]["preview"] and "/" not in state["lobby"]["parcours"].split(":", 1)[0]
    with pytest.raises(OnlineError):  # seul l'hôte règle la partie
        call(api, "/api/settings", code=code, token=bob, teams=3)
    call(api, "/api/settings", code=code, token=alice, teams=3, seats=["joueur", "joueur", "ia"])
    with pytest.raises(OnlineError):  # une place IA ne se prend pas
        call(api, "/api/seat", code=code, token=bob, team=2)
    with pytest.raises(OnlineError):
        call(api, "/api/join", code=code, name="alice")  # nom déjà pris
    call(api, "/api/settings", code=code, token=alice, teams=5)  # 5 équipes : Peloton cochée d'office
    assert "peloton" in call(api, "/api/state", "GET", code=code, token=alice)["lobby"]["extensions"]
    same = call(api, "/api/state", "GET", code=code, token=alice,
                since=call(api, "/api/state", "GET", code=code, token=alice)["version"])
    assert same["same"] is True  # rien n'a changé : rien n'est renvoyé


def test_a_whole_remote_race_each_player_sees_only_his_hand():
    api = Api()
    code, alice, bob = lobby_of_two(api)
    call(api, "/api/settings", code=code, token=alice, teams=3, seats=["joueur", "joueur", "ia"])
    with pytest.raises(OnlineError):
        call(api, "/api/start", code=code, token=bob)
    call(api, "/api/start", code=code, token=alice)
    room = api.lobby.room(code)
    room.game.rng.seed(3)
    steps = 0
    while True:
        a = call(api, "/api/state", "GET", code=code, token=alice)["race"]
        b = call(api, "/api/state", "GET", code=code, token=bob)["race"]
        if a["finished"]:
            break
        assert not (a["hand"] and b["hand"])  # jamais deux mains visibles en même temps
        assert a["map"] and a["profile"]
        if a["phase"] == CHOOSE:
            mover, other = (alice, bob) if a["my_turn"] else (bob, alice)
            with pytest.raises(OnlineError):  # pas son tour
                call(api, "/api/card", code=code, token=other, index=0)
            call(api, "/api/card", code=code, token=mover, index=0)
        else:
            call(api, "/api/advance", code=code, token=bob, phase=a["phase"])
            call(api, "/api/advance", code=code, token=alice, phase=a["phase"])  # double clic : ignoré
        steps += 1
        assert steps < 2000
    final = call(api, "/api/state", "GET", code=code, token=bob)["race"]
    assert final["phase"] == FINISHED and final["winner"] and final["podium"]
    assert any("(IA)" in name for name in final["teams"])
    call(api, "/api/lobby", code=code, token=alice)  # retour au salon pour une revanche
    assert "lobby" in call(api, "/api/state", "GET", code=code, token=bob)


def test_http_server_serves_the_page_and_the_api():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Api()))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        page = urllib.request.urlopen(base + "/").read().decode("utf-8")
        assert "<canvas" in page or "app.js" in page
        req = urllib.request.Request(base + "/api/create", data=json.dumps({"name": "Zoé"}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        created = json.loads(urllib.request.urlopen(req).read())
        state = json.loads(urllib.request.urlopen(
            f"{base}/api/state?code={created['code']}&token={created['token']}").read())
        assert state["me"]["name"] == "Zoé"
        bad = urllib.request.Request(base + "/api/join", data=b'{"code":"ZZZZ","name":"x"}', method="POST")
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(bad)
        assert err.value.code == 400 and "code" in json.loads(err.value.read())["error"]
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/../main.py")  # pas d'accès aux fichiers du PC
    finally:
        httpd.shutdown()
        httpd.server_close()
