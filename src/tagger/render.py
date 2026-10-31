"""Turn a Layout into styled terminal cells, then crop it into rich Text."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.cells import cell_len
from rich.text import Text

from .layout import PAD, Layout, Placed, label

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

DEPTH_COLORS = ["#ffcead", "#7d82d9", "#92a593", "#e9bb4f", "#a3bfd1", "#c89dc1"]
LINK_COLOR = "#6d7db6"
SELECT_BG = "#2a3350"


@dataclass
class Grid:
    cells: dict[tuple[int, int], tuple[str, str]] = field(default_factory=dict)
    links: dict[tuple[int, int], int] = field(default_factory=dict)
    wide: set[tuple[int, int]] = field(default_factory=set)
    width: int = 0
    height: int = 0

    def put(self, x: int, y: int, ch: str, style: str) -> None:
        self.cells[(x, y)] = (ch, style)

    def put_text(self, x: int, y: int, text: str, style: str) -> None:
        for ch in text:
            width = cell_len(ch)
            self.put(x, y, ch, style)
            if width == 2:
                self.wide.add((x + 1, y))
            x += max(width, 1)

    def add_link(self, x: int, y: int, bits: int) -> None:
        self.links[(x, y)] = self.links.get((x, y), 0) | bits

    def finalize(self) -> "Grid":
        for (x, y), bits in self.links.items():
            if (x, y) in self.cells:
                continue
            ch = BOX_CHARS.get(bits)
            if ch:
                self.cells[(x, y)] = (ch, LINK_COLOR)
        return self


def build_grid(layout: Layout, selected_id: str) -> Grid:
    grid = Grid(width=layout.width, height=layout.height)
    for box in layout.boxes.values():
        colour = DEPTH_COLORS[box.depth % len(DEPTH_COLORS)]
        selected = box.node.id == selected_id
        style = f"bold {colour} on {SELECT_BG}" if selected else colour
        _draw_box(grid, box, style)
    for box in layout.boxes.values():
        if box.node.collapsed:
            continue
        for child in box.node.children:
            child_box = layout.boxes.get(child.id)
            if child_box is not None:
                _draw_link(grid, box, child_box)
    return grid.finalize()


def _draw_box(grid: Grid, box: Placed, style: str) -> None:
    inner = box.w - 2
    text = label(box.node)
    pad = " " * (inner - PAD - cell_len(text))
    grid.put_text(box.x, box.y, "╭" + "─" * inner + "╮", style)
    grid.put(box.x, box.y + 1, "│", style)
    grid.put_text(box.x + 1, box.y + 1, " " * PAD + text + pad, style)
    grid.put(box.x + box.w - 1, box.y + 1, "│", style)
    grid.put_text(box.x, box.y + 2, "╰" + "─" * inner + "╯", style)


def _draw_link(grid: Grid, parent: Placed, child: Placed) -> None:
    if child.side > 0:
        start = parent.x + parent.w
        end = child.x - 1
        mid = min(start + 2, max(start + 1, end))
    else:
        start = parent.x - 1
        end = child.x + child.w
        mid = max(start - 2, min(start - 1, end))

    points = [(start, parent.cy), (mid, parent.cy), (mid, child.cy), (end, child.cy)]
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        if y1 == y2:
            _horizontal(grid, x1, x2, y1)
        else:
            _vertical(grid, y1, y2, x1)


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
