from spoider.layout import (
    BOX_H,
    MAX_SPACING,
    MIN_SPACING,
    box_width,
    compute,
    label,
    subtree_height,
)
from spoider.model import MindMap
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


def test_boxes_never_overlap():
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
    assert label(node) == "✅ task"
    assert box_width(node) > plain_width  # emoji + space take cells

    layout = compute(mm.root)
    grid = build_grid(layout, mm.root.id)
    row = "".join(
        char
        for (x, y), (char, _) in sorted(grid.cells.items())
        if y == layout.box(node.id).y + 1
    )
    assert "✅" in row and "task" in row


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


def test_spacing_is_clamped_at_both_ends():
    mm = sample()
    assert compute(mm.root, -99).width == compute(mm.root, MIN_SPACING).width
    assert compute(mm.root, 99).width == compute(mm.root, MAX_SPACING).width


def test_tightest_spacing_still_never_overlaps_boxes():
    layout = compute(sample().root, MIN_SPACING)
    boxes = list(layout.boxes.values())
    for index, a in enumerate(boxes):
        for b in boxes[index + 1 :]:
            disjoint = a.right < b.x or b.right < a.x or a.bottom < b.y or b.bottom < a.y
            assert disjoint, f"{a.node.text} overlaps {b.node.text} at MIN_SPACING"


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
