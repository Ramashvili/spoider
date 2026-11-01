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


def _stacked(spacing: int, first: str = "one", second: str = "two") -> str:
    mm = MindMap(Node("root"), spacing=spacing)
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, first)
    mm.add_child(branch.id, second)
    return _render(mm, width=90, height=30)


def test_stacked_boxes_share_one_rule_joined_by_t_pieces():
    drawn = _stacked(-2)
    shared = [line.strip() for line in drawn.splitlines() if "├" in line]
    assert shared, "two boxes one row apart should share their border row"
    row = shared[0]
    # the rule the two boxes share meets the side walls as a T, not as two
    # rounded corners fighting over the same cells
    assert "├" in row and "┤" in row
    assert "╭────" not in row and "╰────" not in row
    # equal widths, so nothing sticks out sideways
    assert "┬" not in row and "┴" not in row


def test_a_narrower_box_sharing_a_row_leaves_a_stub_junction():
    drawn = _stacked(-2, first="a much longer name", second="short")
    assert any("┬" in line or "┴" in line for line in drawn.splitlines())


def test_a_shared_row_keeps_both_boxes_closed():
    drawn = _stacked(-2).splitlines()
    shared = next(index for index, line in enumerate(drawn) if "├" in line)
    assert "│" in drawn[shared - 1]  # the box above still has its text row
    assert "│" in drawn[shared + 1]  # and the box below its own
    assert drawn[shared - 1].count("│") >= 2


def test_spacing_zero_gives_each_box_its_own_rounded_corners():
    # With air between the boxes no border is shared, so all four corners of
    # every box survive intact; the T's are only where a connector meets a wall.
    mm = MindMap(Node("root"), spacing=0)
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, "one")
    mm.add_child(branch.id, "two")
    layout = compute(mm.root, 0)
    grid = build_grid(layout, mm.root.id)

    for box in layout.boxes.values():
        assert grid.cells[(box.x, box.y)][0] == "╭"
        assert grid.cells[(box.right, box.y)][0] == "╮"
        assert grid.cells[(box.x, box.bottom)][0] == "╰"
        assert grid.cells[(box.right, box.bottom)][0] == "╯"


def test_tight_and_loose_spacing_change_the_drawn_size():
    mm = MindMap(Node("root"))
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, "one")  # siblings on the same side stack vertically
    mm.add_child(branch.id, "two")
    tight = compute(mm.root, -2)
    loose = compute(mm.root, 4)
    assert tight.width < loose.width
    assert tight.height < loose.height


# -- links in the stacked shapes ------------------------------------------


def _shaped(layout: str):
    mm = MindMap(Node("root"))
    mm.add_child(mm.root.id, "child")
    mm.layout = layout
    return compute(mm.root, 0, layout)


def test_a_pyramid_link_leaves_the_parent_edge_and_arrives_at_the_childs():
    layout = _shaped("pyramid")
    drawn = render_text(build_grid(layout, layout.boxes[next(iter(layout.boxes))].node.id),
                        0, 0, layout.width, layout.height).plain
    assert "┬" in drawn  # the trunk hanging off the parent's bottom edge
    assert "┴" in drawn  # and the T where it reaches the child's top edge
    assert "╰───┬" in drawn or "┬───╯" in drawn


def test_a_bush_link_points_upwards():
    layout = _shaped("bush")
    root_id = next(iter(layout.boxes))
    drawn = render_text(build_grid(layout, root_id), 0, 0, layout.width, layout.height).plain
    assert "┬" in drawn and "┴" in drawn


def test_boxes_touching_in_a_pyramid_are_joined_not_overwritten():
    mm = MindMap(Node("root"), spacing=-3)
    mm.layout = "pyramid"
    mm.add_child(mm.root.id, "one")
    mm.add_child(mm.root.id, "two")
    layout = compute(mm.root, -3, "pyramid")
    drawn = render_text(build_grid(layout, mm.root.id), 0, 0, layout.width, layout.height).plain
    # parent and children share one row, and every place they meet is a T
    shared = [row for row in drawn.splitlines() if "┬" in row or "┴" in row]
    assert shared, "expected a shared border row"
    assert "┬" in shared[0] and "┴" in shared[0]


def test_a_child_centred_under_its_parent_stays_connected():
    # the centres line up, so there is no horizontal run to draw — the single row
    # between the two edges still has to be a wall, not a hole
    for name in ("pyramid", "bush"):
        mm = MindMap(Node("root"))
        mm.add_child(mm.root.id, "child")
        layout = compute(mm.root, 0, name)
        drawn = render_text(build_grid(layout, mm.root.id), 0, 0, layout.width, layout.height)
        lines = [line.strip() for line in drawn.plain.splitlines()]
        assert "│" in lines, f"{name}: the two boxes are not joined"
        assert "┬" in drawn.plain and "┴" in drawn.plain


def test_a_connector_leaves_and_arrives_through_t_junctions():
    mm = MindMap(Node("root"))
    child = mm.add_child(mm.root.id, "child")
    layout = compute(mm.root, 0, "branch")
    grid = build_grid(layout, mm.root.id)
    parent_box = layout.boxes[mm.root.id]
    child_box = layout.boxes[child.id]

    # the line leaves the parent's wall and arrives at the child's, and both
    # cells turn into a T pointing along it instead of a plain wall
    assert grid.cells[(parent_box.right, parent_box.cy)][0] == "├"
    assert grid.cells[(child_box.x, child_box.cy)][0] == "┤"


def test_a_shared_wall_between_siblings_is_one_column():
    mm = MindMap(Node("root"), spacing=-2)
    one = mm.add_child(mm.root.id, "one")
    two = mm.add_child(mm.root.id, "two")
    layout = compute(mm.root, -2, "pyramid")
    grid = build_grid(layout, mm.root.id)
    first = layout.boxes[one.id]
    second = layout.boxes[two.id]

    assert first.right == second.x, "siblings should share the column"
    # one wall between them, and a T where it meets the top and bottom edges
    assert grid.cells[(second.x, second.cy)][0] == "│"
    assert grid.cells[(second.x, second.y)][0] == "┬"
    assert grid.cells[(second.x, second.bottom)][0] == "┴"


# -- search highlights ----------------------------------------------------


def test_a_found_word_is_underlined_and_keeps_its_colour():
    mm = MindMap(Node("root"))
    mm.add_child(mm.root.id, "alpha one")
    layout = compute(mm.root, 0, "branch")
    drawn = render_text(build_grid(layout, mm.root.id, "one"), 0, 0, layout.width, layout.height)

    marked = [span for span in drawn.spans if "underline" in str(span.style)]
    assert [drawn.plain[span.start : span.end] for span in marked] == ["one"]
    assert all("cyan" in str(span.style) for span in marked), "the cell keeps its depth colour"


def test_an_empty_or_absent_query_marks_nothing():
    mm = MindMap(Node("root"))
    mm.add_child(mm.root.id, "alpha one")
    layout = compute(mm.root, 0, "branch")
    for query in ("", "   ", "nothing here"):
        drawn = render_text(
            build_grid(layout, mm.root.id, query), 0, 0, layout.width, layout.height
        )
        assert not [span for span in drawn.spans if "underline" in str(span.style)], query


def test_the_search_ignores_case_and_finds_every_occurrence():
    mm = MindMap(Node("One ONE one"))
    layout = compute(mm.root, 0, "branch")
    drawn = render_text(build_grid(layout, mm.root.id, "one"), 0, 0, layout.width, layout.height)
    marked = "".join(drawn.plain[span.start : span.end] for span in drawn.spans if "underline" in str(span.style))
    assert marked == "OneONEone"
