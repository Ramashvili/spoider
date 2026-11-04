"""The canvas widget: lays out, draws, and hit-tests the mind map."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.widget import Widget

from .chrome import DIVIDER
from .layout import BOX_H, Layout, compute
from .properties import sections
from .render import (
    DEPTH_COLORS,
    LINK_COLOR,
    STACK_START,
    Grid,
    build_grid,
    render_text,
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
    layout: str = "",
    dirty: bool = False,
    extra: str = "",
    extra_active: bool = False,
) -> Text:
    """One line: name+version left, location centred, statistics right.

    `stat` is whatever the app wants counted — cells, or the matches of a search —
    `extra` rides beside it (the cuts waiting on the stack) and the shape the map
    is drawn in closes the band. They degrade in stages as the terminal narrows:
    the shape first, then the cuts, then the centre, then the location is
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
    if layout:
        candidate = f"{joined}{GAP}{layout} layout"
        if fits(candidate):
            segments.append((f"{layout} layout", STAT_STYLE))
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
        # No stat() per frame: the app tracks whether a file exists, so a file
        # deleted mid-session does not silently become "New Buffer".
        where = str(app.path) if app.has_file else "New Buffer"
        return compose_top_bar(
            height,
            __version__,
            where,
            app.stat_text(),
            app.mm.layout,
            app.dirty,
            extra=app.cut_stat(),
            extra_active=app.stack_open,
        )


class MindMapView(Widget, can_focus=True):
    """A camera over the map. The view follows the selection instead of scrolling."""

    def __init__(self, spoider: SpoiderApp) -> None:
        super().__init__()
        self.spoider = spoider
        self._layout: Layout | None = None
        self._grid: Grid | None = None
        self._grid_key: tuple[int, tuple[str, ...], str, str] | None = None
        self._offset_x = 0
        self._offset_y = 0

    def refresh_map(self) -> None:
        """Drop the cached layout and picture; call after any document change."""
        self._layout = None
        self._grid = None
        self._grid_key = None
        self.refresh()

    @property
    def layout_(self) -> Layout:
        if self._layout is None:
            mm = self.spoider.mm
            self._layout = compute(mm.root, mm.spacing, mm.layout)
        return self._layout

    def camera(self, width: int, height: int) -> tuple[int, int]:
        layout = self.layout_
        focus = layout.box(self.spoider.selected)
        if focus is not None:
            x = focus.cx - width // 2
            y = focus.cy - height // 2
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

    def render(self) -> Text:
        width, height = self.size.width, self.size.height
        if width <= 0 or height <= 0:
            return Text("")
        layout = self.layout_
        panel = self.spoider.stack_layout()
        # While the stack is open the right of the screen is its column, so the map
        # is framed in what is left instead of being centred underneath it.
        field = width - stack_column(panel, width) if panel is not None else width
        self._offset_x, self._offset_y = self.camera(field, height)
        # Drawing the whole map costs ~25 ms on a 500-cell document, and moving the
        # camera does not change a single cell — only a new layout or a new
        # selection does. Reverse means "you are here", so only one thing wears it:
        # while the stack panel or a prompt has the keys, the cell's frame steps aside
        # and the band above the bar is the place to look.
        query = self.spoider.search_query
        elsewhere = self.spoider.stack_open or self.spoider.mode not in ("keys", "edit")
        chosen = () if elsewhere else tuple(self.spoider.selected_ids)
        lead = self.spoider.selected if len(chosen) > 1 else None
        colours = self.spoider.mm.colours
        key = (id(layout), chosen, query, colours)
        if self._grid is None or self._grid_key != key:
            self._grid = build_grid(layout, chosen, query, lead=lead, colours=colours)
            self._grid_key = key
        grid = self._grid
        if panel is not None:
            grid = self._with_stack(grid, panel, width, height)
        floaters = []
        if self.spoider.show_properties:
            floaters.append((self._property_sections(), LINK_COLOR))
        return render_text(
            grid, self._offset_x, self._offset_y, width, height, floaters=floaters
        )

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

