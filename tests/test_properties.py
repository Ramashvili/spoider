"""The properties overlay: the numbers it shows, and the box it draws."""

from __future__ import annotations

from pathlib import Path

from spoider.layout import compute
from spoider.model import MindMap, Node
from spoider.properties import rows_for
from spoider.render import build_grid, overlay, render_text

README = Path("README.md")


def _map() -> tuple[MindMap, Node, Node]:
    mm = MindMap(Node("root"))
    alpha = mm.add_child(mm.root.id, "alpha")
    deep = mm.add_child(alpha.id, "a much longer name than fits")
    return mm, alpha, deep


def _rows(path: Path | None, **kwargs):
    mm, alpha, deep = _map()
    return dict(rows_for(mm, path, deep.id, 1, alpha.id, dirty=True, autosave=False)), mm, alpha, deep


def test_the_overlay_names_the_file_the_totals_and_the_cursor(tmp_path: Path):
    path = tmp_path / "map.spoider"
    mm, alpha, deep = _map()
    mm.save(path)
    rows = dict(rows_for(mm, path, deep.id, 3, alpha.id, dirty=False, autosave=False))

    assert rows["file"] == str(path)
    assert "cells" in rows["totals"] and "deep" in rows["totals"]
    assert rows["cursor"].startswith("1.1 ") and deep.id in rows["cursor"]
    assert "run of 3" in rows["cursor"]
    assert rows["edited"].startswith("1 ") and '"alpha"' in rows["edited"]
    assert rows["state"] == "saved"


def test_a_file_that_is_not_on_disk_says_so(tmp_path: Path):
    rows, *_ = _rows(tmp_path / "nowhere.spoider")
    assert "not on disk" in rows["file"]


def test_an_unsaved_buffer_has_no_name(tmp_path: Path):
    rows, *_ = _rows(None)
    assert rows["file"] == "not named yet"


def test_nothing_edited_yet_reads_as_a_dash(tmp_path: Path):
    mm, _, deep = _map()
    rows = dict(rows_for(mm, tmp_path / "m.spoider", deep.id, 1, None, dirty=True, autosave=False))
    assert rows["edited"] == "-"


def test_the_box_is_drawn_in_the_top_left_corner():
    mm, _alpha, _deep = _map()
    layout = compute(mm.root, 0)
    grid = build_grid(layout, "")
    overlay(grid, [("file", "x.spoider"), ("cursor", "1.1")], width=80, height=20)
    assert grid.cells[(0, 0)][0] == "╭", "the corner is the grid's own origin"
    drawn = render_text(grid, 0, 0, grid.width, grid.height).plain
    assert drawn.splitlines()[0].startswith("╭")
    assert "x.spoider" in drawn and "cursor" in drawn


def test_the_box_is_clipped_rather_than_overflowing():
    mm, _alpha, _deep = _map()
    layout = compute(mm.root, 0)
    grid = build_grid(layout, "")
    overlay(grid, [("file", "a name long enough to run past a narrow grid")], width=20, height=20)
    assert all(0 <= x < grid.width and 0 <= y < grid.height for (x, y) in grid.cells)


def test_the_readme_names_the_key():
    """The key table is guarded; this is the one line that must mention the overlay."""
    assert "| `i` |" in README.read_text(encoding="utf-8")
