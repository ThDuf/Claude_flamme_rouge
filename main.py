"""Point d'entrée : le menu, puis la course.

    python main.py
"""
import tkinter as tk

from gui import App
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
        MenuScreen(self.container, self.start_game)

    def start_game(self, track, teams: int, secret: bool, animate: bool, extensions=()) -> None:
        self._reset()
        self.app = App(self.container, teams=teams, secret=secret, track=track, on_menu=self.show_menu, animate=animate,
                       extensions=extensions)


def main() -> None:
    root = tk.Tk()
    Launcher(root).show_menu()
    root.mainloop()


if __name__ == "__main__":
    main()
