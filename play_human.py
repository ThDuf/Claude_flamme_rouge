"""Partie à plusieurs sur le même clavier : chaque équipe choisit ses cartes.

    python play_human.py              # 2 équipes
    python play_human.py 3            # 3 équipes
    python play_human.py 2 42         # 2 équipes, graine 42 (même mélange à chaque fois)
    python play_human.py --secret     # masque la main de l'équipe précédente (lignes vides)

L'écran n'est jamais effacé : tu peux remonter pour revoir les tours précédents.
Chaque phase du tour (mouvement, aspiration, fatigue) démarre après une pression sur Entrée.
"""
import argparse
import sys

from flamme_rouge import ROULEUR, SPRINTEUR, Game
from flamme_rouge.decks import all_decks_text
from flamme_rouge.tiles import load_track_file
from flamme_rouge.display import (
    BOLD,
    FINISH,
    TEAM_COLORS,
    board_view,
    legend,
    paint,
    rider_tag,
    terrain_symbol,
)

WIDTH = 64
SECRET = False


def banner(text: str) -> None:
    print("\n" + paint(f"═══ {text} " + "═" * max(3, WIDTH - len(text) - 5), FINISH))


def pause(text: str) -> None:
    input(paint(f"\n▶ {text}", BOLD))


def team_tag(team: int) -> str:
    return paint(f"Équipe {team + 1}", TEAM_COLORS[team])


def describe(card) -> str:
    return f"{card.value} (fatigue)" if card.exhaustion else str(card.value)


def hide() -> None:
    print("\n" * 60)


def human_chooser(game: Game, rider, hand):
    if SECRET and rider.kind == ROULEUR:
        hide()
        pause(f"{team_tag(rider.team)} : les autres ne regardent pas ! Entrée pour voir ta main")

    print(f"\n{team_tag(rider.team)} — {rider.kind} {rider_tag(rider)} (case {rider.position})")
    ahead = " ".join(terrain_symbol(game, s) for s in range(rider.position + 1, rider.position + 11))
    print(f"  devant toi : {ahead}")
    print(f"  pioche : {len(rider.draw_pile)} cartes | recyclage : {len(rider.recycle)} cartes")
    hand = sorted(hand, key=lambda c: c.value)
    for i, card in enumerate(hand, 1):
        print(f"    [{i}] {describe(card)}")
    while True:
        answer = input("  Quelle carte jouer ? (d = voir les decks) ").strip().lower()
        if answer == "d":
            print("\n" + all_decks_text(game) + "\n")
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(hand):
            card = hand[int(answer) - 1]
            break
        print(f"  Tape un nombre entre 1 et {len(hand)}, ou d pour voir les decks.")
    print("  ✔ carte posée face cachée")
    if SECRET and rider.kind == SPRINTEUR:
        hide()
    return card


def show_movement(game: Game, played, order, start) -> None:
    for rider in order:
        card = played[rider]
        wanted = card.value
        effective = game._effective_value(start[rider], wanted)
        notes = []
        if effective > wanted:
            notes.append("descente : 5 minimum")
        elif effective < wanted:
            notes.append("montée : plafonné à 5" if effective <= 5 else f"montée : s'arrête au pied ({effective})")
        if rider.position - start[rider] < effective:
            notes.append("case pleine : s'arrête avant")
        note = f"  ({', '.join(notes)})" if notes else ""
        print(
            f"  {rider_tag(rider)}  carte {describe(card):<12} "
            f"case {start[rider]:>2} → {rider.position:>2}{note}"
        )


def play_turn(game: Game) -> None:
    banner(f"TOUR {game.turn + 1} — choix des cartes")
    print(board_view(game))

    played = game.energy_phase(human_chooser)

    # --- Mouvement (après Entrée) ---
    pause("Toutes les cartes sont posées. Entrée pour révéler les cartes et lancer le MOUVEMENT")
    banner(f"TOUR {game.turn + 1} — mouvement")
    order = sorted(game.riders, key=lambda r: (-r.position, r.lane))  # du premier au dernier
    start = {r: r.position for r in game.riders}
    game.movement_phase(played)
    show_movement(game, played, order, start)
    print()
    print(board_view(game))

    # --- Aspiration (après Entrée) ---
    pause("Entrée pour lancer l'ASPIRATION")
    banner(f"TOUR {game.turn + 1} — aspiration")
    before = {r: r.position for r in game.riders}
    slipstreamed = game.apply_slipstream()
    if slipstreamed:
        for r in sorted(slipstreamed, key=lambda r: -r.position):
            gain = r.position - before[r]
            print(f"  {rider_tag(r)} aspiré : case {before[r]} → {r.position} (+{gain})")
    else:
        print("  Personne n'est aspiré.")
    print()
    print(board_view(game))

    # --- Fatigue (après Entrée) ---
    pause("Entrée pour la FATIGUE")
    banner(f"TOUR {game.turn + 1} — fatigue")
    exhausted = game.apply_exhaustion()
    if exhausted:
        for r in exhausted:
            print(f"  {rider_tag(r)} reçoit une carte Fatigue (2) dans sa pile de recyclage")
    else:
        print("  Personne n'est fatigué.")
    game.check_finish()
    game.turn += 1


def main() -> None:
    global SECRET
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # pour les symboles ▲ ▼ ● sous Windows
    except AttributeError:
        pass

    parser = argparse.ArgumentParser(description="Flamme Rouge à plusieurs sur le même clavier")
    parser.add_argument("teams", nargs="?", type=int, default=2, help="nombre d'équipes (2 à 4)")
    parser.add_argument("seed", nargs="?", type=int, default=None, help="graine du mélange")
    parser.add_argument("--secret", action="store_true", help="masque la main entre deux équipes")
    parser.add_argument("--track", help="parcours .json créé avec editor.py")
    args = parser.parse_args()
    SECRET = args.secret

    track = None
    if args.track:
        try:
            track = load_track_file(args.track)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Impossible de charger le parcours : {exc}")
    game = Game(track=track, num_teams=args.teams, seed=args.seed)
    banner("FLAMME ROUGE")
    print(legend())
    for team in range(args.teams):
        print(f"  {team_tag(team)} : rouleur {paint(f'{team + 1}R', TEAM_COLORS[team])}, "
              f"sprinteur {paint(f'{team + 1}S', TEAM_COLORS[team])}")

    while not game.finished:
        play_turn(game)
        if not game.finished:
            pause("Entrée pour le tour suivant")

    w = game.winner
    banner("ARRIVÉE")
    print(board_view(game))
    print(f"\nVictoire de l'{team_tag(w.team)} avec le {w.kind} {rider_tag(w)} "
          f"(case {w.position}, la ligne est à {len(game.track)}) au tour {game.turn} !")


if __name__ == "__main__":
    main()
