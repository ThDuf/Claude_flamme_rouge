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
from flamme_rouge.boardview import FOLLOW_HEAD, FOLLOW_PELOTON, follow_view, jersey_primitives
from flamme_rouge.stage import MOUNTAIN, SPRINT, format_time
from flamme_rouge.tour import GREEN, POLKA, YELLOW
from flamme_rouge.boardview import podium_primitives, profile_primitives, weather_fx_primitives, map_weather_fx_primitives, map_transform, pan_view, zoom_view, BOARD_W, MAP_H, TEAM_TEXT, map_primitives, terrain_text
from flamme_rouge.geometry import layout_squares, point_on_road
from flamme_rouge.controller import (
    BREAKAWAY,
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
    BREAKAWAY: "enchères de l'échappée",
    CHOOSE: "choix des cartes",
    MOVEMENT: "cartes posées",
    SLIPSTREAM: "mouvement terminé",
    EXHAUSTION: "aspiration terminée",
    FINISHED: "partie terminée",
}
PHASE_INFO = {
    BREAKAWAY: "Chaque équipe mise deux cartes d'un coureur, ou passe : le meilleur total part devant.",
    CHOOSE: "Chaque coureur choisit une carte parmi 4. Le coureur entouré d'un halo doré est en train de choisir.",
    MOVEMENT: "Toutes les cartes sont posées. Clique sur le bouton pour les révéler et lancer le mouvement.",
    SLIPSTREAM: "Regarde le plateau, puis lance l'aspiration.",
    EXHAUSTION: "Regarde le plateau, puis passe à la fatigue.",
    FINISHED: "Clic sur le podium pour revoir la course ; retourne au menu pour refaire une partie.",
}
ACTION_TEXT = {
    BREAKAWAY: "Enchères de l'échappée…",
    CHOOSE: "Choisis les cartes…",
    MOVEMENT: "▶ Révéler les cartes : MOUVEMENT",
    SLIPSTREAM: "▶ ASPIRATION",
    EXHAUSTION: "▶ FATIGUE (puis tour suivant)",
    FINISHED: "Partie terminée",
}


PROFILE_H = 100
WINDOW_W, WINDOW_H = 1040, 985
TOUR_PANEL_W = 230  # Grand Tour : largeur du panneau des jetons et des temps
PANEL_PER_ROW = 4  # pastilles par ligne dans ce panneau
SIDE_PANEL_W = 330  # ce panneau quand il est à droite de la carte (écran large)
CAMERA_ALL = "tout"
CAMERA_CHOICES = [(CAMERA_ALL, "Tout le parcours"), (FOLLOW_PELOTON, "Zoom peloton"), (FOLLOW_HEAD, "Zoom tête de course")]


class App:
    def __init__(self, root, teams: int = 2, seed=None, secret: bool = False, track=None, on_menu=None, animate: bool = True,
                 extensions=(), ai_teams=(), team_types=None, breakaway: bool = False, game=None, on_stage_end=None,
                 stage_title: str = ""):
        """`game` : une partie déjà préparée (étape d'un Grand Tour) ; `on_stage_end()` est appelé quand on clique
        sur « Résultats de l'étape » à la fin d'une étape de Tour ; `stage_title` s'affiche dans la fenêtre."""
        self.parent = root  # conteneur où l'on dessine (la fenêtre, ou un cadre quand on vient du menu)
        self.root = root.winfo_toplevel()  # la fenêtre elle-même : titre, minuteur, fenêtres annexes
        self.root.title("Flamme Rouge")
        self.game = game or Game(track=track, num_teams=teams, seed=seed, extensions=extensions, team_types=team_types)
        self.on_stage_end = on_stage_end
        if stage_title:
            self.root.title(f"Flamme Rouge — {stage_title}")
        self.ctl = TurnController(self.game, ai_teams, breakaway)  # `ai_teams` : jouées par l'IA
        self.on_menu = on_menu  # fonction qui ramène au menu (None : pas de bouton)
        self.secret_var = tk.BooleanVar(value=secret)
        self.animate_var = tk.BooleanVar(value=animate)
        self.revealed = False  # en mode secret : la main est-elle affichée ?
        self.deck_win = None  # fenêtre des decks, quand elle est ouverte
        self.anim = None  # animation en cours (animation.Animation) ou None
        self.anim_start = 0.0
        self.anim_job = None
        self.fx_job = None  # animation de la météo sur le profil
        self.show_podium = True  # à l'arrivée : écran de victoire (un clic sur la carte bascule vers la course)
        self.podium_start = None
        self.podium_job = None
        self.fx_start = time.monotonic()
        self.view = None  # cadrage manuel (échelle, x, y) à la molette / au glissement ; None = cadrage automatique
        # caméra : "tout" (le parcours entier), "peloton" ou "tete" (suit ce groupe), "" (cadrage manuel)
        self.camera_var = tk.StringVar(value=CAMERA_ALL)
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
        self.info_label = tk.Label(left, text="", font=ui.font(10), bg=pal.PANEL, fg=pal.MUTED, anchor="w",
                                   justify="left", wraplength=520)  # passe à la ligne : la fenêtre reste à sa largeur
        self.info_label.pack(anchor="w", pady=(4, 0))
        tools = tk.Frame(top, bg=pal.PANEL)
        tools.pack(side="right", padx=18)
        ui.FlatButton(tools, "Decks des coureurs", self.on_decks, size=10, style="secondary").pack(side="left")
        if self.on_menu is not None:
            ui.FlatButton(tools, "⟵  Menu", self.on_back, size=10, style="ghost").pack(side="left", padx=(8, 0))
        tk.Frame(root, bg=pal.ACCENT, height=2).pack(fill="x")

        # ----- la carte
        # Grand Tour sur un écran assez large : le panneau des jetons et maillots à droite de la carte
        self.side_panel = bool(self.game.tour) and self.root.winfo_screenwidth() >= WINDOW_W + SIDE_PANEL_W + 60
        if self.side_panel:
            ui.place_window(self.root, WINDOW_W + SIDE_PANEL_W + 14, WINDOW_H)
            middle = tk.Frame(root, bg=pal.BG)
            middle.pack(padx=14, pady=(12, 0))  # pas étiré : carte + panneau restent centrés dans la fenêtre
            board_card = ui.card(middle)
            board_card.pack(side="left")
            side_card = ui.card(middle)
            side_card.pack(side="left", fill="y", padx=(14, 0))
            self.tour_panel = tk.Frame(side_card, bg=pal.CARD, width=SIDE_PANEL_W - 22)
            self.tour_panel.pack(fill="both", expand=True, padx=10, pady=8)
            self.tour_panel.pack_propagate(False)  # largeur fixe : la carte garde sa place
        else:
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
        ui.Segmented(bar, CAMERA_CHOICES, self.camera_var, command=self.set_camera).pack(side="left", padx=(10, 0))
        tk.Label(bar, text="molette = zoom · glisser = déplacer\nclic = passer l'animation", font=ui.font(8), bg=pal.BG,
                 fg=pal.FAINT, justify="left").pack(side="left", padx=10)
        ui.Toggle(bar, "Mode secret", self.secret_var, command=self.refresh).pack(side="right")
        ui.Toggle(bar, "Animations", self.animate_var).pack(side="right")

        self.cards_frame = tk.Frame(root, bg=pal.BG)  # cartes révélées au dernier mouvement
        self.cards_frame.pack(fill="x", padx=14, pady=(6, 0))

        # ----- bas : la main à gauche, l'action et le journal à droite
        bottom = tk.Frame(root, bg=pal.BG)
        bottom.pack(fill="both", expand=True, padx=14, pady=12)
        hand_card = ui.card(bottom)
        hand_card.pack(side="left", fill="y", anchor="n")
        self.hand_frame = tk.Frame(hand_card, bg=pal.CARD)
        self.hand_frame.pack(padx=16, pady=14)

        if not self.side_panel:
            self.tour_panel = None
        if self.game.tour and not self.side_panel:  # petit écran : le panneau du Tour sous la carte, à droite
            panel_card = ui.card(bottom)
            panel_card.pack(side="right", fill="y", padx=(14, 0))
            self.tour_panel = tk.Frame(panel_card, bg=pal.CARD, width=TOUR_PANEL_W)
            self.tour_panel.pack(fill="both", expand=True, padx=10, pady=8)

        right = tk.Frame(bottom, bg=pal.BG)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))
        self.action_btn = ui.FlatButton(right, "", self.on_action, style="primary", size=13, pady=12)
        self.action_btn.pack(fill="x", pady=(0, 8))
        log_frame = tk.Frame(right, bg=pal.BG)
        log_frame.pack(fill="both", expand=True)
        # largeur minimale modeste : le journal prend la place qui reste à côté de la main
        self.log = tk.Text(log_frame, width=40, height=6, wrap="word", state="disabled", font=ui.font(10))
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

    def _bid_rider(self, rider) -> None:
        self.ctl.choose_bid_rider(rider)
        self.refresh()

    def on_action(self) -> None:
        """Passe à l'étape suivante du tour ; mouvement et aspiration sont animés."""
        if self.anim is not None:
            return
        phase = self.ctl.phase
        if phase == FINISHED and self.on_stage_end is not None:  # Grand Tour : écran des résultats de l'étape
            self.close()
            self.on_stage_end()
            return
        before = snapshot(self.game.riders)
        self.ctl.advance()
        self.revealed = False
        moves = moves_between(before, self.game.riders)
        if moves and phase in (MOVEMENT, SLIPSTREAM) and self.animate_var.get() is True:
            self.anim = movement_animation(moves) if phase == MOVEMENT else slipstream_animation(moves)
            self.anim_start = time.monotonic()
            self.refresh()  # première image, boutons désactivés
            self._tick()
        else:
            self.refresh()

    # ------------------------------------------------------------ zoom de la carte

    def _auto_view(self):
        return map_transform(self.game)

    def _focus_view(self):
        """Cadrage automatique, recentré sur le milieu des coureurs : point de départ des boutons ＋ et －."""
        scale, _cx, _cy = self._auto_view()
        squares = layout_squares(self.game.track)
        points = [point_on_road(squares, r.position, r.lane) for r in self.game.riders] or [point_on_road(squares, 0, 0)]
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
        self.camera_var.set("")  # zoom à la main : on ne suit plus de groupe
        self._paint_map()

    def on_wheel(self, event) -> None:
        self.zoom_at(1.25 if event.delta > 0 else 0.8, event.x, event.y)

    def reset_view(self) -> None:
        self.camera_var.set(CAMERA_ALL)
        self.set_camera()

    def set_camera(self) -> None:
        """Choix de la caméra : tout le parcours, ou un zoom qui suit le peloton / la tête de course."""
        self.view = None
        self._paint_map()

    def _follow_camera(self) -> None:
        """Caméra de suivi : recadre sur le groupe suivi (appelé à chaque dessin de la carte)."""
        which = self.camera_var.get()
        if which in (FOLLOW_PELOTON, FOLLOW_HEAD):
            self.view = follow_view(self.game, which)  # None (plus personne en course) : tout le parcours

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
        self.camera_var.set("")  # déplacement à la main : on ne suit plus de groupe
        self._paint_map()

    def on_release(self, _event) -> None:
        moved = self._drag is not None and self._drag[2]
        self._drag = None
        if moved:
            return
        if self.ctl.phase == FINISHED and self.anim is None:  # podium <-> course
            self.show_podium = not self.show_podium
            self._paint_map()
            return
        self.skip_animation()

    # ------------------------------------------------------------ écran de victoire

    PODIUM_MS = 33

    def _podium_visible(self) -> bool:
        return self.ctl.phase == FINISHED and self.anim is None and self.show_podium

    def _team_names(self) -> list[str]:
        """« Équipe 2 · IA », « Équipe 3 · Peloton »… pour l'écran de victoire."""
        names = []
        for team in range(max(r.team for r in self.game.all_riders) + 1):
            rider = next(r for r in self.game.all_riders if r.team == team)
            who = self.ctl.controller_of(rider)
            names.append(f"Équipe {team + 1}" + ("" if who == "Joueur" else f" · {who}"))
        return names

    def _paint_podium(self) -> None:
        if self.podium_start is None:
            self.podium_start = time.monotonic()
        t = time.monotonic() - self.podium_start if self.animate_var.get() is True else 10.0
        self._paint(self.board, podium_primitives(self.game, BOARD_W, MAP_H, t, self._team_names()))
        if self.podium_job is None and self.animate_var.get() is True:
            self.podium_job = self.root.after(self.PODIUM_MS, self._podium_tick)

    def _podium_tick(self) -> None:
        self.podium_job = None
        if self.board.winfo_exists() and self._podium_visible():
            self._paint_podium()

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
        if self.fx_job is not None:
            self.root.after_cancel(self.fx_job)
            self.fx_job = None
        if self.podium_job is not None:
            self.root.after_cancel(self.podium_job)
            self.podium_job = None
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
        if self.anim is None:  # le panneau du Tour se met à jour une fois les coureurs arrivés
            self._show_tour_panel()
        self._show_revealed_cards()

        self._show_hand()
        self._refresh_decks()
        tour_end = phase == FINISHED and self.on_stage_end is not None
        self.action_btn.config(
            text="▶ Résultats de l'étape et classements" if tour_end else ACTION_TEXT[phase],
            state="normal" if (phase in (MOVEMENT, SLIPSTREAM, EXHAUSTION) or tour_end) and self.anim is None else "disabled",
        )
        self._flush_log()

    def _paint_map(self) -> None:
        """Dessine la carte (parcours entier, ou cadrage manuel) ; coureurs en mouvement s'il y a une animation.
        À l'arrivée, l'écran de victoire prend la place de la carte."""
        if self._podium_visible():
            self._paint_podium()
            self._paint(self.profile, profile_primitives(self.game.track, BOARD_W, PROFILE_H, riders=self.game.riders,
                                                         weather=self.game.weather, tokens=self.game.tokens,
                                                     jerseys=self.game.jerseys))
            return
        positions = self.anim.positions(time.monotonic() - self.anim_start) if self.anim is not None else None
        self._follow_camera()
        shapes = map_primitives(
            self.game,
            self.ctl.current_rider,
            positions=positions,
            view=self.view,
        )
        self._paint(self.board, shapes)
        self._paint(self.profile, profile_primitives(self.game.track, BOARD_W, PROFILE_H, riders=self.game.riders,
                                                     weather=self.game.weather, tokens=self.game.tokens,
                                                     jerseys=self.game.jerseys))
        self._paint_weather_fx()

    WEATHER_FX_MS = 60

    def _paint_weather_fx(self) -> None:
        """Pluie, vent et soleil animés sur le profil (seulement avec l'extension Météo)."""
        if not self.game.weather:
            return
        t = time.monotonic() - self.fx_start if self.animate_var.get() is True else 0.0
        self.profile.delete("fx")
        ui.paint(self.profile, weather_fx_primitives(self.game.track, self.game.weather, BOARD_W, PROFILE_H, t), tags=("fx",))
        self.board.delete("fx")
        if not self._podium_visible():
            ui.paint(self.board, map_weather_fx_primitives(self.game, t, view=self.view), tags=("fx",))
        if self.fx_job is None and self.animate_var.get() is True:
            self.fx_job = self.root.after(self.WEATHER_FX_MS, self._fx_tick)

    def _fx_tick(self) -> None:
        self.fx_job = None
        if self.profile.winfo_exists():
            self._paint_weather_fx()

    def _paint(self, canvas, shapes) -> None:
        canvas.delete("all")
        ui.paint(canvas, shapes)

    def _show_tour_panel(self) -> None:
        """Grand Tour : les jetons Sprint (maillot vert) et Montagne (à pois) gagnés pendant l'étape, puis les
        temps (jetons Temps d'une minute, arrivées). Au survol, l'infobulle dit pourquoi."""
        panel = self.tour_panel
        if panel is None:
            return
        for widget in panel.winfo_children():
            widget.destroy()
        g = self.game
        wrap = SIDE_PANEL_W - 44 if self.side_panel else TOUR_PANEL_W - 10
        per_row = 5 if self.side_panel else PANEL_PER_ROW

        def heading(text: str, top: int = 8) -> None:
            tk.Label(panel, text=text, font=ui.font(8, True), bg=pal.CARD, fg=pal.FAINT, anchor="w").pack(
                fill="x", pady=(top, 2))

        def rider_chip(parent, rider) -> None:
            tk.Label(parent, text=rider.name, font=ui.font(8, True), bg=pal.TEAM_FILL[rider.team],
                     fg=pal.LABEL_ON_FILL[rider.team], padx=3).pack(side="left", padx=(4, 0))

        def jersey_icon(parent, kind, value=None, bg=pal.CARD) -> None:
            icon = tk.Canvas(parent, width=20, height=20, bg=bg, highlightthickness=0)
            ui.paint(icon, jersey_primitives(10, 10, 18, kind, value))
            icon.pack(side="left")

        if self.side_panel:
            self._side_panel_standings(panel, heading, rider_chip, jersey_icon)
        for kind, title in ((SPRINT, "SPRINT DE L'ÉTAPE · MAILLOT VERT"), (MOUNTAIN, "MONTAGNE DE L'ÉTAPE · À POIS")):
            heading(title, 0 if kind == SPRINT and not self.side_panel else 4)
            wins = [w for w in g.token_log if w.kind == kind]
            if not wins:
                left = [s for s in g.tokens if s.kind == kind and s.values]
                text = ("à prendre : " + ", ".join(f"case {s.square} ({'·'.join(map(str, s.values))})" for s in left)
                        if left else "aucun jeton")
                tk.Label(panel, text=text, font=ui.font(8), bg=pal.CARD, fg=pal.MUTED, anchor="w", justify="left",
                         wraplength=wrap).pack(fill="x")
                continue
            row = None
            for i, win in enumerate(wins):
                if i % per_row == 0:
                    row = tk.Frame(panel, bg=pal.CARD)
                    row.pack(fill="x", pady=1)
                chip = tk.Frame(row, bg=pal.CARD_HI, cursor="question_arrow")
                chip.pack(side="left", padx=(0, 4))
                icon = tk.Canvas(chip, width=20, height=20, bg=pal.CARD_HI, highlightthickness=0)
                ui.paint(icon, jersey_primitives(10, 10, 18, kind, win.value))
                icon.pack(side="left")
                rider_chip(chip, win.rider)
                ui.Tooltip(chip, win.reason())

        heading("TEMPS", 4)
        times = tk.Frame(panel, bg=pal.CARD)
        times.pack(fill="x")
        shown = 0
        for rider in g.arrived:  # arrivés : leur temps d'étape
            arrival = g.arrival_log.get(rider)
            chip = tk.Frame(times, bg=pal.CARD_HI, cursor="question_arrow")
            chip.grid(row=shown // per_row, column=shown % per_row, sticky="w", padx=(0, 4), pady=1)
            rider_chip(chip, rider)
            tk.Label(chip, text=format_time(g.stage_time[rider]), font=ui.font(8, True), bg=pal.CARD_HI,
                     fg=pal.GOOD, padx=3).pack(side="left")
            if arrival is not None:
                ui.Tooltip(chip, arrival.reason())
            shown += 1
        for rider in g.riders:  # encore en course : jetons Temps déjà pris
            minutes = g.minutes.get(rider, 0)
            if not minutes:
                continue
            chip = tk.Frame(times, bg=pal.CARD_HI, cursor="question_arrow")
            chip.grid(row=shown // per_row, column=shown % per_row, sticky="w", padx=(0, 4), pady=1)
            rider_chip(chip, rider)
            tk.Label(chip, text=f"⏱ {minutes}'", font=ui.font(8, True), bg=pal.CARD_HI, fg=pal.TEXT, padx=3).pack(
                side="left")
            ui.Tooltip(chip, f"{rider.name} n'a pas encore passé la ligne : {minutes} jeton(s) Temps d'une minute.\n"
                             "Après la première arrivée, chaque coureur pas encore arrivé en prend un à la fin "
                             "de chaque tour.")
            shown += 1
        if not shown:
            tk.Label(times, text="jetons Temps : dès qu'un coureur passe la ligne, chacun des autres prend 1 minute "
                                 "par tour", font=ui.font(8), bg=pal.CARD, fg=pal.MUTED, anchor="w", justify="left",
                     wraplength=wrap).grid(row=0, column=0, sticky="w")

    def _side_panel_standings(self, panel, heading, rider_chip, jersey_icon) -> None:
        """Panneau large du Grand Tour : maillots du général, haut du classement général, derniers points pris."""
        g = self.game
        info = g.tour_standings or {}
        stage = f"ÉTAPE {info['stage']}/{info['stages']} · " if info else ""
        heading(stage + "MAILLOTS (AVANT L'ÉTAPE)", 0)
        jerseys = info.get("jerseys", [])
        if not jerseys:
            tk.Label(panel, text="Premiers maillots à la fin de cette étape.", font=ui.font(8), bg=pal.CARD,
                     fg=pal.MUTED, anchor="w").pack(fill="x")
        names = {YELLOW: "Jaune", GREEN: "Vert", POLKA: "À pois"}
        for jersey, rider, detail in jerseys:
            row = tk.Frame(panel, bg=pal.CARD)
            row.pack(fill="x", pady=1)
            jersey_icon(row, jersey)
            tk.Label(row, text=names.get(jersey, jersey), font=ui.font(8, True), bg=pal.CARD, fg=pal.TEXT, width=6,
                     anchor="w").pack(side="left", padx=(4, 0))
            rider_chip(row, rider)
            tk.Label(row, text=detail, font=ui.font(8), bg=pal.CARD, fg=pal.MUTED).pack(side="left", padx=(6, 0))
        gc = info.get("gc", [])
        if gc:
            heading("CLASSEMENT GÉNÉRAL")
            for place, (rider, total, gap) in enumerate(gc, 1):
                row = tk.Frame(panel, bg=pal.CARD)
                row.pack(fill="x")
                tk.Label(row, text=f"{place}.", font=ui.font(8, True), bg=pal.CARD, fg=pal.FAINT, width=2,
                         anchor="e").pack(side="left")
                rider_chip(row, rider)
                tk.Label(row, text=total, font=ui.font(8, True), bg=pal.CARD, fg=pal.TEXT).pack(side="left", padx=(6, 0))
                tk.Label(row, text=gap, font=ui.font(8), bg=pal.CARD, fg=pal.MUTED).pack(side="left", padx=(6, 0))
        heading("DERNIERS POINTS DE L'ÉTAPE")
        recent = list(reversed(g.token_log))[:4]
        if not recent:
            tk.Label(panel, text="Personne n'a encore pris de jeton.", font=ui.font(8), bg=pal.CARD, fg=pal.MUTED,
                     anchor="w").pack(fill="x")
        for win in recent:
            row = tk.Frame(panel, bg=pal.CARD, cursor="question_arrow")
            row.pack(fill="x", pady=1)
            jersey_icon(row, win.kind, win.value)
            rider_chip(row, win.rider)
            what = "Sprint" if win.kind == SPRINT else "Montagne"
            tk.Label(row, text=f"+{win.value} {what} · tour {win.turn}, case {win.square}", font=ui.font(8),
                     bg=pal.CARD, fg=pal.TEXT).pack(side="left", padx=(6, 0))
            ui.Tooltip(row, win.reason())

    def _show_revealed_cards(self) -> None:
        """Les cartes jouées au dernier mouvement par chaque coureur, avec qui le joue (Joueur, IA, Peloton,
        Muscle). Elles restent affichées pendant le tour suivant, jusqu'au mouvement d'après."""
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        revealed = self.ctl.last_revealed
        if not revealed:
            tk.Label(self.cards_frame, text="CARTES JOUÉES : elles apparaîtront ici au premier mouvement",
                     font=ui.font(8, True), bg=pal.BG, fg=pal.FAINT).pack(side="left")
            return
        tk.Label(self.cards_frame, text=f"CARTES DU TOUR {self.ctl.last_revealed_turn}", font=ui.font(8, True), bg=pal.BG,
                 fg=pal.FAINT).pack(side="left", padx=(0, 8))
        teams = sorted({r.team for r in revealed})
        for team in teams:  # une pastille par équipe : qui la joue, puis la carte de chaque coureur
            riders = sorted((r for r in revealed if r.team == team), key=lambda r: r.name)
            who = self.ctl.controller_of(riders[0])
            chip = tk.Frame(self.cards_frame, bg=pal.CARD, highlightthickness=1,
                            highlightbackground=pal.ACCENT if who != "Joueur" else pal.BORDER)
            chip.pack(side="left", padx=(0, 4))
            tk.Label(chip, text=who.upper(), font=ui.font(7, True), bg=pal.TEAM_FILL[team],
                     fg=pal.LABEL_ON_FILL[team], padx=3).pack(side="left", fill="y")
            for rider in riders:
                card = revealed[rider]
                short = rider.name[len(str(team + 1)):]  # « R », « S », « P1 »…
                tk.Label(chip, text=f"{short} {card_label(card)}", font=ui.font(10, True), bg=pal.CARD,
                         fg=pal.ACCENT if card.special else pal.MUTED if card.exhaustion else pal.TEXT,
                         padx=3).pack(side="left", pady=1)

    def _show_hand(self) -> None:
        for widget in self.hand_frame.winfo_children():
            widget.destroy()
        frame = self.hand_frame
        rider = self.ctl.current_rider
        if self.ctl.phase == BREAKAWAY and rider is None:  # l'équipe choisit son coureur, ou passe
            team = self.ctl.bid_team
            tk.Label(frame, text=f"Échappée · Équipe {team + 1}", font=ui.font(13, True), bg=pal.CARD,
                     fg=pal.TEAM_TEXT[team]).pack(anchor="w")
            tk.Label(frame, text="Quel coureur tente l'échappée ? (2 cartes misées, 2 cartes Fatigue s'il part)",
                     font=ui.font(11), bg=pal.CARD, fg=pal.MUTED).pack(anchor="w", pady=(6, 8))
            row = tk.Frame(frame, bg=pal.CARD)
            row.pack(anchor="w")
            for candidate in (r for r in self.game.riders if r.team == team):
                ui.FlatButton(row, f"{candidate.name} · {candidate.kind}", lambda r=candidate: self._bid_rider(r),
                              style="primary", size=11).pack(side="left", padx=(0, 6))
            ui.FlatButton(row, "Ne pas participer", lambda: self._bid_rider(None), size=11, style="ghost").pack(side="left")
            return
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

        if self.ctl.phase == BREAKAWAY:
            tk.Label(frame, text=f"Enchère {self.ctl.bid_round} sur 2 : la carte à miser (les autres vont à la défausse)",
                     font=ui.font(11), bg=pal.CARD, fg=pal.MUTED).pack(anchor="w", pady=(8, 8))
        else:
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


def card_label(card) -> str:
    """Texte court d'une carte : « 5 », « 2F » (fatigue), « 5M » (Muscle), « A 2/9 » (Attaque)."""
    if card.special == "attaque":
        return "A 2/9"
    return str(card)


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
