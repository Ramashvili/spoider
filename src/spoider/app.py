"""The spoider application: key handling, inline editing, write/quit flow."""

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

# The character that stands in for the caret while a node is being typed into.
CARET = "▊"

BINDINGS: list[Binding] = [
    Binding("ctrl+a", "add_child", "child"),
    Binding("ctrl+j", "add_sibling", "sib"),
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
    # file first, history last: on a narrow terminal the bar clips its tail,
    # and ^X matters more than ^Z
    Binding("ctrl+s", "save", "save"),
    Binding("ctrl+o", "write", "write"),
    Binding("ctrl+x", "quit", "quit"),
    Binding("ctrl+z", "undo", "undo"),
    Binding("ctrl+y", "redo", "redo", show=False),
]

BINDING_LEGEND = {"ctrl+": "^", "alt+": "⌥"}
EDIT_HINTS = [("⏎", "done"), ("esc/^C", "cancel"), ("←→", "move"), ("⌫", "erase")]


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


def edit_bar() -> Text:
    bar = Text()
    for key, label in EDIT_HINTS:
        bar.append(f" {key} ", style="bold reverse")
        bar.append(f"{label} ")
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
        self._edit_id: str | None = None
        self._edit_buffer = ""
        self._edit_cursor = 0
        self._edit_fresh = False

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
        """Nothing from the app keymap fires while a dialog is open or a node is
        being typed into: ^D must not delete the node you are editing, and ^X
        must not stack another dialog on top."""
        if len(self.screen_stack) > 1 or self.editing:
            return None
        return True

    def action_help_quit(self) -> None:
        """^C is escape in spoider, not Textual's "press ^X to quit" nudge."""
        return

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

    # -- inline editing -------------------------------------------------

    @property
    def editing(self) -> bool:
        return self._edit_id is not None

    def begin_edit(self, node_id: str, *, fresh: bool = False) -> None:
        node = self.mm.find(node_id)
        if node is None:
            return
        if not fresh:
            self._push_undo()
        self._edit_id = node_id
        self._edit_fresh = fresh
        self._edit_buffer = "" if fresh else (node.text or "")
        self._edit_cursor = len(self._edit_buffer)
        self._sync_preview()
        self._sync_footer()

    def _sync_preview(self) -> None:
        node = self.mm.find(self._edit_id) if self._edit_id else None
        if node is None:
            return
        before = self._edit_buffer[: self._edit_cursor]
        after = self._edit_buffer[self._edit_cursor :]
        node.preview = f"{before}{CARET}{after}"
        self.view.refresh_map()

    def _sync_footer(self) -> None:
        self.query_one("#footer", Static).update(
            edit_bar() if self.editing else footer_bar(BINDINGS)
        )

    def handle_edit_key(self, key: str, character: str | None) -> bool:
        """Every keystroke while typing into a node. Returns True if consumed."""
        if not self.editing:
            return False
        if key == "enter":
            self.finish_edit(commit=True)
        elif key in ("escape", "ctrl+c"):
            self.finish_edit(commit=False)
        elif key == "backspace" and self._edit_cursor:
            self._edit_buffer = (
                self._edit_buffer[: self._edit_cursor - 1] + self._edit_buffer[self._edit_cursor :]
            )
            self._edit_cursor -= 1
            self._sync_preview()
        elif key == "delete":
            self._edit_buffer = (
                self._edit_buffer[: self._edit_cursor] + self._edit_buffer[self._edit_cursor + 1 :]
            )
            self._sync_preview()
        elif key in ("left", "ctrl+b"):
            self._edit_cursor = max(0, self._edit_cursor - 1)
            self._sync_preview()
        elif key in ("right", "ctrl+f"):
            self._edit_cursor = min(len(self._edit_buffer), self._edit_cursor + 1)
            self._sync_preview()
        elif key in ("home", "ctrl+a"):
            self._edit_cursor = 0
            self._sync_preview()
        elif key in ("end", "ctrl+e"):
            self._edit_cursor = len(self._edit_buffer)
            self._sync_preview()
        elif character and character.isprintable():
            self._edit_buffer = (
                self._edit_buffer[: self._edit_cursor]
                + character
                + self._edit_buffer[self._edit_cursor :]
            )
            self._edit_cursor += len(character)
            self._sync_preview()
        return True

    def finish_edit(self, *, commit: bool) -> None:
        node_id = self._edit_id
        self._edit_id = None
        node = self.mm.find(node_id) if node_id else None
        text = self._edit_buffer.strip()
        fresh = self._edit_fresh
        if node is not None:
            node.preview = None

        if node is None or not commit or not text:
            # An abandoned new node was only ever a promise; take it away again.
            if fresh and node is not None:
                result = self.mm.delete(node.id)
                if result is not None:
                    self.selected = result[1]
            self._sync_footer()
            self.view.refresh_map()
            return

        if node.text != text:
            node.text = text
            self._mark_dirty()
        else:
            self.view.refresh_map()
        self._sync_footer()

    # -- editing actions ------------------------------------------------

    def action_add_child(self) -> None:
        self._push_undo()
        node = self.mm.add_child(self.selected)
        self.selected = node.id
        self.view.refresh_map()
        self.begin_edit(node.id, fresh=True)

    def action_add_sibling(self) -> None:
        if self.mm.parent(self.selected) is None:
            self.action_add_child()
            return
        self._push_undo()
        node = self.mm.add_sibling(self.selected)
        if node is None:
            self._undo.pop()
            return
        self.selected = node.id
        self.view.refresh_map()
        self.begin_edit(node.id, fresh=True)

    def action_edit(self) -> None:
        if self.node is not None:
            self.begin_edit(self.selected)

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

    # -- history and files ----------------------------------------------

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
        """^S — write straight back to the current file, no questions."""
        self._write(self.path)

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
