"""Interface de jeu (tkinter, inclus avec Python).

Le plus simple est de passer par le menu :   python main.py

Lancement direct, sans menu :
    python gui.py              # 2 équipes
    python gui.py 3            # 3 équipes
    python gui.py 2 42         # 2 équipes, graine 42 (même mélange à chaque fois)
    python gui.py --secret     # cache la main entre deux équipes
    python gui.py --no-anim    # sans animations
    python gui.py --track mon_parcours.json   # joue un parcours créé avec editor.py

Les règles viennent du moteur (flamme_rouge) ; ce fichier ne fait qu'afficher et relayer les clics.
"""
import argparse
import time
import tkinter as tk
from tkinter import messagebox

import ui
from flamme_rouge import ROULEUR, Game
from flamme_rouge import palette as pal
from flamme_rouge.animation import FRAME_MS, moves_between, movement_animation, slipstream_animation, snapshot
from flamme_rouge.boardview import profile_primitives, map_transform, pan_view, zoom_view, BOARD_W, MAP_H, TEAM_TEXT, map_primitives, map_window, terrain_text
from flamme_rouge.geometry import layout_squares, point_on_road
from flamme_rouge.controller import (
    CHOOSE,
    EXHAUSTION,
    FINISHED,
    MOVEMENT,
    SLIPSTREAM,
    TurnController,
)
from flamme_rouge.decks import deck_text
from flamme_rouge.tiles import load_track_file

PHASE_TITLES = {
    CHOOSE: "choix des cartes",
    MOVEMENT: "cartes posées",
    SLIPSTREAM: "mouvement terminé",
    EXHAUSTION: "aspiration terminée",
    FINISHED: "partie terminée",
}
PHASE_INFO = {
    CHOOSE: "Chaque coureur choisit une carte parmi 4. Le coureur entouré d'un halo doré est en train de choisir.",
    MOVEMENT: "Toutes les cartes sont posées. Clique sur le bouton pour les révéler et lancer le mouvement.",
    SLIPSTREAM: "Regarde le plateau, puis lance l'aspiration.",
    EXHAUSTION: "Regarde le plateau, puis passe à la fatigue.",
    FINISHED: "Retourne au menu pour refaire une partie, ou ferme la fenêtre.",
}
ACTION_TEXT = {
    CHOOSE: "Choisis les cartes…",
    MOVEMENT: "▶ Révéler les cartes : MOUVEMENT",
    SLIPSTREAM: "▶ ASPIRATION",
    EXHAUSTION: "▶ FATIGUE (puis tour suivant)",
    FINISHED: "Partie terminée",
}


PROFILE_H = 100
WINDOW_W, WINDOW_H = 1040, 930


class App:
    def __init__(self, root, teams: int = 2, seed=None, secret: bool = False, track=None, on_menu=None, animate: bool = True):
        self.parent = root  # conteneur où l'on dessine (la fenêtre, ou un cadre quand on vient du menu)
        self.root = root.winfo_toplevel()  # la fenêtre elle-même : titre, minuteur, fenêtres annexes
        self.root.title("Flamme Rouge")
        self.game = Game(track=track, num_teams=teams, seed=seed)
        self.ctl = TurnController(self.game)
        self.on_menu = on_menu  # fonction qui ramène au menu (None : pas de bouton)
        self.secret_var = tk.BooleanVar(value=secret)
        self.animate_var = tk.BooleanVar(value=animate)
        self.zoom_var = tk.BooleanVar(value=False)
        self.revealed = False  # en mode secret : la main est-elle affichée ?
        self.deck_win = None  # fenêtre des decks, quand elle est ouverte
        self.anim = None  # animation en cours (animation.Animation) ou None
        self.anim_start = 0.0
        self.anim_job = None
        self.anim_window = None  # cases visibles pendant une animation en mode zoom (figées)
        self.view = None  # cadrage manuel (échelle, x, y) à la molette / au glissement ; None = cadrage automatique
        self._drag = None  # (x, y, déplacé ?) pendant un glissement de la souris
        self._build()
        self.refresh()

    # --------------------------------------------------------------- construction

    def _build(self) -> None:
        root = self.parent
        ui.init(self.root)
        ui.place_window(self.root, WINDOW_W, WINDOW_H)
        root.configure(bg=pal.BG)

        # ----- bandeau : numéro de tour, phase, consigne, boutons
        top = tk.Frame(root, bg=pal.PANEL)
        top.pack(fill="x")
        left = tk.Frame(top, bg=pal.PANEL)
        left.pack(side="left", padx=18, pady=10)
        line = tk.Frame(left, bg=pal.PANEL)
        line.pack(anchor="w")
        self.turn_badge = tk.Label(line, text="TOUR 1", font=ui.font(11, True), bg=pal.ACCENT, fg="#ffffff", padx=10, pady=3)
        self.turn_badge.pack(side="left")
        self.title_label = tk.Label(line, text="", font=ui.font(16, True), bg=pal.PANEL, fg=pal.TEXT)
        self.title_label.pack(side="left", padx=(12, 0))
        self.info_label = tk.Label(left, text="", font=ui.font(10), bg=pal.PANEL, fg=pal.MUTED, anchor="w")
        self.info_label.pack(anchor="w", pady=(4, 0))
        tools = tk.Frame(top, bg=pal.PANEL)
        tools.pack(side="right", padx=18)
        ui.FlatButton(tools, "Decks des coureurs", self.on_decks, size=10, style="secondary").pack(side="left")
        if self.on_menu is not None:
            ui.FlatButton(tools, "⟵  Menu", self.on_back, size=10, style="ghost").pack(side="left", padx=(8, 0))
        tk.Frame(root, bg=pal.ACCENT, height=2).pack(fill="x")

        # ----- la carte
        board_card = ui.card(root)
        board_card.pack(padx=14, pady=(12, 0))
        self.board = tk.Canvas(board_card, width=BOARD_W, height=MAP_H, bg=pal.GRASS, highlightthickness=0)
        self.board.pack(padx=1, pady=1)
        self.board.bind("<ButtonPress-1>", self.on_press)
        self.board.bind("<B1-Motion>", self.on_drag)
        self.board.bind("<ButtonRelease-1>", self.on_release)  # un simple clic passe l'animation
        self.board.bind("<MouseWheel>", self.on_wheel)  # Windows et macOS
        self.board.bind("<Button-4>", lambda e: self.zoom_at(1.25, e.x, e.y))  # Linux
        self.board.bind("<Button-5>", lambda e: self.zoom_at(0.8, e.x, e.y))
        self.profile = tk.Canvas(board_card, width=BOARD_W, height=PROFILE_H, bg=pal.CARD, highlightthickness=0)
        self.profile.pack(padx=1, pady=(0, 1))

        bar = tk.Frame(root, bg=pal.BG)
        bar.pack(fill="x", padx=14, pady=(8, 0))
        ui.FlatButton(bar, "＋", lambda: self.zoom_at(1.4), size=11, padx=12, pady=4).pack(side="left")
        ui.FlatButton(bar, "－", lambda: self.zoom_at(1 / 1.4), size=11, padx=12, pady=4).pack(side="left", padx=(4, 0))
        ui.FlatButton(bar, "Vue auto", self.reset_view, size=9, style="ghost", padx=10, pady=5).pack(side="left", padx=(4, 0))
        tk.Label(bar, text="molette = zoom · glisser = déplacer · clic = passer l'animation", font=ui.font(8), bg=pal.BG, fg=pal.FAINT).pack(
            side="left", padx=10
        )
        ui.Toggle(bar, "Mode secret", self.secret_var, command=self.refresh).pack(side="right")
        ui.Toggle(bar, "Zoom sur le peloton", self.zoom_var, command=self.on_zoom_toggle).pack(side="right", padx=4)
        ui.Toggle(bar, "Animations", self.animate_var).pack(side="right")

        self.standings_frame = tk.Frame(root, bg=pal.BG)
        self.standings_frame.pack(fill="x", padx=14, pady=(8, 0))

        # ----- bas : la main à gauche, l'action et le journal à droite
        bottom = tk.Frame(root, bg=pal.BG)
        bottom.pack(fill="both", expand=True, padx=14, pady=12)
        hand_card = ui.card(bottom)
        hand_card.pack(side="left", fill="y", anchor="n")
        self.hand_frame = tk.Frame(hand_card, bg=pal.CARD)
        self.hand_frame.pack(padx=16, pady=14)

        right = tk.Frame(bottom, bg=pal.BG)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))
        self.action_btn = ui.FlatButton(right, "", self.on_action, style="primary", size=13, pady=12)
        self.action_btn.pack(fill="x", pady=(0, 8))
        log_frame = tk.Frame(right, bg=pal.BG)
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(log_frame, height=6, wrap="word", state="disabled", font=ui.font(10))
        ui.style_text(self.log)
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("heading", font=ui.font(10, True), foreground=pal.TEXT, spacing1=6)
        for team, color in enumerate(pal.TEAM_TEXT):
            self.log.tag_configure(f"team{team}", foreground=color)

    # ------------------------------------------------------------------- actions

    def _secret(self) -> bool:
        return self.secret_var.get() is True

    def on_card(self, card) -> None:
        self.ctl.choose(card)
        # Le prochain rouleur est le premier coureur d'une autre équipe : on recache la main.
        nxt = self.ctl.current_rider
        if nxt is None or nxt.kind == ROULEUR:
            self.revealed = False
        self.refresh()

    def on_action(self) -> None:
        """Passe à l'étape suivante du tour ; mouvement et aspiration sont animés."""
        if self.anim is not None:
            return
        phase = self.ctl.phase
        before = snapshot(self.game.riders)
        self.ctl.advance()
        self.revealed = False
        moves = moves_between(before, self.game.riders)
        if moves and phase in (MOVEMENT, SLIPSTREAM) and self.animate_var.get() is True:
            self.anim = movement_animation(moves) if phase == MOVEMENT else slipstream_animation(moves)
            # en mode zoom, la fenêtre reste fixe pendant l'animation : elle couvre les départs et les arrivées
            self.anim_window = map_window(self.game, [m.start[0] for m in moves])
            self.anim_start = time.monotonic()
            self.refresh()  # première image, boutons désactivés
            self._tick()
        else:
            self.refresh()

    # ------------------------------------------------------------ zoom de la carte

    def _auto_view(self):
        zoom = self.zoom_var.get() is True
        return map_transform(self.game, zoom, self.anim_window if zoom else None)

    def _focus_view(self):
        """Cadrage automatique, recentré sur le milieu des coureurs : point de départ des boutons ＋ et －."""
        scale, _cx, _cy = self._auto_view()
        squares = layout_squares(self.game.track)
        points = [point_on_road(squares, r.position, r.lane) for r in self.game.riders]
        return scale, sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points)

    def zoom_at(self, factor: float, x=None, y=None) -> None:
        """Zoome (factor > 1) ou dézoome ; passe en cadrage manuel.

        Avec une position de souris (x, y) le point visé ne bouge pas ; sans position (boutons ＋ et －),
        on zoome au milieu de la carte, d'abord recentrée sur le peloton."""
        if x is None or y is None:
            x, y = BOARD_W / 2, MAP_H / 2
            base = self.view or self._focus_view()
        else:
            base = self.view or self._auto_view()
        self.view = zoom_view(base, factor, x, y)
        self._paint_map()

    def on_wheel(self, event) -> None:
        self.zoom_at(1.25 if event.delta > 0 else 0.8, event.x, event.y)

    def on_zoom_toggle(self) -> None:
        self.view = None  # le choix « peloton / parcours entier » reprend la main
        self.refresh()

    def reset_view(self) -> None:
        self.view = None
        self._paint_map()

    def on_press(self, event) -> None:
        self._drag = [event.x, event.y, False]

    def on_drag(self, event) -> None:
        if self._drag is None:
            return
        dx, dy = event.x - self._drag[0], event.y - self._drag[1]
        if not self._drag[2] and abs(dx) + abs(dy) < 4:
            return
        self._drag = [event.x, event.y, True]
        self.view = pan_view(self.view or self._auto_view(), dx, dy)
        self._paint_map()

    def on_release(self, _event) -> None:
        moved = self._drag is not None and self._drag[2]
        self._drag = None
        if not moved:
            self.skip_animation()

    def _tick(self) -> None:
        self.anim_job = None
        if self.anim is None:
            return
        elapsed = time.monotonic() - self.anim_start
        if self.anim.done(elapsed):
            self.skip_animation()
            return
        self._paint_map()
        self.anim_job = self.root.after(FRAME_MS, self._tick)

    def skip_animation(self) -> None:
        """Termine tout de suite l'animation en cours (fin naturelle ou clic sur la carte)."""
        if self.anim is None:
            return
        self.anim = None
        self.anim_window = None
        if self.anim_job is not None:
            self.root.after_cancel(self.anim_job)
            self.anim_job = None
        self.refresh()

    def _reveal(self) -> None:
        self.revealed = True
        self.refresh()

    def on_back(self) -> None:
        in_progress = self.ctl.phase != FINISHED and self.game.turn > 0
        if in_progress and not messagebox.askyesno("Retour au menu", "Abandonner la partie en cours ?"):
            return
        self.close()
        self.on_menu()

    def close(self) -> None:
        """À appeler avant de détruire la fenêtre : arrête l'animation et ferme la fenêtre des decks."""
        self.anim = None
        if self.anim_job is not None:
            self.root.after_cancel(self.anim_job)
            self.anim_job = None
        self._close_decks()

    # ---------------------------------------------------------- fenêtre des decks

    def on_decks(self) -> None:
        """Ouvre (ou ramène au premier plan) la fenêtre qui montre le contenu des decks."""
        if self.deck_win is not None and self.deck_win.winfo_exists():
            self.deck_win.lift()
            self._refresh_decks()
            return
        win = tk.Toplevel(self.root)
        win.title("Decks des coureurs")
        win.configure(bg=pal.BG)
        win.protocol("WM_DELETE_WINDOW", self._close_decks)
        self.deck_win = win
        tk.Label(
            win,
            text="Pioche = cartes pas encore tirées · Recyclage = cartes écartées, remélangées quand la pioche est vide · "
            "Jouées = retirées du jeu · F = fatigue",
            font=ui.font(9),
            bg=pal.BG,
            fg=pal.MUTED,
            wraplength=620,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 0))
        frame = tk.Frame(win, bg=pal.BG)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        mono = ("Courier New", 10)
        self.deck_view = tk.Text(frame, width=72, height=34, wrap="none", state="disabled", font=mono)
        ui.style_text(self.deck_view)
        scrollbar = tk.Scrollbar(frame, orient="vertical", command=self.deck_view.yview)
        self.deck_view.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.deck_view.pack(side="left", fill="both", expand=True)
        for team, color in enumerate(pal.TEAM_TEXT):
            self.deck_view.tag_configure(f"team{team}", foreground=color, font=("Courier New", 10, "bold"))
        self._refresh_decks()

    def _close_decks(self) -> None:
        if self.deck_win is not None:
            self.deck_win.destroy()
        self.deck_win = None

    def _refresh_decks(self) -> None:
        if self.deck_win is None or not self.deck_win.winfo_exists():
            return
        view = self.deck_view.yview()[0]  # garde la position de défilement
        self.deck_view.configure(state="normal")
        self.deck_view.delete("1.0", "end")
        for rider in self.game.riders:
            first, _, rest = deck_text(rider).partition("\n")
            self.deck_view.insert("end", first + "\n", f"team{rider.team}")
            self.deck_view.insert("end", rest + "\n\n")
        self.deck_view.configure(state="disabled")
        self.deck_view.yview_moveto(view)

    # ------------------------------------------------------------------ affichage

    def refresh(self) -> None:
        g = self.game
        phase = self.ctl.phase
        if phase == FINISHED:
            self.turn_badge.config(text="ARRIVÉE", bg=pal.GOOD, fg="#052e1b")
            title = "Course terminée !"
        else:
            self.turn_badge.config(text=f"TOUR {g.turn + 1}", bg=pal.ACCENT, fg="#ffffff")
            title = PHASE_TITLES[phase].capitalize()
        self.title_label.config(text=title)
        self.info_label.config(text=PHASE_INFO[phase])

        self._paint_map()
        if self.anim is None:  # le classement se met à jour une fois les coureurs arrivés
            self._show_standings()

        self._show_hand()
        self._refresh_decks()
        self.action_btn.config(
            text=ACTION_TEXT[phase],
            state="normal" if phase in (MOVEMENT, SLIPSTREAM, EXHAUSTION) and self.anim is None else "disabled",
        )
        self._flush_log()

    def _paint_map(self) -> None:
        """Dessine la carte : le parcours entier, ou le zoom ; coureurs en mouvement s'il y a une animation."""
        zoom = self.zoom_var.get() is True
        positions = self.anim.positions(time.monotonic() - self.anim_start) if self.anim is not None else None
        shapes = map_primitives(
            self.game,
            self.ctl.current_rider,
            positions=positions,
            zoom=zoom,
            window=self.anim_window if zoom else None,
            view=self.view,
        )
        self._paint(self.board, shapes)
        leader = max(self.game.riders, key=lambda r: r.position).position
        self._paint(self.profile, profile_primitives(self.game.track, BOARD_W, PROFILE_H, marker=leader))

    def _paint(self, canvas, shapes) -> None:
        canvas.delete("all")
        ui.paint(canvas, shapes)

    def _show_standings(self) -> None:
        for widget in self.standings_frame.winfo_children():
            widget.destroy()
        order = sorted(self.game.riders, key=lambda r: (-r.position, r.lane))
        tk.Label(self.standings_frame, text="CLASSEMENT (case)", font=ui.font(8, True), bg=pal.BG, fg=pal.FAINT).pack(side="left", padx=(0, 8))
        for place, rider in enumerate(order, 1):
            chip = tk.Frame(self.standings_frame, bg=pal.CARD, highlightbackground=pal.BORDER, highlightthickness=1)
            chip.pack(side="left", padx=(0, 5))
            tk.Label(chip, text=f"{place}", font=ui.font(9, True), bg=pal.CARD, fg=pal.FAINT, padx=5).pack(side="left")
            tk.Label(chip, text=rider.name, font=ui.font(10, True), bg=pal.TEAM_FILL[rider.team], fg=pal.LABEL_ON_FILL[rider.team], padx=6).pack(side="left", pady=2)
            tk.Label(chip, text=f"{rider.position}", font=ui.font(9), bg=pal.CARD, fg=pal.MUTED, padx=5).pack(side="left")

    def _show_hand(self) -> None:
        for widget in self.hand_frame.winfo_children():
            widget.destroy()
        frame = self.hand_frame
        rider = self.ctl.current_rider
        if rider is None:
            tk.Label(frame, text="Les cartes sont posées.", font=ui.font(12), bg=pal.CARD, fg=pal.MUTED).pack(anchor="w")
            return

        head = tk.Frame(frame, bg=pal.CARD)
        head.pack(anchor="w", fill="x")
        tk.Label(head, text=rider.name, font=ui.font(12, True), bg=pal.TEAM_FILL[rider.team], fg=pal.LABEL_ON_FILL[rider.team], padx=9, pady=3).pack(side="left")
        tk.Label(
            head, text=f"Équipe {rider.team + 1} · {rider.kind} · case {rider.position}", font=ui.font(12, True),
            bg=pal.CARD, fg=pal.TEAM_TEXT[rider.team],
        ).pack(side="left", padx=10)
        if self._secret() and rider.kind == ROULEUR and not self.revealed:
            tk.Label(frame, text="Les autres équipes ne regardent pas !", font=ui.font(11), bg=pal.CARD, fg=pal.MUTED).pack(
                anchor="w", pady=(10, 8)
            )
            ui.FlatButton(frame, f"Équipe {rider.team + 1} prête : afficher ma main", self._reveal, style="primary", size=11).pack(anchor="w")
            return

        ahead = " ".join(terrain_text(self.game, s) for s in range(rider.position + 1, rider.position + 11))
        tk.Label(frame, text=f"Devant toi :  {ahead}", font=ui.font(11), bg=pal.CARD, fg=pal.MUTED).pack(anchor="w", pady=(8, 8))
        row = tk.Frame(frame, bg=pal.CARD)
        row.pack(anchor="w")
        for card in sorted(self.ctl.hand, key=lambda c: c.value):
            label = f"{card.value}\nfatigue" if card.exhaustion else str(card.value)
            ui.FlatButton(
                row, label, lambda c=card: self.on_card(c), style="warn" if card.exhaustion else "secondary",
                size=14 if card.exhaustion else 22, padx=16 if card.exhaustion else 20, pady=14,
            ).pack(side="left", padx=4)
        tk.Label(
            frame, text=f"Pioche : {len(rider.draw_pile)} cartes   ·   Recyclage : {len(rider.recycle)} cartes",
            font=ui.font(10), bg=pal.CARD, fg=pal.MUTED,
        ).pack(anchor="w", pady=(10, 0))

    def _flush_log(self) -> None:
        self.log.configure(state="normal")
        for line in self.ctl.drain_log():
            if line.heading:
                tag = "heading"
            elif line.team is not None:
                tag = f"team{line.team}"
            else:
                tag = ""
            self.log.insert("end", line.text + "\n", tag)
        self.log.configure(state="disabled")
        self.log.see("end")


def main() -> None:
    parser = argparse.ArgumentParser(description="Flamme Rouge — interface graphique")
    parser.add_argument("teams", nargs="?", type=int, default=2, help="nombre d'équipes (2 à 4)")
    parser.add_argument("seed", nargs="?", type=int, default=None, help="graine du mélange")
    parser.add_argument("--secret", action="store_true", help="cache la main entre deux équipes")
    parser.add_argument("--no-anim", action="store_true", help="désactive les animations")
    parser.add_argument("--track", help="parcours .json créé avec editor.py")
    args = parser.parse_args()

    track = None
    if args.track:
        try:
            track = load_track_file(args.track)
        except (OSError, ValueError) as exc:
            raise SystemExit(f"Impossible de charger le parcours : {exc}")

    root = tk.Tk()
    App(root, args.teams, args.seed, args.secret, track, animate=not args.no_anim)
    root.mainloop()


if __name__ == "__main__":
    main()
