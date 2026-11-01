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


def compose_top_bar(
    width: int, version: str, where: str, cells: int, dirty: bool = False
) -> Text:
    """One line: name+version left, location centred, cell count right.

    Degrades in stages as the terminal narrows: centre out first, then the
    location is truncated from the left (a path's tail is the useful half), then
    the name itself. The unsaved marker rides on the location, because a window
    title is not something everyone can see — tiling window managers have no title
    bar at all."""
    name = f"spoider {version}"
    stat = f"{cells} cell" if cells == 1 else f"{cells} cells"
    if width <= 0:
        return Text("")
    stat_width = cell_len(stat)
    if width < stat_width + 2:
        return Text(clip_head(stat, width), style="bold reverse")

    where = f"{where} *" if dirty else where
    left_room = width - stat_width - 1
    name = clip_head(name, left_room)

    # One blank column separates the name from the centre band, and the band
    # from the stat, so the line always fills exactly `width` cells.
    band = width - cell_len(name) - stat_width - 2
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
        bar.append(" " * (width - cell_len(name) - stat_width))
    bar.append(stat, style="bold reverse")
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
        return compose_top_bar(height, __version__, where, app.mm.count(), app.dirty)


class MindMapView(Widget, can_focus=True):
    """A camera over the map. The view follows the selection instead of scrolling."""

    def __init__(self, spoider: SpoiderApp) -> None:
        super().__init__()
        self.spoider = spoider
        self._layout: Layout | None = None
        self._grid: Grid | None = None
        self._grid_key: tuple[int, str] | None = None
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
        key = (id(layout), self.spoider.selected)
        if self._grid is None or self._grid_key != key:
            self._grid = build_grid(layout, self.spoider.selected)
            self._grid_key = key
        return render_text(self._grid, self._offset_x, self._offset_y, width, height)

    def on_key(self, event: events.Key) -> None:
        """Typing into a node is handled by the app; swallow the key so no
        binding fires underneath it."""
        if self.spoider.handle_edit_key(event.key, event.character):
            event.stop()

    def on_click(self, event: events.Click) -> None:
        if self.spoider.editing:
            self.spoider.finish_edit(commit=True)
            return
        layout = self.layout_
        node_id = layout.hit(event.offset.x + self._offset_x, event.offset.y + self._offset_y)
        if node_id is None:
            return
        event.stop()
        self.spoider.select(node_id)
        if event.chain == 2:
            self.spoider.action_edit()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if not self.spoider.editing:
            self.spoider.action_next()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if not self.spoider.editing:
            self.spoider.action_prev()
