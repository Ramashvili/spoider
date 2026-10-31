"""The spoider application: key handling, undo history, persistence wiring."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Static

from . import nav
from .model import MindMap, Node
from .screens import Confirm, TextPrompt
from .widgets import MindMapView

# No colours here on purpose: the app runs on Textual's ansi theme, so every
# surface inherits the terminal's palette. `ansi_default` means "whatever the
# terminal already uses", and `reverse` swaps its own fg/bg.
APP_CSS = """
MindMapView {
    width: 100%;
    height: 1fr;
}
#footer {
    width: 100%;
    height: 1;
    padding: 0 1;
    background: ansi_default;
    color: ansi_default;
    text-wrap: nowrap;
    text-overflow: clip;
}
"""

# Nano-style: every shortcut is a ctrl chord, arrows stay as plain cursor keys.
BINDINGS: list[Binding] = [
    Binding("ctrl+a", "add_child", "child"),
    Binding("ctrl+s", "add_sibling", "sib"),
    Binding("ctrl+e,enter", "edit", "edit"),
    Binding("ctrl+d", "delete", "del"),
    Binding("ctrl+t", "toggle", "fold"),
    # nano's cursor keys: ^P/^N walk the branch, ^B/^F go up/down the tree
    Binding("ctrl+p,up", "prev", "prev"),
    Binding("ctrl+n,down", "next", "next"),
    Binding("ctrl+b,left", "parent", "out"),
    Binding("ctrl+f,right", "child", "in"),
    Binding("alt+up", "move_up", "reorder up", show=False),
    Binding("alt+down", "move_down", "reorder down", show=False),
    Binding("ctrl+z", "undo", "undo"),
    Binding("ctrl+y", "redo", "redo", show=False),
    Binding("ctrl+o", "write", "write"),
    Binding("ctrl+x", "quit", "quit"),
]

BINDING_LEGEND = {"ctrl+": "^", "alt+": "⌥"}


def footer_bar(bindings: list[Binding]) -> Text:
    """Shortcut bar, built from BINDINGS so it cannot drift out of date."""
    bar = Text()
    for binding in bindings:
        if not binding.show:
            continue
        key = str(binding.key).split(",")[0]
        for prefix, glyph in BINDING_LEGEND.items():
            key = key.replace(prefix, glyph)
        bar.append(f" {key.upper()} ", style="bold reverse")
        bar.append(f"{binding.description} ")
    return bar


class SpoiderApp(App[None]):
    CSS = APP_CSS
    TITLE = "spoider"
    BINDINGS = BINDINGS
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, path: Path | None = None, *, demo: bool = True) -> None:
        super().__init__()
        self.theme = "textual-ansi"
        self.path = Path(path) if path is not None else default_path()
        if self.path.exists():
            self.mm = MindMap.load(self.path)
        else:
            self.mm = MindMap.demo() if demo else MindMap()
        self.selected: str = self.mm.root.id
        self.dirty = False
        self._undo: list[dict] = []
        self._redo: list[dict] = []

    # -- composition ----------------------------------------------------

    def compose(self) -> ComposeResult:
        yield MindMapView(self)
        yield Static(footer_bar(BINDINGS), id="footer")

    def on_mount(self) -> None:
        self._set_terminal_title()
        self.query_one(MindMapView).focus()

    def _title(self) -> str:
        marker = " *" if self.dirty else ""
        return f"spoider — {self.path.name}{marker}"

    def _set_terminal_title(self) -> None:
        """No header bar, so the file name (and the modified marker) live in the
        terminal's title."""
        driver = getattr(self, "_driver", None)
        if driver is not None:
            driver.write(f"\x1b]2;{self._title()}\x07")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Nothing from the app keymap fires while a dialog is open: ^D must not
        delete the node being renamed, and ^X must not stack another dialog."""
        if len(self.screen_stack) > 1:
            return None
        return True

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

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._set_terminal_title()
        self.view.refresh_map()

    def _write(self, path: Path) -> bool:
        try:
            self.mm.save(path)
        except OSError as exc:
            self.notify(f"Could not write {path}: {exc}", severity="error", timeout=4)
            return False
        self.path = path
        self.dirty = False
        self._set_terminal_title()
        self.notify(f"Wrote {self.mm.count()} nodes to {path.name}", timeout=2)
        return True

    def _ask_where_to_write(self, *, then_quit: bool = False) -> None:
        def apply(value: str | None) -> None:
            if value is None or not value.strip():
                return
            if self._write(Path(value.strip()).expanduser()) and then_quit:
                self.exit()

        self.push_screen(TextPrompt("File name to write", str(self.path)), apply)

    def _restore(self, snapshot: dict) -> None:
        self.mm = MindMap.from_dict(snapshot)
        if self.mm.find(self.selected) is None:
            self.selected = self.mm.root.id
        self._mark_dirty()

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
            self._mark_dirty()

        self.push_screen(TextPrompt("Node text", node.text, preselect=preselect), apply)

    # -- editing actions ------------------------------------------------

    def action_add_child(self) -> None:
        self._push_undo()
        node = self.mm.add_child(self.selected)
        self.selected = node.id
        self._mark_dirty()
        self._prompt(node.id, push=False, preselect=True)

    def action_add_sibling(self) -> None:
        node = self.mm.add_sibling(self.selected)
        if node is None:
            self.action_add_child()
            return
        self._push_undo()
        self.selected = node.id
        self._mark_dirty()
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
        self._mark_dirty()

    def action_toggle(self) -> None:
        node = self.node
        if node is None or not node.children:
            return
        self._push_undo()
        node.collapsed = not node.collapsed
        self._mark_dirty()

    # -- movement -------------------------------------------------------

    def action_parent(self) -> None:
        self.select(nav.to_parent(self.mm, self.selected))

    def action_child(self) -> None:
        node = self.node
        if node is not None and node.children and node.collapsed:
            self._push_undo()
            node.collapsed = False
            self._mark_dirty()
            return
        self.select(nav.to_child(self.mm, self.selected))

    def action_prev(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, -1))

    def action_next(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, +1))

    def action_move_up(self) -> None:
        self._reorder(-1)

    def action_move_down(self) -> None:
        self._reorder(+1)

    def _reorder(self, delta: int) -> None:
        self._push_undo()
        if self.mm.move_sibling(self.selected, delta):
            self._mark_dirty()
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

    def action_write(self) -> None:
        """^O — nano's Write Out: always asks which file to write."""
        self._ask_where_to_write()

    def action_quit(self) -> None:
        """^X — nano's Exit: never throw away a modified buffer silently."""
        if not self.dirty:
            self.exit()
            return

        def done(choice: str | None) -> None:
            if choice == "no":
                self.exit()
            elif choice == "yes":
                self._ask_where_to_write(then_quit=True)

        self.push_screen(Confirm("Save modified buffer?"), done)


def default_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "spoider" / "map.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="spoider", description="TUI mind map editor")
    parser.add_argument(
        "path",
        nargs="?",
        help="map file (default: ~/.local/share/spoider/map.json)",
    )
    parser.add_argument(
        "--empty", action="store_true", help="start empty instead of seeding a demo map"
    )
    args = parser.parse_args(argv)
    path = Path(args.path).expanduser() if args.path else default_path()
    SpoiderApp(path, demo=not args.empty).run()


if __name__ == "__main__":
    main()
