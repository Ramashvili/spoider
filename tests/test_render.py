"""The renderer draws whatever is in the document, and a document is untrusted.

These tests exist because a cell's text is written straight to the terminal: an
escape sequence in it is not a rendering bug, it is a way to drive the user's
terminal.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from spoider.layout import PAD, compute, compute_stack, lines_of, mark_cells
from spoider.model import MindMap, Node
from spoider.render import (
    DEPTH_COLORS,
    LINK_COLOR,
    STACK_START,
    build_grid,
    cache_window,
    render_text,
)

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
    node.preview = "typ\x1b[2Jing"
    drawn = _render(MindMap(node))
    # dropping the ESC is enough to defuse the sequence; the rest is plain text
    assert "\x1b" not in drawn
    assert "typ[2Jing" in drawn


def test_a_line_break_grows_the_box_instead_of_escaping_it():
    mm = MindMap(Node("two\nlines"))
    layout = compute(mm.root, 0)
    box = layout.boxes[mm.root.id]
    assert box.h == 4, "one border, two lines of text, one border"
    assert box.w == cell_len("lines") + 4, "the widest line decides the width"
    drawn = _render(mm).splitlines()
    assert "│ two   │" in drawn[1]
    assert "│ lines │" in drawn[2]


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


def test_a_selected_cell_keeps_its_text_and_mark_in_their_own_colours():
    """Selection is a block around a cell, so nothing written inside it is inverted."""
    mm = MindMap(Node("root"))
    child = mm.add_child(mm.root.id, "child")
    child.mark = "⭐"
    layout = compute(mm.root, 0)
    plain = build_grid(layout, child.id)
    box = layout.boxes[child.id]
    row = box.y + 1
    mark_style = plain.cells[(box.x + 1 + PAD, row)][1]
    # the first column of the text: padding, the two-cell star, and its space
    text_style = plain.cells[(box.x + 1 + PAD + cell_len("⭐") + 1, row)][1]
    assert "reverse" not in mark_style, "the mark should keep its own colours"
    assert "reverse" not in text_style, "the letters keep the terminal's own colours"
    wall = plain.cells[(box.x, box.y)][1]
    assert "reverse" in wall, "the frame is what marks the selection"

    # and selection must not move a single character: a split run that is placed one
    # cell off swallows the first letter of the cell and leaves a stray blank at the end
    unselected = build_grid(layout, "")
    drawn = render_text(plain, 0, 0, layout.width, layout.height).plain
    quiet = render_text(unselected, 0, 0, layout.width, layout.height).plain
    assert drawn == quiet


def test_the_folded_count_wears_the_colour_of_the_links():
    """The count is about the structure, so it reads in the grey the connectors use."""
    mm = MindMap(Node("root"))
    parent = mm.add_child(mm.root.id, "folded")
    for name in ("a", "b", "c"):
        mm.add_child(parent.id, name)
    parent.collapsed = True
    layout = compute(mm.root, 0)
    plain = build_grid(layout, "")
    box = layout.boxes[parent.id]
    row = box.y + 1
    note_x = box.x + 1 + PAD + cell_len("folded")
    assert "".join(plain.cells[(note_x + i, row)][0] for i in range(3)) == " +3"
    assert plain.cells[(note_x, row)][1] == LINK_COLOR
    assert plain.cells[(box.x + 1 + PAD, row)][1] != LINK_COLOR, "the text keeps its colour"


def test_the_cut_stack_starts_further_down_the_palette():
    """The panel is a document of its own: its top cells take a colour rather than the
    map's plain foreground."""
    mm = MindMap(Node("root"))
    layout = compute(mm.root, 0)
    drawn = build_grid(layout, "", depth_shift=DEPTH_COLORS.index(STACK_START) + 1)
    box = layout.boxes[mm.root.id]
    assert drawn.cells[(box.x + 1, box.y + 1)][1] == STACK_START


def test_children_of_one_cut_share_a_colour_in_the_panel():
    """A stack is a list, so it colours by level: two children of one cut must match,
    which "family" breaks because each entry is a little tree of its own."""
    entry = Node("cut", children=[Node("a"), Node("b")])
    layout = compute_stack([entry], 0)
    drawn = build_grid(
        layout, "", colours="depth", depth_shift=DEPTH_COLORS.index(STACK_START) + 1
    )
    styles = {
        box.node.text: drawn.cells[(box.x + 1, box.y + 1)][1]
        for box in layout.boxes.values()
    }
    assert styles["a"] == styles["b"]


def test_only_the_selected_box_frame_is_reversed():
    mm = MindMap(Node("root"))
    child = mm.add_child(mm.root.id, "child")
    layout = compute(mm.root, 0)
    plain = build_grid(layout, child.id)
    frames = {box.node.text: plain.cells[(box.x, box.y)][1] for box in layout.boxes.values()}
    assert "reverse" in frames["child"]
    assert "reverse" not in frames["root"]
    for box in layout.boxes.values():
        assert "reverse" not in plain.cells[(box.x + 1, box.y + 1)][1]


def _stacked(spacing: int, first: str = "one", second: str = "two") -> str:
    mm = MindMap(Node("root"), spacing=spacing)
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, first)
    mm.add_child(branch.id, second)
    return _render(mm, width=90, height=30)


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
    tight = compute(mm.root, -1)
    loose = compute(mm.root, 4)
    assert tight.width < loose.width
    assert tight.height < loose.height


# -- links in the stacked shapes ------------------------------------------


def _shaped(layout: str):
    mm = MindMap(Node("root"))
    mm.add_child(mm.root.id, "child")
    mm.layout = layout
    return compute(mm.root, 0, layout)


def _text_cells(lay) -> dict[tuple[int, int], str]:
    """Every cell a box's text stands in, with the character that belongs there."""
    own: dict[tuple[int, int], str] = {}
    for box in lay.boxes.values():
        left = box.x + 1 if lay.walls else box.x
        top = box.y + 1 if lay.walls else box.y
        # the mark holds the columns at the left of every row, so the text starts past them
        for index, line in enumerate(lines_of(box.node)):
            x = left + PAD + mark_cells(box.node)
            for ch in line:
                if ch.strip():
                    own[(x, top + index)] = ch
                x += max(cell_len(ch), 1)
    return own


def _defects(mm: MindMap, layout: str, spacing: int) -> list[str]:
    """Cells where a letter and a line disagree about who owns the cell.

    A glyph standing on a letter is one fault (the letter is lost), and a connector drawn into
    a cell a letter owns is the other (the line comes out in two pieces, because the text wins
    when the grid is finished).
    """
    lay = compute(mm.root, spacing, layout)
    grid = build_grid(lay, mm.root.id)
    wrong: list[str] = []
    for (x, y), ch in _text_cells(lay).items():
        if (x, y) in grid.edges:
            wrong.append(f"a wall on {ch!r} at ({x}, {y})")
        elif (x, y) in grid.links:
            wrong.append(f"a line under {ch!r} at ({x}, {y})")
        elif grid.cells.get((x, y), ("", ""))[0] != ch:
            wrong.append(f"{ch!r} replaced at ({x}, {y})")
    return wrong


def test_a_border_never_paints_out_a_letter():
    """A bare cell's own row is its text, so the wall the stacked drop wrote on the parent's
    edge landed on the letters: at -3 the demo map lost five of them in both shapes."""
    mm = MindMap.demo()
    for layout in ("pyramid", "bush", "spider", "branch", "branch-left"):
        for spacing in (-5, -4, -3, 0, 3):
            assert not _defects(mm, layout, spacing), f"{layout} at {spacing}"


def test_a_straight_drop_between_bare_cells_is_a_line():
    """With no walls there is nothing to join: the one row between two bare cells is a link,
    and the cell it hangs from keeps its text."""
    mm = MindMap()
    mm.root.text = "root"
    child = mm.add_child(mm.root.id, "child")
    lay = compute(mm.root, -3, "pyramid")
    grid = build_grid(lay, mm.root.id)
    root = lay.boxes[mm.root.id]
    assert lay.boxes[child.id].y == root.bottom + 2, "one row between them"

    ch, style = grid.cells[(root.cx, root.bottom + 1)]
    assert (ch, style) == ("│", LINK_COLOR), "the drop is a link"
    assert (root.cx, root.bottom) not in grid.edges, "no wall where there is no wall to join"


def test_a_straight_drop_between_walled_cells_still_joins_them():
    """With borders the same row is a wall, and the box's own edge grows a T pointing at it."""
    mm = MindMap()
    mm.root.text = "root"
    mm.add_child(mm.root.id, "child")
    lay = compute(mm.root, -1, "pyramid")
    grid = build_grid(lay, mm.root.id)
    root = lay.boxes[mm.root.id]

    assert (root.cx, root.bottom) in grid.edges, "the wall carries the join"
    assert (root.cx, root.bottom + 1) in grid.edges, "and the row between is a wall"


def _joined(grid, layout, parent, child) -> bool:
    """Whether the drawn connectors run unbroken from one box's edge to the other's: cells
    walk from the parent's T to the child's T, and only link cells are passable, so a line
    that a wall cuts in two is two lines that do not meet."""
    down = child.flow == "down"
    start = (parent.cx, parent.bottom if down else parent.y)
    goal = (child.cx, child.y if down else child.bottom)
    seen = {start}
    queue = [start]
    while queue:
        x, y = queue.pop()
        if (x, y) == goal:
            return True
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            step = (x + dx, y + dy)
            if step in seen:
                continue
            if step != goal and step not in grid.links:
                continue
            seen.add(step)
            queue.append(step)
    return False


def _mixed_heights() -> MindMap:
    """A level where one cell is three lines tall and its cousins are one: the shape of every
    map on which a trunk used to run through the tall cell's rows."""
    mm = MindMap()
    mm.root.text = "root"
    short = mm.add_child(mm.root.id, "short")
    tall = mm.add_child(mm.root.id, "tall\ncells\nhere")
    mm.add_child(short.id, "s1")
    mm.add_child(short.id, "s2")
    mm.add_child(tall.id, "t1")
    mm.add_child(tall.id, "t2")
    return mm


def test_where_there_is_a_row_the_line_runs_all_the_way():
    """The guard on the band change: a line that exists is one line, from the parent's edge to
    the child's. At the tight spacings there is no row between the levels, so there is no line
    to be whole or broken, which is the shape those settings were chosen to have."""
    mm = _mixed_heights()
    short = mm.root.children[0]
    for layout in ("pyramid", "bush"):
        # -1 and the spacings below it keep no row between levels, so there is no line to
        # draw there in the first place: what this asks is that a line which exists is whole
        for spacing in (0, 2, 5):
            lay = compute(mm.root, spacing, layout)
            grid = build_grid(lay, mm.root.id)
            parent = lay.boxes[mm.root.id]
            assert _joined(grid, lay, parent, lay.boxes[short.id]), f"{layout} at {spacing}"


def _varied_maps(count: int) -> list[MindMap]:
    """Maps whose levels mix one-line cells with three-line ones, which is the shape that
    puts a trunk in a row a cousin owns. Fixed seed: the same maps every run."""
    import random

    words = ["a", "bb", "ccc", "dddd", "eeeee", "ffffff", "widgets", "notes", "planning", "x y z"]
    random.seed(7)
    maps = []
    for _ in range(count):
        mm = MindMap()
        mm.root.text = random.choice(words)

        def grow(node, depth):
            if depth == 0:
                return
            for _ in range(random.randint(1, 3)):
                text = "\n".join(
                    " ".join(random.choice(words) for _ in range(random.randint(1, 3)))
                    for _ in range(random.randint(1, 3))
                )
                grow(mm.add_child(node.id, text), depth - 1)

        grow(mm.root, 3)
        maps.append(mm)
    return maps


def test_no_cell_is_ever_drawn_on_a_connector():
    """A trunk drawn in the row past the parent's own box can be a row of a taller cousin's
    box, and the cousin's wall cuts the line where it stands."""
    for mm in _varied_maps(20):
        for layout in ("pyramid", "bush"):
            for spacing in (-5, -4, -3, -1, 0, 2):
                assert not _defects(mm, layout, spacing), (
                    f"{layout} at {spacing}, {mm.count()} cells"
                )


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


def _matched(layout, query: str) -> list[str]:
    """The runs a search marked, rendered with nothing selected."""
    drawn = render_text(
        build_grid(layout, "nothing-is-selected", query), 0, 0, layout.width, layout.height
    )
    return [drawn.plain[span.start : span.end] for span in drawn.spans if "reverse" in str(span.style)]


def _layout_for(text: str, child: str = "alpha one"):
    mm = MindMap(Node(text))
    mm.add_child(mm.root.id, child)
    return compute(mm.root, 0, "branch")


def test_a_found_word_is_drawn_as_a_block_in_its_own_colour():
    layout = _layout_for("root")
    drawn = render_text(
        build_grid(layout, "nothing-is-selected", "one"), 0, 0, layout.width, layout.height
    )
    marked = [span for span in drawn.spans if "reverse" in str(span.style)]

    assert [drawn.plain[span.start : span.end] for span in marked] == ["one"]
    assert "cyan" in str(marked[0].style), "the cell keeps the colour of its depth"


def test_an_empty_or_absent_query_marks_nothing():
    layout = _layout_for("root")
    for query in ("", "   ", "nothing here"):
        assert _matched(layout, query) == [], query


def test_the_search_ignores_case_and_finds_every_occurrence():
    layout = _layout_for("root", child="One ONE one")
    assert "".join(_matched(layout, "one")) == "OneONEone"


def _styled(mm: MindMap):
    """Rendered with nothing selected, so the only reverse video is the caret."""
    layout = compute(mm.root, mm.spacing)
    grid = build_grid(layout, ())
    text = render_text(grid, 0, 0, max(80, layout.width), max(12, layout.height))
    return layout, text


def _big_map() -> MindMap:
    mm = MindMap(Node("root"))
    for index in range(6):
        branch = mm.add_child(mm.root.id, f"branch {index}")
        for leaf in range(8):
            mm.add_child(branch.id, f"leaf {index}.{leaf} with some words in it")
    return mm


def test_a_window_rounds_out_to_blocks_so_a_small_pan_reuses_the_picture():
    """A caret moving one column pans the camera by one, and rebuilding a screen-sized
    picture for that is the waste this came to remove."""
    assert cache_window(10, 5, 80, 24) == cache_window(11, 5, 80, 24)

    left, top, right, bottom = cache_window(33, 17, 80, 24)
    assert left <= 33 and top <= 17, "the window covers the screen it was asked for"
    assert right >= 113 and bottom >= 41


def test_a_picture_built_for_the_window_draws_the_same_screen():
    """The camera is a window onto the map, so drawing only what it can reach may not change
    one character of what is shown."""
    mm = _big_map()
    layout = compute(mm.root, 0)
    box = layout.box(mm.root.id)
    left, top, width, height = max(0, box.cx - 40), max(0, box.cy - 12), 80, 24
    window = cache_window(left, top, width, height)

    whole = build_grid(layout, (), colours="depth")
    clipped = build_grid(layout, (), colours="depth", window=window)

    assert render_text(clipped, left, top, width, height).plain == render_text(
        whole, left, top, width, height
    ).plain
    assert len(clipped.cells) * 2 < len(whole.cells), "and it is a fraction of the drawing"


def test_the_caret_inverts_its_character_and_does_not_split_the_word():
    plain = Node("alpha")
    typed = Node("alpha")
    typed.preview, typed.caret = "alpha", 2  # between the l and the p

    settled = compute(MindMap(plain).root, 0)
    editing = compute(MindMap(typed).root, 0)
    settled_box = settled.box(plain.id)
    editing_box = editing.box(typed.id)
    assert editing_box is not None and settled_box is not None
    assert editing_box.w == settled_box.w + 1, "one reserved column, wherever the caret is"

    _, text = _styled(MindMap(typed))
    assert "alpha" in text.plain, "the word is whole"
    reversed_cells = [span for span in text.spans if "reverse" in str(span.style)]
    assert len(reversed_cells) == 1, "exactly one cell is inverted, and it is the caret"
    assert text.plain[reversed_cells[0].start] == "p", "the character under the caret"
    assert text.plain.index("alpha") > 0


def test_the_caret_at_the_end_takes_one_blank_column():
    settled = Node("alpha")
    plain = compute(MindMap(settled).root, 0)
    typed = Node("alpha")
    typed.preview, typed.caret = "alpha", 5
    editing = compute(MindMap(typed).root, 0)
    assert editing.box(typed.id).w == plain.box(settled.id).w + 1

    _, text = _styled(MindMap(typed))
    assert any("reverse" in str(span.style) for span in text.spans)


def test_the_cells_width_does_not_change_as_the_caret_moves():
    widths = []
    for caret in range(6):
        node = Node("alpha")
        node.preview, node.caret = "alpha", caret
        widths.append(compute(MindMap(node).root, 0).box(node.id).w)
    assert len(set(widths)) == 1, "moving the caret must not re-centre the map"


def test_depth_colours_a_level_and_family_colours_a_branch():
    from spoider.render import cell_colour

    # depth: same level, same colour, whoever you hang under
    assert cell_colour("depth", 2, 0) == cell_colour("depth", 2, 1)
    # family: same level, different branch, different colour
    assert cell_colour("family", 2, 0) != cell_colour("family", 2, 1)
    # family: different levels, same branch, the same colour
    assert cell_colour("family", 2, 0) == cell_colour("family", 5, 0)
    # the root and the first level read the same in both
    assert cell_colour("family", 1, 3) == cell_colour("depth", 1, 0)
    assert cell_colour("family", 0, 0) is None
    # a family never wears the colour of the first level above it
    assert cell_colour("family", 2, 0) != cell_colour("depth", 1, 0)


def test_the_grid_follows_the_colouring_the_document_asks_for():
    root = Node("root")
    left, right = Node("left"), Node("right")
    mid = Node("mid under left")
    mid.children.append(Node("deep under left"))
    left.children.append(mid)
    right.children.append(Node("shallow under right"))
    root.children.extend([left, right])
    mm = MindMap(root)

    def style_of(mode: str, text: str) -> str:
        layout = compute(mm.root, 0)
        grid = build_grid(layout, (), colours=mode)
        box = next(box for box in layout.boxes.values() if box.node.text == text)
        return grid.cells[(box.x + 2, box.y + 1)][1]

    # by depth: the two second-level cells match, whoever they hang under
    assert style_of("depth", "mid under left") == style_of("depth", "shallow under right")
    # by family: they do not — and the deeper cell joins its own branch's colour
    assert style_of("family", "mid under left") != style_of("family", "shallow under right")
    assert style_of("family", "deep under left") == style_of("family", "mid under left")
    assert style_of("family", "deep under left") != style_of("depth", "deep under left")


def _cell_grid(node: Node):
    """The picture of one cell, and its layout."""
    mm = MindMap(node)
    layout = compute(mm.root, 0)
    return layout, build_grid(layout, (), colours="depth")


def _cell_styles(node: Node, width: int = 60):
    """The grid cells of one cell's text row, as (char, style).

    The caret is not among them: it is a style applied while the window is assembled, so
    moving it costs a repaint rather than a new picture.
    """
    layout, grid = _cell_grid(node)
    box = layout.boxes[node.id]
    return [grid.cells[(x, box.y + 1)] for x in range(box.x + 1, box.right)]


def _assembled(node: Node) -> Text:
    """The window drawn from a cell's picture, caret included."""
    layout, grid = _cell_grid(node)
    return render_text(grid, 0, 0, max(60, layout.width), max(8, layout.height))


def test_the_two_caret_modes_are_drawn_differently():
    inserting, overwriting = Node("abcd"), Node("abcd")
    for node, flag in ((inserting, False), (overwriting, True)):
        node.preview, node.caret, node.overwrite = "abcd", 2, flag

    insert_styles = [str(span.style) for span in _assembled(inserting).spans]
    overwrite_styles = [str(span.style) for span in _assembled(overwriting).spans]
    caret_insert = [style for style in insert_styles if "reverse" in style]
    caret_overwrite = [style for style in overwrite_styles if "underline" in style]
    assert caret_insert, "inserting draws a filled block"
    assert caret_overwrite and "reverse" not in caret_overwrite[0], (
        "overwriting draws an underline, not another block"
    )


def test_selected_text_is_highlighted_in_the_cell():
    node = Node("alpha beta")
    node.preview, node.caret, node.sel = "alpha beta", 5, (0, 5)
    cells = _cell_styles(node)
    highlighted = "".join(ch for ch, style in cells if "reverse" in style)
    assert highlighted == "alpha", "the selection, and only it, is reversed"

    # and the caret is the blank the cell keeps after it, drawn over the picture
    layout, grid = _cell_grid(node)
    box = layout.boxes[node.id]
    assert grid.caret is not None
    assert grid.caret[:2] == (box.x + 1 + 1 + 5, box.y + 1), "the end of the selection"


def test_the_tightest_spacing_drops_the_walls_and_inverts_only_the_cursor():
    """At the bare steps a cell is its text: no box, and the cursor is the one block."""
    mm = MindMap(Node("root"))
    alpha = mm.add_child(mm.root.id, "alpha")
    beta = mm.add_child(mm.root.id, "beta")
    alpha.mark = "⭐"
    layout = compute(mm.root, -3)
    assert layout.walls is False

    drawn = build_grid(layout, alpha.id)
    text = render_text(drawn, 0, 0, layout.width, layout.height).plain
    for wall in ("╭", "╮", "│", "─┤"):
        assert wall not in text, wall

    a, b = layout.boxes[alpha.id], layout.boxes[beta.id]
    text_x = a.x + PAD + cell_len("⭐") + 1  # past the mark and its space
    here = drawn.cells[(text_x, a.y)][1]
    elsewhere = drawn.cells[(b.x + PAD, b.y)][1]
    assert "reverse" in here, "the cursor is what says where the keys are"
    assert "reverse" not in elsewhere, "and nothing else inverts"

    # the mark sits inside the inverted cell and keeps its own colours
    mark = drawn.cells[(a.x + PAD, a.y)][1]
    assert "reverse" not in mark
    assert "reverse" in here, "the text beside the mark does invert"


def _link_cells(mm: MindMap) -> int:
    """Cells drawn as connectors, with the walls off so nothing else is link grey."""
    mm.spacing = -3
    layout = compute(mm.root, mm.spacing)
    grid = build_grid(layout, mm.root.id)
    return sum(1 for _ch, style in grid.cells.values() if style == LINK_COLOR)


def test_connectors_grow_with_the_children_not_with_their_square():
    """One shared spine per parent side: n children cost about n cells, not n²/2."""
    def fan(count: int) -> int:
        mm = MindMap(Node("root"))
        for index in range(count):
            mm.add_child(mm.root.id, f"c{index}")
        return _link_cells(mm)

    ten, twenty, forty = fan(10), fan(20), fan(40)
    assert twenty < ten * 3, f"doubling the children tripled the connectors: {ten} -> {twenty}"
    assert forty < twenty * 3, f"and again: {twenty} -> {forty}"


def test_a_fan_of_children_has_one_vertical_run():
    """The spine is drawn once; the joins are the only per-child cells."""
    mm = MindMap(Node("root"))
    for index in range(6):
        mm.add_child(mm.root.id, f"c{index}")
    mm.spacing = -3
    layout = compute(mm.root, mm.spacing)
    grid = build_grid(layout, mm.root.id)
    columns: dict[int, int] = {}
    for (x, _y), (ch, style) in grid.cells.items():
        if style == LINK_COLOR and ch in "│├┤┬┴┼":
            columns[x] = columns.get(x, 0) + 1
    # a spider splits its children across two sides, so there is one spine each
    assert len(columns) == 2, f"expected one spine per side, got {sorted(columns)}"
    shortest = min(columns.values())
    assert shortest >= 3, f"a spine should span its children, got {shortest} rows"
