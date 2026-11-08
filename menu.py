"""Menu de démarrage, en trois écrans :

1. le type de course : course unique ou Grand Tour ;
2. le parcours (course unique) ou les étapes du Tour, avec l'aperçu, le profil et l'éditeur de parcours ;
3. « Qui joue ? » : le nombre d'équipes et, pour chacune, joueur, IA ou équipe fantôme.
"""
import tkinter as tk
from tkinter import filedialog, messagebox

import ui
from flamme_rouge import palette as pal
from flamme_rouge.boardview import profile_primitives, track_preview_primitives
from flamme_rouge.catalog import GROUP_BASE, GROUP_MINE, GROUP_OFFICIAL, GROUP_PELOTON, Choice, build_choices
from flamme_rouge.extensions import EXTENSIONS, PELOTON
from flamme_rouge.game import TEAM_MUSCLE, TEAM_PELOTON, TEAM_PLAYER
from flamme_rouge.paths import PARCOURS_DIR, ensure_parcours_dir
from flamme_rouge.tiles import KIND_FINISH, KIND_START, make_tile
from flamme_rouge.track import BREAKAWAY

PREVIEW_W, PREVIEW_H = 700, 340
PROFILE_H = 130
TOUR_PARCOURS_H, TOUR_LIST_H = 230, 150  # Grand Tour : parcours et liste du Tour l'un sous l'autre, à gauche
LIST_W = 360
WINDOW_W, WINDOW_H = 1180, 820
SINGLE, TOUR = "course", "tour"  # types de course
MIN_TOUR_STAGES = 3
HUMAN, AI, PELOTON_TEAM, MUSCLE_TEAM = "joueur", "ia", "peloton", "muscle"  # PELOTON_TEAM, MUSCLE_TEAM : Peloton
TEAM_COLORS = ["rouge", "bleue", "verte", "jaune", "rose", "blanche"]  # dans l'ordre de palette.TEAM_FILL
PLAYER_LABELS = {HUMAN: "Joueur", AI: "IA", PELOTON_TEAM: "Équipe Peloton", MUSCLE_TEAM: "Équipe Muscle"}
DEFAULT_CHOICE = "officiel:Avenue Corso Paseo"  # l'étape conseillée pour une première partie
TEAM_CHOICES = [(n, f"{n} équipes") for n in range(2, 7)]  # 5 et 6 : extension Peloton
GROUP_HINTS = {
    GROUP_BASE: "21 tuiles comme dans la boîte (même composition que les cartes étape, sans en être la copie).",
    GROUP_OFFICIAL: "Les cartes étape du jeu, avec les tuiles de la boîte.",
    GROUP_PELOTON: "Les étapes 7 à 12 de l'extension (pavés, ravitaillement, échappée) : extension Peloton.",
    GROUP_MINE: "Parcours créés avec l'éditeur (dossier « parcours »).",
}
RACE_TYPES = [
    (SINGLE, "COURSE UNIQUE", "Une étape, un vainqueur : le premier qui passe la ligne."),
    (TOUR, "GRAND TOUR", "Plusieurs étapes à la suite : temps, maillots jaune, vert et à pois, Points de Tour. "
                         "La fatigue suit les coureurs d'une étape à l'autre."),
]


class ChoiceRow(tk.Frame):
    """Une ligne de la liste des parcours : un titre, un sous-titre, un liseré rouge quand elle est choisie."""

    def __init__(self, parent, choice: Choice, selected: bool, on_click):
        super().__init__(parent, bg=pal.CARD, cursor="hand2" if choice.playable else "arrow")
        self.choice, self.selected, self.on_click = choice, selected, on_click
        self.strip = tk.Frame(self, width=4, bg=pal.CARD)
        self.strip.pack(side="left", fill="y")
        body = tk.Frame(self, bg=pal.CARD)
        body.pack(side="left", fill="x", expand=True, padx=(10, 8), pady=6)
        self.title = tk.Label(body, text=choice.label, font=ui.font(11, True), bg=pal.CARD, anchor="w", justify="left")
        self.title.pack(fill="x")
        sub = choice.details if choice.playable else "Bientôt disponible"
        self.subtitle = tk.Label(body, text=sub, font=ui.font(9), bg=pal.CARD, anchor="w")
        self.subtitle.pack(fill="x")
        self.body = body
        for widget in (self, self.strip, body, self.title, self.subtitle):
            widget.bind("<ButtonRelease-1>", lambda _e: self.on_click(self.choice))
            widget.bind("<Enter>", lambda _e: self.paint(True))
            widget.bind("<Leave>", lambda _e: self.paint(False))
        self.paint(False)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.paint(False)

    def paint(self, hover: bool) -> None:
        playable = self.choice.playable
        bg = pal.CARD_HI if (self.selected or (hover and playable)) else pal.CARD
        for widget in (self, self.body, self.title, self.subtitle):
            widget.configure(bg=bg)
        self.strip.configure(bg=pal.ACCENT if self.selected else bg)
        self.title.configure(fg=pal.TEXT if playable else pal.FAINT)
        self.subtitle.configure(fg=pal.MUTED if playable else pal.FAINT)


class MenuScreen:
    def __init__(self, parent, on_start, on_start_tour=None):
        """`on_start(track, teams, secret, animate, extensions, ai_teams, team_types, breakaway)` lance une course ;
        `on_start_tour(stages, teams, secret, animate, extensions, ai_teams, team_types, breakaway, rest_after)`
        lance un Grand Tour (sans elle, le Grand Tour n'est pas proposé)."""
        self.parent = parent
        self.root = parent.winfo_toplevel()
        ui.init(self.root)
        self.root.title("Flamme Rouge")
        ui.place_window(self.root, WINDOW_W, WINDOW_H)
        parent.configure(bg=pal.BG)
        self.on_start = on_start
        self.on_start_tour = on_start_tour
        self.mode = None  # SINGLE ou TOUR, choisi sur le premier écran
        self.tour_order: list[Choice] = []  # étapes du Tour, dans l'ordre
        self.tour_rest_var = tk.StringVar(value="aucun")
        self.extra_files: list[str] = []
        self.choices: list[Choice] = []
        self.rows: dict[str, ChoiceRow] = {}
        self.choice_var = tk.StringVar(value=DEFAULT_CHOICE)
        self.teams_var = tk.IntVar(value=2)
        self.secret_var = tk.BooleanVar(value=False)
        self.animate_var = tk.BooleanVar(value=True)
        self.extension_vars = {name: tk.BooleanVar(value=False) for name in EXTENSIONS}
        # qui joue chaque équipe : la 1re par un joueur, les autres par l'IA (modifiable sur l'écran « Qui joue ? »)
        self.player_vars = [tk.StringVar(value=HUMAN if team == 0 else AI) for team in range(len(TEAM_COLORS))]
        self.breakaway_var = tk.BooleanVar(value=True)  # variante Échappée (extension Peloton, tuile 2 sur le parcours)
        self.type_frame = None
        self.frame = None
        self.players_frame = None
        self.editor_win = None
        self.show_type_screen()

    # ------------------------------------------------------------ écran 1 : type de course

    def _logo_header(self, parent, subtitle: str) -> None:
        header = tk.Frame(parent, bg=pal.PANEL)
        header.pack(fill="x")
        logo = tk.Frame(header, bg=pal.PANEL)
        logo.pack(side="left", padx=24, pady=(14, 12))
        tk.Label(logo, text="FLAMME ", font=ui.font(26, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left")
        tk.Label(logo, text="ROUGE", font=ui.font(26, True), bg=pal.PANEL, fg=pal.ACCENT).pack(side="left")
        tk.Label(header, text=subtitle, font=ui.font(11), bg=pal.PANEL, fg=pal.MUTED).pack(side="left", padx=4, pady=(14, 0))
        tk.Frame(parent, bg=pal.ACCENT, height=3).pack(fill="x")

    def show_type_screen(self) -> None:
        """Premier écran : course unique ou Grand Tour."""
        for frame in (self.frame, self.players_frame):
            if frame is not None:
                frame.destroy()
        self.frame = self.players_frame = None
        frame = self.type_frame = tk.Frame(self.parent, bg=pal.BG)
        frame.pack(fill="both", expand=True)
        self._logo_header(frame, "Course cycliste à cartes")
        body = tk.Frame(frame, bg=pal.BG)
        body.pack(expand=True)
        ui.title_label(body, "Quelle course ?").pack(pady=(0, 18))
        cards = tk.Frame(body, bg=pal.BG)
        cards.pack()
        for mode, title, text in RACE_TYPES:
            available = mode == SINGLE or self.on_start_tour is not None
            card = tk.Frame(cards, bg=pal.CARD, highlightthickness=2, highlightbackground=pal.BORDER,
                            cursor="hand2" if available else "arrow", width=380, height=220)
            card.pack(side="left", padx=16)
            card.pack_propagate(False)
            title_label = tk.Label(card, text=title, font=ui.font(22, True), bg=pal.CARD,
                                   fg=pal.ACCENT if available else pal.FAINT)
            title_label.pack(pady=(40, 14))
            text_label = tk.Label(card, text=text, font=ui.font(11), bg=pal.CARD, fg=pal.MUTED, wraplength=320,
                                  justify="center")
            text_label.pack(padx=20)
            if not available:
                continue
            for widget in (card, title_label, text_label):
                widget.bind("<ButtonRelease-1>", lambda _e, m=mode: self.choose_mode(m))
                widget.bind("<Enter>", lambda _e, c=card: c.configure(highlightbackground=pal.ACCENT))
                widget.bind("<Leave>", lambda _e, c=card: c.configure(highlightbackground=pal.BORDER))

    def choose_mode(self, mode: str) -> None:
        """Course unique ou Grand Tour : on passe au choix du parcours (ou des étapes)."""
        self.mode = mode
        if self.type_frame is not None:
            self.type_frame.destroy()
            self.type_frame = None
        self.frame = tk.Frame(self.parent, bg=pal.BG)
        self.frame.pack(fill="both", expand=True)
        self._build()
        self.reload()

    # ------------------------------------------------------------ écran 2 : parcours ou étapes

    def _build(self) -> None:
        tour = self.mode == TOUR
        self._logo_header(self.frame, "Grand Tour : choisis les étapes" if tour else "Course unique : choisis le parcours")

        # ----- corps : liste à gauche, aperçu (et liste du Tour) à droite
        body = tk.Frame(self.frame, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=24, pady=(14, 0))

        preview_h, profile_h = PREVIEW_H, PROFILE_H
        left = tk.Frame(body, bg=pal.BG)
        left.pack(side="left", fill="y")
        ui.title_label(left, "Parcours (clic : aperçu)" if tour else "Choisis le parcours").pack(anchor="w", pady=(0, 8))
        listing = ui.card(left)
        listing.pack(fill="both", expand=True)
        # Grand Tour : la liste du Tour se range sous les parcours, l'aperçu garde toute sa taille
        list_h = TOUR_PARCOURS_H if tour else preview_h + profile_h - 4
        self.scroll = ui.ScrollFrame(listing, width=LIST_W, height=list_h)
        self.scroll.pack(fill="both", expand=True, padx=1, pady=1)
        actions = tk.Frame(left, bg=pal.BG)
        actions.pack(fill="x", pady=(10, 0))
        ui.FlatButton(actions, "＋  Créer un parcours", self.on_create, size=10).pack(side="left")
        ui.FlatButton(actions, "Ouvrir un fichier", self.on_open_file, size=10, style="ghost").pack(side="left", padx=8)
        if tour:
            self._build_tour_list(left)

        right = tk.Frame(body, bg=pal.BG)
        right.pack(side="left", fill="both", expand=True, padx=(24, 0))
        head = tk.Frame(right, bg=pal.BG)
        head.pack(fill="x", pady=(0, 8))
        ui.title_label(head, "Aperçu").pack(side="left")
        self.details_title = tk.Label(head, text="", font=ui.font(12, True), bg=pal.BG, fg=pal.TEXT, anchor="w")
        self.details_title.pack(side="left", padx=12)
        self.add_btn = None
        if tour:
            self.add_btn = ui.FlatButton(head, "＋  Ajouter au Tour", self.tour_add_current, style="primary", size=10, pady=5)
            self.add_btn.pack(side="right")
        self.details_label = tk.Label(head, text="", font=ui.font(10), bg=pal.BG, fg=pal.MUTED, anchor="w",
                                      wraplength=240, justify="left")  # un long texte passe à la ligne
        self.details_label.pack(side="left")
        # l'aperçu prend toute la hauteur libre ; le profil reste collé en bas de la colonne
        view = ui.card(right)
        view.pack(fill="both", expand=True)
        self.preview_w, self.preview_h, self.profile_h = PREVIEW_W, preview_h, profile_h
        self.profile = tk.Canvas(view, width=PREVIEW_W, height=profile_h, bg=pal.CARD, highlightthickness=0)
        self.profile.pack(side="bottom", fill="x", padx=1, pady=(0, 1))
        self.preview = tk.Canvas(view, width=PREVIEW_W, height=preview_h, bg=pal.GRASS, highlightthickness=0)
        self.preview.pack(fill="both", expand=True, padx=1, pady=(1, 0))
        self.preview.bind("<Configure>", self._on_preview_resize)

        # ----- barre du bas : options, extensions, suite
        tk.Frame(self.frame, bg=pal.BORDER, height=1).pack(fill="x", pady=(14, 0))
        bottom = tk.Frame(self.frame, bg=pal.PANEL)
        bottom.pack(fill="x")
        inner = tk.Frame(bottom, bg=pal.PANEL)
        inner.pack(fill="x", padx=24, pady=14)
        # retour en bas à gauche, comme « Retour au parcours » sur l'écran « Qui joue ? »
        ui.FlatButton(inner, "⟵  Type de course", self.show_type_screen, size=11, style="ghost").pack(side="left")
        tk.Label(inner, text="Extensions et options : à l'écran suivant", font=ui.font(10), bg=pal.PANEL,
                 fg=pal.FAINT).pack(side="left", padx=20)
        self.start_btn = ui.FlatButton(inner, "Suivant : qui joue ?  ▶", self.on_launch, style="primary", size=14,
                                       padx=28, pady=12)
        self.start_btn.pack(side="right")

    def _build_tour_list(self, parent) -> None:
        """Grand Tour : la liste ordonnée des étapes (▲ ▼ ✕) et le jour de repos."""
        head = tk.Frame(parent, bg=pal.BG)
        head.pack(fill="x", pady=(14, 4))
        ui.title_label(head, "Ton Tour").pack(side="left")
        ui.FlatButton(head, "Tout enlever", self.tour_clear, size=9, style="ghost", pady=3).pack(side="right")
        ui.FlatButton(head, "6 officielles", self.tour_preset_official, size=9, pady=3).pack(side="right", padx=4)
        box = ui.card(parent)
        box.pack(fill="x")
        self.tour_scroll = ui.ScrollFrame(box, width=LIST_W, height=TOUR_LIST_H)
        self.tour_scroll.pack(fill="x", padx=1, pady=1)
        rest = tk.Frame(parent, bg=pal.BG)
        rest.pack(fill="x", pady=(6, 0))
        tk.Label(rest, text="Repos après l'étape", font=ui.font(10, True), bg=pal.BG, fg=pal.TEXT).pack(side="left")
        self.rest_menu_frame = tk.Frame(rest, bg=pal.BG)
        self.rest_menu_frame.pack(side="left", padx=10)
        self.tour_count = tk.Label(rest, text="", font=ui.font(10), bg=pal.BG, fg=pal.MUTED)
        self.tour_count.pack(side="right")

    # ------------------------------------------------------------------- contenu

    def reload(self) -> None:
        """Relit la liste des parcours (après un enregistrement dans l'éditeur, par exemple)."""
        if self.frame is None:
            return
        selected = self.choice_var.get()
        ensure_parcours_dir()
        self.choices = build_choices(PARCOURS_DIR, self.extra_files)
        inner = self.scroll.inner
        for widget in inner.winfo_children():
            widget.destroy()
        self.rows = {}
        keys = {c.key for c in self.choices if c.playable}
        if selected not in keys:
            selected = DEFAULT_CHOICE if DEFAULT_CHOICE in keys else next(iter(sorted(keys)), "")
            self.choice_var.set(selected)
        group = None
        for choice in self.choices:
            if choice.group != group:
                group = choice.group
                self._group_header(group)
            row = ChoiceRow(inner, choice, choice.key == selected, self.on_pick)
            row.pack(fill="x", padx=8, pady=1)
            self.rows[choice.key] = row
        if not any(c.group == GROUP_MINE for c in self.choices):
            self._group_header(GROUP_MINE)
            tk.Label(
                inner, text="Aucun pour l'instant : crée-en un avec le bouton ci-dessous.", font=ui.font(9),
                bg=pal.CARD, fg=pal.FAINT, anchor="w", wraplength=LIST_W - 40, justify="left",
            ).pack(fill="x", padx=18, pady=(0, 8))
        if self.mode == TOUR:  # les étapes déjà choisies suivent les parcours relus (un parcours modifié, par exemple)
            by_key = {c.key: c for c in self.choices if c.playable}
            self.tour_order = [by_key[c.key] for c in self.tour_order if c.key in by_key]
            self.refresh_tour()
        self.on_select()

    def _group_header(self, group: str) -> None:
        tk.Label(self.scroll.inner, text=group.upper(), font=ui.font(9, True), bg=pal.CARD, fg=pal.ACCENT, anchor="w").pack(
            fill="x", padx=14, pady=(12, 2)
        )
        if group in GROUP_HINTS:
            tk.Label(
                self.scroll.inner, text=GROUP_HINTS[group], font=ui.font(8), bg=pal.CARD, fg=pal.FAINT, anchor="w",
                wraplength=LIST_W - 40, justify="left",
            ).pack(fill="x", padx=14, pady=(0, 4))

    def current(self) -> Choice:
        key = self.choice_var.get()
        return next(c for c in self.choices if c.key == key)

    def on_pick(self, choice: Choice) -> None:
        """Clic sur une ligne : un parcours indisponible s'affiche (avec la raison) mais ne se lance pas."""
        self.choice_var.set(choice.key)
        self.on_select()

    def _on_preview_resize(self, event) -> None:
        """L'aperçu a changé de taille (fenêtre agrandie, colonne étirée) : on redessine à la nouvelle taille."""
        size = (max(event.width, 100), max(event.height, 100))
        if size != (self.preview_w, self.preview_h):
            self.preview_w, self.preview_h = size
            if self.choices:
                self.on_select()

    def on_select(self) -> None:
        choice = self.current()
        for key, row in self.rows.items():
            row.set_selected(key == choice.key)
        self.preview.delete("all")
        self.profile.delete("all")
        if choice.track is None:
            self.preview.create_text(self.preview_w / 2, self.preview_h / 2, text=choice.details,
                                     width=self.preview_w - 80, fill=pal.MUTED, font=ui.font(12))
        else:
            ui.paint(self.preview, track_preview_primitives(choice.track, self.preview_w, self.preview_h))
            ui.paint(self.profile, profile_primitives(choice.track, self.preview_w, self.profile_h))
        self.details_title.config(text=choice.label)
        self.details_label.config(text=choice.details)
        if self.add_btn is not None:
            self.add_btn.config(state="normal" if choice.playable else "disabled")
        self._refresh_start()

    def _refresh_start(self) -> None:
        if self.mode == TOUR:
            ok = len(self.tour_order) >= MIN_TOUR_STAGES
        else:
            ok = self.current().playable
        self.start_btn.config(state="normal" if ok else "disabled")

    # ------------------------------------------------------------ Grand Tour : liste des étapes

    def tour_add_current(self) -> None:
        choice = self.current()
        if choice.playable:
            self.tour_order.append(choice)
            self.refresh_tour()

    def tour_remove(self, index: int) -> None:
        del self.tour_order[index]
        self.refresh_tour()

    def tour_move(self, index: int, delta: int) -> None:
        """Avance (delta = -1) ou recule (delta = +1) une étape dans l'ordre du Tour."""
        target = index + delta
        if 0 <= target < len(self.tour_order):
            self.tour_order[index], self.tour_order[target] = self.tour_order[target], self.tour_order[index]
            self.refresh_tour()

    def tour_preset_official(self) -> None:
        self.tour_order = [c for c in self.choices if c.playable and c.group == GROUP_OFFICIAL]
        self.refresh_tour()

    def tour_clear(self) -> None:
        self.tour_order = []
        self.refresh_tour()

    def tour_rest_after(self) -> set[int]:
        value = self.tour_rest_var.get()
        return {int(value)} if value.isdigit() else set()

    def refresh_tour(self) -> None:
        inner = self.tour_scroll.inner
        for widget in inner.winfo_children():
            widget.destroy()
        if not self.tour_order:
            tk.Label(inner, text="Aucune étape : choisis un parcours ci-dessus, puis « Ajouter au Tour » (au moins 3).",
                     font=ui.font(10), bg=pal.CARD, fg=pal.FAINT, wraplength=LIST_W - 30, justify="left").pack(
                anchor="w", padx=10, pady=8)
        rest = self.tour_rest_after()
        for i, choice in enumerate(self.tour_order):
            row = tk.Frame(inner, bg=pal.CARD)
            row.pack(fill="x", padx=6, pady=1)
            tk.Label(row, text=f"Étape {i + 1}", font=ui.font(10, True), bg=pal.CARD, fg=pal.ACCENT, width=8,
                     anchor="w").pack(side="left")
            name = tk.Label(row, text=choice.label, font=ui.font(10), bg=pal.CARD, fg=pal.TEXT, anchor="w", cursor="hand2")
            name.pack(side="left")
            name.bind("<ButtonRelease-1>", lambda _e, c=choice: self.on_pick(c))  # clic : son aperçu
            if i + 1 in rest and i + 1 < len(self.tour_order):
                tk.Label(row, text="· repos", font=ui.font(9, True), bg=pal.CARD, fg=pal.GOOD).pack(
                    side="left", padx=8)
            ui.FlatButton(row, "✕", lambda i=i: self.tour_remove(i), size=9, style="ghost", padx=6, pady=1).pack(side="right")
            down = ui.FlatButton(row, "▼", lambda i=i: self.tour_move(i, 1), size=9, style="ghost", padx=6, pady=1)
            down.pack(side="right")
            up = ui.FlatButton(row, "▲", lambda i=i: self.tour_move(i, -1), size=9, style="ghost", padx=6, pady=1)
            up.pack(side="right")
            if i == 0:
                up.config(state="disabled")
            if i == len(self.tour_order) - 1:
                down.config(state="disabled")
        for widget in self.rest_menu_frame.winfo_children():
            widget.destroy()
        options = ["aucun"] + [str(n) for n in range(1, len(self.tour_order))]
        if self.tour_rest_var.get() not in options:
            self.tour_rest_var.set("aucun")
        menu = tk.OptionMenu(self.rest_menu_frame, self.tour_rest_var, *options, command=lambda _v: self.refresh_tour())
        ui.style_option_menu(menu)
        menu.pack()
        n = len(self.tour_order)
        length = "court" if n <= 7 else "moyen" if n <= 14 else "long"
        self.tour_count.config(text=f"{n} étape(s) · {length}" if n else "")
        self._refresh_start()

    # ------------------------------------------------------------------- actions

    def on_launch(self) -> None:
        """« Suivant » : vérifications, puis l'écran « Qui joue ? »."""
        if self.mode == TOUR:
            if len(self.tour_order) < MIN_TOUR_STAGES:
                messagebox.showinfo("Grand Tour", "Un Tour compte au moins 3 étapes.")
                return
            stages = self.tour_order
        else:
            choice = self.current()
            if not choice.playable:
                messagebox.showinfo("Parcours indisponible", choice.details)
                return
            stages = [choice]
        if self.needs_peloton():  # une étape Peloton : l'extension est cochée d'office sur « Qui joue ? »
            self.extension_vars[PELOTON].set(True)
        self.show_players()

    def needs_peloton(self) -> bool:
        stages = self.tour_order if self.mode == TOUR else [self.current()]
        return any(c.group == GROUP_PELOTON for c in stages)

    # ------------------------------------------------------------ écran 3 : « Qui joue ? »

    def ai_teams(self) -> frozenset[int]:
        """Les équipes (0 = première) jouées par l'IA, parmi celles de la course."""
        return frozenset(t for t in range(int(self.teams_var.get())) if self.player_vars[t].get() == AI)

    def team_types(self) -> list[str]:
        """Pour le moteur : « joueur » (joueur ou IA), « peloton » ou « muscle » pour chaque équipe."""
        kinds = {PELOTON_TEAM: TEAM_PELOTON, MUSCLE_TEAM: TEAM_MUSCLE}
        return [kinds.get(self.player_vars[t].get(), TEAM_PLAYER) for t in range(int(self.teams_var.get()))]

    def player_options(self) -> list[str]:
        """Choix possibles pour une équipe : les équipes fantômes demandent l'extension Peloton."""
        return [HUMAN, AI, PELOTON_TEAM, MUSCLE_TEAM] if PELOTON in self.extensions() else [HUMAN, AI]

    def show_players(self) -> None:
        """Écran « Qui joue ? » : le nombre d'équipes, puis joueur, IA ou équipe fantôme pour chacune."""
        if self.frame is not None:
            self.frame.pack_forget()
        if self.players_frame is not None:
            self.players_frame.destroy()
        frame = self.players_frame = tk.Frame(self.parent, bg=pal.BG)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=pal.PANEL)
        header.pack(fill="x")
        tk.Label(header, text="QUI JOUE ?", font=ui.font(22, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left", padx=24, pady=14)
        what = f"Grand Tour · {len(self.tour_order)} étapes" if self.mode == TOUR else self.current().label
        tk.Label(header, text=what, font=ui.font(11), bg=pal.PANEL, fg=pal.MUTED).pack(side="left", pady=(10, 0))
        tk.Frame(frame, bg=pal.ACCENT, height=3).pack(fill="x")

        body = tk.Frame(frame, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=60, pady=16)
        # extensions et options, rangées sous les équipes (posées en fin de méthode)
        settings = tk.Frame(body, bg=pal.BG)
        exts = tk.Frame(settings, bg=pal.BG)
        exts.pack(side="left")
        ui.title_label(exts, "Extensions").pack(anchor="w")
        row = tk.Frame(exts, bg=pal.BG)
        row.pack(anchor="w", pady=(6, 0))
        for name, (label, _description) in EXTENSIONS.items():
            ui.Toggle(row, label, self.extension_vars[name], command=self._extensions_changed_on_players).pack(
                side="left", padx=(0, 4))
        chosen = self.extensions()
        hint = " · ".join(EXTENSIONS[n][1] for n in EXTENSIONS if n in chosen) or "aucune : jeu de base"
        self.extensions_hint = tk.Label(exts, text=hint, font=ui.font(9), bg=pal.BG, fg=pal.FAINT, anchor="w")
        self.extensions_hint.pack(anchor="w", pady=(2, 0))
        opts = tk.Frame(settings, bg=pal.BG)
        opts.pack(side="right", anchor="n")
        ui.title_label(opts, "Options").pack(anchor="w")
        row = tk.Frame(opts, bg=pal.BG)
        row.pack(anchor="w", pady=(6, 0))
        ui.Toggle(row, "Animations", self.animate_var).pack(side="left", padx=(0, 4))
        ui.Toggle(row, "Mode secret", self.secret_var).pack(side="left")
        count = tk.Frame(body, bg=pal.BG)
        count.pack(fill="x", pady=(0, 12))
        ui.title_label(count, "Nombre d'équipes").pack(side="left")
        ui.Segmented(count, TEAM_CHOICES, self.teams_var, command=self.show_players).pack(side="left", padx=16)
        if PELOTON not in self.extensions():
            tk.Label(count, text="5 et 6 équipes : extension Peloton", font=ui.font(9), bg=pal.BG, fg=pal.FAINT).pack(
                side="left")
        options = self.player_options()
        title = "Pour chaque équipe : un joueur, l'IA, ou une équipe fantôme de l'extension Peloton" if len(options) > 2 \
            else "Pour chaque équipe, choisis un joueur ou l'IA"
        ui.title_label(body, title, 12).pack(anchor="w", pady=(0, 8))
        for team in range(int(self.teams_var.get())):
            if self.player_vars[team].get() not in options:
                self.player_vars[team].set(AI)
            row = ui.card(body)
            row.pack(fill="x", pady=3)
            inner = tk.Frame(row, bg=pal.CARD)
            inner.pack(fill="x", padx=16, pady=6)
            dot = tk.Canvas(inner, width=30, height=30, bg=pal.CARD, highlightthickness=0)
            dot.create_oval(3, 3, 27, 27, fill=pal.TEAM_FILL[team], outline="#ffffff", width=2)
            dot.pack(side="left")
            tk.Label(inner, text=f"Équipe {team + 1}", font=ui.font(14, True), bg=pal.CARD, fg=pal.TEXT).pack(side="left", padx=(12, 6))
            tk.Label(inner, text=TEAM_COLORS[team], font=ui.font(11), bg=pal.CARD, fg=pal.TEAM_TEXT[team]).pack(side="left")
            ui.Segmented(inner, [(o, PLAYER_LABELS[o]) for o in options], self.player_vars[team],
                         command=self._refresh_players).pack(side="right")
        self.players_hint = tk.Label(body, text="", font=ui.font(10), bg=pal.BG, fg=pal.MUTED, anchor="w", justify="left")
        self.players_hint.pack(fill="x", pady=(10, 0))
        if self.breakaway_available():
            row = tk.Frame(body, bg=pal.BG)
            row.pack(fill="x", pady=(12, 0))
            ui.Toggle(row, "Variante Échappée", self.breakaway_var).pack(side="left")
            tk.Label(row, text="avant le départ, chaque équipe peut miser deux cartes d'un coureur pour partir devant",
                     font=ui.font(10), bg=pal.BG, fg=pal.MUTED).pack(side="left", padx=10)
        settings.pack(fill="x", side="bottom")  # collé en bas de l'écran, juste au-dessus de la barre des boutons
        tk.Frame(body, bg=pal.BORDER, height=1).pack(fill="x", side="bottom", pady=(18, 14))

        tk.Frame(frame, bg=pal.BORDER, height=1).pack(fill="x", side="bottom")
        bottom = tk.Frame(frame, bg=pal.PANEL)
        bottom.pack(fill="x", side="bottom")
        bar = tk.Frame(bottom, bg=pal.PANEL)
        bar.pack(fill="x", padx=24, pady=14)
        back = "⟵  Retour aux étapes" if self.mode == TOUR else "⟵  Retour au parcours"
        ui.FlatButton(bar, back, self.hide_players, size=11, style="ghost").pack(side="left")
        label = "▶  Lancer le Tour" if self.mode == TOUR else "▶  C'est parti !"
        ui.FlatButton(bar, label, self.on_players_start, style="primary", size=14, padx=28, pady=12).pack(side="right")
        self._refresh_players()

    def _refresh_players(self) -> None:
        teams = int(self.teams_var.get())
        kinds = [self.player_vars[t].get() for t in range(teams)]
        humans, ai = kinds.count(HUMAN), kinds.count(AI)
        ghosts = teams - humans - ai
        problem = None
        if teams > 4 and PELOTON not in self.extensions():
            problem = "5 ou 6 équipes : il faut l'extension Peloton (coche-la ci-dessus)."
        elif kinds.count(PELOTON_TEAM) > 1:
            problem = "Il ne peut y avoir qu'une équipe Peloton."
        if problem:
            text = problem
        elif humans == 0:
            text = "Aucun joueur : tu regardes la course (avance avec le bouton d'action)."
        else:
            parts = [f"{humans} joueur(s)"] + ([f"{ai} IA"] if ai else []) + ([f"{ghosts} équipe(s) fantôme(s)"] if ghosts else [])
            text = " · ".join(parts) + "."
            if ai or ghosts:
                text += " L'IA et les équipes fantômes posent leurs cartes toutes seules."
        self.players_hint.config(text=text, fg=pal.ACCENT if problem else pal.MUTED)

    def hide_players(self) -> None:
        if self.players_frame is not None:
            self.players_frame.destroy()
            self.players_frame = None
        if self.frame is not None:
            self.frame.pack(fill="both", expand=True)

    def breakaway_available(self) -> bool:
        """La variante Échappée demande l'extension Peloton et une tuile Échappée sur le parcours (ou, pour un
        Tour, sur une de ses étapes)."""
        stages = self.tour_order if self.mode == TOUR else [self.current()]
        return PELOTON in self.extensions() and any(
            c.track is not None and any(c.track.surface(s) == BREAKAWAY for s in range(len(c.track))) for c in stages)

    def on_players_start(self) -> None:
        if self.needs_peloton() and PELOTON not in self.extensions():
            messagebox.showinfo("Extension Peloton", "Ce parcours se joue avec l'extension Peloton : coche-la.")
            return
        if int(self.teams_var.get()) > 4 and PELOTON not in self.extensions():
            messagebox.showinfo("5 ou 6 équipes", "On joue à 5 ou 6 équipes avec l'extension Peloton.")
            return
        if self.team_types().count(TEAM_PELOTON) > 1:
            messagebox.showinfo("Équipe Peloton", "Il ne peut y avoir qu'une équipe Peloton.")
            return
        breakaway = self.breakaway_available() and self.breakaway_var.get() is True
        teams, secret, animate = int(self.teams_var.get()), self.secret_var.get() is True, self.animate_var.get() is True
        if self.mode == TOUR:
            self.on_start_tour(list(self.tour_order), teams, secret, animate, self.extensions(), self.ai_teams(),
                               self.team_types(), breakaway, self.tour_rest_after())
            return
        self.on_start(self.current().track, teams, secret, animate, self.extensions(), self.ai_teams(),
                      self.team_types(), breakaway)

    def extensions(self) -> frozenset[str]:
        """Les extensions cochées."""
        return frozenset(name for name, var in self.extension_vars.items() if var.get() is True)

    def _extensions_changed_on_players(self) -> None:
        """Une extension cochée ou décochée : l'écran se reconstruit (équipes fantômes, 5–6 équipes, variante
        Échappée dépendent de Peloton)."""
        self.show_players()

    def on_open_file(self) -> None:
        path = filedialog.askopenfilename(
            initialdir=ensure_parcours_dir(), filetypes=[("Parcours Flamme Rouge", "*.json"), ("Tous les fichiers", "*.*")]
        )
        if not path:
            return
        if path not in self.extra_files:
            self.extra_files.append(path)
        self.choice_var.set(path)
        self.reload()
        if not self.current().playable:
            messagebox.showwarning("Parcours injouable", self.current().details)

    def on_create(self) -> None:
        """Ouvre l'éditeur dans une fenêtre à part, avec un départ et une arrivée prêts à recevoir des tuiles."""
        if self.editor_win is not None and self.editor_win.winfo_exists():
            self.editor_win.lift()
            return
        from editor import EditorApp  # importé ici : l'éditeur n'est utile qu'à la demande

        window = tk.Toplevel(self.root)
        self.editor_win = window
        EditorApp(window, [make_tile(KIND_START), make_tile(KIND_FINISH)], on_saved=self.reload, select_first=True)
