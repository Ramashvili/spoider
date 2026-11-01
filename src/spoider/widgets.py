"""The canvas widget: lays out, draws, and hit-tests the mind map."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.widget import Widget

from .layout import Layout, compute
from .render import Grid, build_grid, render_text
from .text import clip_head

if TYPE_CHECKING:
    from .app import SpoiderApp


#: The statistics block: black on the terminal's own yellow, so it reads as a band
#: rather than as three colours the app invented. One space separates the items —
#: any more and the block looks like it is falling apart.
STAT_STYLE = "black on yellow"

#: When the stack panel is open its count is the live one, so it is underlined:
#: all three are yellow already, and a colour change would say nothing.
STAT_ACTIVE_STYLE = "bold underline black on yellow"


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
        candidate = f"{joined} {extra}"
        if fits(candidate):
            style = STAT_ACTIVE_STYLE if extra_active else STAT_STYLE
            segments.append((extra, style))
            joined = candidate
    if layout:
        candidate = f"{joined} {layout} layout"
        if fits(candidate):
            segments.append((f"{layout} layout", STAT_STYLE))
            joined = candidate
    right_width = cell_len(joined)
    if width < right_width + 2:
        return Text(clip_head(joined, width), style=STAT_STYLE)

    where = f"{where} *" if dirty else where
    name = clip_head(name, width - right_width - 1)

    # One blank column separates the name from the centre band, and the band from
    # the statistics, so the line always fills exactly `width` cells.
    band = width - cell_len(name) - right_width - 2
    middle = ""
    if band >= 6:
        middle = where if cell_len(where) <= band else "…" + where[-(band - 1) :]

    bar = Text(name, style="bold")
    if middle:
        pad = (band - cell_len(middle)) // 2
        bar.append(" " * (1 + pad))
        bar.append(middle)
        bar.append(" " * (band - pad - cell_len(middle) + 1))
    else:
        bar.append(" " * (width - cell_len(name) - right_width))
    for index, (text, style) in enumerate(segments):
        if index:
            bar.append(" ", style=STAT_STYLE)
        bar.append(text, style=style)
    return bar


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
        self._grid_key: tuple[int, tuple[str, ...], str] | None = None
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
        self._offset_x, self._offset_y = self.camera(width, height)
        # Drawing the whole map costs ~25 ms on a 500-cell document, and moving
        # the camera does not change a single cell — only a new layout or a new
        # selection does (selection is reverse video).
        query = self.spoider.search_query
        chosen = tuple(self.spoider.selected_ids)
        lead = self.spoider.selected if len(chosen) > 1 else None
        key = (id(layout), chosen, query)
        if self._grid is None or self._grid_key != key:
            self._grid = build_grid(layout, chosen, query, lead=lead)
            self._grid_key = key
        grid = self._grid
        panel = self.spoider.stack_layout()
        if panel is not None:
            grid = self._overlay(grid, panel, width)
        return render_text(grid, self._offset_x, self._offset_y, width, height)

    def _overlay(self, grid: Grid, panel: Layout, width: int) -> Grid:
        """Draw the stack panel over the map: opaque, top right, one row under the
        top bar. It is composited cell by cell before the picture is rendered, so
        the panel keeps its own borders and colours and the map shows around it.
        """
        art = build_grid(panel, self.spoider.stack_selected or "", lead=None)
        panel_width = min(panel.width, max(1, width - 2))
        left = self._offset_x + width - panel_width - 1
        top = self._offset_y + 1
        combined = Grid(
            width=max(grid.width, left + panel_width),
            height=max(grid.height, top + panel.height),
        )
        combined.cells.update(grid.cells)
        combined.wide |= grid.wide
        blank = (" ", "")  # the terminal's own colours, as everywhere else
        for row in range(panel.height):
            for column in range(panel_width):
                combined.cells[(left + column, top + row)] = blank
        for (x, y), cell in art.cells.items():
            if x < panel_width:
                combined.cells[(left + x, top + y)] = cell
        for x, y in art.wide:
            if x < panel_width:
                combined.wide.add((left + x, top + y))
        return combined

    def on_key(self, event: events.Key) -> None:
        """Typing into a node, or working inside the stack panel, is handled by the
        app; swallow the key so no binding fires underneath it."""
        if self.spoider.handle_edit_key(event.key, event.character):
            event.stop()
            return
        if self.spoider.handle_stack_key(event.key, event.character):
            event.stop()

    def on_click(self, event: events.Click) -> None:
        if self.spoider.editing:
            self.spoider.finish_edit(commit=True)
            return
        if self.spoider.mode not in ("keys", "edit"):
            return  # a drawer has the screen: a click behind it selects nothing
        layout = self.layout_
        node_id = layout.hit(event.offset.x + self._offset_x, event.offset.y + self._offset_y)
        if node_id is None:
            return
        event.stop()
        self.spoider.select(node_id)
        if event.chain == 2:
            self.spoider.action_edit()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self.spoider.mode == "keys":
            self.spoider.action_next()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self.spoider.mode == "keys":
            self.spoider.action_prev()
