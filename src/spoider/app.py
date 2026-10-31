"""The spoider application: key handling, inline editing, write/quit flow."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding

from . import nav
from .layout import MAX_SPACING, MIN_SPACING
from .chrome import FooterBar
from .config import Config, default_config_path, load_config, save_config
from .model import MindMap, Node
from .screens import Confirm, HelpScreen, SettingsScreen, TextPrompt
from .widgets import MindMapView, TopBar

# No colours here on purpose: the app runs on Textual's ansi theme, so every
# surface inherits the terminal's palette. `ansi_default` means "whatever the
# terminal already uses", and `reverse` swaps its own fg/bg.
APP_CSS = """
#topbar {
    width: 100%;
    height: 1;
    padding: 0 1;
    background: ansi_default;
    color: ansi_default;
    text-wrap: nowrap;
    text-overflow: clip;
}
MindMapView {
    width: 100%;
    height: 1fr;
}
/* Textual's ansi theme paints the text cursor ansi_white on ansi_black *and*
   applies the theme's `reverse` text style on top — two inversions, which land
   back on a black block on a black terminal. Pure reverse video inverts
   whatever the terminal already shows, so the caret is visible on any palette. */
TextPrompt Input > .input--cursor {
    background: ansi_default;
    color: ansi_default;
    text-style: reverse;
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
    # tab/enter are the primary keys here; the ctrl chords stay as aliases.
    # tab needs priority to beat Textual's focus-next binding.
    Binding("tab", "add_child", "child", priority=True),
    Binding("ctrl+a", "add_child", "child", show=False),
    Binding("enter", "add_sibling", "sib"),
    Binding("ctrl+j", "add_sibling", "sib", show=False),
    Binding("ctrl+e", "edit", "edit"),
    Binding("ctrl+d", "delete", "del"),
    Binding("ctrl+t", "toggle", "fold"),
    Binding("ctrl+g", "mark", "mark"),
    # rendered as the pinned cluster at the right edge, not among the hints
    Binding("ctrl+comma", "settings", "settings", show=False),
    Binding("ctrl+slash", "help", "help", show=False),
    # nano's cursor keys, kept spatial: ^P/^N walk the branch, ^B/^F move away
    # from the root or towards it — whichever way that happens to be drawn.
    # Arrows and, further down, hjkl are aliases for the same four actions.
    Binding("ctrl+p,up", "prev", "prev", show=False),
    Binding("ctrl+n,down", "next", "next", show=False),
    Binding("ctrl+b,left", "go_left", "left", show=False),
    Binding("ctrl+f,right", "go_right", "right", show=False),
    # vim cursor keys. Hidden from the bar because the ctrl chords already own
    # those labels; nothing else on any screen binds a bare h/j/k/l.
    Binding("k", "prev", "prev", show=False),
    Binding("j", "next", "next", show=False),
    Binding("h", "go_left", "left", show=False),
    Binding("l", "go_right", "right", show=False),
    Binding("alt+up", "move_up", "reorder up", show=False),
    Binding("alt+down", "move_down", "reorder down", show=False),
    # The key NAMES for the spacing chords are the ones Textual's parser actually
    # produces, which is not what you would guess: ^= arrives as
    # ctrl+shift+equals_sign under the kitty keyboard protocol (which Textual
    # enables), while a plain terminal sends ^- as the ^_ control character.
    # Every spelling is bound, plus alt fallbacks for terminals that swallow the
    # ctrl form.
    Binding(
        "ctrl+shift+equals_sign,ctrl+equals_sign,ctrl+plus,ctrl+shift+plus,"
        "alt+equals_sign,alt+plus",
        "spacing_more",
        "looser",
    ),
    Binding(
        "ctrl+minus,ctrl+shift+minus,ctrl+underscore,alt+minus,alt+underscore",
        "spacing_less",
        "tighter",
    ),
    # file first, history last: on a narrow terminal the bar clips its tail,
    # and ^X matters more than ^Z
    Binding("ctrl+s", "save", "save"),
    Binding("ctrl+o", "write", "write"),
    Binding("ctrl+x", "quit", "quit"),
    Binding("ctrl+z", "undo", "undo"),
    Binding("ctrl+y", "redo", "redo", show=False),
]

class SpoiderApp(App[None]):
    CSS = APP_CSS
    TITLE = "spoider"
    BINDINGS = BINDINGS
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        path: Path | None = None,
        *,
        demo: bool = True,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.config: Config = load_config(self.config_path)
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
        yield TopBar(id="topbar")
        yield MindMapView(self)
        yield FooterBar(id="footer")

    def on_mount(self) -> None:
        self._set_terminal_title()
        self.query_one(MindMapView).focus()

    def _title(self) -> str:
        marker = " *" if self.dirty else ""
        return f"spoider — {self.path.name}{marker}"

    def _set_terminal_title(self) -> None:
        """Mirror the buffer into the terminal title, where the unsaved marker is
        visible even when the top bar is scrolled out of sight."""
        driver = getattr(self, "_driver", None)
        if driver is not None:
            driver.write(f"\x1b]2;{self._title()}\x07")

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Nothing from the app keymap fires while a dialog is open or a node is
        being typed into: ^D must not delete the node you are editing, and ^X
        must not stack another dialog on top."""
        if action in ("help", "settings"):
            # reachable while typing, but not stacked on top of another dialog
            return len(self.screen_stack) == 1
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

    @property
    def autosave(self) -> bool:
        """Editor preference, not document state — written to the config file."""
        return self.config.autosave

    def set_autosave(self, value: bool) -> None:
        if value == self.config.autosave:
            return
        self.config.autosave = bool(value)
        try:
            save_config(self.config, self.config_path)
        except OSError as exc:
            self.notify(f"Could not write config: {exc}", severity="error", timeout=4)
        if self.config.autosave and self.dirty:
            self._autosave()  # commit what is on screen the moment you switch it on
        self._refresh_chrome()

    @property
    def spacing(self) -> int:
        """Per-document: it is written to the file, not held in the editor."""
        return self.mm.spacing

    def select(self, node_id: str) -> None:
        self.selected = node_id
        self.view.refresh()

    def _push_undo(self) -> None:
        self._undo.append(self.mm.to_dict())
        self._redo.clear()

    def _refresh_chrome(self) -> None:
        """Both chrome rows read app state directly, so either can change under
        them: the top bar counts cells, the footer hides ^S under autosave."""
        if not self.is_mounted:
            return
        self.query_one(TopBar).refresh()
        self.query_one(FooterBar).refresh()

    def _autosave(self) -> None:
        """Write silently to the current path; autosave never nags."""
        try:
            self.mm.save(self.path)
        except OSError as exc:
            self.notify(f"Could not write {self.path}: {exc}", severity="error", timeout=4)
            return
        self.dirty = False
        self._set_terminal_title()
        self._refresh_chrome()

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._set_terminal_title()
        self.view.refresh_map()
        self._refresh_chrome()
        if self.autosave:
            self._autosave()

    def _write(self, path: Path) -> bool:
        try:
            self.mm.save(path)
        except OSError as exc:
            self.notify(f"Could not write {path}: {exc}", severity="error", timeout=4)
            return False
        self.path = path
        self.dirty = False
        self._set_terminal_title()
        self._refresh_chrome()
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
        footer = self.query_one("#footer", FooterBar)
        footer.mode = "edit" if self.editing else "keys"
        footer.refresh()

    def handle_edit_key(self, key: str, character: str | None) -> bool:
        """Every keystroke while typing into a node. Returns True if consumed."""
        if not self.editing:
            return False
        if key in ("ctrl+slash", "ctrl+comma"):
            return False  # help and settings stay reachable mid-typing
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

    def action_help(self) -> None:
        """^/ — every key and option, with a line of explanation."""
        self.push_screen(HelpScreen())

    def action_settings(self) -> None:
        """^, — the editor settings."""
        self.push_screen(SettingsScreen())

    def action_mark(self) -> None:
        """^G — cycle the cell's mark: none, ✅, ❌, ❓, ❗, 🕐, none."""
        if self.node is None:
            return
        self._push_undo()
        self.mm.cycle_mark(self.selected)
        self._mark_dirty()

    def action_toggle(self) -> None:
        node = self.node
        if node is None or not node.children:
            return
        self._push_undo()
        node.collapsed = not node.collapsed
        self._mark_dirty()

    # -- movement -------------------------------------------------------

    def _to_parent(self) -> None:
        self.select(nav.to_parent(self.mm, self.selected))

    def _expand_if_collapsed(self) -> bool:
        node = self.node
        if node is not None and node.children and node.collapsed:
            self._push_undo()
            node.collapsed = False
            self._mark_dirty()
            return True
        return False

    def _into_child(self) -> None:
        if self._expand_if_collapsed():
            return
        self.select(nav.to_child(self.mm, self.selected))

    def _from_root(self, want: int) -> None:
        """The root branches both ways, so ← and → each pick their own side."""
        if self._expand_if_collapsed():
            return
        self.select(nav.to_child_on_side(self.mm, self.selected, want))

    @property
    def _at_root(self) -> bool:
        return self.selected == self.mm.root.id

    def action_go_left(self) -> None:
        """^B / ←. On a left-hand branch the children are drawn to the left, so
        the directions swap: left goes deeper, right goes back towards the root.
        From the root itself, left is its left-hand branch."""
        if self._at_root:
            self._from_root(-1)
        elif nav.side(self.mm, self.selected) < 0:
            self._into_child()
        else:
            self._to_parent()

    def action_go_right(self) -> None:
        """^F / →. Mirrors action_go_left."""
        if self._at_root:
            self._from_root(+1)
        elif nav.side(self.mm, self.selected) < 0:
            self._to_parent()
        else:
            self._into_child()

    def action_prev(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, -1))

    def action_next(self) -> None:
        self.select(nav.to_sibling(self.mm, self.selected, +1))

    def action_move_up(self) -> None:
        self._reorder(-1)

    def action_move_down(self) -> None:
        self._reorder(+1)

    def action_spacing_more(self) -> None:
        """^= — breathe: one more column between boxes and one more row between
        subtrees."""
        self._set_spacing(self.spacing + 1)

    def action_spacing_less(self) -> None:
        """^- — tighten. Stops before boxes would touch or overlap."""
        self._set_spacing(self.spacing - 1)

    def _set_spacing(self, value: int) -> None:
        value = max(MIN_SPACING, min(MAX_SPACING, value))
        if value == self.mm.spacing:
            return
        self.mm.spacing = value
        # Document state, so it makes the buffer dirty — but it stays out of the
        # undo stack: nudging the air in three steps should not bury the edit you
        # actually want to undo.
        self._mark_dirty()

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
        if self.autosave:
            if self.dirty:
                self._autosave()
            self.exit()
            return
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
