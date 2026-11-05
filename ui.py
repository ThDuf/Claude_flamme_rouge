"""Petits composants tkinter au look moderne (thème sombre) partagés par le menu, le jeu et l'éditeur.

Les boutons sont des Label stylés : ils prennent les couleurs demandées sur Windows, macOS et Linux
(les vrais boutons tk ignorent souvent les couleurs sous macOS).
"""
import tkinter as tk
import tkinter.font as tkfont

from flamme_rouge import palette as pal

FAMILY = "Helvetica"
_PREFERRED = ["Segoe UI", "SF Pro Text", "Helvetica Neue", "Inter", "Noto Sans", "Cantarell", "DejaVu Sans", "Arial"]


def init(root) -> None:
    """À appeler une fois par fenêtre : choisit la police, la couleur de fond et les réglages par défaut."""
    global FAMILY
    available = set(tkfont.families(root))
    FAMILY = next((name for name in _PREFERRED if name in available), FAMILY)
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont"):
        try:
            tkfont.nametofont(name).configure(family=FAMILY)
        except tk.TclError:
            pass
    root.configure(bg=pal.BG)


def place_window(root, width: int, height: int) -> None:
    """Fixe la taille de la fenêtre et la centre sur l'écran (sans dépasser l'écran)."""
    root.update_idletasks()
    width, height = min(width, root.winfo_screenwidth() - 40), min(height, root.winfo_screenheight() - 80)
    x, y = (root.winfo_screenwidth() - width) // 2, max(0, (root.winfo_screenheight() - height) // 3)
    root.geometry(f"{width}x{height}+{x}+{y}")


def auto_size(root) -> None:
    """Rend à la fenêtre la taille de son contenu (après un écran à taille fixe)."""
    root.geometry("")


def font(size: int = 11, bold: bool = False):
    return (FAMILY, size, "bold" if bold else "normal")


# ----------------------------------------------------------------------- boutons

STYLES = {
    # nom: (fond, fond survolé, texte)
    "primary": (pal.ACCENT, pal.ACCENT_HI, "#ffffff"),
    "secondary": (pal.CARD, pal.CARD_HI, pal.TEXT),
    "ghost": (pal.PANEL, pal.CARD, pal.MUTED),
    "warn": ("#4a2530", "#6a3140", "#ffc2c2"),  # carte fatigue
}


class FlatButton(tk.Label):
    """Bouton plat à coins carrés : survol, appui, état désactivé. `.config(state=, text=, command=)` marche comme un Button."""

    def __init__(self, parent, text="", command=None, style="secondary", size=11, bold=True, padx=16, pady=8, **kw):
        super().__init__(parent, text=text, font=font(size, bold), padx=padx, pady=pady, bd=0, **kw)
        self._command = command
        self._style = style
        self._state = "normal"
        self._hover = False
        self._down = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._paint()

    def configure(self, cnf=None, **kw):
        if cnf:
            kw = {**cnf, **kw}
        repaint = False
        if "state" in kw:
            self._state = kw.pop("state")
            repaint = True
        if "command" in kw:
            self._command = kw.pop("command")
        if "style" in kw:
            self._style = kw.pop("style")
            repaint = True
        if kw:
            super().configure(**kw)
        if repaint:
            self._paint()

    config = configure

    def cget(self, key):
        return self._state if key == "state" else super().cget(key)

    def _paint(self) -> None:
        bg, hi, fg = STYLES[self._style]
        if self._state == "disabled":
            tk.Label.configure(self, bg=pal.DISABLED, fg=pal.FAINT, cursor="arrow")
        else:
            tk.Label.configure(self, bg=hi if self._hover else bg, fg=fg, cursor="hand2")

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._paint()

    def _on_leave(self, _event) -> None:
        self._hover = False
        self._down = False
        self._paint()

    def _on_press(self, _event) -> None:
        self._down = self._state != "disabled"

    def _on_release(self, event) -> None:
        was_down, self._down = self._down, False
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if was_down and inside and self._command is not None:
            self._command()


class Toggle(tk.Label):
    """Interrupteur : une pastille qui s'allume (liée à une BooleanVar)."""

    def __init__(self, parent, text, variable, command=None, **kw):
        super().__init__(parent, font=font(10, True), padx=12, pady=6, bd=0, cursor="hand2",
                         highlightthickness=1, highlightbackground=pal.BORDER, **kw)
        self._text, self._var, self._command = text, variable, command
        self.bind("<ButtonRelease-1>", self._toggle)
        self.bind("<Enter>", lambda _e: self._paint(True))
        self.bind("<Leave>", lambda _e: self._paint(False))
        variable.trace_add("write", lambda *_: self._paint(False))
        self._paint(False)

    def _toggle(self, _event) -> None:
        self._var.set(not self._var.get())
        if self._command is not None:
            self._command()

    def _paint(self, hover: bool) -> None:
        on = bool(self._var.get())
        bg = pal.CARD_HI if hover else pal.CARD
        self.configure(text=("✓  " if on else "     ") + self._text, bg=bg, fg=pal.TEXT if on else pal.MUTED)


class Segmented(tk.Frame):
    """Choix unique présenté en pastilles côte à côte (liées à une IntVar ou StringVar)."""

    def __init__(self, parent, options, variable, command=None, **kw):
        super().__init__(parent, bg=pal.PANEL, **kw)
        self._var, self._command = variable, command
        self._labels = {}
        for value, text in options:
            label = tk.Label(self, text=text, font=font(10, True), padx=14, pady=7, bd=0, cursor="hand2")
            label.pack(side="left", padx=(0, 4))
            label.bind("<ButtonRelease-1>", lambda _e, v=value: self._choose(v))
            self._labels[value] = label
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _choose(self, value) -> None:
        self._var.set(value)
        if self._command is not None:
            self._command()

    def _paint(self) -> None:
        current = self._var.get()
        for value, label in self._labels.items():
            on = value == current
            label.configure(bg=pal.ACCENT if on else pal.CARD, fg="#ffffff" if on else pal.MUTED)


class RadioList(tk.Frame):
    """Liste verticale de choix uniques (liée à une StringVar) : la ligne choisie a un liseré rouge."""

    def __init__(self, parent, options, variable, command=None, bg=pal.CARD, **kw):
        super().__init__(parent, bg=bg, **kw)
        self._var, self._command, self._bg = variable, command, bg
        self._rows = {}
        for value, text in options:
            row = tk.Frame(self, bg=bg, cursor="hand2")
            row.pack(fill="x", pady=1)
            strip = tk.Frame(row, width=4, bg=bg)
            strip.pack(side="left", fill="y")
            label = tk.Label(row, text=text, font=font(10), bg=bg, fg=pal.MUTED, anchor="w", padx=10, pady=5)
            label.pack(side="left", fill="x", expand=True)
            for widget in (row, strip, label):
                widget.bind("<ButtonRelease-1>", lambda _e, v=value: self._choose(v))
            self._rows[value] = (row, strip, label)
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _choose(self, value) -> None:
        self._var.set(value)
        if self._command is not None:
            self._command()

    def _paint(self) -> None:
        current = self._var.get()
        for value, (row, strip, label) in self._rows.items():
            on = value == current
            bg = pal.CARD_HI if on else self._bg
            for widget in (row, label):
                widget.configure(bg=bg)
            strip.configure(bg=pal.ACCENT if on else self._bg)
            label.configure(fg=pal.TEXT if on else pal.MUTED, font=font(10, on))


def style_option_menu(menu: tk.OptionMenu) -> None:
    menu.configure(
        bg=pal.CARD_HI, fg=pal.TEXT, activebackground=pal.BORDER, activeforeground=pal.TEXT, bd=0, relief="flat",
        highlightthickness=0, font=font(10), anchor="w", padx=10, pady=6,
    )
    menu["menu"].configure(bg=pal.CARD, fg=pal.TEXT, activebackground=pal.ACCENT, activeforeground="#ffffff", bd=0, font=font(10))


# ------------------------------------------------------------------------ cartes

def card(parent, **kw) -> tk.Frame:
    """Un panneau à fond de carte avec un fin liseré."""
    return tk.Frame(parent, bg=pal.CARD, highlightbackground=pal.BORDER, highlightthickness=1, **kw)


def title_label(parent, text, size=13, bg=pal.BG, fg=pal.TEXT) -> tk.Label:
    return tk.Label(parent, text=text, font=font(size, True), bg=bg, fg=fg)


def style_text(widget, bg=pal.PANEL) -> None:
    """Applique le thème à un widget Text (journal, decks, messages)."""
    widget.configure(
        bg=bg, fg=pal.TEXT, relief="flat", bd=0, highlightthickness=1, highlightbackground=pal.BORDER,
        highlightcolor=pal.BORDER, insertbackground=pal.TEXT, selectbackground=pal.ACCENT_DK, padx=10, pady=8,
    )


def style_listbox(widget) -> None:
    widget.configure(
        bg=pal.CARD, fg=pal.TEXT, relief="flat", bd=0, highlightthickness=1, highlightbackground=pal.BORDER,
        highlightcolor=pal.ACCENT, selectbackground=pal.ACCENT, selectforeground="#ffffff", activestyle="none",
    )


class ScrollFrame(tk.Frame):
    """Zone qui défile à la molette, avec un fin indicateur de position. Mettre le contenu dans `.inner`."""

    def __init__(self, parent, bg=pal.CARD, width=330, height=400, **kw):
        super().__init__(parent, bg=bg, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, width=width, height=height)
        self.bar = tk.Canvas(self, bg=bg, highlightthickness=0, width=6)
        self.bar.pack(side="right", fill="y", padx=(0, 3))
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        for widget in (self, self.canvas, self.inner):
            widget.bind("<Enter>", self._bind_wheel)
            widget.bind("<Leave>", self._unbind_wheel)

    def _on_inner(self, _event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._on_scroll(*self.canvas.yview())

    def _on_scroll(self, first, last) -> None:
        self.bar.delete("all")
        first, last = float(first), float(last)
        if last - first < 0.999:
            height = self.bar.winfo_height() or 1
            self.bar.create_rectangle(0, first * height, 6, last * height, fill=pal.BORDER, outline="")

    def scroll_to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def _bind_wheel(self, _event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(2, "units"))

    def _unbind_wheel(self, _event) -> None:
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(sequence)

    def _wheel(self, event) -> None:
        step = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(step * 2, "units")


def paint(canvas, shapes) -> None:
    """Dessine des formes du plateau (voir boardview) sur un Canvas."""
    for shape in shapes:
        kind = shape[0]
        if kind == "rect":
            _, x0, y0, x1, y1, fill, outline, width = shape
            canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline=outline, width=width)
        elif kind == "oval":
            _, x0, y0, x1, y1, fill, outline, width = shape
            canvas.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=width)
        elif kind == "poly":
            _, points, fill, outline, width = shape
            canvas.create_polygon(points, fill=fill, outline=outline, width=width)
        elif kind == "line":
            _, x0, y0, x1, y1, color, width = shape
            canvas.create_line(x0, y0, x1, y1, fill=color, width=width, capstyle="round")
        elif kind == "text":
            _, x, y, text, color, size, bold, anchor = shape
            canvas.create_text(x, y, text=text, fill=color, anchor=anchor, font=font(int(size), bool(bold)))
