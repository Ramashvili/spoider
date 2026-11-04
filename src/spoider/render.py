"""Turn a Layout into styled terminal cells, then crop it into rich Text."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
from itertools import pairwise

from rich.cells import cell_len
from rich.text import Text

from .chrome import CARET_STYLE
from .layout import (
    DOWN,
    PAD,
    RIGHT,
    UP,
    Layout,
    Placed,
    caret_pos,
    fold_note,
    lines_of,
    selection_span,
)
from .model import DEFAULT_COLOURS
from .text import clean, find_all

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
#: The cut stack is its own document, so its top cells would wear the map's plain
#: foreground. It starts further down the palette instead, on yellow, which is also the
#: colour the top bar turns when the panel is open.
STACK_START = "yellow"
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
    # No bold anywhere: a terminal fakes it by emboldening the user's own face, which
    # smears the glyphs. Emphasis here is reverse video and ANSI colour, nothing else.
    parts: list[str] = [] if colour is None else [colour]
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
    colours: str = DEFAULT_COLOURS,
    depth_shift: int = 0,
) -> Grid:
    """`selected` is one id or a whole run of them; `lead` is the one the cursor
    is on, which is only worth marking when the run is longer than one."""
    chosen = {selected} if isinstance(selected, str) else set(selected)
    grid = Grid(width=layout.width, height=layout.height)
    for box in sorted(layout.boxes.values(), key=lambda placed: (placed.y, placed.x)):
        # A cell being renamed drops its selection block: the caret is the highlight
        # there, and a reverse-on-reverse caret would be invisible.
        editing = box.node.preview is not None
        colour = cell_colour(
            colours, box.depth + depth_shift, layout.families.get(box.node.id, -1)
        )
        chosen_here = box.node.id in chosen and not editing
        frame = node_style(colour, chosen_here, lead=box.node.id == lead)
        # Selection is a block around the cell, never over its text: inverting the
        # letters fights the terminal's own colours, and an emoji mark comes out as a
        # block of reversed picture instead of a star. With the walls gone there is no
        # block left to draw, so the cursor's cell inverts and nothing else does.
        inside = node_style(colour, chosen_here if not layout.walls else False)
        _draw_box(grid, box, frame, inside, query, walls=layout.walls)
    for box in layout.boxes.values():
        if box.node.collapsed:
            continue
        for child in box.node.children:
            child_box = layout.boxes.get(child.id)
            if child_box is not None:
                _draw_link(grid, box, child_box, walls=layout.walls)
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


def _draw_box(
    grid: Grid, box: Placed, style: str, inside: str, query: str = "", walls: bool = True
) -> None:
    """Draw a box as four walls that know which way they continue.

    Nothing here picks a glyph: a corner is "right and down", a side is "up and
    down", a rule is "left and right". `Grid.finalize` turns each cell's set of
    directions into the one character that fits, so a border shared with another
    box comes out as `├` / `┤` / `┬` / `┴` rather than as two rounded corners
    fighting over the same cell.
    """
    left, right = box.x, box.x + box.w - 1
    top, bottom = box.y, box.y + box.h - 1

    if walls:
        for x in range(left + 1, right):
            grid.add_edge(x, top, L | R, style)
        grid.add_edge(left, top, R | D, style)
        grid.add_edge(right, top, L | D, style)

        for y in range(top + 1, bottom):
            grid.add_edge(left, y, U | D, style)
            grid.add_edge(right, y, U | D, style)

        for x in range(left + 1, right):
            grid.add_edge(x, bottom, L | R, style)
        grid.add_edge(left, bottom, R | U, style)
        grid.add_edge(right, bottom, L | U, style)

    inner = box.w - 2 if walls else box.w
    # the row carries its own padding, so the run starts at the first inner column
    text_x = left + 1 if walls else left
    text_y = top + 1 if walls else top
    lines = lines_of(box.node)
    for index, text in enumerate(lines):
        row = " " * PAD + text + " " * max(0, inner - PAD - cell_len(text))
        mask = _mask(row, query) or [False] * len(row)
        span = selection_span(box.node, index)
        if span is not None:
            start = PAD + span[0]
            for column in range(start, min(start + (span[1] - span[0]), len(mask))):
                mask[column] = True
        # an inverted cell keeps its mark out of the inversion: a picture has no colours
        # to swap, only colours to ruin
        mark = clean(box.node.mark) if box.node.mark else ""
        mark_chars = len(mark) + 1 if mark else 0
        plain = " ".join(part for part in inside.split() if part not in ("reverse", "underline"))
        cut = PAD + mark_chars
        if index == 0 and mark_chars and "reverse" in inside and cut < len(row):
            grid.put_text(text_x, text_y + index, row[:cut], plain, mask[:cut])
            # the row is sliced by character and placed by cell: a wide mark is one
            # character and two columns
            grid.put_text(
                text_x + cell_len(row[:cut]), text_y + index, row[cut:], inside, mask[cut:]
            )
        else:
            grid.put_text(text_x, text_y + index, row, inside, mask)
        # the folded count wears the colour of the links, so it reads as a number about
        # the structure rather than as part of the cell's own text
        note = fold_note(box.node)
        if note and index == len(lines) - 1:
            start = PAD + len(text) - len(note)
            x = text_x + cell_len(row[:start])
            for offset, char in enumerate(note):
                marked = mask[start + offset] if start + offset < len(mask) else False
                grid.put(x, top + 1 + index, char, _marked(LINK_COLOR) if marked else LINK_COLOR)
                x += cell_len(char)
    at = caret_pos(box.node)
    if at is not None:
        line, column = at
        _hang_caret(grid, text_x + PAD + column, text_y + line, inside, box.node.overwrite)


def _hang_caret(grid: Grid, x: int, y: int, style: str, overwrite: bool = False) -> None:
    """Invert the cell the renaming caret is over rather than giving it a column.

    The character stays where it is and only its colours change, so a word is never
    pushed apart by a cursor that is not part of it — nano's block, drawn the same
    way a mark or a search hit is.
    """
    ch, under = grid.cells.get((x, y), (" ", style))
    # Two cursors, two shapes: a filled block while inserting, an underline while
    # overwriting, so the mode is visible at a glance rather than by remembering.
    mark = "underline" if overwrite else CARET_STYLE
    grid.put(x, y, ch, f"{under} {mark}".strip())


def _draw_link(grid: Grid, parent: Placed, child: Placed, walls: bool = True) -> None:
    if child.flow in (DOWN, UP):
        _draw_stack_link(grid, parent, child, child.flow, walls=walls)
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
    if walls:
        grid.add_edge(leave_from, parent.cy, leaves, LINK_COLOR)
        grid.add_edge(arrive_at, child.cy, arrives, LINK_COLOR)


def _draw_stack_link(
    grid: Grid, parent: Placed, child: Placed, flow: str, walls: bool = True
) -> None:
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
        if walls:
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
    if walls:
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


def render_text(
    grid: Grid,
    ox: int,
    oy: int,
    width: int,
    height: int,
    *,
    floaters: list[tuple[list[tuple[str, list[tuple[str, str]]]], str]] | None = None,
) -> Text:
    """The visible window as styled text.

    `floaters` are `(rows, style)` boxes pinned to the top-left of the *screen*, drawn after
    the camera has cropped the grid: an overlay that lived in grid coordinates would slide
    around as the map scrolled and lose its right edge with it.
    """
    screen: list[list[tuple[str, str]]] = []
    for y in range(oy, oy + height):
        line: list[tuple[str, str]] = []
        for x in range(ox, ox + width):
            if (x, y) in grid.wide:
                continue
            line.append(grid.cells.get((x, y), (" ", "")))
        screen.append(line)
    for rows, style in floaters or []:
        paint_box(screen, rows, style)

    out = Text()
    for index, line in enumerate(screen):
        run: list[str] = []
        run_style: str | None = None
        for ch, style in line:
            if run and style != run_style:
                out.append("".join(run), run_style or "")
                run = []
            run_style = style
            run.append(ch)
        if run:
            out.append("".join(run), run_style or "")
        if index != len(screen) - 1:
            out.append("\n")
    return out


def paint_box(
    screen: list[list[tuple[str, str]]],
    sections: list[tuple[str, list[tuple[str, str]]]],
    style: str = LINK_COLOR,
) -> None:
    """Draw titled sections of `(label, value)` rows as a box at the top-left of a screen.

    A title sits alone on its line, sections are parted by one empty line, and the box is as
    wide as its longest line but never wider than the screen it is painted on.
    """
    if not sections or not screen:
        return
    body: list[str] = []
    for index, (title, rows) in enumerate(sections):
        if index:
            body.append("")
        body.append(f" {title}")
        body.extend(f"   {label.ljust(8)} {value}" for label, value in rows)

    width = max(cell_len(line) for line in body) + 2
    height = len(body) + 2

    def put(x: int, y: int, ch: str) -> None:
        if 0 <= y < len(screen) and 0 <= x < len(screen[y]):
            screen[y][x] = (ch, style)

    top = min(width - 1, (len(screen[0]) - 1) if screen[0] else 0)
    put(0, 0, "╭")
    for x in range(1, top):
        put(x, 0, "─")
    put(top, 0, "╮")
    for index, line in enumerate(body, start=1):
        if index >= len(screen) - 1:
            break
        put(0, index, "│")
        put(top, index, "│")
        # the box is opaque: cells behind it are covered, not read through
        for x in range(1, top):
            put(x, index, " ")
        column = 1
        previous: tuple[int, str] | None = None
        for char in line:
            char_width = cell_len(char)
            if char_width == 0:
                # a variation selector or a combining accent belongs to the glyph before
                # it, not to the cell after
                if previous is not None:
                    at, base = previous
                    put(at, index, base + char)
                continue
            if column + char_width > top:
                break
            previous = (column, char)
            put(column, index, char)
            # a wide glyph covers two columns of the screen; the second one contributes
            # nothing, exactly as the map's own grid handles its wide glyphs
            for extra in range(1, char_width):
                put(column + extra, index, "")
            column += char_width
    bottom = min(height - 1, len(screen) - 1)
    put(0, bottom, "╰")
    for x in range(1, top):
        put(x, bottom, "─")
    put(top, bottom, "╯")
