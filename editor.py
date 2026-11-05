"""Éditeur de parcours : assemble des tuiles comme dans la boîte du jeu.

    python editor.py                     # démarre avec un parcours d'exemple
    python editor.py mon_parcours.json   # ouvre un parcours enregistré

Les parcours enregistrés (dossier « parcours ») apparaissent dans le menu : python main.py
Pour jouer un fichier directement :  python gui.py --track mon_parcours.json
"""
import argparse
import tkinter as tk
from tkinter import filedialog, messagebox

import ui
from flamme_rouge import palette as pal
from flamme_rouge.boardview import plan_preview_primitives, tile_card_primitives
from flamme_rouge.paths import ensure_parcours_dir
from flamme_rouge.plan import PlanEditor
from flamme_rouge.tiles import (
    ERROR,
    KIND_FINISH,
    KIND_SHARP,
    KIND_SOFT,
    KIND_START,
    KIND_STRAIGHT,
    example_plan,
    has_errors,
    plan_from_json,
    plan_to_json,
    plan_to_track,
    summary,
    validate,
)
from flamme_rouge.official import OFFICIAL_TILES, official_tile

PREVIEW_W, PREVIEW_H = 600, 470
WINDOW_W, WINDOW_H = 1280, 800

CARD_W, CARD_H = 96, 50
CARD_COLUMNS = 3
FLAT_SIDE, MOUNTAIN_SIDE = "plat", "montagne"
_KIND_ORDER = {KIND_START: 0, KIND_FINISH: 1, KIND_STRAIGHT: 2, KIND_SOFT: 3, KIND_SHARP: 4}


def side_letters(side: str) -> list[str]:
    """Les 21 lettres d'une face de la boîte, rangées par type : départ, arrivée, droites, virages doux, serrés."""
    letters = "abcdefghijklmnopqrstu" if side == FLAT_SIDE else "ABCDEFGHIJKLMNOPQRSTU"
    return sorted(letters, key=lambda c: (_KIND_ORDER[OFFICIAL_TILES[c].kind], OFFICIAL_TILES[c].direction or "", c))


def letter_for_tile(tile) -> str | None:
    """Lettre officielle d'une tuile du parcours (une tuile « libre » identique à une face officielle compte)."""
    if tile.letter in OFFICIAL_TILES:
        return tile.letter
    return next((letter for letter, official in OFFICIAL_TILES.items() if official == tile), None)


class TilePalette(tk.Frame):
    """Les tuiles de la boîte en petites cartes : un clic choisit, un double-clic pose la tuile."""

    def __init__(self, parent, on_pick=None, on_place=None):
        super().__init__(parent, bg=pal.BG)
        self.on_pick, self.on_place = on_pick, on_place
        self.side_var = tk.StringVar(value=FLAT_SIDE)
        self.selected = "b"
        self.used: set[str] = set()
        ui.Segmented(self, [(FLAT_SIDE, "Faces plates a–u"), (MOUNTAIN_SIDE, "Faces montagne A–U")], self.side_var,
                     command=self.redraw).pack(anchor="w", pady=(0, 6))
        grid = tk.Frame(self, bg=pal.BG)
        grid.pack(anchor="w")
        self.cards: list[tk.Canvas] = []
        for i in range(21):
            canvas = tk.Canvas(grid, width=CARD_W, height=CARD_H, bg=pal.BG, highlightthickness=0, cursor="hand2")
            canvas.grid(row=i // CARD_COLUMNS, column=i % CARD_COLUMNS, padx=2, pady=2)
            canvas.bind("<ButtonRelease-1>", lambda _e, i=i: self._click(i))
            canvas.bind("<Double-Button-1>", lambda _e, i=i: self._double(i))
            self.cards.append(canvas)
        self.redraw()

    @property
    def letters(self) -> list[str]:
        return side_letters(self.side_var.get())

    @property
    def tile(self):
        return official_tile(self.selected)

    def _click(self, index: int) -> None:
        self.select(self.letters[index])
        if self.on_pick is not None:
            self.on_pick()

    def _double(self, index: int) -> None:
        self.select(self.letters[index])
        if self.on_place is not None:
            self.on_place()

    def select(self, letter: str) -> None:
        """Choisit une tuile (et affiche la face où elle se trouve)."""
        self.selected = letter
        self.side_var.set(FLAT_SIDE if letter.islower() else MOUNTAIN_SIDE)
        self.redraw()

    def set_used(self, letters) -> None:
        self.used = {c.lower() for c in letters}
        self.redraw()

    def redraw(self) -> None:
        for canvas, letter in zip(self.cards, self.letters):
            canvas.delete("all")
            prims = tile_card_primitives(official_tile(letter), CARD_W, CARD_H,
                                         selected=letter == self.selected, used=letter.lower() in self.used)
            ui.paint(canvas, prims)


class EditorApp:
    def __init__(self, root, tiles=None, on_saved=None, select_first=False):
        """`on_saved()` est appelé après chaque enregistrement ; `select_first` sélectionne la 1re tuile
        (utile pour un parcours neuf : on peut tout de suite insérer des tuiles après le départ)."""
        self.root = root
        self.on_saved = on_saved
        root.title("Flamme Rouge — éditeur de parcours")
        self.plan = PlanEditor(tiles if tiles is not None else example_plan())
        if select_first and self.plan.tiles:
            self.plan.select(0)
        self.teams_var = tk.StringVar(value="2")
        self._build()
        self.refresh()

    # --------------------------------------------------------------- construction

    def _build(self) -> None:
        root = self.root
        ui.init(root)
        ui.place_window(root, WINDOW_W, WINDOW_H)

        header = tk.Frame(root, bg=pal.PANEL)
        header.pack(fill="x")
        tk.Label(header, text="ÉDITEUR DE PARCOURS", font=ui.font(15, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left", padx=20, pady=12)
        tk.Label(header, text="assemble les tuiles comme dans la boîte", font=ui.font(10), bg=pal.PANEL, fg=pal.MUTED).pack(side="left")
        tk.Frame(root, bg=pal.ACCENT, height=2).pack(fill="x")

        main = tk.Frame(root, bg=pal.BG)
        main.pack(fill="both", expand=True, padx=16, pady=14)

        # ----- colonne de gauche : la palette de tuiles
        left = tk.Frame(main, bg=pal.BG)
        left.pack(side="left", fill="y", anchor="n")
        ui.title_label(left, "1 · Choisis une tuile de la boîte", 11).pack(anchor="w", pady=(0, 4))
        self.palette = TilePalette(left, on_place=self.on_place)
        self.palette.pack(anchor="w")
        tk.Label(left, text="double-clic : pose la tuile après la sélection", font=ui.font(9), bg=pal.BG,
                 fg=pal.MUTED).pack(anchor="w")
        ui.title_label(left, "2 · Place-la", 11).pack(anchor="w", pady=(8, 4))
        places = tk.Frame(left, bg=pal.BG)
        places.pack(fill="x")
        ui.FlatButton(places, "À la fin", self.on_append, style="primary", size=9, padx=6, pady=6).pack(
            side="left", fill="x", expand=True, padx=(0, 2))
        self.insert_btn = ui.FlatButton(places, "Après la sélection", self.on_insert, size=9, padx=6, pady=6)
        self.insert_btn.pack(side="left", fill="x", expand=True, padx=2)
        self.replace_btn = ui.FlatButton(places, "Remplacer", self.on_replace, size=9, padx=6, pady=6)
        self.replace_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))

        # ----- au milieu : la liste des tuiles
        middle = tk.Frame(main, bg=pal.BG)
        middle.pack(side="left", fill="y", padx=16)
        ui.title_label(middle, "Parcours (départ → arrivée)", 11).pack(anchor="w", pady=(0, 4))
        list_frame = tk.Frame(middle, bg=pal.BG)
        list_frame.pack(fill="y", expand=True)
        self.listbox = tk.Listbox(list_frame, width=34, height=16, exportselection=False, font=ui.font(10))
        ui.style_listbox(self.listbox)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)
        tk.Label(middle, text="Tuile sélectionnée", font=ui.font(10, True), bg=pal.BG, fg=pal.MUTED).pack(anchor="w", pady=(8, 2))
        moves = tk.Frame(middle, bg=pal.BG)
        moves.pack(fill="x")
        self.up_btn = ui.FlatButton(moves, "◀ Vers le départ", lambda: self.on_move(-1), size=9, pady=5)
        self.up_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.down_btn = ui.FlatButton(moves, "Vers l'arrivée ▶", lambda: self.on_move(1), size=9, pady=5)
        self.down_btn.pack(side="left", fill="x", expand=True, padx=(2, 0))
        more = tk.Frame(middle, bg=pal.BG)
        more.pack(fill="x", pady=(3, 0))
        self.remove_btn = ui.FlatButton(more, "Supprimer", self.on_remove, size=9, pady=5)
        self.remove_btn.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.undo_btn = ui.FlatButton(more, "↶ Annuler", self.on_undo, size=9, pady=5)
        self.undo_btn.pack(side="left", fill="x", expand=True, padx=2)
        ui.FlatButton(more, "Tout effacer", self.on_clear, size=9, pady=5, style="ghost").pack(side="left", fill="x", expand=True, padx=(2, 0))

        # ----- à droite : l'aperçu
        right = tk.Frame(main, bg=pal.BG)
        right.pack(side="left", fill="both", expand=True)
        ui.title_label(right, "Aperçu", 11).pack(anchor="w", pady=(0, 4))
        view = ui.card(right)
        view.pack(anchor="w")
        self.preview = tk.Canvas(view, width=PREVIEW_W, height=PREVIEW_H, bg=pal.GRASS, highlightthickness=0)
        self.preview.pack(padx=1, pady=1)

        # ----- en bas : comptage, messages, fichiers, jeu
        tk.Frame(root, bg=pal.BORDER, height=1).pack(fill="x")
        bottom = tk.Frame(root, bg=pal.PANEL)
        bottom.pack(fill="x")
        inner = tk.Frame(bottom, bg=pal.PANEL)
        inner.pack(fill="x", padx=16, pady=10)
        self.summary_label = tk.Label(inner, text="", font=ui.font(10, True), bg=pal.PANEL, fg=pal.TEXT, anchor="w")
        self.summary_label.pack(fill="x")
        self.messages = tk.Text(inner, height=3, state="disabled", font=ui.font(10))
        ui.style_text(self.messages, bg=pal.BG)
        self.messages.pack(fill="x", pady=6)
        self.messages.tag_configure("error", foreground="#ff7b7d")
        self.messages.tag_configure("warning", foreground="#fbbf24")
        self.messages.tag_configure("ok", foreground=pal.GOOD)

        buttons = tk.Frame(inner, bg=pal.PANEL)
        buttons.pack(fill="x")
        ui.FlatButton(buttons, "Parcours d'exemple", self.on_example, size=10, pady=6).pack(side="left")
        ui.FlatButton(buttons, "Ouvrir…", self.on_open, size=10, pady=6).pack(side="left", padx=6)
        ui.FlatButton(buttons, "Enregistrer…", self.on_save, size=10, pady=6).pack(side="left")
        self.play_btn = ui.FlatButton(buttons, "▶  Jouer ce parcours", self.on_play, style="primary", size=12, padx=22, pady=8)
        self.play_btn.pack(side="right")
        ui.Segmented(buttons, [("2", "2 équipes"), ("3", "3 équipes"), ("4", "4 équipes")], self.teams_var).pack(side="right", padx=(0, 14))

    # ------------------------------------------------------------------- helpers

    def _tile_from_palette(self):
        return self.palette.tile

    def _guard(self, action) -> None:
        """Exécute une action de l'éditeur et affiche proprement les erreurs de saisie."""
        try:
            action()
        except (ValueError, IndexError) as exc:
            messagebox.showinfo("Éditeur", str(exc))
        self.refresh()

    # ------------------------------------------------------------------- actions

    def on_append(self) -> None:
        self._guard(lambda: self.plan.append(self._tile_from_palette()))

    def on_place(self) -> None:
        """Double-clic sur une carte : après la tuile sélectionnée, ou à la fin s'il n'y en a pas."""
        if self.plan.selected is None:
            self.on_append()
        else:
            self.on_insert()

    def on_insert(self) -> None:
        self._guard(lambda: self.plan.insert_after(self._tile_from_palette()))

    def on_replace(self) -> None:
        self._guard(lambda: self.plan.replace(self._tile_from_palette()))

    def on_remove(self) -> None:
        self._guard(self.plan.remove)

    def on_move(self, delta: int) -> None:
        self._guard(lambda: self.plan.move(delta))

    def on_undo(self) -> None:
        self._guard(self.plan.undo)

    def on_clear(self) -> None:
        if self.plan.tiles and not messagebox.askyesno("Tout effacer", "Effacer tout le parcours ? (tu pourras annuler)"):
            return
        self._guard(self.plan.clear)

    def on_example(self) -> None:
        self._guard(lambda: self.plan.load(example_plan()))

    def on_select(self, _event=None) -> None:
        picked = self.listbox.curselection()
        if not picked:
            return
        self.plan.select(picked[0])
        tile = self.plan.tiles[picked[0]]
        # la palette reprend la tuile choisie : pratique pour la remplacer par une variante
        letter = letter_for_tile(tile)
        if letter:
            self.palette.select(letter)
        self._refresh_preview()
        self._refresh_buttons()

    def on_open(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("Parcours Flamme Rouge", "*.json"), ("Tous les fichiers", "*.*")],
            initialdir=ensure_parcours_dir(),  # le même dossier que pour enregistrer
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as handle:
                tiles = plan_from_json(handle.read())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Ouvrir", f"Impossible d'ouvrir ce parcours :\n{exc}")
            return
        self._guard(lambda: self.plan.load(tiles))

    def on_save(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Parcours Flamme Rouge", "*.json")],
            initialdir=ensure_parcours_dir(),
            initialfile="mon_parcours.json",
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(plan_to_json(self.plan.tiles))
        except OSError as exc:
            messagebox.showerror("Enregistrer", f"Impossible d'enregistrer :\n{exc}")
            return
        messagebox.showinfo("Enregistrer", "Parcours enregistré : tu le retrouveras dans le menu, rubrique « Mes parcours ».")
        if self.on_saved is not None:
            self.on_saved()

    def on_play(self) -> None:
        issues = validate(self.plan.tiles)
        if has_errors(issues):
            messagebox.showerror("Parcours injouable", "\n".join(i.text for i in issues if i.level == ERROR))
            return
        from gui import App  # importé ici : gui.py n'est nécessaire que pour jouer

        try:
            teams = max(2, min(4, int(self.teams_var.get())))
        except ValueError:
            teams = 2
        window = tk.Toplevel(self.root)
        App(window, teams=teams, track=plan_to_track(self.plan.tiles))

    # ------------------------------------------------------------------ affichage

    def refresh(self) -> None:
        tiles = self.plan.tiles
        self.listbox.delete(0, "end")
        for i, tile in enumerate(tiles, 1):
            self.listbox.insert("end", f"{i:>2}. {tile.label}")
        if self.plan.selected is not None:
            self.listbox.selection_set(self.plan.selected)
            self.listbox.see(self.plan.selected)
        self._refresh_preview()
        self._refresh_buttons()
        self.palette.set_used(filter(None, (letter_for_tile(t) for t in tiles)))

        self.summary_label.config(text=summary(tiles))
        issues = validate(tiles)
        self.messages.configure(state="normal")
        self.messages.delete("1.0", "end")
        for issue in issues:
            tag = "error" if issue.level == ERROR else "warning"
            sign = "✖" if issue.level == ERROR else "⚠"
            self.messages.insert("end", f"{sign} {issue.text}\n", tag)
        if not issues:
            self.messages.insert("end", "✔ Parcours valide, conforme au contenu de la boîte.\n", "ok")
        self.messages.configure(state="disabled")
        self.play_btn.config(state="disabled" if has_errors(issues) else "normal")

    def _refresh_buttons(self) -> None:
        has_selection = self.plan.selected is not None
        for button in (self.insert_btn, self.replace_btn, self.up_btn, self.down_btn, self.remove_btn):
            button.config(state="normal" if has_selection else "disabled")
        self.undo_btn.config(state="normal" if self.plan.can_undo else "disabled")

    def _refresh_preview(self) -> None:
        self.preview.delete("all")
        ui.paint(self.preview, plan_preview_primitives(self.plan.tiles, PREVIEW_W, PREVIEW_H, self.plan.selected))


def main() -> None:
    parser = argparse.ArgumentParser(description="Flamme Rouge — éditeur de parcours")
    parser.add_argument("file", nargs="?", help="parcours .json à ouvrir")
    args = parser.parse_args()

    tiles = None
    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            tiles = plan_from_json(handle.read())
    root = tk.Tk()
    EditorApp(root, tiles)
    root.mainloop()


if __name__ == "__main__":
    main()
