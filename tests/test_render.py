"""The renderer draws whatever is in the document, and a document is untrusted.

These tests exist because a cell's text is written straight to the terminal: an
escape sequence in it is not a rendering bug, it is a way to drive the user's
terminal.
"""

from __future__ import annotations

from spoider.layout import compute
from spoider.model import MindMap, Node
from spoider.render import build_grid, render_text

EVIL = "\x1b[2J\x1b[31mred\x1b]52;c;SGVsbG8=\x07\x9b31m"


def _render(mm: MindMap, width: int = 80, height: int = 12) -> str:
    layout = compute(mm.root, mm.spacing)
    grid = build_grid(layout, mm.root.id)
    return render_text(grid, 0, 0, max(width, layout.width), max(height, layout.height)).plain


def test_control_characters_in_text_never_reach_the_grid():
    mm = MindMap(Node(f"wiped {EVIL} tail"))
    drawn = _render(mm)
    assert "\x1b" not in drawn
    assert "\x07" not in drawn
    assert "\x9b" not in drawn
    assert "wiped" in drawn


def test_control_characters_in_a_mark_never_reach_the_grid():
    mm = MindMap(Node("cell", mark="\x1b[31mX"))
    drawn = _render(mm)
    assert "\x1b" not in drawn
    assert "X cell" in drawn


def test_the_inline_edit_buffer_is_cleaned_too():
    node = Node("cell")
    node.preview = "typ\x1b[2Jing▊"
    drawn = _render(MindMap(node))
    # dropping the ESC is enough to defuse the sequence; the rest is plain text
    assert "\x1b" not in drawn
    assert "typ[2Jing▊" in drawn


def test_a_pasted_line_break_cannot_break_the_box():
    mm = MindMap(Node("two\nlines"))
    layout = compute(mm.root, 0)
    assert layout.boxes[mm.root.id].h == 3  # still a three-row box
    assert len(_render(mm).splitlines()) >= 3


def test_every_row_is_exactly_the_layout_width():
    mm = MindMap(Node("✅ 日本語 ✅"), spacing=0)
    mm.add_child(mm.root.id, "child ✅")
    layout = compute(mm.root, mm.spacing)
    grid = build_grid(layout, mm.root.id)
    text = render_text(grid, 0, 0, layout.width, layout.height)
    widths = {line.cell_len for line in text.split("\n")}
    assert widths == {layout.width}


def test_cropping_past_the_map_leaves_blank_cells():
    mm = MindMap(Node("tiny"))
    layout = compute(mm.root, 0)
    grid = build_grid(layout, mm.root.id)
    text = render_text(grid, layout.width + 5, layout.height + 5, 4, 2)
    assert text.plain.strip() == ""


def test_only_the_selected_box_is_reversed():
    mm = MindMap(Node("root"))
    child = mm.add_child(mm.root.id, "child")
    layout = compute(mm.root, 0)
    plain = build_grid(layout, child.id)
    styles = {box.node.text: plain.cells[(box.x + 1, box.y + 1)][1] for box in layout.boxes.values()}
    assert "reverse" in styles["child"]
    assert "reverse" not in styles["root"]


def test_a_tight_layout_flattens_the_corners_where_two_boxes_share_a_row():
    mm = MindMap(Node("root"), spacing=-1)
    mm.add_child(mm.root.id, "one")
    mm.add_child(mm.root.id, "two")
    drawn = _render(mm, width=80, height=30)
    # a stranded corner in the middle of a shared rule reads as a glitch
    assert "╭─" in drawn or "╰─" in drawn
    assert "╭╮" not in drawn


def test_tight_and_loose_spacing_change_the_drawn_size():
    mm = MindMap(Node("root"))
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, "one")  # siblings on the same side stack vertically
    mm.add_child(branch.id, "two")
    tight = compute(mm.root, -2)
    loose = compute(mm.root, 4)
    assert tight.width < loose.width
    assert tight.height < loose.height
