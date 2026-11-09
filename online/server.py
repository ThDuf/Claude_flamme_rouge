"""Serveur web des parties à distance (bibliothèque standard seulement).

    python -m online.server            # http://127.0.0.1:8770 (seulement ce PC ; le tunnel s'y branche)
    python -m online.server --lan      # aussi depuis les autres appareils du réseau local

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

from online.rooms import SEAT_KINDS, TEAM_COLORS, Lobby, OnlineError  # noqa: E402
from flamme_rouge.extensions import EXTENSIONS  # noqa: E402

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_FILES = {"/": "index.html", "/index.html": "index.html", "/app.js": "app.js", "/style.css": "style.css"}
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

    def __init__(self, lobby: Optional[Lobby] = None):
        self.lobby = lobby or Lobby()

    def handle(self, method: str, path: str, query: dict, body: dict) -> dict:
        if method == "GET" and path == "/api/info":
            return {"parcours": self.lobby.parcours_list(), "teams": TEAM_COLORS,
                    "extensions": [{"key": k, "label": v[0], "description": v[1]} for k, v in EXTENSIONS.items()],
                    "seat_kinds": SEAT_KINDS}
        if method == "POST" and path == "/api/create":
            room, player = self.lobby.create(body.get("name"))
            return {"code": room.code, "token": player.token}
        room = self.lobby.room(body.get("code") or query.get("code"))
        with room.lock:
            if method == "POST" and path == "/api/join":
                return {"code": room.code, "token": room.join(body.get("name")).token}
            player = room.player(str(body.get("token") or query.get("token") or ""))
            if method == "GET" and path == "/api/state":
                since = int(query.get("since") or 0)
                camera = str(query.get("camera") or "")
                if since == room.version:
                    return {"same": True, "version": room.version}
                return compact(room.state(player, camera))
            if method != "POST":
                raise OnlineError("Action inconnue.")
            if path == "/api/seat":
                team = body.get("team")
                room.take_seat(player, None if team is None else int(team))
            elif path == "/api/settings":
                room.configure(player, body.get("parcours"), body.get("teams"), body.get("extensions"),
                               body.get("seats"))
            elif path == "/api/start":
                room.start(player)
            elif path == "/api/card":
                room.play_card(player, int(body.get("index", -1)))
            elif path == "/api/advance":
                room.advance(player, str(body.get("phase") or ""))
            elif path == "/api/lobby":
                room.back_to_lobby(player)
            else:
                raise OnlineError("Action inconnue.")
            return {"ok": True, "version": room.version}


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FlammeRouge/1.0"

        def log_message(self, fmt, *args):  # journal discret : seulement les erreurs
            pass

        def _send(self, status: int, data: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
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
            self._send(200, data, kind + ("; charset=utf-8" if kind.startswith("text/") or kind.endswith("javascript") else ""))

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path.startswith("/api/"):
                return self._api("POST")
            self._send(404, b"Introuvable", "text/plain; charset=utf-8")

    return Handler


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT) -> None:
    api = Api()
    httpd = ThreadingHTTPServer((host, port), make_handler(api))
    httpd.daemon_threads = True
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
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--lan", action="store_true", help="accepte aussi les appareils du réseau local")
    args = parser.parse_args()
    serve("0.0.0.0" if args.lan else "127.0.0.1", args.port)


if __name__ == "__main__":
    main()
