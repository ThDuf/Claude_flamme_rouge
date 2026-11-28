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
    assert state["me"] == {"name": "Alice", "team": 0, "teams": [0], "host": True}
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


def play_all_hands(api, code, *tokens):
    """Choix simultané : chaque joueur pose la première carte de chacun de ses coureurs, en une seule demande."""
    for token in tokens:
        hands = call(api, "/api/state", "GET", code=code, token=token)["race"]["hands"]
        if hands:
            call(api, "/api/cards", code=code, token=token, choices={h["name"]: 0 for h in hands})


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
        assert a["map"] and a["profile"]
        if a["phase"] == CHOOSE:
            # chacun ne voit que les mains de ses coureurs, et les deux joueurs choisissent en même temps
            assert {h["team"] for h in a["hands"]} <= {0} and {h["team"] for h in b["hands"]} <= {1}
            if steps == 0:
                assert len(a["hands"]) == 2 and len(b["hands"]) == 2 and a["my_turn"] and b["my_turn"]
                with pytest.raises(OnlineError):  # pas le coureur d'un autre joueur
                    call(api, "/api/cards", code=code, token=bob, choices={a["hands"][0]["name"]: 0})
                with pytest.raises(OnlineError):  # rien n'est posé si un des choix est faux
                    call(api, "/api/cards", code=code, token=alice,
                         choices={a["hands"][0]["name"]: 0, a["hands"][1]["name"]: 99})
                assert len(call(api, "/api/state", "GET", code=code, token=alice)["race"]["hands"]) == 2
                # Bob choisit d'abord, Alice ensuite : l'ordre ne compte pas
                play_all_hands(api, code, bob)
                waiting = call(api, "/api/state", "GET", code=code, token=bob)["race"]["waiting"]
                assert "Alice" in waiting
            play_all_hands(api, code, alice, bob)
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
    play_all_hands(api, code, alice, bob)
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    call(api, "/api/advance", code=code, token=alice, phase=race["phase"])  # mouvement
    after = call(api, "/api/state", "GET", code=code, token=bob)
    anim = after["race"]["anim"]
    assert anim["kind"] == "movement" and anim["id"] == after["version"] and anim["moves"]
    by_name = {r["name"]: r for r in after["race"]["riders"]}
    for move in anim["moves"]:
        assert move["to"] == [by_name[move["name"]]["position"], by_name[move["name"]]["lane"]]
        assert move["from"][0] <= move["to"][0]


def test_free_zoom_view_is_drawn_by_the_server():
    from online.rooms import parse_view

    assert parse_view("") is None and parse_view("abc") is None and parse_view("nan,1,2") is None
    assert parse_view("999,10,20") == (140.0, 10.0, 20.0) and parse_view("0.5,1,2") == (3.0, 1.0, 2.0)
    api = Api()
    code, alice, _bob = lobby_of_two(api)
    call(api, "/api/start", code=code, token=alice)
    full = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    scale, cx, cy = full["view"]
    zoomed = call(api, "/api/state", "GET", code=code, token=alice, view=f"{scale * 3},{cx},{cy}")["race"]
    assert zoomed["view"][0] == pytest.approx(scale * 3, abs=0.01)
    assert zoomed["geo"]["scale"] == pytest.approx(scale * 3, abs=0.01)  # animations dans le même cadrage
    assert zoomed["geo"]["radius"] > full["geo"]["radius"]  # coureurs plus gros quand on zoome
    bad = call(api, "/api/state", "GET", code=code, token=alice, view="n'importe quoi")["race"]
    assert bad["view"] == full["view"]  # cadrage illisible : la caméra, sans erreur


def test_breakaway_bidding_online():
    from flamme_rouge.track import BREAKAWAY as BREAKAWAY_TILE
    from online.rooms import online_choices

    api = Api()
    code, alice, bob = lobby_of_two(api)
    plain = call(api, "/api/state", "GET", code=code, token=alice)["lobby"]
    assert plain["breakaway_available"] is False  # parcours de base, sans Peloton
    stage = next(c for c in online_choices()
                 if any(c.track.surface(s) == BREAKAWAY_TILE for s in range(len(c.track))))
    call(api, "/api/settings", code=code, token=alice, parcours=stage.key, teams=3,
         seats=["joueur", "joueur", "ia"])
    lobby = call(api, "/api/state", "GET", code=code, token=bob)["lobby"]
    assert "peloton" in lobby["extensions"] and lobby["breakaway_available"] and lobby["breakaway"]
    call(api, "/api/start", code=code, token=alice)
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["phase"] == "breakaway" and race["title"] == "Enchères de l'échappée"
    first, other = (alice, bob) if race["bid"] else (bob, alice)
    with pytest.raises(OnlineError):  # pas son tour d'enchérir
        call(api, "/api/bid_rider", code=code, token=other, rider=None)
    mine = call(api, "/api/state", "GET", code=code, token=first)["race"]["bid"]
    assert mine["stage"] == "rider" and len(mine["riders"]) == 2
    call(api, "/api/bid_rider", code=code, token=first, rider=mine["riders"][0]["name"])
    for round_ in (1, 2):  # deux mises
        race = call(api, "/api/state", "GET", code=code, token=first)["race"]
        assert race["bid"] == {"stage": "card", "round": round_} and len(race["hand"]) == 4
        assert call(api, "/api/state", "GET", code=code, token=other)["race"]["hand"] == []  # main cachée
        call(api, "/api/card", code=code, token=first, index=0)
    call(api, "/api/bid_rider", code=code, token=other, rider=None)  # l'autre joueur passe
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["phase"] == "choose"  # l'IA a enchéri seule, l'échappée est résolue, le tour 1 commence
    texts = " ".join(line["text"] for line in race["log"])
    assert "tente l'échappée" in texts and "ne participe pas" in texts

    # sans la variante : pas d'enchères
    code2, host2, _guest2 = lobby_of_two(api)
    call(api, "/api/settings", code=code2, token=host2, parcours=stage.key, breakaway=False)
    call(api, "/api/start", code=code2, token=host2)
    assert call(api, "/api/state", "GET", code=code2, token=host2)["race"]["phase"] == "choose"


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
        # la vue 3D : Three.js est servi par le site lui-même (pas de CDN), et gardé en cache par le navigateur
        assert '"/vendor/three-0.170.0/three.module.min.js"' in page
        for path in ("three.module.min.js", "addons/controls/OrbitControls.js", "addons/renderers/CSS2DRenderer.js"):
            with urllib.request.urlopen(f"{base}/vendor/three-0.170.0/{path}") as res:
                assert "javascript" in res.headers["Content-Type"] and "immutable" in res.headers["Cache-Control"]
        with urllib.request.urlopen(base + "/app.js") as res:
            assert res.headers["Cache-Control"] == "no-store"
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_initial_deck_is_sent_to_its_owner_only():
    api = Api()
    code, alice, bob = lobby_of_two(api)
    call(api, "/api/start", code=code, token=alice)
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    decks = {d["name"]: d for d in race["decks"]}
    assert set(decks) == {"1R", "1S"}  # seulement les coureurs d'Alice
    rouleur = {c["label"]: c["count"] for c in decks["1R"]["cards"]}
    assert rouleur == {"3": 3, "4": 3, "5": 3, "6": 3, "7": 3}
    assert sum(c["count"] for c in decks["1S"]["cards"]) == 15 and "9" in [c["label"] for c in decks["1S"]["cards"]]
    play_all_hands(api, code, alice, bob)  # le deck affiché reste celui du départ
    later = call(api, "/api/state", "GET", code=code, token=alice)["race"]["decks"]
    assert {d["name"]: d["cards"] for d in later} == {n: d["cards"] for n, d in decks.items()}
    assert call(api, "/api/state", "GET", code=code, token=bob)["race"]["decks"][0]["name"].startswith("2")


def test_shared_screen_sees_the_race_but_no_private_information():
    api = Api()
    code, alice, bob = lobby_of_two(api)
    assert "lobby" in call(api, "/api/state", "GET", code=code, watch=1)
    call(api, "/api/start", code=code, token=alice)
    screen = call(api, "/api/state", "GET", code=code, watch=1)
    race = screen["race"]
    assert race["map"] and race["profile"] and race["log"] is not None
    assert race["hands"] == [] and race["hand"] == [] and race["decks"] == [] and race["my_riders"] == []
    assert not race["can_act"] and screen["me"]["team"] is None
    assert [p["name"] for p in screen["players"]] == ["Alice", "Bob"]  # l'écran n'est pas un joueur du salon
    with pytest.raises(OnlineError):  # sans jeton, on ne peut rien jouer
        call(api, "/api/advance", code=code, watch=1, phase="movement")


def test_online_3d_view_is_an_option():
    api = Api()
    created = api.handle("POST", "/api/create", {}, {"name": "Alice"})
    code, token = created["code"], created["token"]
    api.handle("POST", "/api/start", {}, {"code": code, "token": token})

    def race(**query):
        return api.handle("GET", "/api/state", {"code": code, "token": token, **query}, {})["race"]

    flat = race()  # par défaut : la carte 2D
    assert flat["iso_angle"] is None and flat["geo"]["iso"] is False
    auto = race(iso="auto")
    assert auto["iso_angle"] % 90 in (30, 45, 60) and auto["geo"]["iso"] is True
    assert race(iso="390")["iso_angle"] == 30  # 390° = 30°
    assert race(iso="abc")["iso_angle"] is None  # illisible : carte 2D, sans erreur


def test_the_3d_scene_is_sent_once_per_race():
    api = Api()
    created = api.handle("POST", "/api/create", {}, {"name": "Alice"})
    code, token = created["code"], created["token"]
    api.handle("POST", "/api/start", {}, {"code": code, "token": token})

    def race(**query):
        return api.handle("GET", "/api/state", {"code": code, "token": token, **query}, {})["race"]

    plain = race()
    assert "scene" not in plain and plain["scene_id"].startswith("course:")  # sans vue 3D : pas de scène
    first = race(scene="-")  # vue 3D, rien en main : la route part avec l'état
    scene = first["scene"]
    assert len(scene["squares"]) == len(scene["z"]) - 1 and scene["n"] > 0
    assert any(len(str(p[0]).split(".")[-1]) == 3 for sq in scene["squares"] for p in sq["left"])  # au millième
    assert "scene" not in race(scene=str(first["scene_id"]))  # déjà reçue : seulement les coureurs
    assert all("crashed" in r for r in first["riders"])
    api.handle("POST", "/api/lobby", {}, {"code": code, "token": token})
    api.handle("POST", "/api/start", {}, {"code": code, "token": token})
    again = race(scene=str(first["scene_id"]))  # nouvelle course : nouvelle scène
    assert again["scene_id"] != first["scene_id"] and "scene" in again


def test_the_lobby_sends_the_3d_scene_of_the_chosen_track():
    api = Api()
    created = api.handle("POST", "/api/create", {}, {"name": "Alice"})
    code, token = created["code"], created["token"]

    def lobby(**query):
        return api.handle("GET", "/api/state", {"code": code, "token": token, **query}, {})["lobby"]

    assert "scene" not in lobby()  # sans vue 3D : pas de scène
    first = lobby(scene="-")
    assert first["scene"]["squares"] and "scene" not in lobby(scene=first["scene_id"])
    other = next(p["key"] for p in api.handle("GET", "/api/info", {}, {})["parcours"] if p["key"] != first["parcours"])
    api.handle("POST", "/api/settings", {}, {"code": code, "token": token, "parcours": other})
    changed = lobby(scene=first["scene_id"])  # autre parcours : nouvelle scène
    assert changed["scene_id"] != first["scene_id"] and changed["scene"]["n"] > 0


def test_finished_race_sends_its_history_for_the_replay():
    api = Api()
    code, alice, _bob = lobby_of_two(api)
    call(api, "/api/settings", code=code, token=alice, seats=["joueur", "ia"])
    call(api, "/api/start", code=code, token=alice)
    room = api.lobby.room(code)
    from flamme_rouge.ai import choose_card
    for _ in range(400):
        ctl = room.ctl
        if ctl.phase == FINISHED:
            break
        if ctl.phase == CHOOSE:
            for rider, hand in list(ctl.hands.items()):
                ctl.choose_for(rider, choose_card(room.game, rider, hand))
        else:
            ctl.advance()
        room.bump()
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["finished"] and race["history"][0]["label"] == "Départ"
    names = {r["name"] for r in race["riders"]}
    assert set(race["history"][-1]["pos"]) == names
    # le profil sans coureurs (la page y place les coureurs de la relecture) : ni pastilles ni groupes
    dots = lambda prims: [p for p in prims if p[0] == "oval" and p[6] == "#ffffff"]  # noqa: E731
    assert len(dots(race["profile"])) == len(names) and dots(race["profile_base"]) == []
    assert not any(p[0] == "text" and "PELOTON" in str(p[3]) for p in race["profile_base"])


def test_same_screen_one_player_holds_several_teams():
    """Même écran : l'hôte prend aussi les autres places ; il voit et joue les mains de toutes ses équipes."""
    api = Api()
    host = call(api, "/api/create", name="Alice")
    code, alice = host["code"], host["token"]
    call(api, "/api/settings", code=code, token=alice, teams=3)
    call(api, "/api/seat", code=code, token=alice, team=1, also=True)
    call(api, "/api/seat", code=code, token=alice, team=2, also=True)
    state = call(api, "/api/state", "GET", code=code, token=alice)
    assert state["me"]["teams"] == [0, 1, 2]
    assert [s["player"] for s in state["lobby"]["seats"]] == ["Alice"] * 3
    guest = call(api, "/api/join", code=code, name="Bob")["token"]
    with pytest.raises(OnlineError):  # une place tenue sur le même écran n'est plus libre
        call(api, "/api/seat", code=code, token=guest, team=1)
    call(api, "/api/seat", code=code, token=alice, team=1, drop=True)  # lâche seulement l'équipe 2
    assert call(api, "/api/state", "GET", code=code, token=alice)["me"]["teams"] == [0, 2]
    call(api, "/api/seat", code=code, token=guest, team=1)
    call(api, "/api/settings", code=code, token=alice, teams=2)  # l'équipe 3 disparaît : la place est lâchée
    assert call(api, "/api/state", "GET", code=code, token=alice)["me"]["teams"] == [0]
    call(api, "/api/seat", code=code, token=guest, team=None)
    call(api, "/api/seat", code=code, token=alice, team=1, also=True)

    call(api, "/api/start", code=code, token=alice)
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["my_turn"] and sorted({h["team"] for h in race["hands"]}) == [0, 1]
    assert len(race["hands"]) == 4 and len(race["decks"]) == 4
    assert call(api, "/api/state", "GET", code=code, token=guest)["race"]["hands"] == []  # Bob regarde
    call(api, "/api/cards", code=code, token=alice, choices={h["name"]: 0 for h in race["hands"]})
    race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
    assert race["hands"] == [] and race["can_act"]
    for _ in range(400):
        race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
        if race["phase"] == FINISHED:
            break
        if race["hands"]:
            call(api, "/api/cards", code=code, token=alice, choices={h["name"]: 0 for h in race["hands"]})
        else:
            call(api, "/api/advance", code=code, token=alice, phase=race["phase"])
    assert race["phase"] == FINISHED and race["winner"]


def test_local_launcher_server_takes_a_free_port():
    """python main.py : le serveur local prend un port libre, sur ce PC seulement."""
    from online.server import start_server

    httpd = start_server("127.0.0.1", 0)
    try:
        host, port = httpd.server_address[:2]
        assert host == "127.0.0.1" and port > 0
    finally:
        httpd.server_close()


def test_fatigue_is_shown_after_the_click_only():
    api = Api()
    created = api.handle("POST", "/api/create", {}, {"name": "Alice"})
    code, token = created["code"], created["token"]
    api.handle("POST", "/api/start", {}, {"code": code, "token": token})

    def race():
        return api.handle("GET", "/api/state", {"code": code, "token": token}, {})["race"]

    hands = race()["hands"]
    api.handle("POST", "/api/cards", {}, {"code": code, "token": token, "choices": {h["name"]: 0 for h in hands}})
    for _ in range(4):
        state = race()
        assert state["fatigue"] is None  # rien tant qu'on n'a pas cliqué sur « Fatigue »
        if state["phase"] == "exhaustion":
            break
        api.handle("POST", "/api/advance", {}, {"code": code, "token": token, "phase": state["phase"]})
    state = race()
    assert state["phase"] == "exhaustion"
    occupied = {r["position"] for r in state["riders"]}
    expected = {r["name"] for r in state["riders"] if r["position"] + 1 not in occupied}
    api.handle("POST", "/api/advance", {}, {"code": code, "token": token, "phase": "exhaustion"})
    after = race()
    assert set(after["fatigue"]["names"]) == expected  # au clic : ceux qui ont pris une carte Fatigue


def test_the_riders_camera_frames_every_rider():
    api = Api()
    created = api.handle("POST", "/api/create", {}, {"name": "Alice"})
    code, token = created["code"], created["token"]
    api.handle("POST", "/api/start", {}, {"code": code, "token": token})
    room = api.lobby.room(code)
    for i, rider in enumerate(room.game.riders):  # coureurs étalés, de la case 3 à la case 3 + 9 × (n − 1)
        rider.position = 3 + 9 * i
    front = max(r.position for r in room.game.riders)
    room.bump()

    def view(camera):
        return api.handle("GET", "/api/state", {"code": code, "token": token, "camera": camera}, {})["race"]["view"]

    from flamme_rouge.boardview import follow_window
    assert follow_window(room.game, "course") == (0, front + 10)  # du dernier au premier, et 10 cases devant
    assert view("course") != view("tete") and view("course") != view("peloton")
