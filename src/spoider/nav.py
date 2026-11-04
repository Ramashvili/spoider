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
    Only the spider has a left-hand side; every other shape hangs its children
    to the right (or below), so everything counts as +1.
    """
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


def towards(layout, here: str, dx: int, dy: int) -> str | None:
    """The nearest cell in a screen direction, or None when that way is empty.

    Nearest wins, and the sideways offset is charged three times so a slightly further
    cell in line is chosen over a closer one well off to the side. Cells that overlap the
    current one across the other axis come first, which is what makes a column of boxes
    read as a column.
    """
    start = layout.boxes.get(here)
    if start is None:
        return None
    best: str | None = None
    best_key: tuple[int, float] | None = None
    for box in layout.boxes.values():
        if box.node.id == here:
            continue
        if dx:
            ahead = (box.cx - start.cx) * dx
            across = abs(box.cy - start.cy)
            overlaps = box.y < start.y + start.h and start.y < box.y + box.h
        else:
            ahead = (box.cy - start.cy) * dy
            across = abs(box.cx - start.cx)
            overlaps = box.x < start.x + start.w and start.x < box.x + box.w
        if ahead <= 0:
            continue
        key = (0 if overlaps else 1, ahead + 3 * across)
        if best_key is None or key < best_key:
            best, best_key = box.node.id, key
    return best


def _standing_after(parent: Node, index: int) -> str:
    """Where the cursor goes when the cells at `index` and above are gone: the cell
    that slid into the gap, else the last one before it, else the parent."""
    if index < len(parent.children):
        return parent.children[index].id
    if parent.children:
        return parent.children[-1].id
    return parent.id
