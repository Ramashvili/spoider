"""The spoider application: key handling, inline editing, write/quit flow."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path

from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding, BindingType

from . import nav
from .chrome import FooterBar
from .config import (
    MAX_MARKS,
    Config,
    default_config_path,
    is_stale,
    load_config,
    write_config,
)
from .layout import MAX_SPACING, MIN_SPACING
from .model import LAYOUTS, MARKS, MapFileError, MindMap, Node
from .screens import Confirm, HelpScreen, SettingsScreen, TextPrompt
from .text import clean
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

BINDINGS: list[BindingType] = [
    # tab/enter are the primary keys here; the ctrl chords stay as aliases.
    # tab needs priority to beat Textual's focus-next binding.
    Binding("tab", "add_child", "child", priority=True, id="add_child"),
    Binding("ctrl+a", "add_child", "child", show=False, id="add_child_alt"),
    Binding("enter", "add_sibling", "sib", id="add_sibling"),
    Binding("ctrl+j", "add_sibling", "sib", show=False, id="add_sibling_alt"),
    Binding("ctrl+e", "edit", "edit", id="edit"),
    Binding("ctrl+d", "delete", "del", id="delete"),
    Binding("ctrl+t", "fold", "fold", id="fold"),
    Binding("ctrl+g", "mark", "mark", id="mark"),
    # rendered as the pinned cluster at the right edge, not among the hints
    Binding("ctrl+comma", "settings", "settings", show=False, id="settings"),
    Binding("ctrl+slash", "help", "help", show=False, id="help"),
    # nano's cursor keys, kept spatial: ^P/^N walk the branch, ^B/^F move away
    # from the root or towards it — whichever way that happens to be drawn.
    # Arrows and, further down, hjkl are aliases for the same four actions.
    Binding("ctrl+p,up", "prev", "prev", show=False, id="prev"),
    Binding("ctrl+n,down", "next", "next", show=False, id="next"),
    Binding("ctrl+b,left", "go_left", "left", show=False, id="left"),
    Binding("ctrl+f,right", "go_right", "right", show=False, id="right"),
    # vim cursor keys. Hidden from the bar because the ctrl chords already own
    # those labels; nothing else on any screen binds a bare h/j/k/l.
    Binding("k", "prev", "prev", show=False, id="prev_vim"),
    Binding("j", "next", "next", show=False, id="next_vim"),
    Binding("h", "go_left", "left", show=False, id="left_vim"),
    Binding("l", "go_right", "right", show=False, id="right_vim"),
    Binding("alt+up", "move_up", "reorder up", show=False, id="move_up"),
    Binding("alt+down", "move_down", "reorder down", show=False, id="move_down"),
    # The key NAMES for the spacing chords are the ones Textual's parser actually
    # produces, which is not what you would guess: ^= arrives as
    # ctrl+shift+equals_sign under the kitty keyboard protocol (which Textual
    # enables), while a plain terminal sends ^- as the ^_ control character.
    # Every spelling is bound, plus alt fallbacks for terminals that swallow the
    # ctrl form.
    # One chord each. Every terminal spelling the same key might arrive as used to
    # be bound too, which made the bar, the help and the config list six keys for
    # two jobs; if a terminal cannot send these, rebind them in the config.
    Binding("ctrl+equals_sign", "spacing_more", "looser", id="spacing_more"),
    Binding("ctrl+minus", "spacing_less", "tighter", id="spacing_less"),

    # file first, history last: on a narrow terminal the bar clips its tail,
    # and ^X matters more than ^Z
    Binding("ctrl+s", "save", "save", id="save"),
    Binding("ctrl+o", "write", "write", id="write"),
    Binding("ctrl+x", "quit", "quit", id="quit"),
    Binding("ctrl+z", "undo", "undo", id="undo"),
    Binding("ctrl+y", "redo", "redo", show=False, id="redo"),
    # Last on purpose: the bar drops its tail on a narrow terminal, and a shape
    # toggle matters less than saving or quitting. Help still lists it.
    Binding("ctrl+l", "layout", "layout", id="layout"),
]

def default_keymap() -> dict[str, str]:
    """id -> the chord(s) that action was born with."""
    return {
        binding.id: binding.key
        for binding in BINDINGS
        if isinstance(binding, Binding) and binding.id
    }


def editor_command() -> list[str]:
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        return shlex.split(raw) or ["nano"]
    except ValueError:  # unbalanced quotes in $EDITOR / $VISUAL
        return ["nano"]


def edit_in_editor(path: Path) -> None:
    """Run the user's editor on a file, in the foreground."""
    subprocess.run([*editor_command(), str(path)], check=False)


def build_keymap(overrides: dict[str, str]) -> dict[str, str]:
    """Defaults, with whatever the config says laid over the top.

    Unknown ids and blank chords are ignored, so a typo in the config cannot take
    a key away from you."""
    keymap = default_keymap()
    for ident, keys in (overrides or {}).items():
        if ident in keymap and isinstance(keys, str) and keys.strip():
            keymap[ident] = keys.strip()
    return keymap


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
        self.has_file = self.path.exists()
        self.load_error: str | None = None
        if self.has_file:
            try:
                self.mm = MindMap.load(self.path)
            except MapFileError as exc:
                # Starting on an empty map beats a traceback on the terminal; the
                # reason is reported once the screen exists.
                self.mm = MindMap()
                self.has_file = False
                self.load_error = str(exc)
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
        # A file written by an older build keeps listing chords that no longer
        # exist; regenerate it, but only when it is actually out of date.
        if is_stale(self.config_path, self.config, self._key_entries()):
            self._save_config()
        if self.load_error is not None:
            self.notify(self.load_error, severity="error", timeout=8)
        self.set_keymap(self.config.keys)
        self._set_terminal_title()
        self.query_one(MindMapView).focus()

    def _title(self) -> str:
        marker = " *" if self.dirty else ""
        return f"spoider — {self.path.name}{marker}"

    def _set_terminal_title(self) -> None:
        """Mirror the buffer into the terminal title, where the unsaved marker is
        visible even when the top bar is scrolled out of sight.

        The file name is untrusted — it can contain an ESC — and this string is
        written straight to the terminal, so it is cleaned like any other text.
        """
        driver = getattr(self, "_driver", None)
        if driver is not None:
            driver.write(f"\x1b]2;{clean(self._title())}\x07")

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
        self._save_config()
        if self.config.autosave and self.dirty:
            self._autosave()  # commit what is on screen the moment you switch it on
        self._refresh_chrome()

    @property
    def keymap(self) -> dict[str, str]:
        """binding id -> chord(s) in force: the defaults with the config on top."""
        return build_keymap(self.config.keys)

    def _key_entries(self) -> list[tuple[str, str, str]]:
        """(id, default chord, what it does) for every rebindable binding."""
        from .screens import describe_action

        entries: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for binding in BINDINGS:
            if not isinstance(binding, Binding) or not binding.id:
                continue
            description = describe_action(binding.action, binding.description)
            if binding.action in seen:
                description = f"{description} (alias)"
            seen.add(binding.action)
            entries.append((binding.id, binding.key, description))
        return entries

    def open_config(self) -> None:
        """Hand the terminal to the editor on the config file, then reload it."""
        if not self.config_path.exists():
            self._save_config()
        try:
            with self.suspend():
                edit_in_editor(self.config_path)
        except (SuspendNotSupported, OSError) as exc:
            self.notify(f"Could not start an editor: {exc}", severity="error", timeout=4)
            return

        self.config = load_config(self.config_path)
        self.set_keymap(self.config.keys)  # new chords take effect straight away
        self._refresh_chrome()
        self.notify("Config reloaded", timeout=2)

    @property
    def marks(self) -> tuple[str, ...]:
        """The emoji ^G cycles through — an editor preference, like autosave."""
        return self.config.marks

    def set_marks(self, marks: Iterable[object]) -> None:
        cleaned = tuple(seen for mark in marks if (seen := clean(mark).strip()))
        cleaned = cleaned[:MAX_MARKS] or tuple(MARKS)
        if cleaned == self.config.marks:
            return
        self.config.marks = cleaned
        self._save_config()

    def _save_config(self) -> None:
        try:
            write_config(self.config, self.config_path, self._key_entries())
        except OSError as exc:
            self.notify(f"Could not write config: {exc}", severity="error", timeout=4)

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

    def _autosave(self) -> bool:
        """Write silently to the current path. False when the write failed, which
        matters to ^X: quitting after a failed autosave would lose the buffer."""
        try:
            self.mm.save(self.path)
        except OSError as exc:
            self.notify(f"Could not write {self.path}: {exc}", severity="error", timeout=4)
            return False
        self.dirty = False
        self.has_file = True
        self._set_terminal_title()
        self._refresh_chrome()
        return True

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
        self.has_file = True
        self.dirty = False
        self._set_terminal_title()
        self._refresh_chrome()
        self.notify(f"Wrote {self.mm.count()} nodes to {path.name}", timeout=2)
        return True

    def _ask_where_to_write(self, *, then_quit: bool = False) -> None:
        def apply(value: str | None) -> None:
            if value is None or not value.strip():
                return
            target = Path(value.strip()).expanduser()
            if target.is_dir():
                self.notify(f"{target} is a directory", severity="error", timeout=4)
                return
            if self._write(target) and then_quit:
                self.exit()

        self.push_screen(TextPrompt("File name to write", str(self.path)), apply)

    def _restore(self, snapshot: dict) -> None:
        try:
            self.mm = MindMap.from_dict(snapshot)
        except MapFileError as exc:  # only reachable if a snapshot were corrupt
            self.notify(f"Cannot restore that state: {exc}", severity="error", timeout=4)
            return
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
        self.mm.cycle_mark(self.selected, self.marks)
        self._mark_dirty()

    def action_fold(self) -> None:
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
        From the root itself, left is its left-hand branch. In a pyramid or a
        tree the siblings sit side by side, so left is simply the one before."""
        if self._stacked:
            self.select(nav.to_sibling(self.mm, self.selected, -1))
            return
        if self._at_root:
            self._from_root(-1)
        elif nav.side(self.mm, self.selected, self.mm.layout) < 0:
            self._into_child()
        else:
            self._to_parent()

    def action_go_right(self) -> None:
        """^F / →. Mirrors action_go_left."""
        if self._stacked:
            self.select(nav.to_sibling(self.mm, self.selected, +1))
            return
        if self._at_root:
            self._from_root(+1)
        elif nav.side(self.mm, self.selected, self.mm.layout) < 0:
            self._to_parent()
        else:
            self._into_child()

    @property
    def _stacked(self) -> bool:
        """True when children hang below (pyramid) or above (tree) the parent:
        the arrows have to mean something different from the sideways shapes."""
        return self.mm.layout in ("pyramid", "tree")

    def action_prev(self) -> None:
        """Previous sibling; up towards the parent when the tree grows sideways."""
        if self._stacked:
            self._to_parent()
        else:
            self.select(nav.to_sibling(self.mm, self.selected, -1))

    def action_next(self) -> None:
        """Next sibling; down a level when the tree grows downwards."""
        if self._stacked:
            self._into_child()
        else:
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

    def action_layout(self) -> None:
        """^L — cycle the shape of the map: spider, pyramid, tree, outline."""
        order = LAYOUTS
        self.mm.layout = order[(order.index(self.mm.layout) + 1) % len(order)]
        # like spacing, the shape is document state but not an edit worth undoing
        self._mark_dirty()
        self.notify(f"Layout: {self.mm.layout}", timeout=1)

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

    async def action_quit(self) -> None:
        """^X — nano's Exit: never throw away a modified buffer silently."""
        if self.autosave:
            if self.dirty and not self._autosave():
                return  # the write failed; keep the buffer and stay
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
