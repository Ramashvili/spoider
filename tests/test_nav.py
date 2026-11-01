"""Selection movement over the tree — especially the left-hand flip."""

from __future__ import annotations

from spoider import nav
from spoider.model import MindMap


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
