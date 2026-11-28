"""Serveur web des parties à distance (bibliothèque standard seulement).

    PORT=10000 python -m online.server # sur Render : écoute sur le port donné, pour tout Internet
    python -m online.server            # pour essayer sur ce PC avant de déployer : http://127.0.0.1:8770

Les navigateurs demandent l'état du salon environ deux fois par seconde (`/api/state?since=version` : rien
n'est renvoyé si rien n'a changé). Voir docs/en_ligne.md.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional
from urllib.parse import parse_qs, urlparse

if __package__ in (None, ""):  # lancé comme un script : le dossier du jeu doit être importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from online import editor_api  # noqa: E402
from online.rooms import SEAT_KINDS, TEAM_COLORS, Lobby, OnlineError, Player, parse_iso, parse_view  # noqa: E402
from flamme_rouge.extensions import EXTENSIONS  # noqa: E402
from flamme_rouge import palette as pal  # noqa: E402
from flamme_rouge.boardview import (  # noqa: E402
    CYCLIST_FRAME, CYCLIST_HEIGHT, CYCLIST_SKIN, CYCLIST_WHEEL, FX_RAIN, FX_SUN, FX_WIND, GROUP_COLORS,
)
from flamme_rouge.weather import CROSSWIND, HEADWIND, RAIN, SUNNY, TAILWIND  # noqa: E402

# couleurs des animations du navigateur (les mêmes que celles du dessin du serveur, boardview.py)
FX_COLORS = {
    "rain": FX_RAIN, "sun": FX_SUN, "wind": {k: v for k, v in FX_WIND.items()},
    "grass": pal.GRASS, "road": pal.TERRAIN_FILL["."], "card": pal.CARD, "shadow": pal.SHADOW,
    "rider_outline": pal.RIDER_OUTLINE, "current_ring": pal.CURRENT_RING, "groups": GROUP_COLORS,
    "cyclist": {"wheel": CYCLIST_WHEEL, "frame": CYCLIST_FRAME, "skin": CYCLIST_SKIN, "height": CYCLIST_HEIGHT},
    "effects": {"rain": RAIN, "tailwind": TAILWIND, "headwind": HEADWIND,
                                                    "crosswind": CROSSWIND, "sunny": SUNNY},
}

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css",
                "/draw.js": "draw.js", "/board3d.js": "board3d.js", "/editeur": "editor.html", "/editor.js": "editor.js"}
# Three.js (vue 3D), copié tel quel depuis le paquet npm « three » : le numéro de version est dans le chemin, donc
# le navigateur peut le garder en cache (un changement de version change l'adresse)
THREE_DIR = "vendor/three-0.170.0"
STATIC_FILES.update({f"/{THREE_DIR}/{name}": f"{THREE_DIR}/{name}" for name in (
    "three.module.min.js", "addons/controls/OrbitControls.js", "addons/renderers/CSS2DRenderer.js", "LICENSE.txt")})
MAX_BODY = 16 * 1024
DEFAULT_PORT = 8770


def compact(value):
    """Arrondit les nombres à virgule (formes du plateau) pour alléger ce qui part sur le réseau."""
    if isinstance(value, float):
        return round(value, 1)
    if isinstance(value, (list, tuple)):
        return [compact(v) for v in value]
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()}
    return value


class Api:
    """Les actions du site, indépendantes du protocole HTTP (testées directement)."""

    def __init__(self, lobby: Optional[Lobby] = None, local: bool = False):
        """`local` : serveur sur ce PC seulement (python main.py) ; l'éditeur peut alors enregistrer des fichiers."""
        self.lobby = lobby or Lobby()
        self.local = local

    def handle(self, method: str, path: str, query: dict, body: dict) -> dict:
        if path.startswith("/api/editor/"):
            return self._editor(method, path[len("/api/editor/"):], query, body)
        if method == "GET" and path == "/api/info":
            return {"parcours": self.lobby.parcours_list(), "local": self.local, "teams": TEAM_COLORS,
                    "extensions": [{"key": k, "label": v[0], "description": v[1]} for k, v in EXTENSIONS.items()],
                    "seat_kinds": SEAT_KINDS, "colors": FX_COLORS}
        if method == "POST" and path == "/api/create":
            room, player = self.lobby.create(body.get("name"))
            return {"code": room.code, "token": player.token}
        room = self.lobby.room(body.get("code") or query.get("code"))
        with room.lock:
            if method == "POST" and path == "/api/join":
                return {"code": room.code, "token": room.join(body.get("name")).token}
            if method == "GET" and path == "/api/state" and query.get("watch"):
                # écran partagé : la course vue par un spectateur (ni main ni deck), sans jeton
                player = Player("", "Écran partagé")
            else:
                player = room.player(str(body.get("token") or query.get("token") or ""))
            if method == "GET" and path == "/api/state":
                since = int(query.get("since") or 0)
                camera = str(query.get("camera") or "")
                view = parse_view(query.get("view"))
                iso = parse_iso(query.get("iso"))
                scene = query.get("scene")
                scene = int(scene) if scene and str(scene).isdigit() else None
                if since == room.version:
                    return {"same": True, "version": room.version}
                state = room.state(player, camera, view, iso, scene)
                road = state["race"].pop("scene", None) if "race" in state else None
                state = compact(state)
                if road is not None:  # au millième : compact() arrondit au dixième, trop grossier pour les virages
                    state["race"]["scene"] = road
                return state
            if method != "POST":
                raise OnlineError("Action inconnue.")
            if path == "/api/seat":
                team = body.get("team")
                room.take_seat(player, None if team is None else int(team), also=bool(body.get("also")),
                               drop=bool(body.get("drop")))
            elif path == "/api/settings":
                room.configure(player, body.get("parcours"), body.get("teams"), body.get("extensions"),
                               body.get("seats"), body.get("breakaway"), body.get("mode"), body.get("tour_stages"),
                               body.get("rest_after"))
            elif path == "/api/bid_rider":
                name = body.get("rider")
                room.bid_rider(player, None if name is None else str(name))
            elif path == "/api/start":
                room.start(player)
            elif path == "/api/card":
                room.play_card(player, int(body.get("index", -1)))
            elif path == "/api/cards":
                room.play_cards(player, body.get("choices"))
            elif path == "/api/advance":
                room.advance(player, str(body.get("phase") or ""))
            elif path == "/api/tour_next":
                room.tour_next(player, int(body.get("stage") or 0), str(body.get("screen") or ""))
            elif path == "/api/lobby":
                room.back_to_lobby(player)
            else:
                raise OnlineError("Action inconnue.")
            return {"ok": True, "version": room.version}

    def _editor(self, method: str, route: str, query: dict, body: dict) -> dict:
        """Éditeur de parcours (page /editeur) : voir online/editor_api.py."""
        if method == "GET" and route == "tiles":
            return editor_api.catalog()
        if method == "GET" and route == "open":
            return {"parcours": editor_api.openable(self.lobby), "local": self.local}
        if method == "GET" and route == "load":
            return editor_api.load(self.lobby, str(query.get("key") or ""))
        if method == "POST" and route == "check":
            selected = body.get("selected")
            return editor_api.check(body.get("tiles"), selected if isinstance(selected, int) else None)
        if method == "POST" and route == "save":
            if not self.local:
                raise OnlineError("Sur le site en ligne, télécharge le fichier : l'enregistrement se fait sur ton PC.")
            return editor_api.save(self.lobby, body.get("name"), body.get("tiles"))
        raise OnlineError("Action inconnue.")


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FlammeRouge/1.0"

        def log_message(self, fmt, *args):  # journal discret : seulement les erreurs
            pass

        def _send(self, status: int, data: bytes, content_type: str, cache: bool = False) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=31536000, immutable" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _json(self, status: int, payload: dict) -> None:
            self._send(status, json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                       "application/json; charset=utf-8")

        def _api(self, method: str) -> None:
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            body = {}
            if method == "POST":
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
                    return self._json(413, {"error": "Requête trop grosse."})
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError
                except ValueError:
                    return self._json(400, {"error": "Requête illisible."})
            try:
                self._json(200, api.handle(method, url.path, query, body))
            except OnlineError as exc:
                self._json(400, {"error": str(exc)})
            except (ValueError, TypeError):
                self._json(400, {"error": "Requête invalide."})
            except Exception as exc:  # une erreur du jeu ne doit pas faire tomber le serveur
                print("Erreur :", repr(exc), file=sys.stderr)
                self._json(500, {"error": "Erreur du serveur."})

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/api/"):
                return self._api("GET")
            name = STATIC_FILES.get(path)
            if name is None:
                return self._send(404, b"Introuvable", "text/plain; charset=utf-8")
            with open(os.path.join(STATIC_DIR, name), "rb") as handle:
                data = handle.read()
            kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self._send(200, data, kind + ("; charset=utf-8" if kind.startswith("text/") or kind.endswith("javascript") else ""),
                       cache=name.startswith(THREE_DIR))

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path.startswith("/api/"):
                return self._api("POST")
            self._send(404, b"Introuvable", "text/plain; charset=utf-8")

    return Handler


class GameServer(ThreadingHTTPServer):
    # Sous Windows, « réutiliser l'adresse » laisse deux serveurs écouter le même port sans erreur (l'ancien
    # continue de répondre) : on refuse plutôt de démarrer si le port est déjà pris.
    allow_reuse_address = os.name != "nt"


def start_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> GameServer:
    """Le serveur prêt à écouter (port 0 : un port libre, voir `server_address`). Quitte si le port est pris."""
    try:
        httpd = GameServer((host, port), make_handler(Api(local=host in ("127.0.0.1", "localhost", "::1"))))
    except OSError:
        print(f"Le port {port} est déjà utilisé : un serveur Flamme Rouge tourne sans doute déjà "
              f"(ferme sa fenêtre), ou choisis-en un autre avec --port.")
        sys.exit(1)
    httpd.daemon_threads = True
    return httpd


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    httpd = start_server(host, port)
    shown = "127.0.0.1" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"Flamme Rouge en ligne : http://{shown}:{port}  (Ctrl+C pour arrêter)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Serveur arrêté.")
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serveur des parties à distance de Flamme Rouge")
    parser.add_argument("--port", type=int, default=None, help="pour un essai sur ce PC (défaut : 8770)")
    args = parser.parse_args()
    # Render fournit le port dans PORT et joint le serveur de l'extérieur du conteneur.
    hosted_port = os.environ.get("PORT")
    if hosted_port and args.port is None:
        serve("0.0.0.0", int(hosted_port))
    else:  # essai sur ce PC : seulement lui
        serve("127.0.0.1", args.port or DEFAULT_PORT)


if __name__ == "__main__":
    main()
