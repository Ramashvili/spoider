"""Tree layout: assign every node a box on a character grid.

Four shapes, all of them a band-packing of the same tree:

- `spider`  — the root's children fan out both sides: the first half down the
  right, the second half down the left, so reading the map top to bottom matches
  the order in the tree; each subtree gets a band and a parent is centred on it.
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

from collections.abc import Sequence
from dataclasses import dataclass, field

from rich.cells import cell_len

from .model import DEFAULT_LAYOUT, LAYOUTS, Node
from .text import clean, clean_text

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

# How far the spacing controls may push the gaps. Two steps is all the tight end
# has room for: a third would draw exactly what the second one draws, because
# boxes already share their walls and their rows.
MIN_SPACING = -2
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
    """The gaps for a spacing setting in a given shape.

    Zero is the default look. Tightening the sideways shapes takes a column out
    each time. The stacked ones go from two columns straight to a shared wall,
    because one column between two boxes is just two walls standing apart; the
    last step then takes the blank row out from between the levels.

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
    else:
        # Both tight settings: siblings share their wall, so a row of them reads
        # as one group. What the last step tightens is the rows — at -1 the
        # levels still have a blank row between them, at -2 they touch as well.
        # A gap of one column in between would be an adjacent pair of walls,
        # which reads as a mistake rather than as either.
        x = -1
    return Gaps(
        x=x,
        # -1 lets two boxes share a border row: they touch, but each keeps its own
        # text row. Below that the text rows themselves would collide.
        y=max(-1, GAP_Y + spacing),
    )


def lines_of(node: Node) -> list[str]:
    """What the cell shows, one entry per row.

    A cell may hold several lines, so the box grows downwards with them; the mark
    rides on the first line and the folded-children count on the last.
    """
    if node.preview is not None:
        text = clean_text(node.preview)
    else:
        text = clean_text(node.text or "").strip() or "(untitled)"
        if node.children and node.collapsed:
            text = f"{text} +{len(node.children)}"
    lines = text.split("\n")
    if node.mark:
        lines[0] = f"{clean(node.mark)} {lines[0]}"
    return lines


def label(node: Node) -> str:
    """The whole cell as one string: search reads this, and so does the width."""
    return "\n".join(lines_of(node))


def selection_span(node: Node, line: int) -> tuple[int, int] | None:
    """The selected columns of display line `line`, in cells, or None.

    The mark rides on the first line, so its width shifts the columns there; the
    span itself is in buffer coordinates, which are one line shorter than the drawn
    box by the borders.
    """
    if node.preview is None or node.sel is None:
        return None
    text = clean_text(node.preview)
    rows = text.split("\n")
    if line >= len(rows):
        return None
    offset = sum(len(row) + 1 for row in rows[:line])
    end_of_line = offset + len(rows[line])
    start, end = node.sel
    low, high = max(start, offset), min(end, end_of_line)
    if low >= high:
        return None
    left = cell_len(text[offset:low])
    right = cell_len(text[offset:high])
    if node.mark and line == 0:
        shift = cell_len(clean(node.mark)) + 1
        left, right = left + shift, right + shift
    return left, right


def box_width(node: Node) -> int:
    width = max((cell_len(line) for line in lines_of(node)), default=0) + 2 * PAD + 2
    if node.preview is not None:
        width += 1  # the caret's column, kept even when it hangs over a character:
        # a box that changes width as the caret moves re-centres the whole map
    return width


def box_height(node: Node) -> int:
    """A border, the text, and a border."""
    return len(lines_of(node)) + 2


def caret_pos(node: Node) -> tuple[int, int] | None:
    """(row, column in cells) of the renaming caret, inside the box's text."""
    if node.preview is None or node.caret is None:
        return None
    buffer = clean_text(node.preview)
    caret = max(0, min(node.caret, len(buffer)))
    line = buffer.count("\n", 0, caret)
    start = buffer.rfind("\n", 0, caret) + 1
    column = cell_len(buffer[start:caret])
    if node.mark and line == 0:
        column += cell_len(clean(node.mark)) + 1
    return line, column


def subtree_height(node: Node, gap_y: int = GAP_Y) -> int:
    """How tall a subtree is when its children stack vertically (side layouts)."""
    own = box_height(node)
    if node.collapsed or not node.children:
        return own
    total = sum(subtree_height(child, gap_y) for child in node.children)
    total += gap_y * (len(node.children) - 1)
    return max(own, total)


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
    #: id -> the index of the first-level branch it hangs under (-1 for the root).
    #: The family colouring reads it; nothing else does.
    families: dict[str, int] = field(default_factory=dict)

    def box(self, node_id: str) -> Placed | None:
        return self.boxes.get(node_id)

    def hit(self, x: int, y: int) -> str | None:
        for box in self.boxes.values():
            if box.x <= x <= box.right and box.y <= y <= box.bottom:
                return box.node.id
        return None


def compute(root: Node, spacing: int = 0, layout: str = DEFAULT_LAYOUT) -> Layout:
    return compute_with(root, gaps_for(spacing, layout), layout)


def families_of(root: Node) -> dict[str, int]:
    """Which branch under the root each cell belongs to, by id.

    The root itself is -1 and every cell below a first-level child carries that
    child's index, however deep it is — that is what makes a subtree one family.
    """
    families: dict[str, int] = {root.id: -1}
    for index, child in enumerate(root.children):
        for node in child.walk():
            families[node.id] = index
    return families


def compute_with(root: Node, gaps: Gaps, layout: str = DEFAULT_LAYOUT) -> Layout:
    if layout not in LAYOUTS:
        layout = DEFAULT_LAYOUT
    boxes: dict[str, Placed] = {}

    if layout in ("pyramid", "bush"):
        flow = DOWN if layout == "pyramid" else UP
        _place_stack(boxes, root, gaps, flow)
    else:
        root_width = box_width(root)
        root_height = box_height(root)
        root_box = Placed(root, -root_width // 2, -(root_height // 2), root_width, root_height, 0, 1, RIGHT)
        boxes[root.id] = root_box
        if root.children and not root.collapsed:
            if layout == "spider":
                # First half down the right, second half down the left. Splitting
                # the list instead of alternating it keeps document order and
                # reading order the same: ↓ walks a side without hopping across
                # the root, and the jump happens once, where the sides meet.
                split = (len(root.children) + 1) // 2
                _place_children(boxes, root_box, root.children[:split], 1, gaps, RIGHT)
                _place_children(boxes, root_box, root.children[split:], -1, gaps, LEFT)
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
    return Layout(boxes, width, height, families_of(root))


def compute_stack(entries: Sequence[Node], spacing: int = 0) -> Layout:
    """The cut stack as a picture: newest at the top, one blank row between
    entries, and each entry's branch hanging to the right of it.

    Every entry is laid out on its own — with the branch shape, so its children
    read left to right — and then stacked, which is what makes the panel a list of
    bubbles rather than a tree with an invisible root.
    """
    boxes: dict[str, Placed] = {}
    families: dict[str, int] = {}
    width = 0
    height = 0
    for entry in entries:
        layer = compute(entry, spacing, "branch")
        for box in layer.boxes.values():
            boxes[box.node.id] = Placed(
                box.node, box.x, box.y + height, box.w, box.h, box.depth, 1, RIGHT
            )
        width = max(width, layer.width)
        height += layer.height + 1
        families.update(layer.families)  # each entry is a root of its own layer
    return Layout(boxes, width, max(0, height - 1), families)


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
    height = box_height(node)
    box = Placed(node, left, cy - height // 2, width, height, depth, side, flow)
    boxes[node.id] = box
    if node.children and not node.collapsed:
        _place_children(boxes, box, node.children, side, gaps, flow)


def _walk(root: Node):
    """Every node under `root`, root included, without recursion."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


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

    # A level is as tall as its tallest cell, so a cell with three lines does not
    # overlap the level below it.
    level_height: dict[int, int] = {}
    for node in _walk(root):
        depth = depths.get(node.id, 0)
        level_height[depth] = max(level_height.get(depth, 0), box_height(node))
    top_of: dict[int, int] = {}
    running = 0
    for depth in range(max(level_height, default=0) + 1):
        top_of[depth] = running
        running += level_height.get(depth, 0) + gaps.y

    centres: dict[str, int] = {root.id: 0}
    pending = [root]
    while pending:
        node = pending.pop()
        centre = centres[node.id]
        width = box_width(node)
        height = box_height(node)
        depth = depths[node.id]
        top = top_of.get(depth, 0)
        # Downwards, a level starts at its top; upwards, it ends at its bottom, so
        # the cells of one row still line up with the links that join them.
        y = top if flow == DOWN else -(top + level_height.get(depth, height))
        boxes[node.id] = Placed(node, centre - width // 2, y, width, height, depth, 1, flow)
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
