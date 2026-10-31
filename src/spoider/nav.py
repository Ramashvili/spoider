"""Selection movement over the tree."""

from __future__ import annotations

from .model import MindMap


def to_parent(mm: MindMap, node_id: str) -> str:
    parent = mm.parent(node_id)
    return parent.id if parent is not None else node_id


def to_child(mm: MindMap, node_id: str) -> str:
    node = mm.find(node_id)
    if node is None or not node.children:
        return node_id
    return node.children[0].id


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


def side(mm: MindMap, node_id: str) -> int:
    """+1 when the node hangs off the right of the root, -1 when off the left.

    Root children alternate sides by index (0 right, 1 left, 2 right, …) and a
    whole branch stays on its side, so the branch owner decides for the subtree.
    """
    chain = mm.path(node_id)
    if len(chain) < 2:
        return 1
    owner = chain[1]
    for index, child in enumerate(mm.root.children):
        if child.id == owner.id:
            return 1 if index % 2 == 0 else -1
    return 1
