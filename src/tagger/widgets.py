"""The canvas widget: lays out, draws, and hit-tests the mind map."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import events
from textual.widget import Widget

from .layout import Layout, compute
from .render import build_grid, render_text

if TYPE_CHECKING:
    from .app import TaggerApp


class MindMapView(Widget, can_focus=True):
    """A camera over the map. The view follows the selection instead of scrolling."""

    def __init__(self, tagger: "TaggerApp") -> None:
        super().__init__()
        self.tagger = tagger
        self._layout: Layout | None = None
        self._offset_x = 0
        self._offset_y = 0

    def refresh_map(self) -> None:
        """Drop the cached layout; call after any document change."""
        self._layout = None
        self.refresh()

    @property
    def layout_(self) -> Layout:
        if self._layout is None:
            self._layout = compute(self.tagger.mm.root)
        return self._layout

    def camera(self, width: int, height: int) -> tuple[int, int]:
        layout = self.layout_
        focus = layout.box(self.tagger.selected)
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
        grid = build_grid(layout, self.tagger.selected)
        return render_text(grid, self._offset_x, self._offset_y, width, height)

    def on_click(self, event: events.Click) -> None:
        layout = self.layout_
        node_id = layout.hit(event.offset.x + self._offset_x, event.offset.y + self._offset_y)
        if node_id is None:
            return
        event.stop()
        self.tagger.select(node_id)
        if event.chain == 2:
            self.tagger.action_edit()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.tagger.action_nav_down()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.tagger.action_nav_up()
