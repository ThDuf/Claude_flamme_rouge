"""Point d'entrée : le menu, puis la course.

    python main.py
"""
import tkinter as tk

from gui import App
from flamme_rouge.tour import Tour, TourStage
from menu import MenuScreen


class Launcher:
    """Fait passer la fenêtre du menu à la course, et inversement."""

    def __init__(self, root):
        self.root = root
        self.container = None
        self.app = None

    def _reset(self) -> None:
        if self.app is not None:
            self.app.close()  # arrête l'animation et ferme la fenêtre des decks
            self.app = None
        if self.container is not None:
            self.container.destroy()
        self.container = tk.Frame(self.root)
        self.container.pack(fill="both", expand=True)

    def show_menu(self) -> None:
        self._reset()
        self.tour = None
        MenuScreen(self.container, self.start_game, self.start_tour)

    def start_game(self, track, teams: int, secret: bool, animate: bool, extensions=(), ai_teams=(), team_types=None,
                   breakaway: bool = False) -> None:
        self._reset()
        self.app = App(self.container, teams=teams, secret=secret, track=track, on_menu=self.show_menu, animate=animate,
                       extensions=extensions, ai_teams=ai_teams, team_types=team_types, breakaway=breakaway)


    # ------------------------------------------------------------ Grand Tour

    def start_tour(self, stages, teams: int, secret: bool, animate: bool, extensions=(), ai_teams=(), team_types=None,
                   breakaway: bool = False, rest_after=()) -> None:
        """Lance un Tour : une étape après l'autre, avec un écran de résultats entre deux étapes."""
        self.tour = Tour([TourStage(c.label, c.track) for c in stages], teams, team_types, extensions, rest_after)
        self.tour_settings = dict(secret=secret, animate=animate, ai_teams=ai_teams, breakaway=breakaway)
        self.play_stage()

    def play_stage(self) -> None:
        self._reset()
        s = self.tour_settings
        game = self.tour.start_stage()
        self.app = App(self.container, game=game, secret=s["secret"], on_menu=self.show_menu, animate=s["animate"],
                       ai_teams=s["ai_teams"], breakaway=s["breakaway"], on_stage_end=self.stage_done,
                       stage_title=f"Étape {self.tour.stage_index + 1}/{len(self.tour.stages)} · {self.tour.current.name}")

    def _team_names(self) -> list[str]:
        from tour_screens import team_names_for

        ctl = self.app.ctl if self.app is not None else None
        game = self.app.game if self.app is not None else None

        def who(team: int) -> str:
            if ctl is None:
                return "Joueur"
            return ctl.controller_of(next(r for r in game.all_riders if r.team == team))

        return team_names_for(self.tour, who)

    def stage_done(self) -> None:
        from tour_screens import StageResultsScreen

        result = self.tour.finish_stage(self.app.game)
        self.team_names = self._team_names()
        self._reset()
        nxt = self.show_final if self.tour.finished else self.play_stage
        StageResultsScreen(self.container, self.tour, result, self.team_names, nxt, self.show_menu).pack(
            fill="both", expand=True)

    def show_final(self) -> None:
        from tour_screens import FinalScreen

        self._reset()
        FinalScreen(self.container, self.tour, self.team_names, self.show_menu).pack(fill="both", expand=True)


def main() -> None:
    root = tk.Tk()
    Launcher(root).show_menu()
    root.mainloop()


if __name__ == "__main__":
    main()
