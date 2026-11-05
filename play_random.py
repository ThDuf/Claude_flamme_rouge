"""Joue une partie complète où chaque coureur joue une carte au hasard.

    python play_random.py            # 2 équipes, graine aléatoire
    python play_random.py 4 42       # 4 équipes, graine 42 (partie reproductible)
"""
import sys

from flamme_rouge import Game
from flamme_rouge.display import render

teams = int(sys.argv[1]) if len(sys.argv) > 1 else 2
seed = int(sys.argv[2]) if len(sys.argv) > 2 else None

game = Game(num_teams=teams, seed=seed)
print(f"Départ ({teams} équipes)\n{render(game)}\n")
while not game.finished:
    report = game.play_turn()
    played = " ".join(f"{name}:{card}" for name, card in report.played.items())
    print(f"Tour {report.turn} — cartes {played}")
    print(f"  aspiration: {report.slipstreamed or '-'} | fatigue: {report.exhausted or '-'}")
    print(render(game), "\n")

w = game.winner
print(f"Victoire de l'équipe {w.team + 1} avec le {w.kind}, case {w.position} (arrivée à {len(game.track)}), tour {game.turn}")
