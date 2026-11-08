"""Écran de démarrage : choix du parcours, du nombre de coureurs, puis lancement de la course."""
import tkinter as tk
from tkinter import filedialog, messagebox

import ui
from flamme_rouge import palette as pal
from flamme_rouge.boardview import profile_primitives, track_preview_primitives
from flamme_rouge.extensions import EXTENSIONS, PELOTON, READY
from flamme_rouge.game import TEAM_MUSCLE, TEAM_PELOTON, TEAM_PLAYER
from flamme_rouge.catalog import GROUP_BASE, GROUP_MINE, GROUP_OFFICIAL, Choice, build_choices
from flamme_rouge.paths import PARCOURS_DIR, ensure_parcours_dir
from flamme_rouge.tiles import KIND_FINISH, KIND_START, make_tile

PREVIEW_W, PREVIEW_H = 700, 340
PROFILE_H = 130
LIST_W = 360
WINDOW_W, WINDOW_H = 1180, 820
HUMAN, AI, PELOTON_TEAM, MUSCLE_TEAM = "joueur", "ia", "peloton", "muscle"  # PELOTON_TEAM, MUSCLE_TEAM : Peloton
TEAM_COLORS = ["rouge", "bleue", "verte", "jaune", "rose", "blanche"]  # dans l'ordre de palette.TEAM_FILL
PLAYER_LABELS = {HUMAN: "Joueur", AI: "IA", PELOTON_TEAM: "Équipe Peloton", MUSCLE_TEAM: "Équipe Muscle"}
DEFAULT_CHOICE = "officiel:Avenue Corso Paseo"  # l'étape conseillée pour une première partie
TEAM_CHOICES = [(n, str(n)) for n in range(2, 7)]  # 5 et 6 : extension Peloton
GROUP_HINTS = {
    GROUP_BASE: "21 tuiles comme dans la boîte (même composition que les cartes étape, sans en être la copie).",
    GROUP_OFFICIAL: "Les cartes étape du jeu, avec les tuiles de la boîte.",
    GROUP_MINE: "Parcours créés avec l'éditeur (dossier « parcours »).",
}


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
    def __init__(self, parent, on_start):
        """`on_start(track, teams, secret, animate, extensions, ai_teams, team_types)` est appelé quand on lance la course."""
        self.parent = parent
        self.root = parent.winfo_toplevel()
        ui.init(self.root)
        self.root.title("Flamme Rouge")
        ui.place_window(self.root, WINDOW_W, WINDOW_H)
        parent.configure(bg=pal.BG)
        self.on_start = on_start
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
        self.players_frame = None
        self.editor_win = None
        self.frame = tk.Frame(parent, bg=pal.BG)
        self.frame.pack(fill="both", expand=True)
        self._build()
        self.reload()

    # --------------------------------------------------------------- construction

    def _build(self) -> None:
        # ----- bandeau du haut
        header = tk.Frame(self.frame, bg=pal.PANEL)
        header.pack(fill="x")
        logo = tk.Frame(header, bg=pal.PANEL)
        logo.pack(side="left", padx=24, pady=(14, 12))
        tk.Label(logo, text="FLAMME ", font=ui.font(26, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left")
        tk.Label(logo, text="ROUGE", font=ui.font(26, True), bg=pal.PANEL, fg=pal.ACCENT).pack(side="left")
        tk.Label(header, text="Course cycliste à cartes", font=ui.font(11), bg=pal.PANEL, fg=pal.MUTED).pack(
            side="left", padx=4, pady=(14, 0)
        )
        tk.Frame(self.frame, bg=pal.ACCENT, height=3).pack(fill="x")

        # ----- corps : liste à gauche, aperçu à droite
        body = tk.Frame(self.frame, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=24, pady=(18, 0))

        left = tk.Frame(body, bg=pal.BG)
        left.pack(side="left", fill="y")
        ui.title_label(left, "1 · Choisis le parcours").pack(anchor="w", pady=(0, 8))
        listing = ui.card(left)
        listing.pack(fill="both", expand=True)
        self.scroll = ui.ScrollFrame(listing, width=LIST_W, height=PREVIEW_H + PROFILE_H - 4)
        self.scroll.pack(fill="both", expand=True, padx=1, pady=1)
        actions = tk.Frame(left, bg=pal.BG)
        actions.pack(fill="x", pady=(10, 0))
        ui.FlatButton(actions, "＋  Créer un parcours", self.on_create, size=10).pack(side="left")
        ui.FlatButton(actions, "Ouvrir un fichier", self.on_open_file, size=10, style="ghost").pack(side="left", padx=8)

        right = tk.Frame(body, bg=pal.BG)
        right.pack(side="left", fill="both", expand=True, padx=(24, 0))
        ui.title_label(right, "Aperçu").pack(anchor="w", pady=(0, 8))
        view = ui.card(right)
        view.pack(anchor="w")
        self.preview = tk.Canvas(view, width=PREVIEW_W, height=PREVIEW_H, bg=pal.GRASS, highlightthickness=0)
        self.preview.pack(padx=1, pady=(1, 0))
        self.profile = tk.Canvas(view, width=PREVIEW_W, height=PROFILE_H, bg=pal.CARD, highlightthickness=0)
        self.profile.pack(padx=1, pady=(0, 1))
        self.details_title = tk.Label(right, text="", font=ui.font(15, True), bg=pal.BG, fg=pal.TEXT, anchor="w")
        self.details_title.pack(fill="x", pady=(12, 0))
        self.details_label = tk.Label(
            right, text="", font=ui.font(11), bg=pal.BG, fg=pal.MUTED, wraplength=PREVIEW_W, justify="left", anchor="w"
        )
        self.details_label.pack(fill="x")

        # ----- barre du bas : équipes, options, lancement
        tk.Frame(self.frame, bg=pal.BORDER, height=1).pack(fill="x", pady=(18, 0))
        bottom = tk.Frame(self.frame, bg=pal.PANEL)
        bottom.pack(fill="x")
        inner = tk.Frame(bottom, bg=pal.PANEL)
        inner.pack(fill="x", padx=24, pady=14)
        step = tk.Frame(inner, bg=pal.PANEL)
        step.pack(side="left")
        tk.Label(step, text="2 · Nombre d'équipes", font=ui.font(11, True), bg=pal.PANEL, fg=pal.TEXT).pack(anchor="w")
        ui.Segmented(step, TEAM_CHOICES, self.teams_var).pack(anchor="w", pady=(6, 0))
        opts = tk.Frame(inner, bg=pal.PANEL)
        opts.pack(side="left", padx=(28, 0))
        tk.Label(opts, text="Options", font=ui.font(11, True), bg=pal.PANEL, fg=pal.TEXT).pack(anchor="w")
        row = tk.Frame(opts, bg=pal.PANEL)
        row.pack(anchor="w", pady=(6, 0))
        ui.Toggle(row, "Animations", self.animate_var).pack(side="left", padx=(0, 4))
        ui.Toggle(row, "Mode secret", self.secret_var).pack(side="left")
        exts = tk.Frame(inner, bg=pal.PANEL)
        exts.pack(side="left", padx=(28, 0))
        tk.Label(exts, text="Extensions", font=ui.font(11, True), bg=pal.PANEL, fg=pal.TEXT).pack(anchor="w")
        row = tk.Frame(exts, bg=pal.PANEL)
        row.pack(anchor="w", pady=(6, 0))
        for name, (label, _description) in EXTENSIONS.items():
            ui.Toggle(row, label, self.extension_vars[name], command=self._refresh_extensions).pack(side="left", padx=(0, 4))
        self.extensions_hint = tk.Label(exts, text="", font=ui.font(8), bg=pal.PANEL, fg=pal.FAINT, anchor="w",
                                        justify="left", wraplength=260)
        self.extensions_hint.pack(anchor="w", pady=(2, 0))
        self._refresh_extensions()
        self.start_btn = ui.FlatButton(inner, "▶  Lancer la course", self.on_launch, style="primary", size=14, padx=28, pady=12)
        self.start_btn.pack(side="right")

    # ------------------------------------------------------------------- contenu

    def reload(self) -> None:
        """Relit la liste des parcours (après un enregistrement dans l'éditeur, par exemple)."""
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

    def on_select(self) -> None:
        choice = self.current()
        for key, row in self.rows.items():
            row.set_selected(key == choice.key)
        self.preview.delete("all")
        self.profile.delete("all")
        if choice.track is None:
            self.preview.create_text(
                PREVIEW_W / 2, PREVIEW_H / 2, text=choice.details, width=PREVIEW_W - 80, fill=pal.MUTED, font=ui.font(12)
            )
        else:
            ui.paint(self.preview, track_preview_primitives(choice.track, PREVIEW_W, PREVIEW_H))
            ui.paint(self.profile, profile_primitives(choice.track, PREVIEW_W, PROFILE_H))
        self.details_title.config(text=choice.label)
        self.details_label.config(text=choice.details)
        self.start_btn.config(state="normal" if choice.playable else "disabled")

    # ------------------------------------------------------------------- actions

    def on_launch(self) -> None:
        choice = self.current()
        if not choice.playable:
            messagebox.showinfo("Parcours indisponible", choice.details)
            return
        if int(self.teams_var.get()) > 4 and PELOTON not in self.extensions():
            messagebox.showinfo("5 ou 6 équipes", "On joue à 5 ou 6 équipes avec l'extension Peloton : coche-la dans « Extensions ».")
            return
        self.show_players()

    # ------------------------------------------------------------ écran « Qui joue ? »

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
        """Remplace le menu par l'écran qui dit, pour chaque équipe, si elle est jouée par un joueur ou par l'IA."""
        self.frame.pack_forget()
        frame = self.players_frame = tk.Frame(self.parent, bg=pal.BG)
        frame.pack(fill="both", expand=True)
        header = tk.Frame(frame, bg=pal.PANEL)
        header.pack(fill="x")
        tk.Label(header, text="QUI JOUE ?", font=ui.font(22, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left", padx=24, pady=14)
        choice = self.current()
        tk.Label(header, text=f"{choice.label} · {int(self.teams_var.get())} équipes", font=ui.font(11), bg=pal.PANEL,
                 fg=pal.MUTED).pack(side="left", pady=(10, 0))
        tk.Frame(frame, bg=pal.ACCENT, height=3).pack(fill="x")

        body = tk.Frame(frame, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=60, pady=20)
        options = self.player_options()
        title = "Pour chaque équipe : un joueur, l'IA, ou une équipe fantôme de l'extension Peloton" if len(options) > 2 \
            else "Pour chaque équipe, choisis un joueur ou l'IA"
        ui.title_label(body, title).pack(anchor="w", pady=(0, 14))
        for team in range(int(self.teams_var.get())):
            if self.player_vars[team].get() not in options:
                self.player_vars[team].set(AI)
            row = ui.card(body)
            row.pack(fill="x", pady=5)
            inner = tk.Frame(row, bg=pal.CARD)
            inner.pack(fill="x", padx=16, pady=8)
            dot = tk.Canvas(inner, width=30, height=30, bg=pal.CARD, highlightthickness=0)
            dot.create_oval(3, 3, 27, 27, fill=pal.TEAM_FILL[team], outline="#ffffff", width=2)
            dot.pack(side="left")
            tk.Label(inner, text=f"Équipe {team + 1}", font=ui.font(14, True), bg=pal.CARD, fg=pal.TEXT).pack(side="left", padx=(12, 6))
            tk.Label(inner, text=TEAM_COLORS[team], font=ui.font(11), bg=pal.CARD, fg=pal.TEAM_TEXT[team]).pack(side="left")
            ui.Segmented(inner, [(o, PLAYER_LABELS[o]) for o in options], self.player_vars[team],
                         command=self._refresh_players).pack(side="right")
        self.players_hint = tk.Label(body, text="", font=ui.font(10), bg=pal.BG, fg=pal.MUTED, anchor="w", justify="left")
        self.players_hint.pack(fill="x", pady=(12, 0))

        tk.Frame(frame, bg=pal.BORDER, height=1).pack(fill="x", side="bottom")
        bottom = tk.Frame(frame, bg=pal.PANEL)
        bottom.pack(fill="x", side="bottom")
        bar = tk.Frame(bottom, bg=pal.PANEL)
        bar.pack(fill="x", padx=24, pady=14)
        ui.FlatButton(bar, "⟵  Retour au menu", self.hide_players, size=11, style="ghost").pack(side="left")
        ui.FlatButton(bar, "▶  C'est parti !", self.on_players_start, style="primary", size=14, padx=28, pady=12).pack(side="right")
        self._refresh_players()

    def _refresh_players(self) -> None:
        teams = int(self.teams_var.get())
        kinds = [self.player_vars[t].get() for t in range(teams)]
        humans, ai = kinds.count(HUMAN), kinds.count(AI)
        ghosts = teams - humans - ai
        if kinds.count(PELOTON_TEAM) > 1:
            text = "Il ne peut y avoir qu'une équipe Peloton."
        elif humans == 0:
            text = "Aucun joueur : tu regardes la course (avance avec le bouton d'action)."
        else:
            parts = [f"{humans} joueur(s)"] + ([f"{ai} IA"] if ai else []) + ([f"{ghosts} équipe(s) fantôme(s)"] if ghosts else [])
            text = " · ".join(parts) + "."
            if ai or ghosts:
                text += " L'IA et les équipes fantômes posent leurs cartes toutes seules."
        self.players_hint.config(text=text, fg=pal.ACCENT if kinds.count(PELOTON_TEAM) > 1 else pal.MUTED)

    def hide_players(self) -> None:
        if self.players_frame is not None:
            self.players_frame.destroy()
            self.players_frame = None
        self.frame.pack(fill="both", expand=True)

    def on_players_start(self) -> None:
        if self.team_types().count(TEAM_PELOTON) > 1:
            messagebox.showinfo("Équipe Peloton", "Il ne peut y avoir qu'une équipe Peloton.")
            return
        choice = self.current()
        self.on_start(choice.track, int(self.teams_var.get()), self.secret_var.get() is True, self.animate_var.get() is True,
                      self.extensions(), self.ai_teams(), self.team_types())

    def extensions(self) -> frozenset[str]:
        """Les extensions cochées."""
        return frozenset(name for name, var in self.extension_vars.items() if var.get() is True)

    def _refresh_extensions(self) -> None:
        chosen = self.extensions()
        waiting = [EXTENSIONS[name][0] for name in EXTENSIONS if name in chosen and name not in READY]
        if not chosen:
            text = "aucune : jeu de base"
        elif waiting:
            text = f"{', '.join(waiting)} : règles à venir"
        else:
            text = " · ".join(EXTENSIONS[name][1] for name in EXTENSIONS if name in chosen)
        self.extensions_hint.config(text=text)

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
