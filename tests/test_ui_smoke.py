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
    assert menu.type_frame is not None and menu.frame is None  # 1er écran : le type de course
    menu.choose_mode("course")
    assert menu.start_btn.cget("state") == "normal"
    menu.on_pick(menu.rows["officiel:Ronde van Wevelgem"].choice)
    assert menu.start_btn.cget("state") == "normal"  # les étapes officielles sont jouables
    menu.on_pick(menu.rows["base:Classique"].choice)
    menu.on_launch()  # ouvre l'écran « Qui joue ? » : nombre d'équipes, extensions et options
    assert launcher.app is None and menu.players_frame is not None
    assert "jeu de base" in menu.extensions_hint.cget("text")
    menu.extension_vars["meteo"].set(True)
    menu._extensions_changed_on_players()
    assert "pluie" in menu.extensions_hint.cget("text")  # règles Météo programmées
    menu.teams_var.set(3)
    menu.show_players()
    assert menu.ai_teams() == frozenset({1, 2})  # par défaut : équipe 1 jouée par un joueur, les autres par l'IA
    menu.hide_players()  # retour au menu, puis on revient
    menu.on_launch()
    menu.on_players_start()
    app = launcher.app
    assert len(app.game.riders) == 6
    assert app.ctl.ai_teams == frozenset({1, 2})
    assert app.game.extensions == frozenset({"meteo"})
    app.camera_var.set("tete")  # caméra qui suit la tête de course
    app.set_camera()
    assert app.view is not None
    app.camera_var.set("peloton")  # puis le peloton, pendant toute la partie
    app.set_camera()
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
    assert app.camera_var.get() == ""  # zoom à la main : plus de suivi
    app.zoom_at(1.5, 300, 200)
    app.reset_view()
    assert app.camera_var.get() == "tout" and app.view is None
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
    launcher.start_tour(stages, 2, False, False, [], {0, 1}, None, False, {1})
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


def test_grand_tour_menu_stages_reordered_then_players(root):
    from menu import MenuScreen

    started = []
    menu = MenuScreen(root, lambda *a: None, lambda *a: started.append(a))
    menu.choose_mode("tour")
    root.update()
    assert menu.add_btn is not None and menu.start_btn.cget("state") == "disabled"  # moins de 3 étapes
    menu.on_pick(menu.rows["officiel:La Haut Montagne"].choice)
    menu.tour_add_current()  # le parcours affiché dans l'aperçu
    menu.tour_preset_official()
    names = [c.label for c in menu.tour_order]
    assert len(names) == 6 and menu.start_btn.cget("state") == "normal"
    menu.tour_move(0, 1)  # la 1re étape passe en 2e
    assert [c.label for c in menu.tour_order][:2] == [names[1], names[0]]
    menu.tour_move(len(names) - 1, -1)  # la dernière remonte d'un cran
    assert menu.tour_order[-2].label == names[-1]
    menu.tour_move(0, -1)  # déjà en tête : rien ne bouge
    assert menu.tour_order[0].label == names[1]
    menu.tour_remove(0)
    assert len(menu.tour_order) == 5
    menu.tour_rest_var.set("2")
    menu.refresh_tour()
    menu.on_launch()  # « Qui joue ? » avec le nombre d'équipes
    root.update()
    assert menu.players_frame is not None
    menu.teams_var.set(4)
    menu.show_players()
    menu.on_players_start()
    stages, teams = started[0][0], started[0][1]
    assert [c.label for c in stages] == [c.label for c in menu.tour_order] and teams == 4
    assert started[0][-1] == {2}  # jour de repos après l'étape 2
    menu.show_type_screen()  # retour au premier écran
    assert menu.frame is None and menu.type_frame is not None


def test_extensions_can_be_chosen_on_the_players_screen(root):
    from flamme_rouge.extensions import PELOTON
    from menu import MenuScreen

    started = []
    menu = MenuScreen(root, lambda *a: started.append(a), lambda *a: None)
    menu.choose_mode("course")
    menu.on_launch()
    root.update()
    assert menu.player_options() == ["joueur", "ia"]
    menu.extension_vars[PELOTON].set(True)
    menu._extensions_changed_on_players()  # l'écran se reconstruit avec les équipes fantômes
    assert "peloton" in menu.player_options() and "équipes fantômes" in menu.extensions_hint.cget("text")
    menu.teams_var.set(6)
    menu.show_players()
    menu.extension_vars[PELOTON].set(False)
    menu._extensions_changed_on_players()  # sans Peloton : 6 équipes refusées
    assert "Peloton" in menu.players_hint.cget("text")
    menu.extension_vars[PELOTON].set(True)
    menu._extensions_changed_on_players()
    menu.on_players_start()
    assert started and started[0][1] == 6 and PELOTON in started[0][4]
