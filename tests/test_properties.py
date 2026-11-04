"""The properties overlay: the sections it shows, and the box it draws."""

from __future__ import annotations

from pathlib import Path

from rich.cells import cell_len

from spoider.layout import compute
from spoider.model import MindMap, Node
from spoider.properties import sections, state_text
from spoider.render import LINK_COLOR, build_grid, render_text

README = Path("README.md")


def _map() -> tuple[MindMap, Node, Node]:
    mm = MindMap(Node("root"))
    alpha = mm.add_child(mm.root.id, "alpha")
    deep = mm.add_child(alpha.id, "a much longer name than fits")
    return mm, alpha, deep


def _file_rows(path: Path | None, dirty: bool = False) -> dict[str, str]:
    mm, _alpha, _deep = _map()
    return dict(dict(sections(mm, path, mm.root.id, 1, None, dirty=dirty, autosave=False))["file state"])


def _editor_rows(selected: str = "", run: int = 1, last_edited: str | None = None, autosave: bool = False):
    mm, _alpha, deep = _map()
    chosen = selected or deep.id
    return dict(dict(sections(mm, None, chosen, run, last_edited, dirty=False, autosave=autosave))["editor state"])


def test_the_box_has_a_file_section_and_an_editor_section():
    mm, alpha, deep = _map()
    titled = sections(mm, None, deep.id, 1, alpha.id, dirty=False, autosave=True)
    assert [title for title, _rows in titled] == ["file state", "editor state"]


def test_the_file_section_holds_what_is_in_the_file(tmp_path: Path):
    path = tmp_path / "map.spoider"
    mm, _alpha, _deep = _map()
    mm.save(path)
    rows = dict(dict(sections(mm, path, mm.root.id, 1, None, dirty=False, autosave=False))["file state"])
    assert rows["file"] == str(path)
    assert "written" in rows["size"]
    assert "cells" in rows["totals"] and "deep" in rows["totals"]
    assert rows["format"] == "1", "the map file's own version"
    assert rows["shape"] in ("spider", "pyramid", "bush", "branch")
    assert rows["colours"] in ("family", "depth")
    assert rows["spacing"].lstrip("-").isdigit()
    assert rows["justify"] == "-", "no wrap is saved yet"
    assert rows["state"] == "saved"


def test_the_marks_go_on_one_line_and_justify_on_the_next(tmp_path: Path):
    mm, _alpha, _deep = _map()
    mm.marks = ("⭐", "💡", "❓")
    mm.justify = 66
    rows = list(dict(sections(mm, tmp_path / "m.spoider", mm.root.id, 1, None, dirty=False, autosave=False))["file state"])
    labels = [label for label, _value in rows]
    assert labels.count("marks") == 1 and labels.count("justify") == 1
    values = dict(rows)
    assert values["marks"] == "⭐ 💡 ❓"
    assert values["justify"] == "66"


def test_autosave_is_editor_state_not_file_state():
    mm, _alpha, deep = _map()
    titled = dict(sections(mm, None, deep.id, 1, None, dirty=False, autosave=True))
    assert "autosave" not in dict(titled["file state"])
    assert dict(titled["editor state"])["autosave"] == "on"


def test_the_editor_section_names_the_cursor_and_the_last_edit():
    rows = _editor_rows(run=3, last_edited=None)
    assert rows["cursor"].startswith("1.1 ") and "run of 3" in rows["cursor"]
    assert rows["edited"] == "-"


def test_the_last_edited_cell_is_named_with_its_text():
    mm, alpha, deep = _map()
    rows = dict(dict(sections(mm, None, deep.id, 1, alpha.id, dirty=False, autosave=False))["editor state"])
    assert rows["edited"].startswith("1 ") and '"alpha"' in rows["edited"]


def test_a_new_buffer_is_new_unsaved(tmp_path: Path):
    assert state_text(None, dirty=False) == "new unsaved"
    assert state_text(tmp_path / "missing.spoider", dirty=False) == "new unsaved"
    path = tmp_path / "there.spoider"
    path.write_text("{}", encoding="utf-8")
    assert state_text(path, dirty=True) == "unsaved"
    assert state_text(path, dirty=False) == "saved"


def _screen(rows, *, ox=0, oy=0, width=80, height=20):
    mm, _alpha, _deep = _map()
    grid = build_grid(compute(mm.root, 0), "")
    return render_text(grid, ox, oy, width, height, floaters=[(rows, LINK_COLOR)]).plain


def test_the_box_is_drawn_in_the_top_left_corner():
    mm, _alpha, deep = _map()
    drawn = _screen(sections(mm, None, deep.id, 1, None, dirty=False, autosave=False))
    assert drawn.splitlines()[0].startswith("╭")
    assert "file state" in drawn and "editor state" in drawn


def test_the_boxs_lines_all_have_the_same_width():
    """Emoji take two columns; the border must still be straight."""
    mm, _alpha, deep = _map()
    mm.marks = ("⭐", "💡", "❓", "✅", "📌")
    drawn = _screen(sections(mm, None, deep.id, 1, None, dirty=False, autosave=False))
    lines = drawn.splitlines()

    def char_at(line: str, column: int) -> str | None:
        walked = 0
        for char in line:
            if walked == column:
                return char
            walked += cell_len(char)
        return None

    top = lines[0]
    width = cell_len(top[: top.index("╮") + 1])
    body = [line for line in lines if line.startswith("│")]
    assert body, "the box was not drawn"
    for line in body:
        assert char_at(line, width - 1) == "│", f"the right border is ragged at {width - 1}: {line!r}"


def test_the_box_covers_what_is_behind_it():
    mm, _alpha, deep = _map()
    drawn = _screen(sections(mm, None, deep.id, 1, None, dirty=False, autosave=False))
    assert "root" not in drawn.splitlines()[0], "the map does not show through the border"


def test_the_box_does_not_move_when_the_camera_does():
    """It is pinned to the screen, not to the map: the camera must not drag it off."""
    mm, _alpha, deep = _map()
    rows = sections(mm, Path("/home/somebody/a-map-with-a-long-name.spoider"), deep.id, 1, None, dirty=False, autosave=False)
    near = _screen(rows)
    far = _screen(rows, ox=40, oy=12)
    assert far.splitlines()[0].startswith("╭")
    assert "/home/somebody/a-map-with-a-long-name.spoider" in far, "the path is not clipped"
    top = far.splitlines()[0]
    corner = top.index("╮") + 1
    assert near.splitlines()[0][:corner] == top[:corner]


def test_the_path_is_shown_whole_even_when_it_is_long():
    mm, _alpha, deep = _map()
    rows = sections(mm, Path("/home/somebody/a-map-with-a-long-name.spoider"), deep.id, 1, None, dirty=False, autosave=False)
    assert "a-map-with-a-long-name.spoider" in _screen(rows)


def test_the_box_is_clipped_only_by_the_screen():
    mm, _alpha, deep = _map()
    drawn = _screen(sections(mm, None, deep.id, 1, None, dirty=False, autosave=False), width=20)
    assert drawn.splitlines()[0].startswith("╭")
    assert cell_len(drawn.splitlines()[0]) == 20


def test_the_readme_names_the_key():
    """The key table is guarded; this is the one line that must mention the overlay."""
    assert "| &#96; |" in README.read_text(encoding="utf-8")


def test_a_variation_selector_stays_with_its_glyph():
    """`⚠️` is two code points; splitting them into two cells unaligns the row."""
    mm, _alpha, deep = _map()
    mm.marks = ("⚠️", "✅")
    drawn = _screen(sections(mm, None, deep.id, 1, None, dirty=False, autosave=False))
    assert "⚠️" in drawn
