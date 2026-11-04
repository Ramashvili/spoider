"""Selection movement over the tree — especially the left-hand flip."""

from __future__ import annotations

from spoider import nav
from spoider.layout import RIGHT, Layout, Placed
from spoider.model import MindMap, Node


def _map():
    """root with four branches: the first two on the right, the last two left."""
    mm = MindMap()
    branches = [mm.add_child(mm.root.id, f"b{index}") for index in range(4)]
    leaves = [mm.add_child(branch.id, f"leaf{index}") for index, branch in enumerate(branches)]
    return mm, branches, leaves


def test_the_first_half_of_the_children_is_on_the_right():
    mm, branches, _ = _map()
    # four children fill the right side first, then the left: reading down one
    # side is the same as reading down the tree
    assert [nav.side(mm, branch.id) for branch in branches] == [1, 1, -1, -1]


def test_a_whole_branch_keeps_its_side():
    mm, _branches, leaves = _map()
    assert [nav.side(mm, leaf.id) for leaf in leaves] == [1, 1, -1, -1]


def test_the_root_counts_as_the_right():
    mm, _, _ = _map()
    assert nav.side(mm, mm.root.id) == 1


def test_to_parent_of_the_root_is_the_root():
    mm, _, _ = _map()
    assert nav.to_parent(mm, mm.root.id) == mm.root.id


def test_to_child_stops_on_a_leaf():
    mm, _, leaves = _map()
    assert nav.to_child(mm, leaves[0].id) == leaves[0].id


def test_to_child_on_side_picks_the_matching_branch_and_gives_up_quietly():
    mm, branches, leaves = _map()
    assert nav.to_child_on_side(mm, mm.root.id, 1) == branches[0].id
    assert nav.to_child_on_side(mm, mm.root.id, -1) == branches[2].id
    # a node with no children has no side to offer, so it stays selected
    assert nav.to_child_on_side(mm, leaves[0].id, 1) == leaves[0].id
    empty = MindMap()
    assert nav.to_child_on_side(empty, empty.root.id, -1) == empty.root.id


def test_to_sibling_climbs_out_of_a_branch():
    mm = MindMap()
    first = mm.add_child(mm.root.id, "first")
    second = mm.add_child(mm.root.id, "second")
    leaf = mm.add_child(first.id, "leaf")

    assert nav.to_sibling(mm, first.id, +1) == second.id
    # a leaf with no sibling beside it climbs out to its parent's next sibling
    assert nav.to_sibling(mm, leaf.id, +1) == second.id
    # nothing is to the right of the last branch, and the root has no siblings
    # to climb to, so the selection stays where it was
    assert nav.to_sibling(mm, second.id, +1) == second.id


def test_to_sibling_at_the_root_stays_put():
    mm = MindMap()
    mm.add_child(mm.root.id, "only")
    assert nav.to_sibling(mm, mm.root.id, +1) == mm.root.id
    assert nav.to_sibling(mm, mm.root.id, -1) == mm.root.id


def test_unknown_ids_are_inert_everywhere():
    mm = MindMap()
    assert nav.to_parent(mm, "nope") == "nope"
    assert nav.to_child(mm, "nope") == "nope"
    assert nav.to_sibling(mm, "nope", +1) == "nope"
    assert nav.to_child_on_side(mm, "nope", 1) == "nope"
    assert nav.side(mm, "nope") == 1


def placed(node: Node, x: int, y: int, w: int = 8, h: int = 3) -> Placed:
    return Placed(node, x, y, w, h, 0, 1, RIGHT)


def layout_of(*boxes: Placed) -> Layout:
    return Layout({box.node.id: box for box in boxes}, width=80, height=40)


def test_towards_takes_the_nearest_cell_in_line():
    here, near, far = Node("here"), Node("near"), Node("far")
    layout = layout_of(placed(here, 0, 0), placed(near, 0, 10), placed(far, 0, 20))
    assert nav.towards(layout, here.id, 0, +1) == near.id


def test_a_cell_in_line_beats_a_closer_one_off_to_the_side():
    here, in_line, off_side = Node("here"), Node("in line"), Node("off side")
    layout = layout_of(
        placed(here, 0, 0),
        placed(in_line, 1, 12),      # two rows further, but the same column
        placed(off_side, 30, 4),     # nearer, but well to the right
    )
    assert nav.towards(layout, here.id, 0, +1) == in_line.id


def test_nothing_ahead_means_no_move():
    here, behind = Node("here"), Node("behind")
    layout = layout_of(placed(here, 0, 10), placed(behind, 0, 0))
    assert nav.towards(layout, here.id, 0, +1) is None


def test_the_sideways_offset_is_charged():
    here, beside, ahead = Node("here"), Node("beside"), Node("ahead")
    layout = layout_of(placed(here, 0, 0), placed(beside, 0, 8), placed(ahead, 40, 1))
    assert nav.towards(layout, here.id, 0, +1) == beside.id


def test_only_a_parent_child_or_sibling_counts_as_a_relative():
    mm = MindMap(Node("root"))
    one = mm.add_child(mm.root.id, "one")
    two = mm.add_child(mm.root.id, "two")
    child = mm.add_child(one.id, "child")
    stranger = mm.add_child(two.id, "stranger")
    assert nav.is_direct_relative(mm, one.id, child.id)
    assert nav.is_direct_relative(mm, child.id, one.id)
    assert nav.is_direct_relative(mm, one.id, two.id)
    assert not nav.is_direct_relative(mm, child.id, stranger.id), "cousins are not relatives"
    assert not nav.is_direct_relative(mm, one.id, one.id)


def test_a_closer_cell_wins_even_when_it_is_not_the_one_in_line():
    """The tie-break is a tie-break: sharing a column must not outrank distance."""
    here, near_off_axis, far_in_line = Node("here"), Node("near"), Node("far")
    layout = layout_of(
        placed(here, 10, 0),
        placed(near_off_axis, 13, 4),    # four rows down, a little to the right
        placed(far_in_line, 10, 20),     # the same column, but much further
    )
    assert nav.towards(layout, here.id, 0, +1) == near_off_axis.id
