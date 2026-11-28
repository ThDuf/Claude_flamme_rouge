"""Point d'entrée : le jeu dans le navigateur.

    python main.py                  # un serveur sur ce PC (port libre), puis la page du jeu s'ouvre
    python main.py --port 8770      # un port choisi
    python main.py --no-browser     # sans ouvrir le navigateur (l'adresse s'affiche)

Le serveur n'écoute que ce PC. Plusieurs joueurs peuvent partager l'écran : dans le salon, « + Ici aussi » ajoute
une équipe jouée sur cet appareil. Pour jouer à distance, voir docs/en_ligne.md (site hébergé sur Render).
L'éditeur de parcours est à l'adresse /editeur (lien sur l'accueil et dans le salon).
"""
import argparse
import threading
import webbrowser

from online.server import start_server


def main_browser(port: int = 0, open_browser: bool = True) -> None:
    """Serveur sur ce PC seulement (127.0.0.1), sur un port libre si `port` vaut 0, puis la page du jeu."""
    httpd = start_server("127.0.0.1", port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"Flamme Rouge : {url}  (laisse cette fenêtre ouverte ; Ctrl+C pour arrêter)")
    if open_browser:
        threading.Timer(0.3, webbrowser.open, [url]).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Serveur arrêté.")
    finally:
        httpd.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Flamme Rouge dans le navigateur")
    parser.add_argument("--port", type=int, default=0, help="port du serveur local (défaut : un port libre)")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    args = parser.parse_args()
    main_browser(args.port, not args.no_browser)


if __name__ == "__main__":
    main()
