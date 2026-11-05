from flamme_rouge import Game
from flamme_rouge.display import board_view, render


def test_render_shows_all_riders():
    out = render(Game(seed=1))
    for name in ("1R", "1S", "2R", "2S"):
        assert name in out


def test_render_box_lines_are_aligned():
    lines = render(Game(seed=1)).splitlines()
    assert len({len(line) for line in lines[:-1]}) == 1  # tout sauf la ligne des numéros


def test_board_view_works_at_the_end_of_a_game():
    g = Game(num_teams=3, seed=4)
    while not g.finished:
        g.play_turn()
    out = board_view(g)
    assert "Classement" in out and g.winner.name in out
