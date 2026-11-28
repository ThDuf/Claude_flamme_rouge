"""Interface de jeu (tkinter, inclus avec Python).

Le plus simple est de passer par le menu :   python main.py --tk

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
from dataclasses import replace
import tkinter as tk
from tkinter import messagebox

import ui
from flamme_rouge import ROULEUR, Game
from flamme_rouge import palette as pal
from flamme_rouge.animation import FRAME_MS, ease, moves_between, movement_animation, slipstream_animation, snapshot
from flamme_rouge.boardview import FOLLOW_HEAD, FOLLOW_PELOTON, follow_view, jersey_primitives
from flamme_rouge.iso import best_angle, projection
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
from flamme_rouge.decks import deck_summary, whole_deck
from flamme_rouge.game import TEAM_PLAYER
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
    CHOOSE: "Chaque équipe choisit en même temps une carte pour son rouleur et une pour son sprinteur, puis valide.",
    MOVEMENT: "Toutes les cartes sont posées. Clique sur le bouton pour les révéler et lancer le mouvement.",
    SLIPSTREAM: "Regarde le plateau, puis lance l'aspiration.",
    EXHAUSTION: "Regarde le plateau, puis passe à la fatigue.",
    FINISHED: "« Revoir la course » (sous la carte) rejoue toute la course, avec une barre de progression.",
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
ROTATE_STEP = 30  # degrés : un clic sur ⟲ ou ⟳ en vue 3D
DECK_PANEL_W, DECK_TAB_W, DECK_PER_ROW = 330, 34, 5  # panneau « Deck de départ » sur le bord droit
HAND_CARD_SCALE = 0.72  # cartes de la main plus petites : deux mains (rouleur et sprinteur) l'une sous l'autre
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
        # `ai_teams` : jouées par l'IA. Choix simultané : chaque joueur choisit les cartes de ses deux coureurs ensemble
        self.ctl = TurnController(self.game, ai_teams, breakaway, simultaneous=True)
        self.picks: dict = {}  # carte choisie (pas encore validée) pour chaque coureur de l'équipe qui choisit
        self.on_menu = on_menu  # fonction qui ramène au menu (None : pas de bouton)
        self.secret_var = tk.BooleanVar(value=secret)
        self.animate_var = tk.BooleanVar(value=animate)
        self.revealed = False  # en mode secret : la main est-elle affichée ?
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
        self.iso_var = tk.BooleanVar(value=False)  # vue 3D isométrique du plateau (option ; la 2D par défaut)
        self.iso_angle = None  # rotation de la vue 3D ; None = celle qui montre le parcours le plus grand
        self._drag = None  # (x, y, déplacé ?) pendant un glissement de la souris
        # deck de départ de chaque coureur (panneau « Deck » sur le bord droit), relevé avant le premier tour
        self.start_decks = {r: deck_summary(whole_deck(r)) for r in self.game.riders}
        self.deck_open = False
        self._build()
        self._build_deck_panel()
        self.refresh()

    # --------------------------------------------------------------- construction

    def _build(self) -> None:
        ui.init(self.root)
        ui.place_window(self.root, WINDOW_W, WINDOW_H)
        self.parent.configure(bg=pal.BG)
        # tout l'écran de jeu, à gauche ; le panneau « Deck de départ » se range à sa droite et le pousse
        self.content = root = tk.Frame(self.parent, bg=pal.BG)
        root.pack(side="left", fill="both", expand=True)

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
        if self.on_menu is not None:
            ui.FlatButton(tools, "⟵  Menu", self.on_back, size=10, style="ghost").pack(side="left")
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

        # revoir la course (à l'arrivée) : lecture / pause, barre de progression, étape montrée, retour au podium
        self.replay_bar = rb = tk.Frame(root, bg=pal.BG)
        self.replay_toggle = ui.FlatButton(rb, "⟲  Revoir la course", self.toggle_replay, style="primary", size=10,
                                           padx=12, pady=5)
        self.replay_toggle.pack(side="left")
        self.replay_play = ui.FlatButton(rb, "▶", self.replay_play_pause, size=11, padx=12, pady=4)
        self.replay_var = tk.DoubleVar(value=0.0)
        self.replay_scale = tk.Scale(rb, from_=0, to=1, resolution=0.01, orient="horizontal", showvalue=False,
                                     variable=self.replay_var, command=self._on_replay_scale, bg=pal.BG,
                                     troughcolor=pal.CARD_HI, activebackground=pal.ACCENT, highlightthickness=0,
                                     bd=0, sliderlength=18, width=12, length=420)
        self.replay_label = tk.Label(rb, text="", font=ui.font(10, True), bg=pal.BG, fg=pal.TEXT)
        self.replay_t = 0.0  # position dans l'historique (fractionnaire : entre deux étapes)
        self.replay_playing = False
        self.replay_job = None
        self._replay_from_code = False

        bar = self.tool_bar = tk.Frame(root, bg=pal.BG)
        bar.pack(fill="x", padx=14, pady=(8, 0))
        ui.FlatButton(bar, "＋", lambda: self.zoom_at(1.4), size=11, padx=12, pady=4).pack(side="left")
        ui.FlatButton(bar, "－", lambda: self.zoom_at(1 / 1.4), size=11, padx=12, pady=4).pack(side="left", padx=(4, 0))
        ui.Segmented(bar, CAMERA_CHOICES, self.camera_var, command=self.set_camera).pack(side="left", padx=(10, 0))
        # vue 3D isométrique, et rotation du plateau autour de la verticale
        ui.Toggle(bar, "Vue 3D", self.iso_var, command=self.set_camera).pack(side="left", padx=(10, 0))
        ui.FlatButton(bar, "⟲", lambda: self.rotate(-ROTATE_STEP), size=11, padx=9, pady=4).pack(side="left", padx=(4, 0))
        ui.FlatButton(bar, "⟳", lambda: self.rotate(ROTATE_STEP), size=11, padx=9, pady=4).pack(side="left", padx=(2, 0))
        help_mark = tk.Label(bar, text="?", font=ui.font(10, True), bg=pal.CARD, fg=pal.MUTED, padx=7, pady=2,
                             cursor="question_arrow")
        help_mark.pack(side="left", padx=8)
        ui.Tooltip(help_mark, "Molette : zoom · glisser la carte : déplacer\nClic sur la carte : passer l'animation\n"
                              "Vue 3D : le plateau en relief ; ⟲ ⟳ le font tourner")
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
        """Variante Échappée : la carte misée par le coureur qui tente l'échappée."""
        self.ctl.choose(card)
        if self.ctl.current_rider is None:  # l'équipe a fini d'enchérir : on recache la main
            self.revealed = False
        self.refresh()

    # choix simultané : l'équipe qui choisit voit les mains de ses deux coureurs, en touche une carte dans chacune
    # (on peut changer d'avis), puis valide ; l'équipe suivante prend la main.

    def choosing_team(self):
        """L'équipe dont c'est le tour de choisir (la plus petite parmi celles qui ont encore des mains), ou None."""
        if self.ctl.phase != CHOOSE or not self.ctl.hands:
            return None
        return min(r.team for r in self.ctl.hands)

    def choosing_riders(self) -> list:
        team = self.choosing_team()
        return [r for r in self.game.riders if r in self.ctl.hands and r.team == team]

    def focus_rider(self):
        """Le coureur à mettre en avant (halo doré) : celui qui mise pour l'échappée, ou le premier coureur de l'équipe
        qui choisit dont la carte n'est pas encore choisie."""
        if self.ctl.current_rider is not None:
            return self.ctl.current_rider
        riders = self.choosing_riders()
        return next((r for r in riders if r not in self.picks), riders[0] if riders else None)

    def pick(self, rider, card) -> None:
        """Touche une carte pour ce coureur (sans la poser) ; un autre clic change d'avis."""
        if rider not in self.ctl.hands or card not in self.ctl.hands[rider]:
            return
        self.picks[rider] = card
        self._show_hand()
        self._paint_map()
        self._update_action()

    def validate(self) -> None:
        """Pose les cartes choisies de l'équipe qui choisit ; quand tout le monde a posé, place au mouvement."""
        riders = self.choosing_riders()
        if not riders or any(r not in self.picks for r in riders):
            return
        for rider in riders:
            self.ctl.choose_for(rider, self.picks.pop(rider))
        self.revealed = False  # en mode secret, l'équipe suivante doit dire qu'elle est prête
        self.refresh()

    def _bid_rider(self, rider) -> None:
        self.ctl.choose_bid_rider(rider)
        self.refresh()

    def on_action(self) -> None:
        """Passe à l'étape suivante du tour ; mouvement et aspiration sont animés."""
        if self.anim is not None:
            return
        phase = self.ctl.phase
        if phase == CHOOSE:  # choix simultané : le bouton valide les cartes de l'équipe qui choisit
            self.validate()
            return
        if phase == FINISHED and self.on_stage_end is not None:  # Grand Tour : écran des résultats de l'étape
            self.close()
            self.on_stage_end()
            return
        if phase == FINISHED:  # course unique terminée : plus rien à faire avancer
            return
        before = snapshot(self.game.riders)
        self.ctl.advance()
        self.revealed = False
        self.picks = {}
        moves = moves_between(before, self.game.riders)
        if moves and phase in (MOVEMENT, SLIPSTREAM) and self.animate_var.get() is True:
            self.anim = movement_animation(moves) if phase == MOVEMENT else slipstream_animation(moves)
            self.anim_start = time.monotonic()
            self.refresh()  # première image, boutons désactivés
            self._tick()
        else:
            self.refresh()

    # ------------------------------------------------------------ zoom de la carte

    def _proj(self):
        """La projection de la vue 3D (None : carte plate vue du dessus)."""
        if self.iso_var.get() is not True:
            return None
        if self.iso_angle is None:
            self.iso_angle = best_angle(self.game.track, BOARD_W, MAP_H)
        return projection(self.game.track, self.iso_angle)

    def rotate(self, step: float) -> None:
        """Tourne le plateau (vue 3D) ; le cadrage repart de la vue choisie (tout le parcours ou le suivi)."""
        if self.iso_var.get() is not True:
            self.iso_var.set(True)
        self.iso_angle = ((self.iso_angle if self.iso_angle is not None else best_angle(self.game.track, BOARD_W, MAP_H))
                          + step) % 360
        if self.camera_var.get() == "":
            self.camera_var.set(CAMERA_ALL)
        self.set_camera()

    def _auto_view(self):
        return map_transform(self.game, proj=self._proj())

    def _focus_view(self):
        """Cadrage automatique, recentré sur le milieu des coureurs : point de départ des boutons ＋ et －."""
        scale, _cx, _cy = self._auto_view()
        squares = layout_squares(self.game.track)
        spots = [(r.position, r.lane) for r in self.game.riders] or [(0, 0)]
        proj = self._proj()
        if proj is None:
            points = [point_on_road(squares, p, l) for p, l in spots]
        else:
            points = [proj(point_on_road(squares, p, l), proj.z_at(p)) for p, l in spots]
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
            # None (plus personne en course) : tout le parcours
            self.view = follow_view(self.game, which, proj=self._proj())

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
        if self.ctl.phase == FINISHED and self.anim is None:  # podium <-> revoir la course
            self.toggle_replay()
            return
        self.skip_animation()

    # ------------------------------------------------------------ revoir la course

    REPLAY_STEP_S = 0.8  # durée d'une étape de l'historique pendant la lecture

    def _replay_active(self) -> bool:
        return self.ctl.phase == FINISHED and self.anim is None and not self.show_podium and len(self.ctl.history) > 1

    def _replay_positions(self) -> dict:
        """Positions des coureurs à l'instant `replay_t` de l'historique (entre deux étapes : en douceur)."""
        history = self.ctl.history
        last = len(history) - 1
        t = min(max(self.replay_t, 0.0), float(last))
        i = min(int(t), max(last - 1, 0))
        f = ease(t - i)
        a, b = history[i][1], history[min(i + 1, last)][1]
        out = {}
        for rider in self.game.riders:
            if rider in a and rider in b:
                (p0, l0), (p1, l1) = a[rider], b[rider]
                out[rider] = (p0 + (p1 - p0) * f, l0 + (l1 - l0) * f)
        return out

    def toggle_replay(self) -> None:
        """Podium -> revoir la course (lecture depuis le départ) ; course -> podium."""
        if self.ctl.phase != FINISHED:
            return
        self.show_podium = not self.show_podium
        if self.show_podium:
            self._replay_stop()
        else:
            self.replay_t = 0.0
            self._replay_start()
        self._show_replay_bar()
        self._paint_map()

    def replay_play_pause(self) -> None:
        if self.replay_playing:
            self._replay_stop()
        else:
            if self.replay_t >= len(self.ctl.history) - 1:  # à la fin : on recommence
                self.replay_t = 0.0
            self._replay_start()
        self._show_replay_bar()

    def _replay_start(self) -> None:
        self.replay_playing = True
        self._replay_last = time.monotonic()
        if self.replay_job is None:
            self.replay_job = self.root.after(FRAME_MS, self._replay_tick)

    def _replay_stop(self) -> None:
        self.replay_playing = False
        if self.replay_job is not None:
            self.root.after_cancel(self.replay_job)
            self.replay_job = None

    def _replay_tick(self) -> None:
        self.replay_job = None
        if not self.replay_playing or not self._replay_active():
            self.replay_playing = False
            return
        now = time.monotonic()
        self.replay_t += (now - self._replay_last) / self.REPLAY_STEP_S
        self._replay_last = now
        last = len(self.ctl.history) - 1
        if self.replay_t >= last:  # arrivée : on s'arrête sur la dernière image
            self.replay_t = float(last)
            self.replay_playing = False
        self._sync_replay_bar()
        self._paint_map()
        if self.replay_playing:
            self.replay_job = self.root.after(FRAME_MS, self._replay_tick)
        else:
            self._show_replay_bar()

    def _on_replay_scale(self, value) -> None:
        """La barre de progression déplacée à la souris : on se place à cet instant (et la lecture s'arrête)."""
        if self._replay_from_code:
            return
        self._replay_stop()
        self.replay_t = float(value)
        self._sync_replay_bar()
        self._show_replay_bar()
        self._paint_map()

    def _sync_replay_bar(self) -> None:
        self._replay_from_code = True
        self.replay_var.set(self.replay_t)
        self._replay_from_code = False
        history = self.ctl.history
        step = min(int(round(self.replay_t)), len(history) - 1)
        self.replay_label.config(text=f"{history[step][0]}   ({step + 1}/{len(history)})")

    def _show_replay_bar(self) -> None:
        """À l'arrivée : la barre sous la carte (podium : « Revoir la course » ; course : lecture et progression)."""
        bar = self.replay_bar
        finished = self.ctl.phase == FINISHED and len(self.ctl.history) > 1
        if not finished:
            bar.pack_forget()
            return
        if not bar.winfo_ismapped():
            bar.pack(fill="x", padx=14, pady=(8, 0), before=self.tool_bar)
        replaying = not self.show_podium
        self.replay_toggle.config(text="🏆  Voir le podium" if replaying else "⟲  Revoir la course")
        for widget in (self.replay_play, self.replay_scale, self.replay_label):
            widget.pack_forget()
        if replaying:
            self.replay_scale.config(to=len(self.ctl.history) - 1)
            self.replay_play.config(text="⏸" if self.replay_playing else "▶")
            self.replay_play.pack(side="left", padx=(12, 6))
            self.replay_scale.pack(side="left", fill="x", expand=True, padx=(0, 10))
            self.replay_label.pack(side="left")
            self._sync_replay_bar()

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
        self._replay_stop()
        if self.deck_open:  # la fenêtre reprend sa largeur pour l'écran suivant
            try:
                self.set_deck_open(False)
            except tk.TclError:
                pass

    # ------------------------------------------------------------ deck de départ (bord droit)

    def _build_deck_panel(self) -> None:
        """Onglet « Deck » au bord droit de l'écran de jeu, et le panneau qu'il ouvre à sa droite (il pousse l'écran,
        sans le recouvrir) : le deck de départ des coureurs de l'équipe qui joue, une petite carte par valeur avec le
        nombre d'exemplaires dessous (comme en ligne)."""
        panel = self.deck_panel = tk.Frame(self.parent, bg=pal.PANEL, width=DECK_PANEL_W, highlightthickness=3,
                                           highlightbackground=pal.ACCENT, highlightcolor=pal.ACCENT)
        panel.pack_propagate(False)  # largeur fixe : c'est l'écran de jeu qui se pousse
        head = tk.Frame(panel, bg=pal.PANEL)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text="Deck de départ", font=ui.font(15, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left")
        ui.FlatButton(head, "✕", lambda: self.set_deck_open(False), size=10, style="ghost", padx=8, pady=2).pack(
            side="right")
        self.deck_body = tk.Frame(panel, bg=pal.PANEL)
        self.deck_body.pack(fill="both", expand=True, padx=16)
        # l'onglet, sur le bord droit de l'écran de jeu : contre le panneau quand il est ouvert
        tab = self.deck_tab = tk.Label(self.content, text="🂠\n\nD\nE\nC\nK", font=ui.font(10, True), bg=pal.CARD_HI,
                                       fg=pal.TEXT, padx=7, pady=12, cursor="hand2", justify="center",
                                       highlightthickness=1, highlightbackground=pal.BORDER)
        tab.place(relx=1.0, rely=0.5, anchor="e")
        tab.bind("<ButtonRelease-1>", lambda _e: self.set_deck_open(not self.deck_open))
        ui.Tooltip(tab, "Voir ou cacher le deck de départ des coureurs de l'équipe qui joue")
        self._width_before_deck = None

    def set_deck_open(self, open_: bool) -> None:
        """Ouvre ou ferme le panneau. Il se range à droite de l'écran de jeu et le pousse : la fenêtre s'élargit
        d'autant si l'écran le permet (sinon c'est l'écran de jeu qui se resserre), et reprend sa largeur à la
        fermeture. Une fenêtre agrandie (plein écran) ne change pas de taille."""
        if open_ == self.deck_open:
            return
        self.deck_open = open_
        win = self.root
        win.update_idletasks()
        zoomed = win.state() == "zoomed"
        if open_:
            if not zoomed:
                self._width_before_deck = win.winfo_width()
                wanted = min(self._width_before_deck + DECK_PANEL_W, win.winfo_screenwidth() - 20)
                x = max(0, min(win.winfo_x(), win.winfo_screenwidth() - wanted - 10))
                win.geometry(f"{wanted}x{win.winfo_height()}+{x}+{win.winfo_y()}")
            self.deck_panel.pack(side="right", fill="y", before=self.content)
            self._show_deck_panel()
        else:
            self.deck_panel.pack_forget()
            if not zoomed and self._width_before_deck:
                win.geometry(f"{self._width_before_deck}x{win.winfo_height()}+{win.winfo_x()}+{win.winfo_y()}")
            self._width_before_deck = None
        self.deck_tab.configure(bg=pal.ACCENT if open_ else pal.CARD_HI, fg="#ffffff" if open_ else pal.TEXT)
        self.deck_tab.lift()

    def _deck_team(self) -> int:
        """L'équipe dont on montre le deck : celle qui choisit, sinon la première équipe d'un joueur."""
        rider = self.focus_rider()
        if rider is not None:
            return rider.team
        humans = [t for t in range(len(self.game.team_types))
                  if t not in self.ctl.ai_teams and self.game.team_types[t] == TEAM_PLAYER]
        return humans[0] if humans else 0

    def _show_deck_panel(self) -> None:
        if not self.deck_open:
            return
        for widget in self.deck_body.winfo_children():
            widget.destroy()
        team = self._deck_team()
        riders = [r for r in self.start_decks if r.team == team]
        for rider in riders:
            cards = self.start_decks[rider]
            total = sum(c["count"] for c in cards)
            title = tk.Frame(self.deck_body, bg=pal.PANEL)
            title.pack(fill="x", pady=(12, 6))
            tk.Label(title, text=rider.name, font=ui.font(10, True), bg=pal.TEAM_FILL[rider.team],
                     fg=pal.LABEL_ON_FILL[rider.team], padx=5).pack(side="left")
            tk.Label(title, text=f" {rider.kind.capitalize()}", font=ui.font(11, True), bg=pal.PANEL,
                     fg=pal.TEXT).pack(side="left")
            tk.Label(title, text=f" · {total} cartes", font=ui.font(9), bg=pal.PANEL, fg=pal.MUTED).pack(side="left")
            grid = tk.Frame(self.deck_body, bg=pal.PANEL)
            grid.pack(fill="x")
            for i, card in enumerate(cards):
                cell = tk.Frame(grid, bg=pal.PANEL)
                cell.grid(row=i // DECK_PER_ROW, column=i % DECK_PER_ROW, padx=(0, 6), pady=(0, 6))
                tk.Label(cell, text=card["label"], font=ui.font(20 if len(card["label"]) <= 2 else 12, True),
                         bg="#94a3b8" if card["fatigue"] else "#f8fafc", fg="#0f172a", width=2 if len(card["label"]) <= 2 else 3,
                         height=1, padx=4, pady=6).pack()
                tk.Label(cell, text=f"×{card['count']}", font=ui.font(10, True), bg=pal.PANEL, fg=pal.MUTED).pack()
                ui.Tooltip(cell, f"{card['count']} carte{'s' if card['count'] > 1 else ''} {card['label']}")
        team_name = f"Équipe {team + 1}"
        tk.Label(self.deck_body, text=f"{team_name} : le deck avant la première carte de l'étape.", font=ui.font(8),
                 bg=pal.PANEL, fg=pal.FAINT, anchor="w", justify="left", wraplength=DECK_PANEL_W - DECK_TAB_W - 40).pack(
            fill="x", pady=(10, 0))

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
        self._show_deck_panel()
        self._show_replay_bar()
        self._update_action()
        self._flush_log()

    def _update_action(self) -> None:
        """Le grand bouton d'action : mouvement / aspiration / fatigue, résultats d'étape, ou, pendant le choix des
        cartes, « Valider les cartes » de l'équipe qui choisit (actif quand chaque coureur a sa carte)."""
        phase = self.ctl.phase
        tour_end = phase == FINISHED and self.on_stage_end is not None
        if phase == CHOOSE and self.choosing_riders():
            riders = self.choosing_riders()
            missing = [r.name for r in riders if r not in self.picks]
            hidden = self._secret() and not self.revealed
            text = (f"✓ Valider les cartes de l'équipe {riders[0].team + 1}" if not missing
                    else "Choisis une carte pour " + " et ".join(missing) + "…")
            self.action_btn.config(text=text, state="normal" if not missing and not hidden else "disabled")
            return
        self.action_btn.config(
            text="▶ Résultats de l'étape et classements" if tour_end else ACTION_TEXT[phase],
            state="normal" if (phase in (MOVEMENT, SLIPSTREAM, EXHAUSTION) or tour_end) and self.anim is None else "disabled",
        )

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
        replay = self._replay_active()
        if replay:  # revoir la course : les coureurs là où ils étaient à ce moment de la course
            positions = self._replay_positions()
        self._follow_camera()
        shapes = map_primitives(
            self.game,
            None if replay else self.focus_rider(),
            positions=positions,
            view=self.view,
            proj=self._proj(),
        )
        self._paint(self.board, shapes)
        riders = self.game.riders
        if replay:  # le profil suit aussi la relecture : des copies des coureurs, placées à ce moment de la course
            riders = [replace(r, position=int(round(positions[r][0])), lane=int(round(positions[r][1])))
                      for r in self.game.riders if r in positions]
        self._paint(self.profile, profile_primitives(self.game.track, BOARD_W, PROFILE_H, riders=riders,
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
            ui.paint(self.board, map_weather_fx_primitives(self.game, t, view=self.view, proj=self._proj()), tags=("fx",))
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
        if self.ctl.phase == CHOOSE:
            self._show_team_hands(frame)
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
        for card in sorted(self.ctl.hand, key=lambda c: c.value):  # cartes blanches, comme en ligne
            text = "A 2/9" if card.special == "attaque" else str(card.value)
            caption = "fatigue" if card.exhaustion else "muscle" if card.special == "muscle" else ""
            ui.PlayingCard(row, text, lambda c=card: self.on_card(c), fatigue=card.exhaustion, caption=caption).pack(
                side="left", padx=(0, 10))
        tk.Label(
            frame, text=f"Pioche : {len(rider.draw_pile)} cartes   ·   Recyclage : {len(rider.recycle)} cartes",
            font=ui.font(10), bg=pal.CARD, fg=pal.MUTED,
        ).pack(anchor="w", pady=(10, 0))

    def _show_team_hands(self, frame) -> None:
        """Choix simultané : les mains des deux coureurs de l'équipe qui choisit, une carte à toucher dans chacune,
        puis « Valider mes cartes »."""
        riders = self.choosing_riders()
        if not riders:
            tk.Label(frame, text="Les cartes sont posées.", font=ui.font(12), bg=pal.CARD, fg=pal.MUTED).pack(anchor="w")
            return
        team = riders[0].team
        head = tk.Frame(frame, bg=pal.CARD)
        head.pack(anchor="w", fill="x")
        tk.Label(head, text=f"Équipe {team + 1}", font=ui.font(12, True), bg=pal.TEAM_FILL[team],
                 fg=pal.LABEL_ON_FILL[team], padx=9, pady=3).pack(side="left")
        tk.Label(head, text="une carte pour chaque coureur", font=ui.font(11, True), bg=pal.CARD,
                 fg=pal.TEAM_TEXT[team]).pack(side="left", padx=10)
        if self._secret() and not self.revealed:
            tk.Label(frame, text="Les autres équipes ne regardent pas !", font=ui.font(11), bg=pal.CARD,
                     fg=pal.MUTED).pack(anchor="w", pady=(10, 8))
            ui.FlatButton(frame, f"Équipe {team + 1} prête : afficher mes mains", self._reveal, style="primary",
                          size=11).pack(anchor="w")
            return
        for rider in riders:
            block = tk.Frame(frame, bg=pal.CARD)
            block.pack(anchor="w", fill="x", pady=(4, 0))
            line = tk.Frame(block, bg=pal.CARD)
            line.pack(anchor="w", fill="x")
            tk.Label(line, text=rider.name, font=ui.font(10, True), bg=pal.TEAM_FILL[rider.team],
                     fg=pal.LABEL_ON_FILL[rider.team], padx=6).pack(side="left")
            tk.Label(line, text=f" {rider.kind} · case {rider.position}", font=ui.font(10, True), bg=pal.CARD,
                     fg=pal.TEXT).pack(side="left")
            ahead = " ".join(terrain_text(self.game, s) for s in range(rider.position + 1, rider.position + 9))
            tk.Label(line, text=f"   devant : {ahead}", font=ui.font(9), bg=pal.CARD, fg=pal.MUTED).pack(side="left")
            row = tk.Frame(block, bg=pal.CARD)
            row.pack(anchor="w", pady=(3, 0))
            chosen = self.picks.get(rider)
            for card in sorted(self.ctl.hands[rider], key=lambda c: c.value):
                text = "A 2/9" if card.special == "attaque" else str(card.value)
                caption = "fatigue" if card.exhaustion else "muscle" if card.special == "muscle" else ""
                ui.PlayingCard(row, text, lambda r=rider, c=card: self.pick(r, c), fatigue=card.exhaustion,
                               caption=caption, selected=card is chosen, scale=HAND_CARD_SCALE).pack(
                    side="left", padx=(0, 8))
        # la validation se fait avec le grand bouton d'action, à droite (« ✓ Valider les cartes »)

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
