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


def road_point(road, progress, lane):
    """Le calcul de app.js (roadPoint), recopié ici pour le comparer à la géométrie du jeu."""
    last = len(road) - 1
    progress = min(max(progress, 0), last)
    i = min(int(progress), max(last - 1, 0))
    f = progress - i

    def at(row):
        rx, ry, lx, ly, lanes = row
        g = (lane + 0.5) / lanes
        return rx + (lx - rx) * g, ry + (ly - ry) * g

    (x0, y0), (x1, y1) = at(road[i]), at(road[i + 1])
    return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


def test_browser_geometry_matches_the_map_and_movements_are_replayed():
    from flamme_rouge.boardview import _map_frame, follow_view, road_geometry
    from flamme_rouge.geometry import point_on_road
    from flamme_rouge.official import official_stages
    from flamme_rouge.tiles import plan_to_track
    from flamme_rouge.game import Game

    g = Game(plan_to_track(official_stages()[1].tiles), num_teams=3, seed=0)
    for view in (None, follow_view(g, "tete")):
        squares, _first, _last, _scale, tr = _map_frame(g, False, None, 1000, 430, view)
        road = road_geometry(g, view)["road"]
        for progress, lane in ((0, 0), (12.5, 1), (30.25, 0.4), (55, -1.3), (70.9, 2.8)):
            expected = tr(point_on_road(squares, progress, lane))
            got = road_point(road, progress, lane)
            assert abs(got[0] - expected[0]) < 1e-6 and abs(got[1] - expected[1]) < 1e-6

    api = Api()
    code, alice, bob = lobby_of_two(api)
    call(api, "/api/settings", code=code, token=alice, extensions=["meteo"])
    call(api, "/api/start", code=code, token=alice)
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["anim"] is None and race["weather"] and race["geo"]["road"] and race["profile_geo"]["ys"]
    assert len(race["map_base"]) < len(race["map"])  # la route sans les coureurs
    while race["phase"] == CHOOSE:
        mover = alice if race["my_turn"] else bob
        call(api, "/api/card", code=code, token=mover, index=0)
        race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    call(api, "/api/advance", code=code, token=alice, phase=race["phase"])  # mouvement
    after = call(api, "/api/state", "GET", code=code, token=bob)
    anim = after["race"]["anim"]
    assert anim["kind"] == "movement" and anim["id"] == after["version"] and anim["moves"]
    by_name = {r["name"]: r for r in after["race"]["riders"]}
    for move in anim["moves"]:
        assert move["to"] == [by_name[move["name"]]["position"], by_name[move["name"]]["lane"]]
        assert move["from"][0] <= move["to"][0]


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
