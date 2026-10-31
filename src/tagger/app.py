"""The tagger application: key handling, undo history, persistence wiring."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header

from . import nav
from .model import MindMap, Node
from .screens import TextPrompt
from .widgets import MindMapView

APP_CSS = """
Screen {
    background: #0a1024;
    color: #ffcead;
}
MindMapView {
    width: 100%;
    height: 1fr;
    background: #0a1024;
}
Header {
    background: #131a3a;
    color: #ffcead;
}
Footer {
    background: #131a3a;
    color: #a3bfd1;
}
Footer .footer--key {
    background: #252e56;
    color: #ffcead;
}
"""


class TaggerApp(App[None]):
    CSS = APP_CSS
    TITLE = "tagger"

    BINDINGS = [
        Binding("tab", "add_child", "child", priority=True),
        Binding("enter", "add_sibling", "sibling"),
        Binding("e", "edit", "edit"),
        Binding("d", "delete", "delete"),
        Binding("space", "toggle", "fold"),
        Binding("left,h", "nav_left", "parent"),
        Binding("right,l", "nav_right", "child"),
        Binding("up,k", "nav_up", "prev"),
        Binding("down,j", "nav_down", "next"),
        Binding("K", "move_up", "move up"),
        Binding("J", "move_down", "move down"),
        Binding("u", "undo", "undo"),
        Binding("ctrl+r", "redo", "redo"),
        Binding("ctrl+s", "save", "save"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(self, path: Path | None = None, *, demo: bool = True) -> None:
        super().__init__()
        self.path = Path(path) if path is not None else default_path()
        if self.path.exists():
            self.mm = MindMap.load(self.path)
        else:
            self.mm = MindMap.demo() if demo else MindMap()
        self.selected: str = self.mm.root.id
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self.sub_title = str(self.path)

    # -- composition ----------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield MindMapView(self)
        yield Footer()

    def on_mount(self) -> None:
        if not self.path.exists():
            self._save()
        self.query_one(MindMapView).focus()

    # -- state ----------------------------------------------------------

    @property
    def view(self) -> MindMapView:
        return self.query_one(MindMapView)

    @property
    def node(self) -> Node | None:
        return self.mm.find(self.selected)

    def select(self, node_id: str) -> None:
        self.selected = node_id
        self.view.refresh()

    def _push_undo(self) -> None:
        self._undo.append(self.mm.to_dict())
        self._redo.clear()

    def _save(self) -> None:
        try:
            self.mm.save(self.path)
        except OSError as exc:
            self.notify(f"Could not save: {exc}", severity="error", timeout=4)

    def _changed(self) -> None:
        self._save()
        self.view.refresh_map()

    def _restore(self, snapshot: dict) -> None:
        self.mm = MindMap.from_dict(snapshot)
        if self.mm.find(self.selected) is None:
            self.selected = self.mm.root.id
        self._changed()

    def _prompt(self, node_id: str, *, push: bool = True, preselect: bool = False) -> None:
        node = self.mm.find(node_id)
        if node is None:
            return

        def apply(value: str | None) -> None:
            if value is None:
                return
            target = self.mm.find(node_id)
            if target is None:
                return
            if push:
                self._push_undo()
            target.text = value.strip() or "Untitled"
            self._changed()

        self.push_screen(TextPrompt("Node text", node.text, preselect=preselect), apply)

    # -- editing actions ------------------------------------------------

    def action_add_child(self) -> None:
        self._push_undo()
        node = self.mm.add_child(self.selected)
        self.selected = node.id
        self._changed()
        self._prompt(node.id, push=False, preselect=True)

    def action_add_sibling(self) -> None:
        node = self.mm.add_sibling(self.selected)
        if node is None:
            self.action_add_child()
            return
        self._push_undo()
        self.selected = node.id
        self._changed()
        self._prompt(node.id, push=False, preselect=True)

    def action_edit(self) -> None:
        if self.node is not None:
            self._prompt(self.selected)

    def action_delete(self) -> None:
        if self.selected == self.mm.root.id:
            self.notify("The root node cannot be deleted", timeout=2)
            return
        self._push_undo()
        result = self.mm.delete(self.selected)
        if result is None:
            self._undo.pop()
            return
        _, successor = result
        self.selected = successor
        self._changed()

    def action_toggle(self) -> None:
        node = self.node
        if node is None or not node.children:
            return
        self._push_undo()
        node.collapsed = not node.collapsed
        self._changed()

    # -- movement -------------------------------------------------------

    def action_nav_left(self) -> None:
        self.select(nav.to_parent(self.mm, self.selected))

    def action_nav_right(self) -> None:
        node = self.node
        if node is not None and node.children and node.collapsed:
            self._push_undo()
            node.collapsed = False
            self._changed()
            return
        self.select(nav.to_child(self.mm, self.selected))

    def action_nav_up(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, -1))

    def action_nav_down(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, +1))

    def action_move_up(self) -> None:
        self._reorder(-1)

    def action_move_down(self) -> None:
        self._reorder(+1)

    def _reorder(self, delta: int) -> None:
        self._push_undo()
        if self.mm.move_sibling(self.selected, delta):
            self._changed()
        else:
            self._undo.pop()

    # -- history --------------------------------------------------------

    def action_undo(self) -> None:
        if not self._undo:
            self.notify("Nothing to undo", timeout=1)
            return
        self._redo.append(self.mm.to_dict())
        self._restore(self._undo.pop())

    def action_redo(self) -> None:
        if not self._redo:
            self.notify("Nothing to redo", timeout=1)
            return
        self._undo.append(self.mm.to_dict())
        self._restore(self._redo.pop())

    def action_save(self) -> None:
        self._save()
        self.notify(f"Saved {self.path.name}", timeout=1)


def default_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "tagger" / "map.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tagger", description="TUI mind map editor")
    parser.add_argument(
        "path",
        nargs="?",
        help="map file (default: ~/.local/share/tagger/map.json)",
    )
    parser.add_argument(
        "--empty", action="store_true", help="start empty instead of seeding a demo map"
    )
    args = parser.parse_args(argv)
    path = Path(args.path).expanduser() if args.path else default_path()
    TaggerApp(path, demo=not args.empty).run()


if __name__ == "__main__":
    main()
