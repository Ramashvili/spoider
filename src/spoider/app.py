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
from textual.binding import Binding
from textual.notifications import SeverityLevel

from .actions_edit import EditActions
from .actions_map import MapActions
from .actions_stack import StackActions
from .addressing import parse as parse_address
from .addressing import resolve as resolve_address
from .chrome import (
    FooterBar,
    ask_chunks,
    help_chunks,
    prompt_chunks,
    settings_chunks,
)
from .config import (
    Config,
    default_config_path,
    is_stale,
    load_config,
    write_config,
)
from .desktop import install_desktop, registered
from .drawers import AskBar, PanelBar, PromptBar
from .editing import Buffer
from .files import SUFFIX, default_path
from .keys import (
    BINDINGS,
    action_chords,
    build_action_keymap,
    build_keymap,
)
from .layout import label
from .model import MapFileError, MindMap, Node, marks_of
from .nav import to_end, to_extreme_sibling, to_home
from .screens import help_text, settings_text
from .text import clean, find_all, one_line
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
/* A row of air under the header and under the map, so the map does not butt
   against either. Only when the window is tall enough to spare the rows: at the
   height below, every row is content and the air goes first. The drawers are not
   wrapped: a panel already keeps a blank line above the bar, and one is enough. */
Screen.roomy #topbar {
    margin-bottom: 1;
}
Screen.roomy MindMapView {
    margin-bottom: 1;
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
/* Toasts are about what just happened, so they carry a meaning: green when it
   worked, yellow for a cut or a paste, red when it did not. They hang from the
   top right corner, over the map, where they do not cover the bar. */
ToastRack {
    dock: top;
    align: right top;
    margin-top: 1;
    margin-bottom: 0;
}
Toast {
    width: 44;
    max-width: 50%;
}
/* Bright tones, all three from the palette: the app has no colours of its own,
   and one bright and two dim would say more about the terminal than the message. */
Toast.-information {
    color: ansi_bright_green;
    border-left: outer ansi_bright_green;
}
Toast.-warning {
    color: ansi_bright_yellow;
    border-left: outer ansi_bright_yellow;
}
Toast.-error {
    color: ansi_bright_red;
    border-left: outer ansi_bright_red;
}
"""


#: What ↑ and ↓ do in each shape. The siblings always sit side by side; it is the
#: level that moves. A pyramid hangs its children below the parent, so down goes
#: deeper; a bush hangs them above it, so up goes deeper and down goes home.









def editor_command() -> list[str]:
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        return shlex.split(raw) or ["nano"]
    except ValueError:  # unbalanced quotes in $EDITOR / $VISUAL
        return ["nano"]


def edit_in_editor(path: Path) -> None:
    """Run the user's editor on a file, in the foreground."""
    subprocess.run([*editor_command(), str(path)], check=False)




class SpoiderApp(MapActions, StackActions, EditActions, App[None]):
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
        position: str | None = None,
    ) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.config: Config = load_config(self.config_path, self._binding_ids())
        self.theme = "textual-ansi"
        # No file named means a new buffer: spoider never guesses at one. The
        # default location is only *offered* when you first write it out.
        self.path: Path | None = Path(path) if path is not None else None
        self.has_file = self.path is not None and self.path.exists()
        self.load_error: str | None = None
        if self.has_file and self.path is not None:
            try:
                self.mm = MindMap.load(self.path, marks=self.config.marks_default)
            except MapFileError as exc:
                # Starting on an empty map beats a traceback on the terminal; the
                # reason is reported once the screen exists. The path is dropped with
                # it: the file is not a map, and ^S must never quietly replace it.
                self.mm = MindMap(marks=self.config.marks_default)
                self.has_file = False
                self.path = None
                self.load_error = str(exc)
        else:
            self.mm = MindMap.demo() if demo else MindMap(marks=self.config.marks_default)
        self.selected: str = self.mm.root.id
        #: Where `--position` asked the cursor to start; resolved once the screen exists.
        self.start_position = position
        #: The properties overlay: off by default, a debugging aid rather than furniture.
        self.show_properties = False
        #: The last cell whose text or mark was changed, for the overlay to name.
        self.last_edited: str | None = None
        #: The far end of a run of selected siblings; None means one cell.
        self.anchor: str | None = None
        #: Id of the cell selected inside the stack panel; None when it is shut.
        #: Whether the cut stack has the keys, and where the map's cursor waits
        #: while it does: the cursor itself is `selected`/`anchor` in both places.
        self._stack_open = False
        self._map_cursor: tuple[str | None, str | None] | None = None
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
        #: The words the open yes/no question offers, so the bar can name them.
        self._ask_words: tuple[str, str] = ("save", "discard")
        self._show_matches = False  # the count sits in the bar only for a while
        self._count_timer = None
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._edit_id: str | None = None
        self._buffer: Buffer | None = None
        #: Text cut or copied out of a cell. Kept here as well as pushed to the
        #: system clipboard, because reading that back needs a query a terminal may
        #: not answer.
        self._text_clip = ""
        self._justify_id: str | None = None
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

    #: Rows a window needs before it can afford air around the map: below this,
    #: two rows of map are worth more than the tidier picture.
    ROOMY_HEIGHT = 30

    def on_resize(self, event: events.Resize) -> None:
        """Give the bars a row of air each while the window can spare them."""
        self.screen.set_class(event.size.height > self.ROOMY_HEIGHT, "roomy")

    def on_mount(self) -> None:
        # A file written by an older build keeps listing chords that no longer
        # exist; regenerate it, but only when it is actually out of date.
        if is_stale(self.config_path, self.config, self._key_entries()):
            self._save_config()
        if self.load_error is not None:
            self.notify(self.load_error, severity="error", timeout=8)
        self.set_keymap(build_action_keymap(self.config.keys))
        self._set_terminal_title()
        self._apply_start_position()
        self.query_one(MindMapView).focus()
        self._offer_desktop_once()

    def action_go_home(self) -> None:
        """`home` — the main cell of the tree the cursor is in, hierarchy only."""
        self.select(to_home(self.mm, self.selected))

    def action_go_end(self) -> None:
        """`end` — the deepest cell below this one, hierarchy only."""
        self.select(to_end(self.mm, self.selected))

    def action_top_sibling(self) -> None:
        """`pageup` — the first sibling under the same parent."""
        self.select(to_extreme_sibling(self.mm, self.selected, last=False))

    def action_bottom_sibling(self) -> None:
        """`pagedown` — the last sibling under the same parent."""
        self.select(to_extreme_sibling(self.mm, self.selected, last=True))

    def action_toggle_properties(self) -> None:
        """`i` — the file's own properties, drawn over the top-left of the map."""
        self.show_properties = not self.show_properties
        self.view.refresh()
        self._sync_footer()

    def _touched(self, node_id: str | None) -> None:
        """Remember the cell a change happened in, so the overlay can name it."""
        if node_id:
            self.last_edited = node_id

    def _apply_start_position(self) -> None:
        """Where the cursor starts: the address if one was given, else the map's own
        memory of where it was, else the root.

        A cell on the cut stack opens the panel first, because a cell you cannot see is
        not a place the cursor can be.
        """
        found: str | None = None
        in_stack = False
        if self.start_position is not None:
            address = parse_address(self.start_position)
            if address is not None:
                found = resolve_address(self.mm, address)
                in_stack = address.stack
        elif self.mm.cursor:
            found, in_stack = self._find_saved_cursor(self.mm.cursor)
        if not found:
            return
        if in_stack:
            self.action_toggle_stack()
            self._stack_select(self._stack_doc(), found)
            return
        self.selected = found
        self.anchor = None

    def _find_saved_cursor(self, ident: str) -> tuple[str | None, bool]:
        """The id, and whether it names a cut rather than a cell in the map."""
        if self.mm.find(ident) is not None:
            return ident, False
        for entry in self.mm.cut_stack:
            if any(node.id == ident for node in entry.walk()):
                return ident, True
        return None, False

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
        """The widget that must hold the keys: whatever prompt is on screen.

        Reading the widget rather than a list of mode names is the point. A mode
        added later — justify was one — keeps the keys on return without anyone
        remembering to add it here, which is how a prompt came to be left open with
        the map taking its keys.
        """
        for kind in (PromptBar, AskBar, PanelBar):
            drawer = self.query_one(kind)
            if drawer.display:
                return drawer
        return None

    def _restore_focus(self) -> None:
        if not self.is_mounted:
            return
        owner = self._drawer_owner()
        (owner or self.view).focus()

    def _title(self) -> str:
        marker = " *" if self.dirty else ""
        name = clean(self.path.name) if self.path else "untitled"
        return f"spoider — {name}{marker}"

    def _set_terminal_title(self) -> None:
        """Mirror the buffer into the terminal title, where the unsaved marker is
        visible even when the top bar is scrolled out of sight.

        The file name is untrusted — it can contain an ESC — and this string is
        written straight to the terminal, so it is cleaned like any other text.
        """
        driver = getattr(self, "_driver", None)
        if driver is not None:
            driver.write(f"\x1b]2;{clean(self._title())}\x07")

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: SeverityLevel = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """A toast is written straight to the terminal, and some of what goes into
        one is untrusted — a file name, a cell's text, a parse error quoting the
        file. Clean it here so no call site has to remember, and flatten it: a toast
        is one row, so the line break in a cell's text becomes a space instead of
        joining two words."""
        super().notify(
            one_line(message),
            title=one_line(title),
            severity=severity,
            timeout=timeout,
            markup=markup,
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Nothing from the app keymap fires while a drawer or a cell has the
        keys: ^D must not delete the node you are editing, and ^X must not quit
        from behind a question.

        """
        if self._mode not in ("keys", "edit"):
            return None  # the drawer owns the keys, and its bar says so
        # The stack panel is the map with one difference, and it consumes the keys
        # it implements itself (cut, paste, delete, edit, new cells, marks, folds,
        # undo) before a binding can see them. What is left — save, quit, colours,
        # shape, spacing, help — means the same thing in both places, so it runs.
        if action in ("help", "settings"):
            return True  # reachable while typing, without losing the edit
        if self.editing:
            return None
        return True

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
    def stack_open(self) -> bool:
        """True while the cut stack is open in its own panel."""
        return self._stack_open

    @property
    def selected_ids(self) -> list[str]:
        """What an action applies to: a run of siblings, or just one cell."""
        if self.anchor is None or self.anchor == self.selected:
            return [self.selected]
        return self.document.range_between(self.anchor, self.selected)

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

    @staticmethod
    def _binding_ids() -> set[str]:
        """Every id the config file may name: the chords this build can bind."""
        return {binding.id for binding in BINDINGS if isinstance(binding, Binding) and binding.id}

    def _key_entries(self) -> list[tuple[str, str, str]]:
        """(id, every chord that action answers to, what it does), one line each.

        Aliases share their action's line: two entries saying the same thing would
        be two places to keep in step.
        """
        from .screens import describe_action

        chords = action_chords()
        entries: list[tuple[str, str, str]] = []
        seen: set[str] = set()
        for binding in BINDINGS:
            if not isinstance(binding, Binding) or not binding.id or binding.action in seen:
                continue
            seen.add(binding.action)
            entries.append(
                (
                    binding.id,
                    " ".join(chords[binding.action]),
                    describe_action(binding.action, binding.description),
                )
            )
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

        self.config = load_config(self.config_path, self._binding_ids())
        self.set_keymap(build_action_keymap(self.config.keys))  # new chords take effect straight away
        self._refresh_chrome()
        self.notify("Config reloaded", timeout=2)

    @property
    def marks(self) -> tuple[str, ...]:
        """The marks this map cycles through, in the order m walks them."""
        return self.mm.marks

    def set_marks(self, marks: Iterable[object]) -> None:
        """The palette is the map's, so it goes into the map rather than the rc."""
        cleaned = marks_of(marks)
        if cleaned == self.mm.marks:
            return
        self.mm.marks = cleaned
        self._mark_dirty()

    def _save_config(self) -> None:
        try:
            write_config(self.config, self.config_path, self._key_entries())
        except OSError as exc:
            self.notify(f"Could not write config: {exc}", severity="error", timeout=4)

    #: How long the match count stays up after a search is taken, in seconds.
    MATCH_COUNT_SECONDS = 2.0

    def cut_stat(self) -> str:
        """How many cuts are waiting, always shown: an empty stack is a fact about
        the document too, and a count that appears and disappears is harder to
        read than one that sits at zero."""
        count = len(self.mm.cut_stack)
        return "1 cut in stack" if count == 1 else f"{count} cuts in stack"

    def stat_text(self) -> str:
        """What the top bar counts: the matches just after a search, else cells."""
        if self._show_matches and self.search_query.strip():
            found = len(self.matches)
            return f"{found} match" if found == 1 else f"{found} matches"
        cells = self.mm.count()
        return "1 cell total" if cells == 1 else f"{cells} cells total"

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
            self.notify(
                f"No match for {query!r}" if query else "Nothing to find",
                severity="error",
                timeout=2,
            )
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
        """Move the cursor; a plain move gives up the run of selected cells."""
        self.anchor = None
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
        self._set_terminal_title()
        self.view.refresh_map()
        self._refresh_chrome()
        if self.autosave:
            self._autosave()  # one write per change, after the screen agrees

    def _write(self, path: Path) -> bool:
        # the file remembers where the cursor was, so opening it returns there
        self.mm.cursor = self.selected
        try:
            self.mm.save(path)
        except OSError as exc:
            self.notify(f"Could not write {clean(str(path))}: {exc}", severity="error", timeout=4)
            return False
        self.path = path
        self.has_file = True
        self.dirty = False
        self._set_terminal_title()
        self._refresh_chrome()
        self.notify(f"Wrote {self.mm.count()} nodes to {clean(path.name)}", timeout=2)
        return True

    def _ask_where_to_write(self, *, then_quit: bool = False) -> None:
        self._write_then_quit = then_quit
        offered, caret = self._write_offer()
        self._show_prompt(
            "write",
            "File name to write: ",
            offered,
            cursor=caret,
            submit=self._write_submitted,
            cancel=self._close_drawers,
        )

    def _write_offer(self) -> tuple[str, int]:
        """What the write prompt offers, and where the caret sits.

        The name comes with the map suffix already on it and the caret just before it, so
        the first keystroke edits the name and the suffix stays put.
        """
        name = self._suggested_name()
        if not name:
            return "", 0
        if name.endswith(SUFFIX):
            return name, len(name) - len(SUFFIX)
        # a name with no suffix of its own gets one; an existing file of any other kind
        # is left exactly as the reader named it
        if Path(name).suffix:
            return name, len(name)
        return f"{name}{SUFFIX}", len(name)

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
            self.mm = MindMap.from_dict(snapshot, marks=self.mm.marks)
        except MapFileError as exc:  # only reachable if a snapshot were corrupt
            self.notify(f"Cannot restore that state: {exc}", severity="error", timeout=4)
            return
        if self.mm.find(self.selected) is None:
            self.selected = self.mm.root.id
        # the anchor belongs to the document we just replaced
        self.anchor = None
        self._mark_dirty()

    # -- inline editing -------------------------------------------------

    @property
    def editing(self) -> bool:
        return self._edit_id is not None

    def _live_node(self, node_id: str) -> Node | None:
        """A cell by id: from the map, or from the stack when that has the keys."""
        if self.stack_open:
            found = self._stack_doc().find(node_id)
            if found is not None:
                return found
        return self.mm.find(node_id)



    def _sync_footer(self) -> None:
        """The bar never leaves; it swaps to the keys of whatever has them now."""
        footer = self.query_one("#footer", FooterBar)
        mode = self._mode
        if mode in ("keys", "edit"):
            if self.editing:
                footer.mode = "edit"
            elif self.stack_open:
                footer.mode = "stack"
            else:
                footer.mode = "keys"
        elif mode == "search":
            footer.mode = "search"
        elif mode in ("write", "marks", "justify"):
            footer.mode = "custom"
            footer.custom = prompt_chunks("save" if mode == "marks" else mode)
        elif mode == "ask":
            footer.mode = "custom"
            footer.custom = ask_chunks(*self._ask_words)
        elif mode == "settings":
            footer.mode = "custom"
            footer.custom = settings_chunks()
        else:  # help
            footer.mode = "custom"
            footer.custom = help_chunks()
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
        cursor: int | None = None,
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
            cursor=cursor,
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





    # -- justify ---------------------------------------------------------------




    # -- editing actions ------------------------------------------------











    @property
    def document(self) -> MindMap:
        """The tree the keys are in.

        The stack panel is an ordinary MindMap built over the same Node objects, so
        everything below can work on `self.document` and mean the right thing in
        both places: editing, marks, folds, justify, new cells.
        """
        return self._stack_doc() if self.stack_open else self.mm

    @property
    def focus(self) -> str:
        """The cell the keys are on, in whichever document has them."""
        return self.selected












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
        row.append("\n")  # one line of air between the rows and the bar
        self._hide_drawers(PanelBar)
        self.query_one(PanelBar).show(row, self._settings_key)
        self._sync_footer()

    def _ask_to_save(self) -> None:
        self._ask_words = ("save", "discard")
        self._mode = "ask"
        self._hide_drawers(AskBar)
        self.query_one(AskBar).ask("Save modified buffer?", self._save_answered)
        self._sync_footer()

    def _offer_desktop_once(self) -> None:
        """Ask, on the first run, whether .spoider files should open in spoider.

        Installation cannot do it: neither `uv tool install` nor any wheel runs code at
        install time, so the first launch is the first moment the program can ask.
        """
        if self.config.desktop_asked or registered():
            return
        self._ask_words = ("register", "not now")
        self._mode = "ask"
        self._hide_drawers(AskBar)
        self.query_one(AskBar).ask(
            "Open .spoider files with spoider from now on?", self._desktop_answered
        )
        self._sync_footer()

    def _desktop_answered(self, choice: str | None) -> None:
        self._close_drawers()
        self.config.desktop_asked = True
        self._save_config()
        if choice == "yes":
            install_desktop()
            self.notify("A .spoider map now opens with spoider", timeout=3)

    def _settings_key(self, key: str) -> None:
        if key in ("escape", "ctrl+c", "ctrl+comma", "ctrl+x"):
            self._close_drawers()
        elif key in ("up", "k"):
            self._settings_row = max(0, self._settings_row - 1)
            self._draw_settings()
        elif key in ("down", "j"):
            self._settings_row = min(1, self._settings_row + 1)
            self._draw_settings()
        elif key in ("enter", "space"):
            self._settings_activate()

    def _settings_activate(self) -> None:
        if self._settings_row == 0:
            self.set_autosave(not self.autosave)
            self._draw_settings()
            return
        self.open_config()
        self._open_settings()  # back to the list you left





    # -- movement -------------------------------------------------------



























    # -- history and files ----------------------------------------------

    def action_undo(self) -> None:
        if not self._undo:
            self.notify("Nothing to undo", severity="error", timeout=1)
            return
        self._redo.append(self.mm.to_dict())
        self._restore(self._undo.pop())

    def action_redo(self) -> None:
        if not self._redo:
            self.notify("Nothing to redo", severity="error", timeout=1)
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




def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="spoider",
        description="TUI mind map editor: one map, one bar of keys, your terminal's colours.",
        epilog="tab makes a child, return a sibling, the arrows walk the canvas, "
        "and ^/ lists every key once the program is open.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="map file to open; without one, spoider starts a new buffer",
    )
    parser.add_argument(
        "-d",
        "--demo",
        action="store_true",
        help="start with the manual as a map instead of an empty buffer",
    )
    parser.add_argument(
        "-p",
        "--position",
        default=None,
        metavar="ADDRESS",
        help="cell to put the cursor on: 0 is the root, 9 the ninth child, 7.4.9 a path "
        "down, s2 or s2.1 a cell on the cut stack; anything else starts at the root",
    )
    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="register .spoider files with the desktop, then exit",
    )
    args = parser.parse_args(argv)
    if args.position is not None and not args.position.strip():
        parser.error("-p/--position needs an address: 0 for the root, 7.4.9 for a path")
    if args.install_desktop:
        raise SystemExit(install_desktop())
    path = Path(args.path).expanduser() if args.path else None
    SpoiderApp(path, demo=args.demo, position=args.position).run(mouse=False)


if __name__ == "__main__":
    main()
