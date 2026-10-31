"""Tree layout: assign every node a box on a character grid.

Children fan out both sides of the root (even indices right, odd left), each
subtree gets a vertical band, and a parent is centred on its children's band.
Coordinates may go negative during placement and are normalised at the end.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.cells import cell_len

from .model import Node

GAP_X = 5
GAP_Y = 1
PAD = 1
BOX_H = 3

# How far the spacing controls may push the gaps. The floors live in gaps_for()
# (2 columns between boxes, -1 rows between subtrees) and the clamp here has to
# stay in step with them: at MIN_SPACING both floors are reached.
MIN_SPACING = -3
MAX_SPACING = 12


@dataclass(frozen=True)
class Gaps:
    """Blank columns between a box and its children, and rows between subtrees."""

    x: int = GAP_X
    y: int = GAP_Y


def gaps_for(spacing: int) -> Gaps:
    """Spacing 0 is the default look; each step adds a column and a row.

    Clamped here as well as in the app, so the layout itself can never be asked
    for a setting that collapses or explodes."""
    spacing = max(MIN_SPACING, min(MAX_SPACING, spacing))
    return Gaps(
        x=max(2, GAP_X + spacing),
        # -1 lets two boxes share a border row: they touch, but each keeps its own
        # text row. Below that the text rows themselves would collide.
        y=max(-1, GAP_Y + spacing),
    )


def label(node: Node) -> str:
    if node.preview is not None:
        text = node.preview
    else:
        text = (node.text or "").strip() or "(untitled)"
        if node.children and node.collapsed:
            text = f"{text} +{len(node.children)}"
    if node.mark:
        text = f"{node.mark} {text}"
    return text


def box_width(node: Node) -> int:
    return cell_len(label(node)) + 2 * PAD + 2


def subtree_height(node: Node, gap_y: int = GAP_Y) -> int:
    if node.collapsed or not node.children:
        return BOX_H
    total = sum(subtree_height(child, gap_y) for child in node.children)
    total += gap_y * (len(node.children) - 1)
    return max(BOX_H, total)


@dataclass
class Placed:
    node: Node
    x: int
    y: int
    w: int
    h: int
    depth: int
    side: int

    @property
    def right(self) -> int:
        return self.x + self.w - 1

    @property
    def bottom(self) -> int:
        return self.y + self.h - 1

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass
class Layout:
    boxes: dict[str, Placed]
    width: int
    height: int

    def box(self, node_id: str) -> Placed | None:
        return self.boxes.get(node_id)

    def hit(self, x: int, y: int) -> str | None:
        for box in self.boxes.values():
            if box.x <= x <= box.right and box.y <= y <= box.bottom:
                return box.node.id
        return None


def compute(root: Node, spacing: int = 0) -> Layout:
    return compute_with(root, gaps_for(spacing))


def compute_with(root: Node, gaps: Gaps) -> Layout:
    boxes: dict[str, Placed] = {}
    root_width = box_width(root)
    root_box = Placed(root, -root_width // 2, -(BOX_H // 2), root_width, BOX_H, 0, 1)
    boxes[root.id] = root_box

    if root.children and not root.collapsed:
        _place_children(boxes, root_box, root.children[0::2], 1, gaps)
        _place_children(boxes, root_box, root.children[1::2], -1, gaps)

    min_x = min(box.x for box in boxes.values())
    min_y = min(box.y for box in boxes.values())
    if min_x or min_y:
        for box in boxes.values():
            box.x -= min_x
            box.y -= min_y

    width = max(box.right for box in boxes.values()) + 1
    height = max(box.bottom for box in boxes.values()) + 1
    return Layout(boxes, width, height)


def _place_children(
    boxes: dict[str, Placed],
    parent: Placed,
    children: list[Node],
    side: int,
    gaps: Gaps,
) -> None:
    if not children:
        return
    near_x = parent.x + parent.w + gaps.x if side > 0 else parent.x - gaps.x
    heights = [subtree_height(child, gaps.y) for child in children]
    total = sum(heights) + gaps.y * (len(heights) - 1)
    top = parent.cy - total // 2
    for child, height in zip(children, heights):
        _place_subtree(boxes, child, near_x, top + height // 2, side, parent.depth + 1, gaps)
        top += height + gaps.y


def _place_subtree(
    boxes: dict[str, Placed],
    node: Node,
    x: int,
    cy: int,
    side: int,
    depth: int,
    gaps: Gaps,
) -> None:
    width = box_width(node)
    left = x if side > 0 else x - width
    box = Placed(node, left, cy - BOX_H // 2, width, BOX_H, depth, side)
    boxes[node.id] = box
    if node.children and not node.collapsed:
        _place_children(boxes, box, node.children, side, gaps)
