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


def placed(node: Node, x: int, y: int, w: int = 8, h: int = 3, depth: int = 0) -> Placed:
    return Placed(node, x, y, w, h, depth, 1, RIGHT)


def layout_of(*boxes: Placed) -> Layout:
    return Layout({box.node.id: box for box in boxes}, width=80, height=40)


def _family() -> tuple[MindMap, dict[str, Node]]:
    """root -> alpha(a1, a2), beta(b1, b2), gamma(g1): three sibling groups."""
    mm = MindMap(Node("root"))
    alpha = mm.add_child(mm.root.id, "alpha")
    beta = mm.add_child(mm.root.id, "beta")
    gamma = mm.add_child(mm.root.id, "gamma")
    nodes = {"alpha": alpha, "beta": beta, "gamma": gamma}
    for parent, names in ((alpha, ("a1", "a2")), (beta, ("b1", "b2")), (gamma, ("g1",))):
        for name in names:
            nodes[name] = mm.add_child(parent.id, name)
    return mm, nodes


def _boxes(nodes: dict[str, Node]) -> Layout:
    return layout_of(
        placed(nodes["alpha"], 0, 0, depth=1),
        placed(nodes["a1"], 20, 0, depth=2),
        placed(nodes["a2"], 20, 6, depth=2),
        placed(nodes["beta"], 60, 0, depth=1),
        placed(nodes["b1"], 80, 0, depth=2),
        placed(nodes["b2"], 80, 6, depth=2),
        placed(nodes["gamma"], 120, 0, depth=1),
        placed(nodes["g1"], 140, 0, depth=2),
    )


def test_the_closest_cell_in_the_direction_wins():
    mm, nodes = _family()
    layout = _boxes(nodes)
    # from a2, right: b1 and b2 are both next door and on our level, and b2 is nearer
    assert nav.towards(mm, layout, nodes["a2"].id, +1, 0) == nodes["b2"].id


def test_our_own_level_wins_over_a_closer_cell_below_it():
    mm, nodes = _family()
    layout = layout_of(
        placed(nodes["alpha"], 0, 0, depth=1),
        placed(nodes["a2"], 20, 6, depth=2),
        placed(nodes["beta"], 60, 0, depth=1),
        placed(nodes["b1"], 80, 0, depth=2),
        placed(Node("stray"), 24, 6, depth=3),  # one step away, but a level deeper
    )
    assert nav.towards(mm, layout, nodes["a2"].id, +1, 0) == nodes["b1"].id


def test_the_branch_whose_parent_sits_beside_ours_wins_over_one_further_along():
    """Next door is measured on the parents: a cousin's parent is beside ours."""
    mm = MindMap(Node("root"))
    alpha = mm.add_child(mm.root.id, "alpha")
    beta = mm.add_child(mm.root.id, "beta")
    a1 = mm.add_child(alpha.id, "a1")
    a2 = mm.add_child(alpha.id, "a2")
    b1 = mm.add_child(beta.id, "b1")
    a1x = mm.add_child(a1.id, "a1x")
    a2x = mm.add_child(a2.id, "a2x")
    b1x = mm.add_child(b1.id, "b1x")

    layout = layout_of(
        placed(a1x, 20, 6, depth=3),
        placed(b1x, 30, 6, depth=3),   # nearer, but its parent is a different branch
        placed(a2x, 80, 6, depth=3),   # further, but a2 is a1's sibling
    )
    assert nav.towards(mm, layout, a1x.id, +1, 0) == a2x.id


def test_nothing_in_that_direction_means_no_move():
    mm, nodes = _family()
    layout = _boxes(nodes)
    assert nav.towards(mm, layout, nodes["g1"].id, +1, 0) is None


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
