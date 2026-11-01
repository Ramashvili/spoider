"""Turn a Layout into styled terminal cells, then crop it into rich Text."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from itertools import pairwise

from rich.cells import cell_len
from rich.text import Text

from .chrome import CARET_STYLE
from .layout import DOWN, PAD, RIGHT, UP, Layout, Placed, caret_index, label
from .text import find_all

R, D, L, U = 1, 2, 4, 8

BOX_CHARS = {
    R | L: "─",
    U | D: "│",
    R | D: "╭",
    L | D: "╮",
    R | U: "╰",
    L | U: "╯",
    R | L | D: "┬",
    R | L | U: "┴",
    U | D | R: "├",
    U | D | L: "┤",
    R | L | U | D: "┼",
    R: "─",
    L: "─",
    U: "│",
    D: "│",
}

DEPTH_COLORS = ["cyan", "green", "yellow", "magenta", "blue", "red"]
LINK_COLOR = "bright_black"


@dataclass
class Grid:
    """Characters and, underneath them, the geometry that produced them.

    A box border is stored as the set of directions that cell connects to — the
    same bits BOX_CHARS is keyed by — not as a finished glyph. Two boxes that
    share a border row then merge the way walls really would: `╰` and `╭` in the
    same cell become `├`, instead of one box's rounded corner overwriting the
    other's and leaving a notch.
    """

    cells: dict[tuple[int, int], tuple[str, str]] = field(default_factory=dict)
    edges: dict[tuple[int, int], tuple[int, str]] = field(default_factory=dict)
    links: dict[tuple[int, int], int] = field(default_factory=dict)
    wide: set[tuple[int, int]] = field(default_factory=set)
    width: int = 0
    height: int = 0

    def put(self, x: int, y: int, ch: str, style: str) -> None:
        self.cells[(x, y)] = (ch, style)

    def put_text(
        self, x: int, y: int, text: str, style: str, mask: list[bool] | None = None
    ) -> None:
        """Draw a run; `mask` marks the characters a search found."""
        for index, ch in enumerate(text):
            width = cell_len(ch)
            found = mask is not None and index < len(mask) and mask[index]
            self.put(x, y, ch, _marked(style) if found else style)
            if width == 2:
                self.wide.add((x + 1, y))
            x += max(width, 1)

    def add_edge(self, x: int, y: int, bits: int, style: str) -> None:
        """Join this cell to its neighbours in the given directions.

        Whoever claims a cell first keeps its style, so a wall that a link later
        joins stays in the colour of the box that owns it.
        """
        current, owner = self.edges.get((x, y), (0, style))
        self.edges[(x, y)] = (current | bits, owner)

    def add_link(self, x: int, y: int, bits: int) -> None:
        self.links[(x, y)] = self.links.get((x, y), 0) | bits

    def finalize(self) -> Grid:
        # Borders first: a link never overwrites a wall it only meets.
        for (x, y), (bits, style) in self.edges.items():
            ch = BOX_CHARS.get(bits)
            if ch:
                self.cells[(x, y)] = (ch, style)
        for (x, y), bits in self.links.items():
            if (x, y) in self.cells:
                continue
            ch = BOX_CHARS.get(bits)
            if ch:
                self.cells[(x, y)] = (ch, LINK_COLOR)
        return self


def cell_colour(mode: str, depth: int, family: int) -> str | None:
    """The ANSI colour a cell wears, or None for the terminal's default foreground.

    `depth` colours a whole level alike: everything at the same depth matches.
    `family` colours a whole subtree alike: every cell under the nth first-level
    branch wears one colour, so cells of different depths in one branch agree and
    cells at the same depth in different branches do not. The root and the first
    level read the same either way, and a family is offset past the first level's
    colour so no branch wears the colour of its own parent row.
    """
    if depth == 0:
        return None
    if mode == "family" and depth >= 2 and family >= 0:
        return DEPTH_COLORS[(family + 1) % len(DEPTH_COLORS)]
    return DEPTH_COLORS[(depth - 1) % len(DEPTH_COLORS)]


def node_style(colour: str | None, selected: bool, lead: bool = False) -> str:
    """ANSI colour names only — the terminal palette decides the actual colour.

    `colour` is None for the root, which keeps the terminal's default foreground;
    selection is a reverse video block, which inverts whatever fg/bg the terminal is
    already using.
    """
    parts: list[str] = ["bold"] if colour is None else [colour]
    if selected:
        parts.append("reverse")
        if lead:
            # inside a run of selected cells the cursor needs its own mark: the
            # underline survives the inversion and does not touch the colour
            parts.append("underline")
    return " ".join(parts)


def build_grid(
    layout: Layout,
    selected: str | Collection[str],
    query: str = "",
    *,
    lead: str | None = None,
    colours: str = "depth",
) -> Grid:
    """`selected` is one id or a whole run of them; `lead` is the one the cursor
    is on, which is only worth marking when the run is longer than one."""
    chosen = {selected} if isinstance(selected, str) else set(selected)
    grid = Grid(width=layout.width, height=layout.height)
    for box in sorted(layout.boxes.values(), key=lambda placed: (placed.y, placed.x)):
        # A cell being renamed drops its selection block: the caret is the highlight
        # there, and a reverse-on-reverse caret would be invisible.
        editing = box.node.preview is not None
        colour = cell_colour(colours, box.depth, layout.families.get(box.node.id, -1))
        style = node_style(
            colour, box.node.id in chosen and not editing, lead=box.node.id == lead
        )
        _draw_box(grid, box, style, query)
    for box in layout.boxes.values():
        if box.node.collapsed:
            continue
        for child in box.node.children:
            child_box = layout.boxes.get(child.id)
            if child_box is not None:
                _draw_link(grid, box, child_box)
    return grid.finalize()


def _marked(style: str) -> str:
    """A found word is drawn as a block, like a selection.

    Inside the selected cell the two blocks cancel out: the reader still sees the
    cell they picked, and a search that found something there is reported by the
    counter instead.
    """
    return style if "reverse" in style else f"{style} reverse"


def _mask(row: str, query: str) -> list[bool] | None:
    spans = find_all(row, query)
    if not spans:
        return None
    mask = [False] * len(row)
    for start, end in spans:
        for index in range(start, min(end, len(row))):
            mask[index] = True
    return mask


def _draw_box(grid: Grid, box: Placed, style: str, query: str = "") -> None:
    """Draw a box as four walls that know which way they continue.

    Nothing here picks a glyph: a corner is "right and down", a side is "up and
    down", a rule is "left and right". `Grid.finalize` turns each cell's set of
    directions into the one character that fits, so a border shared with another
    box comes out as `├` / `┤` / `┬` / `┴` rather than as two rounded corners
    fighting over the same cell.
    """
    left, right = box.x, box.x + box.w - 1
    top, middle, bottom = box.y, box.y + 1, box.y + 2

    for x in range(left + 1, right):
        grid.add_edge(x, top, L | R, style)
    grid.add_edge(left, top, R | D, style)
    grid.add_edge(right, top, L | D, style)

    grid.add_edge(left, middle, U | D, style)
    grid.add_edge(right, middle, U | D, style)

    for x in range(left + 1, right):
        grid.add_edge(x, bottom, L | R, style)
    grid.add_edge(left, bottom, R | U, style)
    grid.add_edge(right, bottom, L | U, style)

    inner = box.w - 2
    text = label(box.node)
    row = " " * PAD + text + " " * (inner - PAD - cell_len(text))
    grid.put_text(left + 1, middle, row, style, _mask(row, query))
    at = caret_index(box.node)
    if at is not None:
        _hang_caret(grid, left + 1 + PAD + at, middle, style)


def _hang_caret(grid: Grid, x: int, y: int, style: str) -> None:
    """Invert the cell the renaming caret is over rather than giving it a column.

    The character stays where it is and only its colours change, so a word is never
    pushed apart by a cursor that is not part of it — nano's block, drawn the same
    way a mark or a search hit is.
    """
    ch, under = grid.cells.get((x, y), (" ", style))
    grid.put(x, y, ch, f"{under} {CARET_STYLE}".strip())


def _draw_link(grid: Grid, parent: Placed, child: Placed) -> None:
    if child.flow in (DOWN, UP):
        _draw_stack_link(grid, parent, child, child.flow)
        return
    if child.flow == RIGHT:
        start = parent.x + parent.w
        end = child.x - 1
        leave_from = parent.x + parent.w - 1  # the parent's right wall
        arrive_at = child.x  # the child's left wall
        leaves, arrives = R, L
        mid = min(start + 2, max(start + 1, end))
    else:
        start = parent.x - 1
        end = child.x + child.w
        leave_from = parent.x  # the parent's left wall
        arrive_at = child.x + child.w - 1  # the child's right wall
        leaves, arrives = L, R
        mid = max(start - 2, min(start - 1, end))

    points = [(start, parent.cy), (mid, parent.cy), (mid, child.cy), (end, child.cy)]
    for (x1, y1), (x2, y2) in pairwise(points):
        if y1 == y2:
            _horizontal(grid, x1, x2, y1)
        else:
            _vertical(grid, y1, y2, x1)

    # The line leaves one wall and arrives at the other, and both become a T
    # pointing at it — the same treatment the stacked shapes get. Without this
    # the connector stops a column short of the box and reads as unattached.
    grid.add_edge(leave_from, parent.cy, leaves, LINK_COLOR)
    grid.add_edge(arrive_at, child.cy, arrives, LINK_COLOR)


def _draw_stack_link(grid: Grid, parent: Placed, child: Placed, flow: str) -> None:
    """A link between two levels of a pyramid or a bush: down or up the page."""
    down = flow == DOWN
    step = 1 if down else -1
    start = parent.bottom + 1 if down else parent.y - 1
    end = child.y - 1 if down else child.bottom + 1
    parent_edge = parent.bottom if down else parent.y
    child_edge = child.y if down else child.bottom
    room = (end - start) * step

    if room < -1:
        # The two boxes share a border row; the border merge already joins them.
        return
    if room == -1:
        # Nothing between the edges: say which way the line goes on each of them.
        grid.add_edge(parent.cx, parent_edge, D if down else U, LINK_COLOR)
        grid.add_edge(child.cx, child_edge, U if down else D, LINK_COLOR)
        return

    mid = start + step * min(1, room)

    if start == end and parent.cx == child.cx:
        # One row between the edges and the centres line up: a straight drop.
        # There is no segment to draw, so the single cell has to be set by hand.
        grid.add_edge(parent.cx, start, U | D, LINK_COLOR)
        grid.add_edge(parent.cx, parent_edge, D if down else U, LINK_COLOR)
        grid.add_edge(child.cx, child_edge, U if down else D, LINK_COLOR)
        return

    points = [(parent.cx, start), (parent.cx, mid), (child.cx, mid), (child.cx, end)]
    for (x1, y1), (x2, y2) in pairwise(points):
        if y1 == y2:
            _horizontal(grid, x1, x2, y1)
        else:
            _vertical(grid, y1, y2, x1)

    # the trunk leaves the parent's edge and arrives at the child's
    grid.add_edge(parent.cx, parent_edge, D if down else U, LINK_COLOR)
    if end == mid:
        grid.add_edge(child.cx, child_edge, U if down else D, LINK_COLOR)


def _horizontal(grid: Grid, x1: int, x2: int, y: int) -> None:
    if x1 == x2:
        return
    step = 1 if x2 > x1 else -1
    for x in range(x1, x2, step):
        grid.add_link(x, y, R if step > 0 else L)
        grid.add_link(x + step, y, L if step > 0 else R)


def _vertical(grid: Grid, y1: int, y2: int, x: int) -> None:
    if y1 == y2:
        return
    step = 1 if y2 > y1 else -1
    for y in range(y1, y2, step):
        grid.add_link(x, y, D if step > 0 else U)
        grid.add_link(x, y + step, U if step > 0 else D)


def render_text(grid: Grid, ox: int, oy: int, width: int, height: int) -> Text:
    out = Text()
    rows = range(oy, oy + height)
    for index, y in enumerate(rows):
        run: list[str] = []
        run_style: str | None = None
        for x in range(ox, ox + width):
            if (x, y) in grid.wide:
                continue
            ch, style = grid.cells.get((x, y), (" ", ""))
            if run and style != run_style:
                out.append("".join(run), run_style or "")
                run = []
            run_style = style
            run.append(ch)
        if run:
            out.append("".join(run), run_style or "")
        if index != len(rows) - 1:
            out.append("\n")
    return out
