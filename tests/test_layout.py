from spoider.layout import (
    BOX_H,
    MAX_SPACING,
    MIN_SPACING,
    box_width,
    compute,
    gaps_for,
    label,
    subtree_height,
)
from spoider.model import LAYOUTS, MindMap, Node
from spoider.render import build_grid


def sample() -> MindMap:
    mm = MindMap()
    mm.root.text = "root"
    for index in range(4):
        child = mm.add_child(mm.root.id, f"child {index}")
        for leaf in range(2):
            mm.add_child(child.id, f"leaf {index}.{leaf}")
    return mm


def test_every_node_is_placed():
    mm = sample()
    layout = compute(mm.root)
    assert set(layout.boxes) == {node.id for node in mm.nodes()}


def test_boxes_never_overlap_at_default_spacing():
    layout = compute(sample().root)
    boxes = list(layout.boxes.values())
    for index, a in enumerate(boxes):
        for b in boxes[index + 1 :]:
            disjoint = a.right < b.x or b.right < a.x or a.bottom < b.y or b.bottom < a.y
            assert disjoint, f"{a.node.text} overlaps {b.node.text}"


def test_root_children_sit_on_both_sides():
    mm = sample()
    layout = compute(mm.root)
    sides = {layout.boxes[child.id].side for child in mm.root.children}
    assert sides == {1, -1}


def test_children_are_outside_the_parent_box():
    mm = sample()
    layout = compute(mm.root)
    for node in mm.nodes():
        parent_box = layout.boxes[node.id]
        for child in node.children:
            child_box = layout.boxes[child.id]
            # Children of the root alternate sides, so each child carries its own.
            if child_box.side > 0:
                assert child_box.x > parent_box.right
            else:
                assert child_box.right < parent_box.x


def test_collapsed_branch_hides_its_subtree():
    mm = sample()
    branch = mm.root.children[0]
    branch.collapsed = True

    layout = compute(mm.root)
    assert branch.id in layout.boxes
    assert all(child.id not in layout.boxes for child in branch.children)
    assert box_width(branch) > len(branch.text) + 2  # "+N" marker widens the box


def test_subtree_height_brackets_children():
    mm = sample()
    branch = mm.root.children[0]
    assert subtree_height(branch) >= sum(subtree_height(c) for c in branch.children)
    assert subtree_height(mm.root.children[0]) == 2 * BOX_H + 1


def test_hit_test_finds_the_root():
    mm = sample()
    layout = compute(mm.root)
    root_box = layout.boxes[mm.root.id]
    assert layout.hit(root_box.cx, root_box.cy) == mm.root.id
    assert layout.hit(-50, -50) is None


def test_mark_prefixes_the_label_and_widens_the_box():
    mm = MindMap()
    node = mm.add_child(mm.root.id, "task")
    plain_width = box_width(node)

    mm.cycle_mark(node.id)
    assert label(node) == "⭐ task"  # the first mark of the palette
    assert box_width(node) > plain_width  # emoji + space take cells

    layout = compute(mm.root)
    grid = build_grid(layout, mm.root.id)
    row = "".join(
        char
        for (x, y), (char, _) in sorted(grid.cells.items())
        if y == layout.box(node.id).y + 1
    )
    assert "⭐" in row and "task" in row


def test_grid_draws_boxes_and_links():
    mm = sample()
    layout = compute(mm.root)
    grid = build_grid(layout, mm.root.id)
    chars = {char for char, _ in grid.cells.values()}
    assert {"╭", "╯", "─", "│"} <= chars
    assert grid.width == layout.width and grid.height == layout.height


def test_spacing_widens_then_tightens_the_grid():
    mm = sample()
    tight = compute(mm.root, -2)
    base = compute(mm.root, 0)
    loose = compute(mm.root, 6)

    assert tight.width < base.width < loose.width
    assert tight.height < base.height < loose.height


def test_spacing_is_document_state():
    from spoider.model import MindMap

    mm = sample()
    mm.spacing = 4
    clone = MindMap.from_dict(mm.to_dict())
    assert clone.spacing == 4
    assert MindMap.from_dict({"root": {}}).spacing == 0  # older files
    assert MindMap.from_dict({"spacing": "junk", "root": {}}).spacing == 0


def test_spacing_is_clamped_at_both_ends():
    mm = sample()
    assert compute(mm.root, -99).width == compute(mm.root, MIN_SPACING).width
    assert compute(mm.root, 99).width == compute(mm.root, MAX_SPACING).width


def test_the_second_tightest_spacing_shares_a_border_but_never_a_text_row():
    layout = compute(sample().root, MIN_SPACING + 1)
    boxes = list(layout.boxes.values())
    for index, a in enumerate(boxes):
        for b in boxes[index + 1 :]:
            same_columns = not (a.right < b.x or b.right < a.x)
            if same_columns:
                # sharing the border row is the point; sharing the text row is not
                assert a.cy != b.cy, f"{a.node.text} and {b.node.text} share a text row"


def test_the_tightest_spacing_has_no_walls_at_all():
    """At the floor a cell is its text, so there is no box to share or to draw."""
    layout = compute(sample().root, MIN_SPACING)
    assert layout.walls is False
    heights = {box.h for box in layout.boxes.values()}
    assert heights == {1}, "each cell is one row: its text"


def test_the_vertical_gap_bottoms_out_with_a_row_of_its_own():
    from spoider.layout import GAP_Y, gaps_for

    assert gaps_for(0).y == GAP_Y
    assert gaps_for(-1).y == 0, "touching: no blank row between the levels"
    # at the floor a cell is one row of text, so it cannot share a row with a
    # neighbour the way two border rows used to
    assert gaps_for(MIN_SPACING).y == 0
    assert gaps_for(-99).y == 0, "and no further"


def test_stacked_shapes_keep_their_siblings_closer_together():
    from spoider.layout import GAP_X, STACK_GAP_X

    assert GAP_X > STACK_GAP_X, "sideways shapes need the columns for a connector"
    # the spider spends columns between a box and its children; a pyramid or a
    # bush spends them between siblings standing side by side, so it starts close
    assert gaps_for(0, "spider").x == GAP_X
    assert gaps_for(0, "branch").x == GAP_X
    assert gaps_for(0, "pyramid").x == STACK_GAP_X
    assert gaps_for(0, "bush").x == STACK_GAP_X


def test_stacked_shapes_step_down_to_a_shared_wall():
    assert gaps_for(0, "pyramid").x == 2
    # both tight settings share the wall between siblings; the last one also
    # takes the blank row out from between the levels
    assert gaps_for(MIN_SPACING + 1, "pyramid").x == -1
    assert gaps_for(MIN_SPACING, "pyramid").x == -1
    assert gaps_for(MIN_SPACING, "pyramid").y == 0
    assert gaps_for(MIN_SPACING + 1, "pyramid").y == 0
    assert gaps_for(-99, "pyramid").x == -1  # clamped, not further
    # a sideways shape keeps its columns: the connector needs the room
    from spoider.layout import GAP_X

    assert gaps_for(-99, "spider").x == GAP_X + MIN_SPACING


def test_every_tightening_step_looks_different():
    # the complaint that started this: two settings that draw the same thing
    mm, _alpha, _beta, _a1, _a2 = _shaped()
    seen = {
        spacing: (layout.width, layout.height)
        for spacing in range(MIN_SPACING, 1)
        if (layout := compute(mm.root, spacing, "pyramid"))
    }
    assert len(set(seen.values())) == len(seen), f"two settings draw alike: {seen}"


def test_siblings_share_a_wall_at_both_tight_settings():
    for spacing in (MIN_SPACING + 1, MIN_SPACING):
        mm, alpha, beta, _a1, _a2 = _shaped()
        layout = compute(mm.root, spacing, "pyramid")
        assert layout.boxes[alpha.id].right == layout.boxes[beta.id].x


def test_cousins_never_share_a_wall():
    mm = MindMap()
    alpha = mm.add_child(mm.root.id, "alpha")
    a1 = mm.add_child(alpha.id, "a1")
    beta = mm.add_child(mm.root.id, "beta")
    b1 = mm.add_child(beta.id, "b1")

    layout = compute(mm.root, -2, "pyramid")
    boxes = layout.boxes
    left, right = sorted((boxes[a1.id], boxes[b1.id]), key=lambda box: box.x)
    assert right.x > left.right, "two cousins must not read as one group"


def test_siblings_do_not_share_a_wall_when_there_is_room():
    mm, alpha, beta, _a1, _a2 = _shaped()
    layout = compute(mm.root, 0, "pyramid")
    assert layout.boxes[beta.id].x > layout.boxes[alpha.id].right


def test_the_stacked_gap_is_what_makes_a_pyramid_narrow():
    from spoider.layout import GAP_X, STACK_GAP_X, Gaps, compute_with

    mm = MindMap(Node("root"))
    for name in ("one", "two", "three", "four"):
        mm.add_child(mm.root.id, name)
    tight = compute(mm.root, 0, "pyramid").width
    wide = compute_with(mm.root, Gaps(x=GAP_X, y=1), "pyramid").width
    # four siblings in a row: three gaps, each three columns wider sideways
    assert wide - tight == 3 * (GAP_X - STACK_GAP_X)


def test_tight_layout_flattens_two_rules_into_one():
    mm = MindMap()
    branch = mm.add_child(mm.root.id, "branch")
    mm.add_child(branch.id, "a much longer name than the one below it")
    mm.add_child(branch.id, "b")

    grid = build_grid(compute(mm.root, MIN_SPACING), mm.root.id)
    layout = compute(mm.root, MIN_SPACING)
    for y in range(layout.height):
        row = "".join(grid.cells.get((x, y), (" ", ""))[0] for x in range(layout.width))
        assert "╰╭" not in row, row
        assert "╮╯" not in row, row


def test_comfy_layout_keeps_every_corner():
    layout = compute(sample().root, 0)
    grid = build_grid(layout, "")
    for box in layout.boxes.values():
        top = "".join(
            grid.cells.get((x, box.y), (" ", ""))[0] for x in range(box.x, box.right + 1)
        )
        bottom = "".join(
            grid.cells.get((x, box.bottom), (" ", ""))[0] for x in range(box.x, box.right + 1)
        )
        assert top == "╭" + "─" * (box.w - 2) + "╮", box.node.text
        assert bottom == "╰" + "─" * (box.w - 2) + "╯", box.node.text


def test_styles_are_ansi_named_never_truecolour():
    mm = sample()
    layout = compute(mm.root)
    grid = build_grid(layout, mm.root.children[0].id)
    for _, style in grid.cells.values():
        assert "#" not in style, f"hardcoded colour in style: {style!r}"


def test_selection_uses_reverse_video():
    mm = sample()
    root_id = mm.root.id
    grid = build_grid(compute(mm.root), root_id)
    styles = {style for _, style in grid.cells.values()}
    assert any("reverse" in style for style in styles)
    assert all("reverse" not in style for style in styles if "cyan" in style)


# -- the four shapes ------------------------------------------------------


def _shaped():
    mm = MindMap()
    alpha = mm.add_child(mm.root.id, "alpha")
    a1 = mm.add_child(alpha.id, "a1")
    a2 = mm.add_child(alpha.id, "a2")
    beta = mm.add_child(mm.root.id, "beta")
    return mm, alpha, beta, a1, a2


def test_pyramid_puts_the_root_on_top_and_its_children_below():
    mm, alpha, beta, a1, _a2 = _shaped()
    layout = compute(mm.root, 0, "pyramid")
    root = layout.boxes[mm.root.id]
    first = layout.boxes[alpha.id]
    second = layout.boxes[beta.id]

    assert root.y == 0
    assert first.y == second.y == root.bottom + gaps_for(0).y + 1
    assert first.x < second.x  # siblings sit side by side, in tree order
    assert layout.boxes[a1.id].y > first.y  # grandchildren are placed too


def test_pyramid_centres_a_parent_between_its_first_and_last_child():
    mm, alpha, beta, _a1, _a2 = _shaped()
    layout = compute(mm.root, 0, "pyramid")
    root = layout.boxes[mm.root.id]
    first = layout.boxes[alpha.id]
    last = layout.boxes[beta.id]
    assert abs(root.cx - (first.cx + last.cx) // 2) <= 1


def test_bush_is_the_pyramid_upside_down():
    mm, _, _, a1, _ = _shaped()
    pyramid = compute(mm.root, 0, "pyramid")
    bush = compute(mm.root, 0, "bush")

    assert (bush.width, bush.height) == (pyramid.width, pyramid.height)
    for node_id, box in pyramid.boxes.items():
        twin = bush.boxes[node_id]
        assert twin.x == box.x
        assert twin.y == pyramid.height - box.y - BOX_H
    assert bush.boxes[mm.root.id].y > bush.boxes[a1.id].y  # root at the bottom


def test_branch_hangs_every_child_to_the_right_of_its_parent():
    mm, _alpha, _beta, _a1, _a2 = _shaped()
    layout = compute(mm.root, 0, "branch")
    for node in mm.nodes():
        parent = mm.parent(node.id)
        if parent is None:
            continue
        assert layout.boxes[node.id].x > layout.boxes[parent.id].right


def test_spider_keeps_both_sides():
    mm, alpha, beta, _a1, _a2 = _shaped()
    layout = compute(mm.root, 0, "spider")
    root = layout.boxes[mm.root.id]
    assert layout.boxes[alpha.id].x > root.right
    assert layout.boxes[beta.id].right < root.x


def test_no_two_boxes_overlap_in_any_shape():
    mm, _, _, _a1, _ = _shaped()
    for name in LAYOUTS:
        layout = compute(mm.root, 0, name)
        boxes = list(layout.boxes.values())
        for index, one in enumerate(boxes):
            for other in boxes[index + 1 :]:
                overlap = (
                    one.x <= other.right
                    and other.x <= one.right
                    and one.y <= other.bottom
                    and other.y <= one.bottom
                )
                assert not overlap, f"{name}: {one.node.text} overlaps {other.node.text}"


def test_spacing_still_tightens_every_shape():
    mm, _, _, _a1, _ = _shaped()
    for name in LAYOUTS:
        tight = compute(mm.root, -3, name)
        loose = compute(mm.root, 6, name)
        assert tight.width <= loose.width and tight.height < loose.height, name


def test_an_unknown_shape_falls_back_to_the_spider():
    mm, _, _, _a1, _ = _shaped()
    assert compute(mm.root, 0, "hexagon").boxes.keys() == compute(mm.root, 0, "spider").boxes.keys()


def test_the_spider_fills_the_right_side_before_the_left():
    mm = MindMap()
    cells = [mm.add_child(mm.root.id, f"c{index}") for index in range(5)]

    layout = compute(mm.root, 0, "spider")

    sides = [layout.boxes[cell.id].side for cell in cells]
    assert sides == [1, 1, 1, -1, -1], "three down the right, two down the left"
    for side in (1, -1):
        ys = [layout.boxes[cell.id].y for cell in cells if layout.boxes[cell.id].side == side]
        assert ys == sorted(ys), "each side reads top to bottom in tree order"
