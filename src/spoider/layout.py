"""Tree layout: assign every node a box on a character grid.

Four shapes, all of them a band-packing of the same tree:

- `spider`  — children fan out both sides of the root (even indices right, odd
  left); each subtree gets a vertical band and a parent is centred on it.
- `branch`  — the same, but every child hangs to the right of its parent, so the
  map reads like a table of contents down the left margin.
- `pyramid` — the root sits at the top and children stack below it.
- `bush`    — the same, upside down: the root is at the bottom and the branches
  grow upwards.

`side` is the left/right half a box lives on (only the spider uses both), and
`flow` is the direction a box's children hang in, which is what the renderer
uses to draw the link.
"""

from __future__ import annotations

from dataclasses import dataclass

from rich.cells import cell_len

from .model import DEFAULT_LAYOUT, LAYOUTS, Node
from .text import clean

#: Columns between a box and what hangs off it, and rows between siblings.
#: Sideways shapes need the columns: that is where the connector runs. Stacked
#: shapes put the siblings side by side, where a column is expensive, so they
#: start twice as close and spend the extra space on the rows instead.
GAP_X = 5
STACK_GAP_X = 2
GAP_Y = 1
PAD = 1
BOX_H = 3

#: The direction a box's children hang in.
RIGHT, LEFT, DOWN, UP = "right", "left", "down", "up"

# How far the spacing controls may push the gaps. The floors live in gaps_for()
# (2 columns between boxes, -1 rows between subtrees) and the clamp here has to
# stay in step with them: at MIN_SPACING both floors are reached.
MIN_SPACING = -3
MAX_SPACING = 12


@dataclass(frozen=True)
class Gaps:
    """Blank columns between neighbours, and blank rows between levels.

    A negative `x` means neighbours *share* a column: at the tightest settings a
    run of siblings is drawn as one wall with partitions, which is what marks
    them as siblings rather than as cells that merely happen to sit together.
    """

    x: int = GAP_X
    y: int = GAP_Y


def gaps_for(spacing: int, layout: str = DEFAULT_LAYOUT) -> Gaps:
    """Spacing 0 is the default look; each step adds a column and a row.

    Clamped here as well as in the app, so the layout itself can never be asked
    for a setting that collapses or explodes.
    """
    spacing = max(MIN_SPACING, min(MAX_SPACING, spacing))
    if layout in ("spider", "branch"):
        # a sideways shape needs a column to run a connector through, and its
        # neighbours are levels apart rather than side by side
        x = max(2, GAP_X + spacing)
    elif spacing >= 0:
        x = STACK_GAP_X + spacing
    elif spacing == -1:
        x = 1
    else:
        # the two tightest settings: siblings share their wall. An adjacent pair
        # of walls one column apart would read as a mistake, and a shared wall is
        # what draws a row of cells as one group.
        x = -1
    return Gaps(
        x=x,
        # -1 lets two boxes share a border row: they touch, but each keeps its own
        # text row. Below that the text rows themselves would collide.
        y=max(-1, GAP_Y + spacing),
    )


def label(node: Node) -> str:
    """What the cell shows. Cleaned here as well as when the file is read, so a
    text that reached the model by any other route still cannot emit an escape."""
    if node.preview is not None:
        text = clean(node.preview)
    else:
        text = clean(node.text or "").strip() or "(untitled)"
        if node.children and node.collapsed:
            text = f"{text} +{len(node.children)}"
    if node.mark:
        text = f"{clean(node.mark)} {text}"
    return text


def box_width(node: Node) -> int:
    return cell_len(label(node)) + 2 * PAD + 2


def subtree_height(node: Node, gap_y: int = GAP_Y) -> int:
    """How tall a subtree is when its children stack vertically (side layouts)."""
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
    #: +1 when the box hangs off the right of the root, -1 when off the left.
    side: int
    #: Which way this box's children hang: right/left/down/up.
    flow: str = RIGHT

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


def compute(root: Node, spacing: int = 0, layout: str = DEFAULT_LAYOUT) -> Layout:
    return compute_with(root, gaps_for(spacing, layout), layout)


def compute_with(root: Node, gaps: Gaps, layout: str = DEFAULT_LAYOUT) -> Layout:
    if layout not in LAYOUTS:
        layout = DEFAULT_LAYOUT
    boxes: dict[str, Placed] = {}

    if layout in ("pyramid", "bush"):
        flow = DOWN if layout == "pyramid" else UP
        _place_stack(boxes, root, gaps, flow)
    else:
        root_width = box_width(root)
        root_box = Placed(root, -root_width // 2, -(BOX_H // 2), root_width, BOX_H, 0, 1, RIGHT)
        boxes[root.id] = root_box
        if root.children and not root.collapsed:
            if layout == "spider":
                _place_children(boxes, root_box, root.children[0::2], 1, gaps, RIGHT)
                _place_children(boxes, root_box, root.children[1::2], -1, gaps, LEFT)
            else:  # branch: every child, at every depth, hangs to the right
                _place_children(boxes, root_box, root.children, 1, gaps, RIGHT)

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
    flow: str,
) -> None:
    if not children:
        return
    near_x = parent.x + parent.w + gaps.x if side > 0 else parent.x - gaps.x
    heights = [subtree_height(child, gaps.y) for child in children]
    total = sum(heights) + gaps.y * (len(heights) - 1)
    top = parent.cy - total // 2
    for child, height in zip(children, heights):
        _place_subtree(boxes, child, near_x, top + height // 2, side, parent.depth + 1, gaps, flow)
        top += height + gaps.y


def _place_subtree(
    boxes: dict[str, Placed],
    node: Node,
    x: int,
    cy: int,
    side: int,
    depth: int,
    gaps: Gaps,
    flow: str,
) -> None:
    width = box_width(node)
    left = x if side > 0 else x - width
    box = Placed(node, left, cy - BOX_H // 2, width, BOX_H, depth, side, flow)
    boxes[node.id] = box
    if node.children and not node.collapsed:
        _place_children(boxes, box, node.children, side, gaps, flow)


def _place_stack(boxes: dict[str, Placed], root: Node, gaps: Gaps, flow: str) -> None:
    """Place a whole pyramid (flow=down) or bush (flow=up).

    Levels are fixed rows, so only the columns have to be solved. That is done by
    `_stack_outline`, which packs each row of siblings against the *outline* of
    the subtrees already placed rather than against a reserved rectangle: a child
    with wide grandchildren no longer leaves an empty band beside its own narrow
    box. The parent ends up centred between its first and last child.
    """
    offsets: dict[str, int] = {}  # child id -> offset from its parent's centre
    depths: dict[str, int] = {}
    _stack_outline(root, 0, gaps, offsets, depths)

    step = BOX_H + gaps.y
    centres: dict[str, int] = {root.id: 0}
    pending = [root]
    while pending:
        node = pending.pop()
        centre = centres[node.id]
        width = box_width(node)
        depth = depths[node.id]
        y = depth * step if flow == DOWN else -depth * step
        boxes[node.id] = Placed(node, centre - width // 2, y, width, BOX_H, depth, 1, flow)
        for child in node.children:
            if child.id in offsets:
                centres[child.id] = centre + offsets[child.id]
                pending.append(child)


def _separation(gaps: Gaps, level: int) -> int:
    """Distance from the right edge of one subtree to the left edge of the next.

    A positive gap clears that many blank columns; a negative one overlaps, which
    is the shared wall. At the sibling's own level the setting stands as it is.
    Below it a column is always kept, because those cells have different parents
    — two cousins must never merge the way two siblings do.
    """
    if gaps.x < 0 and level:
        return 2  # one blank column: enough to read as two walls, not one
    return gaps.x + 1


def _stack_outline(
    node: Node,
    depth: int,
    gaps: Gaps,
    offsets: dict[str, int],
    depths: dict[str, int],
) -> dict[int, tuple[int, int]]:
    """Pack a subtree with its own centre at column 0; return its outline.

    The outline maps a level to the leftmost and rightmost column the subtree
    reaches there, measured from the node's centre. Siblings are separated by the
    minimum shift that keeps those outlines `gaps.x` apart at every level, which
    is what removes the wasted band a rectangle packer leaves behind.

    `offsets` collects each child's column relative to its parent's centre.
    """
    width = box_width(node)
    half = width // 2
    depths[node.id] = depth
    own = (-half, width - 1 - half)

    if node.collapsed or not node.children:
        return {0: own}

    placed: dict[int, tuple[int, int]] = {}  # level -> extent of children so far
    columns: list[int] = []
    for index, child in enumerate(node.children):
        outline = _stack_outline(child, depth + 1, gaps, offsets, depths)
        shift = 0
        if index:
            for level, (left, _right) in outline.items():
                reached = placed.get(level)
                if reached is not None:
                    # both extents are cell columns, so clearing by a gap means
                    # starting one past it; a negative gap is deliberate overlap
                    shift = max(shift, reached[1] + _separation(gaps, level) - left)
        columns.append(shift)
        for level, (left, right) in outline.items():
            moved = (left + shift, right + shift)
            reached = placed.get(level)
            placed[level] = moved if reached is None else (
                min(reached[0], moved[0]),
                max(reached[1], moved[1]),
            )

    middle = (columns[0] + columns[-1]) // 2
    for child, column in zip(node.children, columns):
        offsets[child.id] = column - middle

    outline = {0: own}
    for level, (left, right) in placed.items():
        outline[level + 1] = (left - middle, right - middle)
    return outline
