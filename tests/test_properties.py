"""The properties overlay: the numbers it shows, and the box it draws."""

from __future__ import annotations

from pathlib import Path

from spoider.layout import compute
from spoider.model import MindMap, Node
from spoider.properties import rows_for
from spoider.render import LINK_COLOR, build_grid, render_text

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


def _screen(rows, *, ox=0, oy=0, width=80, height=20):
    mm, _alpha, _deep = _map()
    grid = build_grid(compute(mm.root, 0), "")
    return render_text(
        grid, ox, oy, width, height, floaters=[(rows, LINK_COLOR)]
    ).plain


def test_the_box_is_drawn_in_the_top_left_corner():
    drawn = _screen([("file", "x.spoider"), ("cursor", "1.1")])
    assert drawn.splitlines()[0].startswith("╭")
    assert "x.spoider" in drawn and "cursor" in drawn


def test_the_box_does_not_move_when_the_camera_does():
    """It is pinned to the screen, not to the map: the camera must not drag it off."""
    rows = [("file", "/home/somebody/a-map-with-a-long-name.spoider"), ("cursor", "1.1")]
    near = _screen(rows)
    far = _screen(rows, ox=40, oy=12)
    assert far.splitlines()[0].startswith("╭")
    assert "/home/somebody/a-map-with-a-long-name.spoider" in far, "the path is not clipped"
    # the map behind the box differs with the camera; the box itself must not
    top = far.splitlines()[0]
    corner = top.index("╮") + 1
    assert near.splitlines()[0][:corner] == top[:corner]


def test_the_box_is_clipped_only_by_the_screen():
    drawn = _screen([("file", "a name long enough to run past a narrow grid")], width=20)
    assert drawn.splitlines()[0].startswith("╭")
    assert len(drawn.splitlines()[0]) == 20


def test_the_readme_names_the_key():
    """The key table is guarded; this is the one line that must mention the overlay."""
    assert "| `i` |" in README.read_text(encoding="utf-8")
