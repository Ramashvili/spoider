"""The spoider application: key handling, inline editing, write/quit flow."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from collections.abc import Iterable
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding, BindingType

from . import nav
from .chrome import CARET, FooterBar, ask_chunks, prompt_chunks, settings_chunks
from .config import (
    MAX_MARKS,
    Config,
    default_config_path,
    is_stale,
    load_config,
    write_config,
)
from .drawers import AskBar, PanelBar, PromptBar
from .layout import MAX_SPACING, MIN_SPACING, label
from .model import LAYOUTS, MARKS, MapFileError, MindMap, Node
from .screens import help_text, settings_text
from .text import clean, find_all
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
/* The drawers sit above the bar, never over the map. One of them is shown at a
   time and each takes only the rows it needs. */
#panel, #ask, #prompt {
    width: 100%;
    padding: 0 1;
    background: ansi_default;
    color: ansi_default;
    display: none;
    text-wrap: nowrap;
    text-overflow: clip;
}
#ask, #prompt {
    height: 1;
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
/* The search prompt takes the footer's row while it is open, like nano's. */
#search {
    width: 100%;
    height: 1;
    padding: 0 1;
    background: ansi_default;
    color: ansi_default;
    display: none;
}
"""

BINDINGS: list[BindingType] = [
    # tab/enter are the primary keys here; the ctrl chords stay as aliases.
    # tab needs priority to beat Textual's focus-next binding.
    Binding("tab", "add_child", "child", priority=True, id="add_child"),
    Binding("ctrl+a", "add_child", "child", show=False, id="add_child_alt"),
    Binding("enter", "add_sibling", "sib", id="add_sibling"),
    Binding("ctrl+j", "add_sibling", "sib", show=False, id="add_sibling_alt"),
    # Five of these have earned a bare key: they are reached for constantly and
    # collide with nothing, since h/j/k/l are the only bare letters spoken for.
    Binding("e", "edit", "edit", id="edit"),
    Binding("ctrl+e", "edit", "edit", show=False, id="edit_alt"),
    Binding("ctrl+d", "delete", "del", id="delete"),
    Binding("t", "fold", "fold", id="fold"),
    Binding("ctrl+t", "fold", "fold", show=False, id="fold_alt"),
    Binding("g", "mark", "mark", id="mark"),
    Binding("ctrl+g", "mark", "mark", show=False, id="mark_alt"),
    # search sits with the other editing keys: it is what you reach for while
    # reading a map, and the bar has room for one more
    Binding("ctrl+f", "search", "search", id="search"),
    # rendered as the pinned cluster at the right edge, not among the hints
    Binding("ctrl+comma", "settings", "settings", show=False, id="settings"),
    Binding("ctrl+slash", "help", "help", show=False, id="help"),
    # nano's cursor keys, kept spatial: ^P/^N walk the branch, ^B/^F move away
    # from the root or towards it — whichever way that happens to be drawn.
    # Arrows and, further down, hjkl are aliases for the same four actions.
    Binding("ctrl+p,up", "prev", "prev", show=False, id="prev"),
    Binding("ctrl+n,down", "next", "next", show=False, id="next"),
    Binding("ctrl+b,left", "go_left", "left", show=False, id="left"),
    Binding("right", "go_right", "right", show=False, id="right"),
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
    Binding("equals_sign", "spacing_more", "looser", id="spacing_more"),
    Binding("minus", "spacing_less", "tighter", id="spacing_less"),

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

#: What ↑ and ↓ do in each shape. The siblings always sit side by side; it is the
#: level that moves. A pyramid hangs its children below the parent, so down goes
#: deeper; a bush hangs them above it, so up goes deeper and down goes home.
UP_MEANING: dict[str, str] = {
    "spider": "prev",
    "branch": "prev",
    "pyramid": "parent",
    "bush": "child",
}

DOWN_MEANING: dict[str, str] = {
    "spider": "next",
    "branch": "next",
    "pyramid": "child",
    "bush": "parent",
}


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
        demo: bool = False,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.config: Config = load_config(self.config_path)
        self.theme = "textual-ansi"
        # No file named means a new buffer: spoider never guesses at one. The
        # default location is only *offered* when you first write it out.
        self.path: Path | None = Path(path) if path is not None else None
        self.has_file = self.path is not None and self.path.exists()
        self.load_error: str | None = None
        if self.has_file and self.path is not None:
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
        #: What was typed into the search prompt; empty means no search is on.
        self.search_query = ""
        #: Ids of the cells that contain it, in document order.
        self.matches: list[str] = []
        self._last_query = ""  # the last one submitted, to know a repeat
        self._search_history: list[str] = []
        self._write_then_quit = False
        self._settings_row = 0
        #: keys | search | write | marks | ask | settings | help
        self._mode = "keys"
        self._show_matches = False  # the count sits in the bar only for a while
        self._count_timer = None
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
        # whatever the app has to ask is asked here, above the bar, and never in
        # a window over the map: one bar, and it says what the question accepts
        yield PanelBar(id="panel")
        yield AskBar(id="ask")
        yield PromptBar(id="prompt")
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

    def on_app_focus(self, event: events.AppFocus) -> None:
        """Come back to the terminal exactly where you left it."""
        self._restore_focus()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Only the open drawer may hold the keys.

        Coming back to a window is usually a click, and a click focuses whatever
        is under the pointer — the map, behind a drawer that is still on screen.
        Rather than police individual events, the rule is enforced wherever focus
        lands: if a drawer is open, it takes the focus back.
        """
        owner = self._drawer_owner()
        if owner is not None and self.focused is not owner:
            self.call_later(owner.focus)

    def _drawer_owner(self):
        """The widget that must hold the keys for the current mode, if any."""
        if self._mode in ("search", "write", "marks"):
            return self.query_one(PromptBar)
        if self._mode == "ask":
            return self.query_one(AskBar)
        if self._mode in ("settings", "help"):
            return self.query_one(PanelBar)
        return None

    def _restore_focus(self) -> None:
        if not self.is_mounted:
            return
        owner = self._drawer_owner()
        (owner or self.view).focus()

    def _title(self) -> str:
        marker = " *" if self.dirty else ""
        return f"spoider — {self.path.name if self.path else 'untitled'}{marker}"

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
        """Nothing from the app keymap fires while a drawer or a cell has the
        keys: ^D must not delete the node you are editing, and ^X must not quit
        from behind a question."""
        if self._mode not in ("keys", "edit"):
            return None  # the drawer owns the keys, and its bar says so
        if action in ("help", "settings"):
            return True  # reachable while typing, without losing the edit
        if self.editing:
            return None
        return True

    @property
    def _searching(self) -> bool:
        return self._mode == "search"

    @property
    def mode(self) -> str:
        """Who has the keys: the map, a cell being typed into, or a drawer."""
        if self._mode == "keys" and self.editing:
            return "edit"
        return self._mode

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

    #: How long the match count stays up after a search is taken, in seconds.
    MATCH_COUNT_SECONDS = 2.0

    def stat_text(self) -> str:
        """What the top bar counts: the matches just after a search, else cells."""
        if self._show_matches and self.search_query.strip():
            found = len(self.matches)
            return f"{found} match" if found == 1 else f"{found} matches"
        cells = self.mm.count()
        return f"{cells} cell" if cells == 1 else f"{cells} cells"

    # -- search ---------------------------------------------------------

    def action_search(self) -> None:
        """^F — find cells by their words, nano style: a prompt on the last line."""
        if self._mode not in ("keys", "edit"):
            return
        self._show_matches = True
        self._stop_count_timer()
        offered = self._search_history[0] if self._search_history else ""
        self._show_prompt(
            "search",
            "Search: ",
            offered,
            preselect=True,
            recall=self._search_history,
            change=self._search_changed,
            submit=self._search_submitted,
            cancel=self._search_cancelled,
        )

    def _search_changed(self, value: str) -> None:
        self.search_query = value
        self._show_matches = True
        self._refresh_matches()

    def _search_submitted(self, query: str) -> None:
        repeat = bool(self.matches) and query.casefold() == self._last_query.casefold()
        self._last_query = query
        self.search_query = query
        self._refresh_matches()
        self._close_drawers()
        if not self.matches:
            self._settle_count()
            self.notify(f"No match for {query!r}" if query else "Nothing to find", timeout=2)
            return
        self._jump_to_match(skip_current=repeat)
        # the count has made its point: back to the cell count shortly
        self._stop_count_timer()
        self._count_timer = self.set_timer(self.MATCH_COUNT_SECONDS, self._settle_count)

    def _settle_count(self) -> None:
        self._count_timer = None
        if self._mode != "search":
            self._show_matches = False
        self._refresh_chrome()

    def _stop_count_timer(self) -> None:
        if self._count_timer is not None:
            self._count_timer.stop()
            self._count_timer = None

    def _search_cancelled(self) -> None:
        self.search_query = ""
        self._last_query = ""
        self.matches = []
        self._show_matches = False
        self._stop_count_timer()
        self._close_drawers()
        self.view.refresh_map()
        self._refresh_chrome()

    def _refresh_matches(self) -> None:
        query = self.search_query.strip()
        self.matches = [node.id for node in self.mm.nodes() if find_all(label(node), query)]
        self.view.refresh_map()
        self._refresh_chrome()

    def _jump_to_match(self, *, skip_current: bool) -> None:
        """Select the next match from here, wrapping — nano's forward search."""
        order = [node.id for node in self.mm.nodes()]
        if not order or not self.matches:
            return
        try:
            start = order.index(self.selected)
        except ValueError:
            start = 0
        offset = 1 if skip_current else 0
        for step in range(offset, len(order) + offset):
            candidate = order[(start + step) % len(order)]
            if candidate in self.matches:
                self._reveal(candidate)
                return

    def _reveal(self, node_id: str) -> None:
        """Open the folds above a match, so that selecting it actually shows it."""
        opened = False
        for node in self.mm.path(node_id)[:-1]:
            if node.collapsed:
                node.collapsed = False
                opened = True
        if opened:
            self._mark_dirty()
        self.select(node_id)

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
        if self.path is None:  # a new buffer has nowhere to go yet
            return False
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
        if self.search_query:
            self._refresh_matches()
        if self.autosave and self.path is not None:
            self._autosave()
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
        self._write_then_quit = then_quit
        self._show_prompt(
            "write",
            "File name to write: ",
            self._suggested_name(),
            preselect=True,
            submit=self._write_submitted,
            cancel=self._close_drawers,
        )

    def _suggested_name(self) -> str:
        """What to offer in the write prompt.

        The file the buffer belongs to, if it has one. A new buffer is offered
        the default place only while that is free: offering a path that already
        holds someone's map would turn "press enter" into "overwrite it".
        """
        if self.path is not None:
            return str(self.path)
        fallback = default_path()
        return "" if fallback.exists() else str(fallback)

    def _write_submitted(self, value: str) -> None:
        self._close_drawers()
        if not value.strip():
            return
        target = Path(value).expanduser()
        if target.is_dir():
            self.notify(f"{target} is a directory", severity="error", timeout=4)
            return
        if self._write(target) and self._write_then_quit:
            self.exit()

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
        """The bar never leaves; it swaps to the keys of whatever has them now."""
        footer = self.query_one("#footer", FooterBar)
        mode = self._mode
        if mode in ("keys", "edit"):
            footer.mode = "edit" if self.editing else "keys"
        elif mode == "search":
            footer.mode = "search"
        elif mode in ("write", "marks"):
            footer.mode = "custom"
            footer.custom = prompt_chunks("write" if mode == "write" else "save")
        elif mode == "ask":
            footer.mode = "custom"
            footer.custom = ask_chunks()
        elif mode == "settings":
            footer.mode = "custom"
            footer.custom = settings_chunks()
        else:  # help closes on any key, and saying so is the one thing it need not
            footer.mode = "custom"
            footer.custom = []
        footer.refresh()

    # -- the drawers themselves ------------------------------------------

    def _hide_drawers(self, *keep: type) -> None:
        """Only one drawer is ever on screen: they share the bottom lines."""
        for drawer in (PromptBar, AskBar, PanelBar):
            if drawer not in keep:
                self.query_one(drawer).close()

    def _show_prompt(
        self,
        mode: str,
        label: str,
        value: str = "",
        *,
        preselect: bool = False,
        recall: list[str] | None = None,
        change=None,
        submit,
        cancel,
    ) -> None:
        self._mode = mode
        self._hide_drawers(PromptBar)
        self.query_one(PromptBar).ask(
            label,
            value,
            preselect=preselect,
            recall=recall,
            submit=submit,
            cancel=cancel,
            change=change,
        )
        self._sync_footer()
        self._refresh_chrome()

    def _close_drawers(self) -> None:
        """Put the drawers away and give the keys back — to the cell being typed
        into, or to the map."""
        for drawer in (PromptBar, AskBar, PanelBar):
            self.query_one(drawer).close()
        self._mode = "keys"
        self._sync_footer()
        self.view.focus()
        self._refresh_chrome()

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
        self._mode = "help"
        self._hide_drawers(PanelBar)
        self.query_one(PanelBar).show(help_text(self), lambda key: self._close_drawers())
        self._sync_footer()

    def action_settings(self) -> None:
        """^, — the editor settings."""
        self._settings_row = 0
        self._open_settings()

    def _open_settings(self) -> None:
        self._mode = "settings"
        self._draw_settings()

    def _draw_settings(self) -> None:
        row = settings_text(self, self._settings_row)
        self._hide_drawers(PanelBar)
        self.query_one(PanelBar).show(row, self._settings_key)
        self._sync_footer()

    def _ask_to_save(self) -> None:
        self._mode = "ask"
        self._hide_drawers(AskBar)
        self.query_one(AskBar).ask("Save modified buffer?", self._save_answered)
        self._sync_footer()

    def _settings_key(self, key: str) -> None:
        if key in ("escape", "ctrl+c", "ctrl+comma", "ctrl+x"):
            self._close_drawers()
        elif key in ("up", "k"):
            self._settings_row = max(0, self._settings_row - 1)
            self._draw_settings()
        elif key in ("down", "j"):
            self._settings_row = min(2, self._settings_row + 1)
            self._draw_settings()
        elif key in ("enter", "space"):
            self._settings_activate()

    def _settings_activate(self) -> None:
        row = self._settings_row
        if row == 0:
            self.set_autosave(not self.autosave)
            self._draw_settings()
        elif row == 1:
            self._show_prompt(
                "marks",
                "Marks, in the order ^G cycles: ",
                " ".join(self.marks),
                preselect=True,
                submit=self._marks_submitted,
                cancel=self._open_settings,
            )
        else:
            self.open_config()
            self._open_settings()  # back to the list you left

    def _marks_submitted(self, value: str) -> None:
        self.set_marks(value.split())
        self._open_settings()

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
        From the root itself, left is its left-hand branch. Where the levels are
        stacked the siblings sit side by side, so left is simply the one before."""
        if self._sideways_arrows_are_siblings:
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
        if self._sideways_arrows_are_siblings:
            self.select(nav.to_sibling(self.mm, self.selected, +1))
            return
        if self._at_root:
            self._from_root(+1)
        elif nav.side(self.mm, self.selected, self.mm.layout) < 0:
            self._to_parent()
        else:
            self._into_child()

    @property
    def _sideways_arrows_are_siblings(self) -> bool:
        """True when the levels are stacked, so ← / → walk the row of siblings
        and ↑ / ↓ are left to cross a level."""
        return self.mm.layout in ("pyramid", "bush")

    def action_prev(self) -> None:
        """^P / ↑ — whatever is above the selection in this shape."""
        self._move(UP_MEANING[self.mm.layout])

    def action_next(self) -> None:
        """^N / ↓ — whatever is below the selection in this shape."""
        self._move(DOWN_MEANING[self.mm.layout])

    def _move(self, kind: str) -> None:
        if kind == "prev":
            self.select(nav.to_sibling(self.mm, self.selected, -1))
        elif kind == "next":
            self.select(nav.to_sibling(self.mm, self.selected, +1))
        elif kind == "parent":
            self._to_parent()
        else:  # "child"
            self._into_child()

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
        """^L — cycle the shape of the map: spider, pyramid, bush, branch."""
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
        """^S — write straight back to the current file. A new buffer has no file
        yet, so it asks for one, the way nano does."""
        if self.path is None:
            self._ask_where_to_write()
            return
        self._write(self.path)

    def action_write(self) -> None:
        """^O — nano's Write Out: always asks which file to write."""
        self._ask_where_to_write()

    async def action_quit(self) -> None:
        """^X — nano's Exit: never throw away a modified buffer silently."""
        if self.autosave and self.path is not None:
            if self.dirty and not self._autosave():
                return  # the write failed; keep the buffer and stay
            self.exit()
            return
        if not self.dirty:
            self.exit()
            return

        self._ask_to_save()

    def _save_answered(self, choice: str | None) -> None:
        self._close_drawers()
        if choice == "no":
            self.exit()
        elif choice == "yes":
            self._ask_where_to_write(then_quit=True)


def default_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "spoider" / "map.json"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="spoider", description="TUI mind map editor")
    parser.add_argument(
        "path",
        nargs="?",
        help="map file to open; without one, spoider starts a new buffer",
    )
    parser.add_argument(
        "--demo", action="store_true", help="start with the demo map instead of an empty buffer"
    )
    args = parser.parse_args(argv)
    path = Path(args.path).expanduser() if args.path else None
    SpoiderApp(path, demo=args.demo).run()


if __name__ == "__main__":
    main()
