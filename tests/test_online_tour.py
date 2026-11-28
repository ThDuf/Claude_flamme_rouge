"""Grand Tour en ligne : réglage dans le salon, étapes à la suite, résultats entre deux étapes, classement final."""
import pytest

from flamme_rouge.controller import FINISHED
from online.rooms import OnlineError
from online.server import Api


def call(api, path, method="POST", **body):
    query = {k: str(v) for k, v in body.items()} if method == "GET" else {}
    return api.handle(method, path, query, {} if method == "GET" else body)


def official_keys(api, n):
    keys = [p["key"] for p in call(api, "/api/info", "GET")["parcours"] if p["key"].startswith("officiel:")]
    assert len(keys) >= n
    return keys[:n]


def play_stage(api, code, *tokens):
    """Joue l'étape en cours jusqu'à l'arrivée : chaque joueur pose la première carte de chacune de ses mains."""
    for _ in range(400):
        race = call(api, "/api/state", "GET", code=code, token=tokens[0])["race"]
        if race["phase"] == FINISHED:
            return race
        if race["phase"] in ("choose", "breakaway"):
            for token in tokens:
                mine = call(api, "/api/state", "GET", code=code, token=token)["race"]
                if mine["hands"]:
                    call(api, "/api/cards", code=code, token=token, choices={h["name"]: 0 for h in mine["hands"]})
                elif mine["bid"]:
                    call(api, "/api/bid_rider", code=code, token=token, rider=None)
        else:
            call(api, "/api/advance", code=code, token=tokens[0], phase=race["phase"])
    raise AssertionError("l'étape ne finit pas")


def test_tour_settings_in_the_lobby():
    api = Api()
    host = call(api, "/api/create", name="Alice")
    code, alice = host["code"], host["token"]
    keys = official_keys(api, 3)
    call(api, "/api/settings", code=code, token=alice, mode="tour", tour_stages=keys[:2])
    with pytest.raises(OnlineError):  # au moins 3 étapes
        call(api, "/api/start", code=code, token=alice)
    with pytest.raises(OnlineError):
        call(api, "/api/settings", code=code, token=alice, tour_stages=["inconnu"])
    call(api, "/api/settings", code=code, token=alice, tour_stages=keys, rest_after=2)
    lobby = call(api, "/api/state", "GET", code=code, token=alice)["lobby"]
    assert lobby["mode"] == "tour" and [s["key"] for s in lobby["tour_stages"]] == keys
    assert lobby["rest_after"] == 2
    call(api, "/api/settings", code=code, token=alice, rest_after=3)  # pas de repos après la dernière étape
    assert call(api, "/api/state", "GET", code=code, token=alice)["lobby"]["rest_after"] is None


def test_a_whole_online_tour():
    api = Api()
    host = call(api, "/api/create", name="Alice")
    code, alice = host["code"], host["token"]
    bob = call(api, "/api/join", code=code, name="Bob")["token"]
    keys = official_keys(api, 3)
    call(api, "/api/settings", code=code, token=alice, mode="tour", tour_stages=keys, rest_after=1)
    call(api, "/api/start", code=code, token=alice)

    for number in (1, 2, 3):
        race = call(api, "/api/state", "GET", code=code, token=alice)["race"]
        assert race["tour"]["stage"] == number and race["tour"]["stages"] == 3
        if number > 1:  # après la 1re étape, les maillots sont portés et le général est affiché
            assert race["tour"]["jerseys"] and race["tour"]["gc"]
        play_stage(api, code, *((alice, bob) if number % 2 else (bob, alice)))
        with pytest.raises(OnlineError):  # une étape suivante ne se lance pas par erreur pendant la course
            call(api, "/api/tour_next", code=code, token="inconnu", stage=number, screen="race")
        call(api, "/api/tour_next", code=code, token=bob, stage=number, screen="race")
        call(api, "/api/tour_next", code=code, token=alice, stage=number, screen="race")  # double clic : rien
        call(api, "/api/tour_next", code=code, token=alice, stage=number - 1, screen="results")  # périmé : rien
        results = call(api, "/api/state", "GET", code=code, token=alice)["tour_results"]
        assert results["stage"] == number and len(results["arrival"]) == 4
        assert results["gc"][0]["gap"] == "" and results["points"]
        assert any("repos" in n for n in results["notes"]) == (number == 1)
        if number < 3:
            assert not results["finished"] and results["next"]
            call(api, "/api/tour_next", code=code, token=alice, stage=number, screen="results")
        else:
            assert results["finished"] and results["final"]["winner"]
            assert len(results["final"]["ranking"]) == 2
            call(api, "/api/tour_next", code=code, token=alice, stage=number, screen="results")  # fini : rien
            assert "tour_results" in call(api, "/api/state", "GET", code=code, token=alice)
    call(api, "/api/lobby", code=code, token=alice)
    assert "lobby" in call(api, "/api/state", "GET", code=code, token=alice)
