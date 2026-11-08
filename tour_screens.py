"""Écrans du Grand Tour : résultats entre deux étapes, classement final (le choix des étapes est dans menu.py)."""
import tkinter as tk
from tkinter import messagebox

import ui
from flamme_rouge import palette as pal
from flamme_rouge.stage import format_time
from flamme_rouge.tour import GREEN, JERSEY_NAMES, POLKA, YELLOW, StageResult, Tour

JERSEY_COLORS = {YELLOW: "#facc15", GREEN: "#22c55e", POLKA: "#f87171"}
TEAM_COLOR_NAMES = ["rouge", "bleue", "verte", "jaune", "rose", "blanche"]


def _header(parent, title: str, subtitle: str = "") -> None:
    header = tk.Frame(parent, bg=pal.PANEL)
    header.pack(fill="x")
    tk.Label(header, text=title, font=ui.font(22, True), bg=pal.PANEL, fg=pal.TEXT).pack(side="left", padx=24, pady=14)
    if subtitle:
        tk.Label(header, text=subtitle, font=ui.font(11), bg=pal.PANEL, fg=pal.MUTED).pack(side="left", pady=(10, 0))
    tk.Frame(parent, bg=pal.ACCENT, height=3).pack(fill="x")


def _bottom_bar(parent):
    tk.Frame(parent, bg=pal.BORDER, height=1).pack(fill="x", side="bottom")
    bottom = tk.Frame(parent, bg=pal.PANEL)
    bottom.pack(fill="x", side="bottom")
    bar = tk.Frame(bottom, bg=pal.PANEL)
    bar.pack(fill="x", padx=24, pady=14)
    return bar


def _rider_chip(parent, name: str, team: int, bg=pal.CARD) -> tk.Label:
    return tk.Label(parent, text=name, font=ui.font(10, True), bg=pal.TEAM_FILL[team], fg=pal.LABEL_ON_FILL[team],
                    padx=5, width=4)


# ---------------------------------------------------------------------- résultats


def _table(parent, title: str, rows: list[tuple], columns: int = 3) -> None:
    """Petit tableau : un titre puis des lignes (texte ou (nom, équipe) pour une pastille de coureur)."""
    box = ui.card(parent)
    box.pack(fill="x", pady=(0, 10))
    inner = tk.Frame(box, bg=pal.CARD)
    inner.pack(fill="x", padx=12, pady=8)
    tk.Label(inner, text=title, font=ui.font(11, True), bg=pal.CARD, fg=pal.TEXT, anchor="w").grid(
        row=0, column=0, columnspan=columns + 1, sticky="w", pady=(0, 4))
    if not rows:
        tk.Label(inner, text="—", font=ui.font(10), bg=pal.CARD, fg=pal.FAINT).grid(row=1, column=0, sticky="w")
    for r, row in enumerate(rows, 1):
        for c, cell in enumerate(row):
            if isinstance(cell, tuple):
                _rider_chip(inner, *cell).grid(row=r, column=c, sticky="w", padx=(0, 6), pady=1)
            else:
                color = pal.TEXT if c else pal.FAINT
                if isinstance(cell, str) and cell.startswith("●"):
                    color = JERSEY_COLORS.get(cell[1:], pal.TEXT)
                    cell = "●"
                tk.Label(inner, text=str(cell), font=ui.font(10, c == 0), bg=pal.CARD, fg=color, anchor="w").grid(
                    row=r, column=c, sticky="w", padx=(0, 10))


class StageResultsScreen(tk.Frame):
    """Entre deux étapes : arrivée, classements, maillots, Points de Tour."""

    def __init__(self, parent, tour: Tour, result: StageResult, team_names, on_next, on_menu):
        super().__init__(parent, bg=pal.BG)
        number = len(tour.results)
        _header(self, f"ÉTAPE {number} / {len(tour.stages)}", result.name)
        body = tk.Frame(self, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=24, pady=14)
        names = tour.names

        def chip(k):
            return names[k], k[0]

        col1, col2, col3 = (tk.Frame(body, bg=pal.BG) for _ in range(3))
        for col in (col1, col2, col3):
            col.pack(side="left", fill="both", expand=True, padx=8, anchor="n")
        winner_time = result.times[result.order[0]]
        _table(col1, "Arrivée de l'étape", [
            (f"{i}.", chip(k), format_time(result.times[k]),
             "+" + format_time(result.times[k] - winner_time) if i > 1 else "")
            for i, k in enumerate(result.order, 1)])
        points = [(chip(k), f"sprint +{result.sprint[k]}") for k in result.sprint] + \
                 [(chip(k), f"montagne +{result.mountain[k]}") for k in result.mountain]
        _table(col1, "Jetons pris", points, columns=1)

        gc = tour.gc_order()
        leader = tour.total_time[gc[0]]
        _table(col2, "Classement général (temps)", [
            (f"{i}.", chip(k), tour.time_text(k), "+" + format_time(tour.total_time[k] - leader) if i > 1 else "",
             "●" + tour.jersey_of(k) if tour.jersey_of(k) else "")
            for i, k in enumerate(gc, 1)], columns=4)
        jerseys = [("●" + j, JERSEY_NAMES[j], chip(k)) for j, k in tour.jerseys.items()]
        _table(col2, "Maillots", jerseys)

        teams = sorted(range(tour.num_teams), key=lambda t: -tour.tour_points(t, with_bonus=False))
        _table(col3, "Points de Tour (podiums + repos)", [
            (f"{team_names[t]}", f"{tour.tour_points(t, with_bonus=False)} PT",
             f"podiums {tour.podium_points[t]}" + (f" · repos {tour.rest_points[t]}" if tour.rest_points[t] else ""))
            for t in teams])
        sprint = [(chip(k), f"{tour.sprint[k]} pts") for k in tour.sprint_order()[:4]]
        mountain = [(chip(k), f"{tour.mountain[k]} pts") for k in tour.mountain_order()[:4]]
        _table(col3, "Sprint", sprint, columns=1)
        _table(col3, "Montagne", mountain, columns=1)
        notes = []
        if result.rest_day:
            gained = ", ".join(f"{team_names[t]} +{p}" for t, p in result.rest_points.items())
            notes.append(f"Jour de repos : les leaders rapportent 1 PT ({gained}) et les autres récupèrent encore.")
        returned = sum(result.fatigue_returned.values())
        notes.append(f"Fatigue : chaque coureur a rendu la moitié de ses cartes Fatigue ({returned} au total) ; "
                     "le reste le suit à l'étape suivante.")
        tk.Label(self, text="\n".join(notes), font=ui.font(10), bg=pal.BG, fg=pal.MUTED, justify="left",
                 anchor="w").pack(fill="x", padx=32)

        bar = _bottom_bar(self)
        ui.FlatButton(bar, "⟵  Abandonner le Tour", lambda: self._quit(on_menu), size=11, style="ghost").pack(side="left")
        label = "Classement final  ▶" if tour.finished else f"Étape {number + 1} : {tour.current.name}  ▶"
        ui.FlatButton(bar, label, on_next, style="primary", size=14, padx=28, pady=12).pack(side="right")

    @staticmethod
    def _quit(on_menu) -> None:
        if messagebox.askyesno("Grand Tour", "Abandonner le Tour en cours ?"):
            on_menu()


class FinalScreen(tk.Frame):
    """Fin du Tour : bonus des classements et classement final des équipes."""

    def __init__(self, parent, tour: Tour, team_names, on_menu):
        super().__init__(parent, bg=pal.BG)
        ranking = tour.final_ranking()
        winner = ranking[0]
        _header(self, "FIN DU TOUR", f"{len(tour.stages)} étapes · victoire : {team_names[winner]}")
        body = tk.Frame(self, bg=pal.BG)
        body.pack(fill="both", expand=True, padx=40, pady=18)
        bonus = tour.bonus_points()
        rows = []
        for place, t in enumerate(ranking, 1):
            b = bonus[t]
            detail = (f"podiums {tour.podium_points[t]} · général {b['général']} · équipe {b['équipe']} · "
                      f"sprint {b['sprint']} · montagne {b['montagne']}"
                      + (f" · repos {tour.rest_points[t]}" if tour.rest_points[t] else ""))
            rows.append((f"{place}.", team_names[t], f"{tour.tour_points(t)} PT", detail))
        _table(body, "Classement du Tour (Points de Tour)", rows, columns=3)
        names = tour.names
        gc = tour.gc_order()
        leader = tour.total_time[gc[0]]
        cols = tk.Frame(body, bg=pal.BG)
        cols.pack(fill="x")
        left, right = tk.Frame(cols, bg=pal.BG), tk.Frame(cols, bg=pal.BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))
        right.pack(side="left", fill="both", expand=True, padx=(8, 0))
        _table(left, "Classement général final", [
            (f"{i}.", (names[k], k[0]), tour.time_text(k), "+" + format_time(tour.total_time[k] - leader) if i > 1 else "")
            for i, k in enumerate(gc, 1)])
        _table(right, "Maillots", [("●" + j, JERSEY_NAMES[j], (names[k], k[0])) for j, k in tour.jerseys.items()])
        tk.Label(body, text=f"★  {team_names[winner]} remporte le Tour !", font=ui.font(18, True),
                 bg=pal.BG, fg=pal.TEAM_TEXT[winner]).pack(anchor="w", pady=(6, 0))
        bar = _bottom_bar(self)
        ui.FlatButton(bar, "Retour au menu", on_menu, style="primary", size=14, padx=28, pady=12).pack(side="right")


def team_names_for(tour: Tour, controller_of_team) -> list[str]:
    """« Équipe 1 (rouge) · IA »… ; `controller_of_team(t)` renvoie Joueur, IA, Peloton ou Muscle."""
    names = []
    for t in range(tour.num_teams):
        who = controller_of_team(t)
        names.append(f"Équipe {t + 1} ({TEAM_COLOR_NAMES[t]})" + ("" if who == "Joueur" else f" · {who}"))
    return names
