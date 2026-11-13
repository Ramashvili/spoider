"""Selection movement over the tree."""

from __future__ import annotations

from .model import MindMap, Node


def to_parent(mm: MindMap, node_id: str) -> str:
    parent = mm.parent(node_id)
    return parent.id if parent is not None else node_id


def to_child(mm: MindMap, node_id: str) -> str:
    node = mm.find(node_id)
    if node is None or not node.children:
        return node_id
    return node.children[0].id


def to_child_on_side(mm: MindMap, node_id: str, want: int) -> str:
    """First child drawn on the requested side, or the node itself if that side
    is empty. Only the root has children on both sides."""
    node = mm.find(node_id)
    if node is None or not node.children:
        return node_id
    for child in node.children:
        if side(mm, child.id) == want:
            return child.id
    return node_id


def to_sibling(mm: MindMap, node_id: str, delta: int) -> str:
    """Previous/next sibling, climbing to the parent's siblings when at an edge."""
    current = node_id
    while True:
        parent = mm.parent(current)
        if parent is None:
            return node_id
        index = [child.id for child in parent.children].index(current)
        target = index + delta
        if 0 <= target < len(parent.children):
            return parent.children[target].id
        current = parent.id


def side(mm: MindMap, node_id: str, layout: str = "spider") -> int:
    """+1 when the node hangs off the right of the root, -1 when off the left.

    Root children fill the right side first and the left side second — the same
    split the layout makes — and a whole branch stays on its side, so the branch
    owner decides for the subtree.
    The spider splits the root's children between the two sides; the branch shapes are
    single-sided, `branch-left` hanging everything off the left. The vertical shapes
    stack, so their side does not decide an arrow.
    """
    if layout == "branch-left":
        return -1
    if layout != "spider":
        return 1
    chain = mm.path(node_id)
    if len(chain) < 2:
        return 1
    owner = chain[1]
    split = (len(mm.root.children) + 1) // 2
    for index, child in enumerate(mm.root.children):
        if child.id == owner.id:
            return 1 if index < split else -1
    return 1


def is_direct_relative(mm: MindMap, here: str, there: str) -> bool:
    """True when `there` is a parent, a child, or a sibling of `here`.

    These are the moves the arrows already made before the canvas had a say, so they keep
    priority: a reader who learned that ↑ walks the siblings should not have it climb out
    of the branch because some unrelated cell happens to sit above.
    """
    if here == there:
        return False
    parent_here, parent_there = mm.parent(here), mm.parent(there)
    if parent_there is not None and parent_there.id == here:
        return True
    if parent_here is not None and parent_here.id == there:
        return True
    return parent_here is not None and parent_there is not None and parent_here.id == parent_there.id


def towards(mm: MindMap, layout, here: str, dx: int, dy: int) -> str | None:
    """The cell an arrow should reach when the hierarchy has nothing to offer.

    Closest in the direction pressed, measured between the boxes' nearest edges rather
    than between their middles: a cell is as far away as the gap you have to cross, so a
    long cell next door does not count as distant. Two preferences outrank distance: a cell
    at our own level, and among those a cell whose parent sits beside our parent. Crossing
    a gap means reaching the branch next door, not one across the map.
    """
    start = layout.boxes.get(here)
    if start is None:
        return None

    # the parents of the cells that are "next door" to us: our parent's siblings
    neighbours: set[str] = set()
    parent_here = mm.parent(here)
    grandparent = mm.parent(parent_here.id) if parent_here is not None else None
    if parent_here is not None and grandparent is not None:
        neighbours = {child.id for child in grandparent.children if child.id != parent_here.id}

    best: str | None = None
    best_key: tuple[int, int, int] | None = None
    for box in layout.boxes.values():
        if box.node.id == here:
            continue
        ahead = (box.cx - start.cx) * dx if dx else (box.cy - start.cy) * dy
        if ahead <= 0:
            continue
        # the gap to cross, not the distance between middles: a wide cell beside us is
        # close however long it is
        across_gap = max(0, max(box.x - start.right, start.x - box.right))
        down_gap = max(0, max(box.y - start.bottom, start.y - box.bottom))
        distance = across_gap + down_gap
        parent = mm.parent(box.node.id)
        beside = parent is not None and parent.id in neighbours
        same_level = box.depth == start.depth
        key = (0 if same_level else 1, 0 if beside else 1, distance)
        if best_key is None or key < best_key:
            best, best_key = box.node.id, key
    return best


def nearest(mm: MindMap, layout, here: str, dx: int, dy: int) -> str | None:
    """The cell a step reaches when it has to cross the picture rather than the tree.

    Wholly ahead, because a cell beside us that starts in our own column is not to our right of
    us. Then the closest line, measured between the boxes' bands across that way — the rows for a
    sidewise step, the columns for one up or down — so a wide cell shares a line with a narrow one
    beside it and a tall cell shares a column with a short one. Bands that touch or overlap are the
    same line. Then the shorter gap, between the boxes' nearest edges, and a cell on our own
    level of the tree breaks an exact tie.
    """
    start = layout.boxes.get(here)
    if start is None:
        return None
    best: str | None = None
    best_key: tuple[int, int, int] | None = None
    for box in layout.boxes.values():
        if box.node.id == here:
            continue
        if dx > 0:
            ahead = box.x - start.right
        elif dx < 0:
            ahead = start.x - box.right
        elif dy > 0:
            ahead = box.y - start.bottom
        else:
            ahead = start.y - box.bottom
        if ahead < 0:
            continue
        if dx:
            across = max(0, max(box.y - start.bottom, start.y - box.bottom))
        else:
            across = max(0, max(box.x - start.right, start.x - box.right))
        same_level = 0 if box.depth == start.depth else 1
        key = (across, ahead, same_level)
        if best_key is None or key < best_key:
            best, best_key = box.node.id, key
    return best


def child_towards(mm: MindMap, layout, here: str, dx: int, dy: int) -> str | None:
    """The child the canvas puts nearest in the direction pressed.

    A parent with several children is a row of them; which one you meant is a question
    about where they sit, not about the order they were made in. Distance is the gap
    between the boxes, so a wide child beside us is close, and a child level with us wins
    over one a row away. None when no child lies that way at all.
    """
    node = mm.find(here)
    start = layout.boxes.get(here)
    if node is None or start is None or not node.children:
        return None
    best: str | None = None
    best_key: tuple[int, int] | None = None
    for child in node.children:
        box = layout.boxes.get(child.id)
        if box is None:
            continue
        ahead = (box.cx - start.cx) * dx if dx else (box.cy - start.cy) * dy
        if ahead <= 0:
            continue
        across_gap = max(0, max(box.x - start.right, start.x - box.right))
        down_gap = max(0, max(box.y - start.bottom, start.y - box.bottom))
        sideways = abs(box.cy - start.cy) if dx else abs(box.cx - start.cx)
        key = (across_gap + down_gap, sideways)
        if best_key is None or key < best_key:
            best, best_key = child.id, key
    return best


def _standing_after(parent: Node, index: int) -> str:
    """Where the cursor goes when the cells at `index` and above are gone: the cell
    that slid into the gap, else the last one before it, else the parent."""
    if index < len(parent.children):
        return parent.children[index].id
    if parent.children:
        return parent.children[-1].id
    return parent.id


def tree_root(mm: MindMap, node_id: str) -> str:
    """The top of the tree this cell belongs to: the map's root, or a cut's own root."""
    current = node_id
    for _ in range(400):
        parent = mm.parent(current)
        if parent is None:
            return current
        current = parent.id
    return node_id


def to_entry(mm: MindMap, node_id: str) -> str:
    """The entry this cell belongs to: the top of the cut's own tree.

    A cut stack is one document whose root nothing draws, so the walk up stops at the entry
    rather than at that root — each entry is a tree with a main cell of its own.
    """
    node = mm.find(node_id)
    while node is not None:
        parent = mm.parent(node.id)
        if parent is None or parent.id == mm.root.id:
            return node.id
        node = parent
    return node_id


def to_home(mm: MindMap, node_id: str) -> str:
    """The main cell of the tree the cursor is in."""
    return tree_root(mm, node_id)


def to_end(mm: MindMap, node_id: str) -> str:
    """The deepest cell below this one: follow last children while the branch is open.

    Hierarchy only, like the rest of the six keys — a folded branch is where the walk
    stops, because that is as deep as the map currently shows.
    """
    node = mm.find(node_id)
    for _ in range(400):
        if node is None or not node.children or node.collapsed:
            break
        node = node.children[-1]
    return node.id if node is not None else node_id


def to_extreme_sibling(mm: MindMap, node_id: str, *, last: bool) -> str:
    """The first or last sibling under the same parent."""
    parent = mm.parent(node_id)
    if parent is None or not parent.children:
        return node_id
    return (parent.children[-1] if last else parent.children[0]).id
