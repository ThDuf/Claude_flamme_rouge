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
    assert "jeu de base" in menu.extensions_hint.cget("text")
    menu.extension_vars["meteo"].set(True)
    menu._refresh_extensions()
    assert "pluie" in menu.extensions_hint.cget("text")  # règles Météo programmées
    menu.on_launch()  # ouvre l'écran « Qui joue ? »
    assert launcher.app is None and menu.players_frame is not None
    assert menu.ai_teams() == frozenset({1, 2})  # par défaut : équipe 1 jouée par un joueur, les autres par l'IA
    menu.hide_players()  # retour au menu, puis on revient
    menu.on_launch()
    menu.on_players_start()
    app = launcher.app
    assert len(app.game.riders) == 6
    assert app.ctl.ai_teams == frozenset({1, 2})
    assert app.game.extensions == frozenset({"meteo"})
    turns = 0
    while app.ctl.phase != FINISHED and turns < 100:
        while app.ctl.phase == CHOOSE:
            app.on_card(app.ctl.hand[0])
        for _ in range(3):
            app.on_action()
            app.skip_animation()
        turns += 1
    assert app.ctl.phase == FINISHED
    assert app._podium_visible()  # écran de victoire à la place de la carte
    app._paint_map()
    app.on_release(None)  # un clic : retour à la course
    assert not app._podium_visible()
    app.on_release(None)  # un autre : de nouveau le podium
    assert app._podium_visible()
    app.on_release(None)
    app.zoom_at(2.0)
    app.zoom_at(1.5, 300, 200)
    app.reset_view()
    app.on_back()
    assert launcher.app is None


def test_editor_tile_cards(root):
    from editor import EditorApp, WINDOW_H, WINDOW_W
    from flamme_rouge.tiles import KIND_FINISH, KIND_START, make_tile

    app = EditorApp(root, [make_tile(KIND_START), make_tile(KIND_FINISH)], select_first=True)
    root.update()
    assert len(app.palette.cards) == 21
    assert app.palette.letters[:2] == ["a", "u"]  # départ et arrivée en tête
    assert root.winfo_reqwidth() <= WINDOW_W and root.winfo_reqheight() <= WINDOW_H
    app.palette._click(app.palette.letters.index("g"))
    app.on_place()  # double-clic : après la sélection (le départ)
    assert [t.letter for t in app.plan.tiles] == [None, "g", None] and app.plan.selected == 1
    assert "g" in app.palette.used
    app.palette.select("N")
    assert app.palette.side_var.get() == "montagne" and app.palette.tile.cells == "uuuuuu"
    app.on_replace()
    assert app.plan.tiles[1].letter == "N"
    app.listbox.selection_clear(0, "end")
    app.listbox.selection_set(0)
    app.on_select()
    assert app.palette.selected == "a"  # la palette suit la tuile choisie dans la liste


def test_a_whole_grand_tour_through_the_screens(root):
    from flamme_rouge.catalog import build_choices
    from flamme_rouge.controller import FINISHED
    from main import Launcher

    launcher = Launcher(root)
    launcher.show_menu()
    stages = [c for c in build_choices() if c.key.startswith("officiel:")][:3]
    launcher.start_tour(stages, 2, False, False, ["grandtour"], {0, 1}, None, False, {1})
    for number in range(1, 4):
        app = launcher.app
        assert app.game.tour and launcher.tour.stage_index == number - 1
        turns = 0
        while app.ctl.phase != FINISHED and turns < 200:
            app.on_action()
            turns += 1
        assert app._podium_visible()
        app.on_action()  # « Résultats de l'étape » : écran entre deux étapes
        root.update()
        assert launcher.app is None and len(launcher.tour.results) == number
        if launcher.tour.finished:
            launcher.show_final()
        else:
            launcher.play_stage()
    root.update()
    assert launcher.tour.finished and len(launcher.tour.final_ranking()) == 2


def test_tour_stages_can_be_reordered(root):
    from flamme_rouge.catalog import build_choices
    from tour_screens import TourSetupScreen

    chosen = []
    screen = TourSetupScreen(root, build_choices(), lambda: None, lambda stages, rest: chosen.append((stages, rest)))
    screen.pack()
    screen.preset_official()
    names = [c.label for c in screen.order]
    screen.move(0, 1)  # la 1re étape passe en 2e
    assert [c.label for c in screen.order][:2] == [names[1], names[0]]
    screen.move(len(names) - 1, -1)  # la dernière remonte d'un cran
    assert screen.order[-2].label == names[-1]
    screen.move(0, -1)  # déjà en tête : rien ne bouge
    assert screen.order[0].label == names[1]
    root.update()
    screen.go()
    assert [c.label for c in chosen[0][0]] == [c.label for c in screen.order]
