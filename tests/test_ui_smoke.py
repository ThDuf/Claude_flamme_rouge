"""Essai en vraie fenêtre tkinter (ignoré s'il n'y a pas de tkinter ou pas d'écran)."""
import os
import sys

import pytest

tk = pytest.importorskip("tkinter")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError:
        pytest.skip("pas d'écran disponible")
    errors = []
    window.report_callback_exception = lambda *exc: errors.append(exc)
    yield window
    window.destroy()
    assert not errors


def test_menu_then_a_whole_game_then_back(root):
    from flamme_rouge.controller import CHOOSE, FINISHED
    from main import Launcher
    from menu import MenuScreen

    launcher = Launcher(root)
    launcher.show_menu()
    launcher.container.destroy()
    launcher.container = tk.Frame(root)
    launcher.container.pack(fill="both", expand=True)
    menu = MenuScreen(launcher.container, launcher.start_game)
    assert menu.start_btn.cget("state") == "normal"
    menu.on_pick(menu.rows["officiel:Ronde van Wevelgem"].choice)
    assert menu.start_btn.cget("state") == "normal"  # les étapes officielles sont jouables
    menu.on_pick(menu.rows["base:Classique"].choice)
    menu.teams_var.set(3)
    menu.on_launch()
    app = launcher.app
    assert len(app.game.riders) == 6
    turns = 0
    while app.ctl.phase != FINISHED and turns < 100:
        while app.ctl.phase == CHOOSE:
            app.on_card(app.ctl.hand[0])
        for _ in range(3):
            app.on_action()
            app.skip_animation()
        turns += 1
    assert app.ctl.phase == FINISHED
    app.zoom_at(2.0)
    app.zoom_at(1.5, 300, 200)
    app.reset_view()
    app.on_back()
    assert launcher.app is None
