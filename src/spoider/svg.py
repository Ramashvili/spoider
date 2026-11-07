"""Write a map as an SVG: the picture the renderer already drew, as a file.

Nothing here decides layout, colour or wording. `compose` takes the cells the renderer
produced, gives the cut stack a column of its own when asked, adds a caption, and moves the
origin to zero so a left branch is inside the picture rather than hanging off it. `svg` turns
that into text.
"""

from __future__ import annotations

import errno
import os
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from .files import write_atomic
from .layout import compute, compute_stack
from .model import MindMap
from .palettes import (
    PALETTES,
    Font,
    Ink,
    Palette,
    by_name,
    embedded,
    font_by_name,
    fonts,
    ink,
    is_truetype,
    metrics,
)
from .render import Grid, build_grid
from .text import cell_len

#: Cell size in multiples of the type size, used only when a face will not say. A face that
#: does say gets its own advance and line height, so the boxes and the text agree.
CELL_WIDTH = 0.6
CELL_HEIGHT = 1.4

#: The type size a picture is drawn at. Not a question worth asking: every coordinate is a
#: multiple of it, so a different size writes the same drawing with bigger numbers.
FONT_SIZE = 12.0

#: Blank cells around the picture, and between the map and the stack column. Two, so a
#: box edge is visibly inside the picture rather than a hairline from its border.
MARGIN = 5
GAP = 3


class ExportError(Exception):
    """Something about this export cannot be done, said in words a person can act on."""


@dataclass(frozen=True)
class Sheet:
    """One picture: the cells, the caption under them, and how to draw them."""

    grid: Grid
    caption: str
    palette: Palette
    font: Font

    @property
    def width(self) -> int:
        return self.grid.width

    @property
    def height(self) -> int:
        return self.grid.height


def _normalised(grid: Grid) -> Grid:
    """The same picture with its top-left cell at (0, 0).

    A layout is free to place a left branch at negative coordinates, which is right while a
    camera decides what to show and wrong for a file: everything left of zero would be cut
    off the picture instead of sitting in the margin.
    """
    points = [*grid.cells, *grid.edges, *grid.links]
    if not points:
        return grid
    left = min(x for x, _y in points)
    top = min(y for _x, y in points)
    if left == 0 and top == 0:
        return grid
    out = Grid(
        width=max(x for x, _y in points) - left + 1,
        height=max(y for _x, y in points) - top + 1,
    )
    for (x, y), value in grid.cells.items():
        out.cells[(x - left, y - top)] = value
    for (x, y), value in grid.edges.items():
        out.edges[(x - left, y - top)] = value
    for (x, y), value in grid.links.items():
        out.links[(x - left, y - top)] = value
    out.wide.update((x - left, y - top) for x, y in grid.wide)
    return out


def _paste(target: Grid, source: Grid, at_x: int, at_y: int) -> None:
    for (x, y), value in source.cells.items():
        target.cells[(at_x + x, at_y + y)] = value
    for (x, y), value in source.edges.items():
        target.edges[(at_x + x, at_y + y)] = value
    for (x, y), value in source.links.items():
        target.links[(at_x + x, at_y + y)] = value
    target.wide.update((at_x + x, at_y + y) for x, y in source.wide)


def _count(number: int, word: str) -> str:
    """`1 cut`, `2 cuts`: a caption that says "1 cuts" reads like a bug."""
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def compose(*, document: MindMap, palette: Palette, font: Font, with_stack: bool = True) -> Sheet:
    """The map, the stack beside it when asked for, and a caption counting what it holds.

    There is no cursor and no search highlight: this is a picture of the document, so what a
    person was doing when they asked for it leaves no trace in it.
    """
    layout = compute(document.root, document.spacing, document.layout)
    main = _normalised(build_grid(layout, selected=(), colours=document.colours).finalize())

    entries = list(reversed(document.cut_stack))
    panel = (
        _normalised(
            build_grid(
                compute_stack(entries, document.spacing), selected=(), colours="depth"
            ).finalize()
        )
        if with_stack and entries
        else None
    )

    width = MARGIN * 2 + main.width + (GAP + panel.width if panel is not None else 0)
    caption = _count(document.count(), "cell") + (
        f", {_count(len(entries), 'cut')}" if panel is not None else ""
    )
    picture = Grid(width=width, height=main.height + MARGIN * 3)

    _paste(picture, main, MARGIN, MARGIN)
    if panel is not None:
        _paste(picture, panel, MARGIN + main.width + GAP, MARGIN)
    picture.put_text(MARGIN, MARGIN + main.height + MARGIN, caption, "bright_black")
    picture.finalize()
    # the canvas is measured from the cells that are really there, not from the arithmetic
    # that placed them: a picture whose right edge touches a box is a picture that lost its
    # margin somewhere no one was looking
    return Sheet(grid=_framed(picture), caption=caption, palette=palette, font=font)


def _framed(grid: Grid) -> Grid:
    """The picture with `MARGIN` cells of air on all four sides, measured from its content."""
    if not grid.cells:
        return grid
    widest = max(x for x, _y in grid.cells)
    deepest = max(y for _x, y in grid.cells)
    out = Grid(width=max(grid.width, widest + 1 + MARGIN), height=max(grid.height, deepest + 1 + MARGIN))
    for (x, y), value in grid.cells.items():
        out.cells[(x, y)] = value
    for (x, y), value in grid.edges.items():
        out.edges[(x, y)] = value
    for (x, y), value in grid.links.items():
        out.links[(x, y)] = value
    out.wide.update(grid.wide)
    return out


def _runs(sheet: Sheet, row_number: int) -> list[tuple[int, str, int, Ink]]:
    """Cells on one row, joined into runs that share an ink and touch each other.

    Each run comes with the number of *cells* it covers, not the number of characters: an
    emoji is one character and two cells, and a run measured in characters would come up a
    cell short for every one of them.
    """
    row = sorted(
        (x, ch, style) for (x, y), (ch, style) in sheet.grid.cells.items() if y == row_number
    )
    runs: list[tuple[int, str, int, Ink, int]] = []
    for x, ch, style in row:
        current = ink(sheet.palette, style)
        if runs and runs[-1][3] == current and runs[-1][4] == x:
            start, text, cells, same, _end = runs[-1]
            runs[-1] = (start, text + ch, cells + cell_len(ch), same, x + cell_len(ch))
        else:
            runs.append((x, ch, cell_len(ch), current, x + cell_len(ch)))
    return [(start, text, cells, current) for start, text, cells, current, _end in runs]


def svg(sheet: Sheet) -> str:
    """The sheet as an SVG document: text where the text is, rectangles under reverse video."""
    advance, line = (
        metrics(str(sheet.font.path)) if sheet.font.path is not None else (CELL_WIDTH, CELL_HEIGHT)
    )
    cell_w = FONT_SIZE * advance
    cell_h = FONT_SIZE * line
    width = sheet.width * cell_w
    height = sheet.height * cell_h
    baseline = cell_h * 0.78

    family = sheet.font.families
    face = ""
    if sheet.font.path is not None and is_truetype(str(sheet.font.path)):
        media, payload = embedded(str(sheet.font.path))
        kind = "woff2" if media.endswith("woff2") else "truetype"
        face = (
            "<style>@font-face{font-family:'Spoider Export';"
            f"src:url(data:{media};base64,{payload}) format('{kind}')"
            "}</style>"
        )
        family = "Spoider Export, " + family

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.2f}" height="{height:.2f}" '
            f'viewBox="0 0 {width:.2f} {height:.2f}">'
        ),
        *( [face] if face else [] ),
        f'<rect width="{width:.2f}" height="{height:.2f}" fill="{sheet.palette.background}"/>',
        (
            f"<g font-family={quoteattr(family)} "
            f'font-size="{FONT_SIZE:.2f}" xml:space="preserve">'
        ),
    ]

    for row_number in sorted({y for _x, y in sheet.grid.cells}):
        for start, text, cells, current in _runs(sheet, row_number):
            if not text.strip() and not current.reverse:
                continue
            y = row_number * cell_h
            if current.reverse:
                parts.append(
                    f'<rect x="{start * cell_w:.2f}" y="{y:.2f}" '
                    f'width="{max(cells, 1) * cell_w:.2f}" height="{cell_h:.2f}" '
                    f'fill="{current.background}"/>'
                )
            foreground, _fill = current.resolved()
            decoration = ' text-decoration="underline"' if current.underline else ""
            # textLength is the cell span, counted in cells: a face with its own advance still
            # lands on the grid, and an emoji still takes the two cells it was given
            parts.append(
                f'<text x="{start * cell_w:.2f}" y="{y + baseline:.2f}" '
                f'textLength="{cells * cell_w:.2f}" lengthAdjust="spacing" '
                f'fill="{foreground}"{decoration}>{escape(text)}</text>'
            )

    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def write_svg(sheet: Sheet, path: Path, *, overwrite: bool = False) -> Path:
    """Write the sheet where asked, and never over something that is already there.

    A command that writes wherever it is pointed can write over a person's notes, their keys,
    or the map it was reading a moment ago, and the mistake is silent. The folder has to exist
    and the file has to be new, unless `overwrite` was asked for by name; the write is atomic,
    so an interrupted export leaves the old file rather than half of a new one.
    """
    if not Path(path).expanduser().parent.is_dir():
        # the atomic writer would build the road; an export writes the file and no more
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(path))
    if path.exists() and not overwrite:
        raise ExportError(f"{path} already exists; ask for it to be replaced")
    written = Path(path).expanduser()
    write_atomic(written, svg(sheet))
    return written


def export_map(
    path: Path,
    *,
    output: Path | None = None,
    overwrite: bool = False,
    palette_name: str | None = None,
    font_name: str | None = None,
    with_stack: bool = True,
) -> tuple[Path, Sheet]:
    """Read a map and write it as SVG, saying where it went.

    A named palette or typeface that is not there is an error rather than a silent fallback:
    a person who asked for one face and got another would rightly call that a bug.
    """
    try:
        document = MindMap.load(path)
    except Exception as exc:  # MapFileError and anything else the reader raises
        raise ExportError(str(exc)) from None

    palette = by_name(palette_name or "paper")
    if palette is None:
        known = ", ".join(item.name for item in PALETTES)
        raise ExportError(f"no palette called {palette_name}; there is {known}")

    # only TrueType travels: a CFF face embeds, loads and then draws nothing at all, and a
    # bitmap face cannot be scaled, so both would leave a viewer to pick a substitute
    usable = [face for face in fonts() if face.available and is_truetype(str(face.path))]
    if font_name:
        font = font_by_name(font_name)
        if font is None or not font.available:
            known = ", ".join(item.name for item in fonts())
            raise ExportError(f"no typeface called {font_name}; there is {known}")
        if font not in usable:
            known = ", ".join(face.name for face in usable) or "none on this machine"
            raise ExportError(
                f"{font.label} is not a TrueType face, so a viewer would draw nothing; "
                f"there is {known}"
            )
    else:
        if not usable:
            raise ExportError("this machine has no TrueType monospace face to draw with")
        font = usable[0]

    sheet = compose(document=document, palette=palette, font=font, with_stack=with_stack)
    target = output or path.with_suffix(".svg")
    if target.exists() and target.resolve() == Path(path).expanduser().resolve():
        raise ExportError(f"{target} is the map itself; choose another name")
    return write_svg(sheet, target, overwrite=overwrite), sheet
