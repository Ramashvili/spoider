"""The canvas widget: lays out, draws, and hit-tests the mind map."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.geometry import Region
from textual.strip import Strip
from textual.widget import Widget

from .chrome import DIVIDER
from .layout import BOX_H, PAD, Layout, caret_pos, compute
from .properties import sections
from .render import (
    DEPTH_COLORS,
    LINK_COLOR,
    STACK_START,
    Grid,
    build_grid,
    cache_window,
    caret_cell,
    caret_style,
    paint_box,
    strip_of,
)
from .text import clean, clip_head

if TYPE_CHECKING:
    from .app import SpoiderApp


#: The counts are plain text in the terminal's own colours. Reverse belongs to one
#: thing at a time — the place the keys are — and the top line is not a place, it is
#: what the map contains. A single space between the numbers keeps them as items.
STAT_STYLE = ""

#: The stack count turns yellow while the panel is open. One item changing colour
#: says which one is live; changing all of them says nothing.
STAT_ACTIVE_STYLE = "black on yellow"

#: The air between two counts. They are separate items, not a sentence, and at one
#: column they read as one long string of numbers.
GAP = "  "


def compose_top_bar(
    width: int,
    version: str,
    where: str,
    stat: str,
    dirty: bool = False,
    extra: str = "",
    extra_active: bool = False,
) -> Text:
    """One line: name+version left, location centred, statistics right.

    `stat` is whatever the app wants counted — cells, or the matches of a search —
    and `extra` rides beside it (the cuts waiting on the stack). They degrade in
    stages as the terminal narrows: the cuts, then the centre, then the location is
    truncated from the left (a path's tail is the useful half), then the name. The
    unsaved marker rides on the location, because a window title is not something
    everyone can see — tiling window managers have no title bar at all.
    """
    name = f"spoider {version}"
    if width <= 0:
        return Text("")

    def fits(candidate: str) -> bool:
        return width >= cell_len(candidate) + 6  # the name, and a gap either side

    segments: list[tuple[str, str]] = [(stat, STAT_STYLE)]
    joined = stat
    if extra:
        candidate = f"{joined}{GAP}{extra}"
        if fits(candidate):
            style = STAT_ACTIVE_STYLE if extra_active else STAT_STYLE
            segments.append((extra, style))
            joined = candidate
    right_width = cell_len(joined)
    if width < right_width + 2:
        return Text(clip_head(joined, width), style=STAT_STYLE)

    where = clean(f"{where} *") if dirty else clean(where)
    name = clip_head(name, width - right_width - 1)

    # One blank column separates the name from the centre band, and the band from
    # the statistics, so the line always fills exactly `width` cells.
    band = width - cell_len(name) - right_width - 2
    middle = ""
    if band >= 6:
        middle = where if cell_len(where) <= band else "…" + where[-(band - 1) :]

    bar = Text(name)
    if middle:
        pad = (band - cell_len(middle)) // 2
        bar.append(" " * (1 + pad))
        bar.append(middle)
        bar.append(" " * (band - pad - cell_len(middle) + 1))
    else:
        bar.append(" " * (width - cell_len(name) - right_width))
    for index, (text, style) in enumerate(segments):
        if index:
            bar.append(GAP)  # each count is its own item
        bar.append(text, style=style)
    return bar


def name_bar(width: int, version: str) -> Text:
    """The name and the version alone, for the one state where nothing else is true.

    A file that could not be read has no path worth showing, no cell count and no shape
    drawn. The version is the only fact a reader may need from that screen, and it is the
    first thing anyone reporting the problem is asked for.
    """
    if width <= 0:
        return Text("")
    name = clip_head(f"spoider {version}", width)
    return Text(name + " " * max(0, width - cell_len(name)))


#: What the stack column calls itself, at the top of the wall.
STACK_TITLE = "LIFO cut/paste stack"


def stack_column(panel: Layout | None, width: int) -> int:
    """How many columns the stack takes: its own width, never more than half the
    screen, and never so narrow that the title does not fit."""
    if panel is None:
        return 0
    wanted = max(panel.width + 3, len(STACK_TITLE) + 3)
    return min(wanted, max(1, width // 2))


class TopBar(Widget):
    """Chrome above the map: identity, location, size."""

    def render(self) -> Text:
        from . import __version__

        app = cast("SpoiderApp", self.app)
        height = self.size.width
        if height <= 0:
            return Text("")
        if app.load_error is not None:
            return name_bar(height, __version__)
        # The name, not the file: `spoider new.spoider` names where the first ^S goes, and
        # a file deleted mid-session is still where the next ^S goes. "New Buffer" is left
        # for a buffer with no name at all, which includes one whose file would not load.
        where = str(app.path) if app.path is not None else "New Buffer"
        return compose_top_bar(
            height,
            __version__,
            where,
            app.stat_text(),
            app.dirty,
            extra=app.cut_stat(),
            extra_active=app.stack_open,
        )


class MindMapView(Widget, can_focus=True):
    """A camera over the map, drawn a line at a time.

    A key changes a few rows of the screen: the cell being typed into, the cell that lost the
    cursor, the rows a cell has pushed aside. So the view is asked for a line and draws that line,
    and marks only the rows that changed: Textual keeps the lines it already holds, and a keystroke
    costs the lines it touches instead of the window. Painting is where the time went -- a
    screen-sized widget repainted for one changed cell measured 49 ms against 1 ms for the cell
    itself -- and this is the shape that follows from the measurement.
    """

    def __init__(self, spoider: SpoiderApp) -> None:
        super().__init__()
        self.spoider = spoider
        self._layout: Layout | None = None
        #: What the field, the camera and the caret were worked out for: rows are drawn against
        #: what is settled here, so two rows of one frame cannot disagree about the camera.
        self._settled_for: tuple | None = None
        self._offset_x = 0
        self._offset_y = 0
        self._field = 0
        #: The caret's place in the grid, when a cell is being typed into.
        self._caret: tuple[int, int, bool] | None = None
        #: Every row of the window, drawn once for the frame this was drawn for.
        self._rows: list[list[tuple[str, str]]] | None = None
        self._rows_for: tuple | None = None

    # -- what the app says changed ------------------------------------
    def refresh_map(self) -> None:
        """A change of shape or structure: the arrangement is done again.

        The map is drawn once for the window and its rows are cut from that, and only the rows
        that actually moved are handed back to Textual: a letter that grows a cell moves the
        cells below and beside it, not the whole screen.
        """
        previous = self._layout
        camera = (self._offset_x, self._offset_y)
        self._layout = None
        self._forget()
        self._settle()
        if camera != (self._offset_x, self._offset_y) or previous is None:
            self.refresh()
            return
        self._mark(self._moved_rows(previous, self.layout_))

    def refresh_picture(self) -> None:
        """A cell says something else at the size it had: only its own rows are new."""
        self._forget()
        self._touch([self.spoider.selected])

    def refresh_selection(self, was: str | None) -> None:
        """The cursor moved: the two cells it left and reached changed colour, nothing else."""
        self._forget()
        self._touch([node for node in (was, self.spoider.selected) if node])

    def refresh_caret(self) -> None:
        """Only the caret moved: the row it left and the row it reached, and no picture rebuilt."""
        before = self._caret
        # the rows of the frame are drawn without the caret, so only its place is worked out again
        self._caret = self._caret_here(self.layout_)
        rows = {
            row
            for row in (self._row_on_screen(before), self._row_on_screen(self._caret))
            if row is not None
        }
        self._mark(rows)

    def _forget(self) -> None:
        """Everything worked out for the last frame is out of date."""
        self._settled_for = None
        self._rows = None
        self._rows_for = None

    def _moved_rows(self, before: Layout, after: Layout) -> set[int]:
        """The screen rows whose glyphs changed: the cells that moved, and the places they left."""
        rows: set[int] = set()
        for node_id, box in after.boxes.items():
            old = before.boxes.get(node_id)
            if old is not None and (old.x, old.y, old.w, old.h) == (box.x, box.y, box.w, box.h):
                continue
            rows.update(range(box.y, box.y + box.h))
            if old is not None:
                rows.update(range(old.y, old.y + old.h))
        for node_id, old in before.boxes.items():
            if node_id not in after.boxes:
                rows.update(range(old.y, old.y + old.h))
        on_screen = {row - self._offset_y for row in rows}
        return {row for row in on_screen if 0 <= row < self.size.height}

    def _touch(self, ids: list[str]) -> None:
        """Mark the rows of these cells dirty, and only those."""
        self._settle()
        rows: set[int] = set()
        for node_id in ids:
            box = self.layout_.box(node_id)
            if box is None:
                continue
            for row in range(box.y, box.y + box.h):
                on_screen = self._row_on_screen((box.x, row, False))
                if on_screen is not None:
                    rows.add(on_screen)
        self._mark(rows)

    def _row_on_screen(self, cell: tuple[int, int, bool] | None) -> int | None:
        if cell is None:
            return None
        row = cell[1] - self._offset_y
        return row if 0 <= row < self.size.height else None

    def _mark(self, rows: set[int]) -> None:
        """Ask Textual for these rows again, and for nothing else."""
        if not rows:
            return
        width = self.size.width or 1
        self.refresh(*(Region(0, row, width, 1) for row in sorted(rows)))

    @property
    def layout_(self) -> Layout:
        if self._layout is None:
            mm = self.spoider.mm
            self._layout = compute(mm.root, mm.spacing, mm.layout)
        return self._layout

    def caret_row(self, layout, focus) -> int | None:
        """The layout row the caret sits on inside a cell being typed into.

        A cell can be taller than the screen. Centring on the box would leave the
        caret below the fold while the reader types, so while editing the camera
        follows the line instead of the cell.
        """
        at = caret_pos(focus.node)
        if at is None:
            return None
        return focus.y + (1 if layout.walls else 0) + at[0]

    def caret_column(self, layout, focus) -> int | None:
        """The layout column the caret sits on inside a cell being typed into.

        The same argument as `caret_row`, sideways: a cell can be wider than the
        screen, and the caret can be past its right edge. The column comes from
        `caret_pos`, so a tab counts as the cells it is drawn in and the camera
        centres on the character the reader sees under the caret.
        """
        at = caret_pos(focus.node)
        if at is None:
            return None
        left = focus.x + (1 if layout.walls else 0) + PAD
        return left + at[1]

    def camera(self, width: int, height: int) -> tuple[int, int]:
        layout = self.layout_
        focus = layout.box(self.spoider.selected)
        if focus is not None:
            across = self.caret_column(layout, focus)
            x = (across if across is not None else focus.cx) - width // 2
            aimed = self.caret_row(layout, focus)
            y = (aimed if aimed is not None else focus.cy) - height // 2
        else:
            x = layout.width // 2 - width // 2
            y = layout.height // 2 - height // 2

        if layout.width <= width:
            x = -((width - layout.width) // 2)
        else:
            x = min(max(x, 0), layout.width - width)
        if layout.height <= height:
            y = -((height - layout.height) // 2)
        else:
            y = min(max(y, 0), layout.height - height)
        return x, y

    def _settle(self) -> None:
        """Work out the field, the camera and the caret once for the rows about to be drawn."""
        key = (
            id(self.layout_),
            self.spoider.selected,
            tuple(self.spoider.selected_ids),
            self.spoider.search_query,
            self.spoider.mm.colours,
            self.size,
            self.spoider.stack_open,
            self.spoider.mode,
            self.spoider.show_properties,
        )
        if key == self._settled_for:
            return
        width, height = self.size
        panel = self.spoider.stack_layout()
        # While the stack is open the right of the screen is its column, so the map is framed in
        # what is left of the screen instead of being centred underneath it.
        self._field = width - stack_column(panel, width) if panel is not None else width
        self._offset_x, self._offset_y = self.camera(self._field, height)
        self._caret = self._caret_here(self.layout_)
        self._settled_for = key

    def _chosen(self) -> tuple[str, ...]:
        """What wears the reverse: one thing at a time, and nothing while a bar has the keys."""
        elsewhere = self.spoider.stack_open or self.spoider.mode not in ("keys", "edit")
        return () if elsewhere else tuple(self.spoider.selected_ids)

    def screen_cells(self) -> list[list[tuple[str, str]]]:
        """Every row of the window as it is drawn: what the tests read, and what the eye sees."""
        return [self._row_at(y) for y in range(self.size.height)]

    def render_line(self, y: int) -> Strip:
        """One row of the window, drawn from the arrangement and the camera."""
        width = self.size.width
        if width <= 0 or y < 0 or y >= self.size.height:
            return Strip.blank(max(width, 0))
        return strip_of(self._row_at(y), width)

    def _row_at(self, y: int) -> list[tuple[str, str]]:
        """One row of the window, with the caret on it if the caret is on it.

        The rows of the frame are drawn without the caret and kept until the map itself changes,
        so a caret move is a copy of one row with one glyph restyled: the picture is not built
        again for it, and no other row is touched.
        """
        self._settle()
        row = self._rows_frame()[y]
        caret = self._caret
        if caret is not None and caret[1] - self._offset_y == y:
            x = caret[0] - self._offset_x
            if 0 <= x < len(row):
                glyph, style = row[x]
                row = list(row)
                row[x] = (glyph, caret_style(style, caret[2]))
        return row

    def _rows_frame(self) -> list[list[tuple[str, str]]]:
        """Every row of the window, drawn once for this frame.

        One picture for the whole window, cut into rows: a row drawn on its own would have to
        walk the map to find the cells on it, and the connectors between two cells resolve from
        the rows above and below them, so a row is not something that can be drawn in isolation.
        """
        if self._rows is not None and self._rows_for == self._settled_for:
            return self._rows
        width, height = self.size
        chosen = self._chosen()
        panel = self.spoider.stack_layout()
        grid = build_grid(
            self.layout_,
            chosen,
            self.spoider.search_query,
            lead=self.spoider.selected if len(chosen) > 1 else None,
            colours=self.spoider.mm.colours,
            window=cache_window(self._offset_x, self._offset_y, self._field, height),
        )
        if panel is not None:
            grid = self._with_stack(grid, panel, width, height)
        rows: list[list[tuple[str, str]]] = []
        for row in range(height):
            cells: list[tuple[str, str]] = []
            for x in range(self._offset_x, self._offset_x + width):
                if (x, self._offset_y + row) in grid.wide:
                    continue
                cells.append(grid.cells.get((x, self._offset_y + row), (" ", "")))
            rows.append(cells)
        if self.spoider.show_properties:
            paint_box(rows, self._property_sections(), LINK_COLOR)
        self._rows, self._rows_for = rows, self._settled_for
        return rows

    def render(self) -> Text:
        """The whole window as one Text: what the tests read, and what the screen holds."""
        text = Text()
        for y in range(self.size.height):
            for segment in self.render_line(y):
                text.append(segment.text, segment.style or "")
            if y != self.size.height - 1:
                text.append("\n")
        return text

    def _caret_here(self, layout) -> tuple[int, int, bool] | None:
        """Where the caret hangs now, or None when no cell is being typed into."""
        focus = layout.box(self.spoider.selected)
        if focus is None or focus.node.preview is None:
            return None
        at = caret_cell(focus, layout.walls)
        return None if at is None else (at[0], at[1], focus.node.overwrite)

    def _property_sections(self) -> list[tuple[str, list[tuple[str, str]]]]:
        spoider = self.spoider
        return sections(
            spoider.mm,
            spoider.path,
            spoider.selected,
            len(spoider.selected_ids),
            spoider.last_edited,
            dirty=spoider.dirty,
            autosave=spoider.autosave,
        )

    def _with_stack(self, grid: Grid, panel: Layout, width: int, height: int) -> Grid:
        """Give the right-hand columns to the stack.

        A wall down the full height of the view, the title at the top of it, the
        cells inside. The column is cleared first, so the map is genuinely out of
        the way rather than showing through between the bubbles, and the wall goes
        all the way down — that is what says the screen is shared between the two
        rather than a card floated over the map.
        """
        column = stack_column(panel, width)
        wall = width - column
        combined = Grid(width=max(grid.width, width), height=max(grid.height, height))
        combined.cells.update(grid.cells)
        combined.wide |= grid.wide
        blank = (" ", "")
        for row in range(height):
            for x in range(wall, width):
                combined.cells[(self._offset_x + x, self._offset_y + row)] = blank
            combined.cells[(self._offset_x + wall, self._offset_y + row)] = (DIVIDER, "bright_black")

        inner = max(0, column - 3)
        for index, char in enumerate(STACK_TITLE[:inner]):
            combined.cells[(self._offset_x + wall + 2 + index, self._offset_y)] = (char, "")

        # The panel colours by level, never by family: its entries are separate
        # little trees, so "family" would give two children of one cut two colours.
        art = build_grid(
            panel,
            tuple(self.spoider.selected_ids),
            self.spoider.search_query,  # a hit is a hit in either document
            lead=None,
            colours="depth",
            depth_shift=DEPTH_COLORS.index(STACK_START) + 1,
        )
        # a stack taller than the column follows its own selection
        shift = 0
        chosen = self.spoider.selected
        focus = panel.box(chosen) if chosen else None
        if focus is not None and focus.y + 2 + BOX_H > height - 1:
            shift = focus.y + 2 + BOX_H - (height - 1)
        for (x, y), cell in art.cells.items():
            row = y - shift + 2
            if x <= inner and 0 < row < height:
                combined.cells[(self._offset_x + wall + 2 + x, self._offset_y + row)] = cell
        for x, y in art.wide:
            row = y - shift + 2
            if x <= inner and 0 < row < height:
                combined.wide.add((self._offset_x + wall + 2 + x, self._offset_y + row))
        return combined

    def on_key(self, event: events.Key) -> None:
        """Typing into a node, or working inside the stack panel, is handled by the
        app; swallow the key so no binding fires underneath it."""
        if self.spoider.handle_edit_key(event.key, event.character):
            event.stop()
            return
        if self.spoider.handle_stack_key(event.key, event.character):
            event.stop()

