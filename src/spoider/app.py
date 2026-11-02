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
from textual.notifications import SeverityLevel

from . import nav
from .chrome import FooterBar, ask_chunks, help_chunks, key_cap, prompt_chunks, settings_chunks
from .config import (
    Config,
    default_config_path,
    is_stale,
    load_config,
    write_config,
)
from .drawers import AskBar, PanelBar, PromptBar
from .editing import Buffer, reflow
from .layout import MAX_SPACING, MIN_SPACING, compute_stack, label
from .model import LAYOUTS, MapFileError, MindMap, Node, marks_of
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
Toast .toast--title {
    text-style: bold;
}
"""

BINDINGS: list[BindingType] = [
    # tab/enter are the primary keys here; the ctrl chords stay as aliases.
    # tab needs priority to beat Textual's focus-next binding.
    Binding("tab", "add_child", "child", priority=True, id="add_child"),
    # ^A selects: the whole text while typing, every sibling on the map
    Binding("ctrl+a", "select_all", show=False, id="select_all"),
    Binding("enter", "add_sibling", "sib", id="add_sibling"),
    Binding("ctrl+j", "justify", "justify", id="justify"),
    Binding("alt+6", "copy", "copy", show=False, id="copy"),
    # Five of these have earned a bare key: they are reached for constantly and
    # collide with nothing, since h/j/k/l are the only bare letters spoken for.
    Binding("e", "edit", "edit", id="edit"),
    Binding("ctrl+e", "edit", "edit", show=False, id="edit_alt"),
    Binding("ctrl+k", "cut", "cut", id="cut"),
    Binding("ctrl+u", "paste", "paste", id="paste"),
    Binding("ctrl+i", "toggle_stack", "show stack", id="toggle_stack"),
    Binding("ctrl+d", "delete", "del", id="delete"),
    Binding("t", "fold", "fold", id="fold"),
    Binding("ctrl+t", "fold", "fold", show=False, id="fold_alt"),
    Binding("m", "mark", "mark", id="mark"),
    Binding("ctrl+m", "set_marks", "set marks", id="set_marks"),
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
    # shift walks the same arrows the layout uses for siblings, so the run grows
    # in the direction the cells are drawn
    Binding("shift+up", "extend_prev", "select", show=False, id="extend_prev"),
    Binding("shift+down", "extend_next", "select", show=False, id="extend_next"),
    Binding("shift+left", "extend_left", "select", show=False, id="extend_left"),
    Binding("shift+right", "extend_right", "select", show=False, id="extend_right"),
    Binding("escape", "clear_selection", "clear", show=False, id="clear_selection"),
    Binding("alt+up", "move_up", "reorder up", show=False, id="move_up"),
    Binding("alt+down", "move_down", "reorder down", show=False, id="move_down"),
    # The spacing keys are bare = and -: the key names Textual produces for them
    # are the ones nobody would guess, and binding every spelling a terminal might
    # send made the bar, help and config list six keys for two jobs. If a terminal
    # cannot send these, rebind them in the config.
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
    # how the cells are coloured is a property of the document, so it sits with the
    # shape rather than in the settings
    Binding("c", "colours", "colours", id="colours"),
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


def action_chords(overrides: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Every chord each action answers to, in the order the bindings list them.

    A config line names one action and lists the chords it answers to, so the line
    is the whole truth for that action: a chord left off it stops working, which is
    what "the file says what the keys are" means. Defaults come from the binding
    table, split where a single binding already carries several keys ("ctrl+p,up").
    """
    chords: dict[str, list[str]] = {}
    action_of: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        action_of[binding.id] = binding.action
        keys = [part for part in binding.key.split(",") if part]
        chords.setdefault(binding.action, []).extend(keys)
    for ident, value in (overrides or {}).items():
        action = action_of.get(ident)
        listed = [part for part in (value or "").split() if part]
        if action is not None and listed:
            chords[action] = listed
    return chords


def build_action_keymap(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """action -> "a,b", which is the shape Textual's own keymap wants."""
    return {action: ",".join(chords) for action, chords in action_chords(overrides).items()}


def default_keymap() -> dict[str, str]:
    """id -> the first chord that action was born with; the whole of it in
    `action_chords`, so the two cannot drift apart."""
    return build_keymap()


def editor_command() -> list[str]:
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        return shlex.split(raw) or ["nano"]
    except ValueError:  # unbalanced quotes in $EDITOR / $VISUAL
        return ["nano"]


def edit_in_editor(path: Path) -> None:
    """Run the user's editor on a file, in the foreground."""
    subprocess.run([*editor_command(), str(path)], check=False)


def build_keymap(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """id -> the first chord its action answers to, which is what the bars show.

    Unknown ids and blank lines are ignored, so a typo in the config cannot take a
    key away from you. The whole list lives in `action_chords`."""
    chords = action_chords(overrides)
    keymap: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        keymap.setdefault(binding.id, chords.get(binding.action, [binding.key])[0])
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
                # reason is reported once the screen exists.
                self.mm = MindMap(marks=self.config.marks_default)
                self.has_file = False
                self.load_error = str(exc)
        else:
            self.mm = MindMap.demo(marks=self.config.marks_default) if demo else MindMap(
                marks=self.config.marks_default
            )
        self.selected: str = self.mm.root.id
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
        file. Clean it here so no call site has to remember."""
        super().notify(
            clean(message), title=clean(title), severity=severity, timeout=timeout, markup=markup
        )

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Nothing from the app keymap fires while a drawer or a cell has the
        keys: ^D must not delete the node you are editing, and ^X must not quit
        from behind a question."""
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

    def begin_edit(self, node_id: str, *, fresh: bool = False) -> None:
        node = self._live_node(node_id)
        if node is None:
            return
        if not fresh:
            self._push_undo()
        self._edit_id = node_id
        self._edit_fresh = fresh
        self._buffer = Buffer("" if fresh else (node.text or ""))
        self._sync_preview()
        self._sync_footer()

    def _sync_preview(self) -> None:
        node = self._live_node(self._edit_id) if self._edit_id else None
        if node is None:
            return
        if self._buffer is None:
            return
        node.preview = self._buffer.text
        node.caret = self._buffer.caret
        node.overwrite = self._buffer.overwrite
        node.sel = self._buffer.selection()
        self.view.refresh_map()

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
            footer.custom = ask_chunks()
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
        """Every keystroke while typing into a cell. Returns True if consumed.

        The cell is a small text editor, so these are a text editor's keys: lines,
        a selection dragged out with shift, word deletes, an overwrite mode, cut
        and copy through the clipboard, and ^J to reflow the text. Enter keeps its
        meaning here, which is to finish the cell; a line break is its own key.
        """
        if not self.editing or self._buffer is None:
            return False
        buffer = self._buffer
        if key in ("ctrl+slash", "ctrl+comma"):
            return False  # help and settings stay reachable mid-typing

        if key == "enter":
            self.finish_edit(commit=True)
            return True
        if key in ("escape", "ctrl+c"):
            self.finish_edit(commit=False)
            return True

        base = key.removeprefix("shift+")
        extend = base != key
        moves = {
            "left": buffer.left,
            "right": buffer.right,
            "up": buffer.up,
            "down": buffer.down,
            "home": buffer.home,
            "end": buffer.end,
            "ctrl+e": buffer.end,
            "ctrl+home": buffer.document_home,
            "ctrl+end": buffer.document_end,
        }
        if base in moves:
            moves[base](extend=extend)
        elif key == "shift+enter":
            buffer.insert("\n")
        elif key == "backspace":
            buffer.backspace()
        elif key == "delete":
            buffer.delete()
        elif key in ("alt+backspace", "ctrl+w"):
            buffer.delete_word_before()
        elif key == "alt+d":
            buffer.delete_word_after()
        elif self._action_for(key) == "select_all":
            buffer.select_all()
        elif key == "insert":
            buffer.overwrite = not buffer.overwrite
        elif self._action_for(key) == "cut":
            self._cut_or_copy(cut=True)
        elif self._action_for(key) == "copy":
            self._cut_or_copy(cut=False)
        elif self._action_for(key) == "paste":
            buffer.insert(self._text_clip)
        elif self._action_for(key) == "justify":
            self.action_justify()
        elif self._action_for(key) == "undo":
            buffer.undo()
        elif self._action_for(key) == "redo":
            buffer.redo()
        elif character and character.isprintable():
            buffer.insert(character)
        self._sync_preview()
        return True

    def action_copy(self) -> None:
        """M-6 — copy text: the selection while typing, else the selected cell's."""
        if self.editing:
            self._cut_or_copy(cut=False)
            return
        node = self.document.find(self.focus)
        if node is None or not node.text.strip():
            return
        self._text_clip = node.text
        self.copy_to_clipboard(node.text)
        self.notify("Copied the cell's text", timeout=1)

    def _cut_or_copy(self, *, cut: bool) -> None:
        """^K cuts the selection out of a cell, M-6 copies it.

        With nothing selected the whole cell's text goes, which is what a box this
        size usually wants. The text also goes to the system clipboard (OSC 52), so
        it can leave spoider.
        """
        if self._buffer is None:
            return
        text = self._buffer.selected_text() or self._buffer.text
        if not text:
            return
        self._text_clip = text
        self.copy_to_clipboard(text)
        if cut:
            if self._buffer.selection() is None:
                self._buffer.select_all()
            self._buffer.insert("")

    def on_paste(self, event: events.Paste) -> None:
        """Text the terminal pasted (ctrl+shift+v) lands at the caret."""
        if self.editing and self._buffer is not None:
            self._buffer.insert(event.text)
            self._sync_preview()
            event.stop()

    # -- justify ---------------------------------------------------------------

    def action_justify(self) -> None:
        """^J — reflow a cell's text to a width you give, the way nano justifies."""
        node_id = self._edit_id if self.editing else self.focus
        if node_id is None:
            return
        self._justify_id = node_id
        self._show_prompt(
            "justify",
            "Justify to width: ",
            str(self.mm.justify or self.config.justify_width_default),
            preselect=True,
            submit=self._justify_submitted,
            cancel=self._close_drawers,
        )

    def _justify_submitted(self, value: str) -> None:
        self._close_drawers()
        try:
            width = int(value.strip())
        except ValueError:
            width = self.mm.justify or self.config.justify_width_default
        width = max(10, min(width, 400))
        if width != self.mm.justify:
            # the width is part of the map, so a file opened elsewhere justifies
            # the same way; the config only holds the default to offer
            self.mm.justify = width
            self._mark_dirty()
        node_id, self._justify_id = self._justify_id, None
        if node_id is None:
            return
        if self.editing and self._buffer is not None and node_id == self._edit_id:
            self._buffer.text = reflow(self._buffer.text, width)
            self._buffer.caret = min(self._buffer.caret, len(self._buffer.text))
            self._buffer.anchor = None
            self._sync_preview()
            return
        node = self.document.find(node_id)
        if node is None:
            return
        wrapped = reflow(node.text, width)
        if wrapped == node.text:
            return
        self._push_undo()
        node.text = wrapped
        self._mark_dirty()

    def finish_edit(self, *, commit: bool) -> None:
        node_id = self._edit_id
        self._edit_id = None
        node = self._live_node(node_id) if node_id else None
        text = self._buffer.text.strip() if self._buffer is not None else ""
        fresh = self._edit_fresh
        if node is not None:
            node.preview = None
            node.caret = None
            node.overwrite = False
            node.sel = None
        self._buffer = None

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
        """^Tab — a new cell under the selection, in the map or in a cut."""
        doc = self.document
        self._push_undo()
        node = doc.add_child(self.focus)
        if node is None:
            self._undo.pop()
            return
        self._inserted(node, doc)

    def action_add_sibling(self) -> None:
        """⏎ — a new cell beside the selection; a sibling of a top-level cut is a
        new entry on the stack, because at that level the stack is the top level."""
        doc = self.document
        if doc.parent(self.focus) is None:
            self.action_add_child()
            return
        self._push_undo()
        node = doc.add_sibling(self.focus)
        if node is None:
            self._undo.pop()
            return
        self._inserted(node, doc)

    def _inserted(self, node: Node, doc: MindMap) -> None:
        """Stand on a cell that has just been made, and type its name."""
        if self.stack_open:
            self._commit_stack(doc)  # the document the cell was made in
            self.selected, self.anchor = node.id, None
            self._stack_changed()
        else:
            self.anchor = None
            self.selected = node.id
            self.view.refresh_map()
        self.begin_edit(node.id, fresh=True)

    def action_edit(self) -> None:
        """Renaming a run of cells at once would give them all one name, so this
        is the one action that stays with the cell the cursor is on."""
        if self.node is not None:
            self.anchor = None
            self.begin_edit(self.selected)

    def action_delete(self) -> None:
        """^D — delete everything selected, as one undoable step."""
        ids = self.selected_ids
        if self.mm.root.id in ids:
            self.notify("The root node cannot be deleted", severity="error", timeout=2)
            return
        self._push_undo()
        if len(ids) == 1:
            result = self.mm.delete(ids[0])
            if result is None:
                self._undo.pop()
                return
            _, successor = result
            self.selected = successor
        else:
            # a run leaves you on the parent it hung from
            parent = self.mm.parent(ids[0])
            for node_id in ids:
                self.mm.delete(node_id)
            self.selected = parent.id if parent is not None else self.mm.root.id
        self.anchor = None
        self._mark_dirty()

    def action_cut(self) -> None:
        """^K — take the selected cells out of the map and put them on the stack.

        They are not deleted: the stack is last in, first out, and any of the cuts
        on it can be pasted back under whatever cell is selected. The cursor stays
        on a sibling, where the eye already is.

        The cursor stays where the eye already is: on the cell that closes the gap
        the cut left, or on the one before it when the run ended the branch. Only
        an only child leaves you on the parent, because there is nothing else
        left to stand on.
        """
        ids = self.selected_ids
        if self.mm.root.id in ids:
            self.notify("The root node cannot be cut", severity="error", timeout=2)
            return
        parent = self.mm.parent(ids[0])
        if parent is None:
            return
        # the slot the run will leave behind, read before it is closed up
        end = [child.id for child in parent.children].index(ids[-1])
        self._push_undo()
        taken: list[Node] = []
        for node_id in ids:
            result = self.mm.delete(node_id)
            if result is not None:
                taken.append(result[0])
        if not taken:
            self._undo.pop()
            return
        self.mm.push_cut(taken)
        self.anchor = None
        self.selected = _standing_after(parent, end)
        self._mark_dirty()
        what = taken[0].text.strip() or "1 cell" if len(taken) == 1 else f"{len(taken)} cells"
        self.notify(f"Cut {what}", severity="warning", timeout=2)

    def action_paste(self) -> None:
        """^U — take the most recent cut off the stack and hang it here.

        Last in, first out: cutting three branches and pressing ^U three times
        puts them back in the order they were cut, and each press empties the
        stack by one. A paste the eye cannot see is worth nothing, so the
        selection stays on the target as its children arrive.
        """
        if not self.mm.cut_stack:
            self.notify("Nothing to paste", severity="error", timeout=2)
            return
        self._push_undo()  # the snapshot holds the stack, so undo puts it back
        cell = self.mm.pop_cut()
        if cell is None or self.mm.paste(self.selected, cell) is None:
            self._undo.pop()
            return
        self._mark_dirty()
        self.notify(f"Pasted {cell.text.strip() or '1 cell'}", severity="warning", timeout=2)

    def action_toggle_stack(self) -> None:
        """^I — the stack itself, as a panel of cells over the map.

        The stack is where every cut cell waits, last in first out, until it is
        pasted somewhere; the panel shows what is on it and lets you work on a
        cell — rename it, mark it, cut it again, drop it — without pasting it back
        into the map first.
        """
        if self.stack_open:
            self._stack_open = False
            if self._map_cursor is not None:
                selected, anchor = self._map_cursor
                if selected is not None and self.mm.find(selected) is not None:
                    self.selected, self.anchor = selected, anchor
                self._map_cursor = None
            self.view.refresh()
            self._sync_footer()
            self._refresh_chrome()
            return
        entries = self._stack_entries()
        if not entries:
            self.notify("Nothing cut yet", severity="error", timeout=2)
            return
        self._map_cursor = (self.selected, self.anchor)  # where the map left off
        self._stack_open = True
        self.selected, self.anchor = entries[0].id, None  # the newest cut
        self.view.refresh()
        self._sync_footer()
        self._refresh_chrome()

    def _stack_entries(self) -> list[Node]:
        """The stack as the panel reads it: newest first."""
        return list(reversed(self.mm.cut_stack))

    def stack_layout(self):
        """The picture of the stack, or None when the panel is shut."""
        if not self.stack_open:
            return None
        return compute_stack(self._stack_entries(), self.mm.spacing)

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

    def _stack_doc(self) -> MindMap:
        """The stack as a document, made of the same Node objects.

        Its root is a cell of its own that nothing draws: it is there so the
        ordinary navigation helpers have a parent to walk up to, and its children
        are the stack, newest first.
        """
        return MindMap(Node("", children=self._stack_entries()))

    def _commit_stack(self, doc: MindMap) -> None:
        """The panel's top level *is* the stack: structural changes go back to it."""
        self.mm.cut_stack = list(reversed(doc.root.children))

    def _stack_changed(self) -> None:
        """Write the panel's state back and let the document know."""
        self._mark_dirty()
        self.view.refresh()

    def _stack_after_history(self) -> None:
        """Undo and redo swap the whole document, so the panel's cursor has to be
        put somewhere that still exists — and the panel closed if the stack the
        restored document carries is empty."""
        entries = self._stack_entries()
        if not entries:
            self.stack_open_or_close_after_undo()
            return
        known = {node.id for entry in entries for node in entry.walk()}
        if self.selected not in known:
            self.selected, self.anchor = entries[0].id, None  # the top of the stack
        self.view.refresh()

    def _stack_select(self, doc: MindMap, node_id: str) -> None:
        if node_id != doc.root.id:  # the invisible root is not a cell you can be on
            self.select(node_id)

    def _action_for(self, key: str) -> str | None:
        """Which action a chord belongs to, according to the keymap in force.

        The stack panel reads keys through this instead of matching strings, so a
        chord the reader has rebound works there too.
        """
        for action, chords in action_chords(self.config.keys).items():
            if key in chords:
                return action
        return None

    def handle_stack_key(self, key: str, character: str | None) -> bool:
        """Every key while the stack panel is open.

        The actions are the map's own — navigation is the branch shape's, because
        that is how the panel is drawn (up and down walk the stack, right goes into
        a cell's children, left comes back out) — so every key means what it means
        on the map, and the bar can say so in the same words.
        """
        if not self.stack_open:
            return False
        action = None if key in ("escape", "ctrl+c") else self._action_for(key)
        doc = self._stack_doc()
        selected = self.selected or doc.root.id

        if action is None and key not in ("escape", "ctrl+c", "ctrl+i"):
            return False
        if action == "toggle_stack" or key in ("escape", "ctrl+c"):
            self.action_toggle_stack()
        elif action == "prev":
            self._stack_select(doc, nav.to_sibling(doc, selected, -1))
        elif action == "next":
            self._stack_select(doc, nav.to_sibling(doc, selected, 1))
        elif action == "go_right":
            self._stack_select(doc, nav.to_child(doc, selected))
        elif action == "go_left":
            self._stack_select(doc, nav.to_parent(doc, selected))
        elif action == "edit":
            if doc.find(selected) is not None:
                self.begin_edit(selected)
        elif action == "select_all":
            self.action_select_all()
        elif action in ("extend_prev", "extend_next"):
            # the panel is always the branch shape: up and down walk siblings, so
            # those are the arrows that grow a run there
            self._extend("prev" if action == "extend_prev" else "next")
        elif action in ("extend_left", "extend_right"):
            pass  # left and right go to the parent and into a cell, never sideways
        elif action == "mark":
            self._push_undo()
            mark = doc.next_mark(selected, self.marks)
            for node_id in self.selected_ids:
                node = doc.find(node_id)
                if node is not None:
                    node.mark = mark
            self._stack_changed()
        elif action == "fold":
            lead = doc.find(selected)
            if lead is not None and lead.children:
                self._push_undo()
                fold = not lead.collapsed
                for node_id in self.selected_ids:
                    node = doc.find(node_id)
                    if node is not None and node.children:
                        node.collapsed = fold
                self._stack_changed()
        elif action == "cut":
            self._stack_take(doc, self.selected_ids, discard=False)
        elif action == "paste":
            self._stack_paste()
        elif action == "justify":
            self.action_justify()
        elif action == "copy":
            self.action_copy()
        elif action == "delete":
            self._stack_take(doc, self.selected_ids, discard=True)
        elif action == "move_up":
            self._stack_reorder(doc, selected, -1)
        elif action == "move_down":
            self._stack_reorder(doc, selected, 1)
        elif action == "spacing_more":
            self._set_spacing(self.mm.spacing + 1)
        elif action == "spacing_less":
            self._set_spacing(self.mm.spacing - 1)
        elif action == "undo":
            self.action_undo()
            self._stack_after_history()
        elif action == "redo":
            self.action_redo()
            self._stack_after_history()
        else:
            return False
        return True

    def _stack_reorder(self, doc: MindMap, node_id: str, delta: int) -> None:
        """Move a cell among its siblings inside the panel. For an entry at the
        top level that is the stack's own order, so alt+↑ puts it nearer the top."""
        parent = doc.parent(node_id)
        if parent is None:
            return
        order = [child.id for child in parent.children]
        index = order.index(node_id)
        target = index + delta
        if not 0 <= target < len(order):
            return
        self._push_undo()
        node = parent.children.pop(index)
        parent.children.insert(target, node)
        self.mm.cut_stack = list(reversed(doc.root.children))
        self._stack_changed()

    def stack_open_or_close_after_undo(self) -> None:
        """Undo can empty the stack a panel is showing; the panel goes with it."""
        self._stack_open = False
        if self._map_cursor is not None:
            selected, anchor = self._map_cursor
            if selected is not None and self.mm.find(selected) is not None:
                self.selected, self.anchor = selected, anchor
            self._map_cursor = None
        self._sync_footer()
        self._refresh_chrome()
        self.view.refresh()

    def _stack_paste(self) -> None:
        """^U inside the panel: hang the newest cut under the selected cell.

        This rearranges the stack without touching the map — the top comes off the
        stack and becomes a child of whatever is selected in the panel. A cell
        cannot be pasted into itself or into one of its own children (that would
        be a cycle), so that case does nothing at all and leaves the stack as it
        was, rather than reporting a failure for a key that cannot work here.
        """
        if not self.mm.cut_stack:
            self.notify("Nothing to paste", severity="error", timeout=2)
            return
        top = self.mm.cut_stack[-1]
        target = self.selected
        if target is None or any(node.id == target for node in top.walk()):
            return  # into itself, or into something it already contains

        self._push_undo()  # the stack is document state, so undo covers this too
        cell = self.mm.pop_cut()
        doc = self._stack_doc()  # rebuilt without the cell that left the stack
        if cell is None or doc.find(target) is None:
            self.mm.cut_stack.append(cell) if cell is not None else None
            self._undo.pop()
            return
        doc.paste(target, cell)
        self.mm.cut_stack = list(reversed(doc.root.children))
        self._mark_dirty()
        self.view.refresh()

    def _stack_take(self, doc: MindMap, ids: list[str], *, discard: bool) -> None:
        """Take cells off the stack: throw them away, or cut them again.

        Cutting again is the whole point of a stack — the cells go back on top,
        which is where a cut always goes, and the panel shows them at the top.
        A run keeps its order, so the first of them ends up highest in the panel.
        """
        if not ids:
            return
        parent = doc.parent(ids[0])
        if parent is None:
            return
        self._push_undo()  # every stack change is one step, like a map change
        taken: list[Node] = []
        for node_id in ids:
            holder = doc.parent(node_id)
            if holder is None:
                continue
            for position, child in enumerate(holder.children):
                if child.id == node_id:
                    taken.append(holder.children.pop(position))
                    break
        node = taken[0] if taken else None
        if node is None:
            self._undo.pop()
            return
        index = 0
        if not discard:
            # the panel reads newest first, so the top of the stack is its index 0
            for cell in reversed(taken):
                doc.root.children.insert(0, cell)
        entries = list(reversed(doc.root.children))  # the file's order: oldest first
        self.mm.cut_stack = entries
        self._stack_changed()
        if not entries:  # nothing left to show
            self.stack_open_or_close_after_undo()
            return
        self.anchor = None
        self.selected = node.id if not discard else entries[min(index, len(entries) - 1)].id
        self.view.refresh()

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

    def action_set_marks(self) -> None:
        """^M — the marks this map cycles through, in the order m walks them.

        A line of its own rather than something buried in the settings: the
        vocabulary is part of the map, and it is edited while the map is in front
        of you. The list is not preselected — appending to it is the common case.
        """
        self._show_prompt(
            "marks",
            f"Marks, in the order {key_cap(self.keymap.get('mark', 'm'))} cycles: ",
            " ".join(self.marks),
            submit=self._marks_submitted,
            cancel=self._close_drawers,
        )

    def _marks_submitted(self, value: str) -> None:
        self.set_marks(value.split())
        self._close_drawers()
        self.view.focus()

    def action_mark(self) -> None:
        """m — cycle the mark: none, ⭐, 💡, ❓, ⚠️, ✅, 📌, ⌛, 🤡, none.

        A run of cells all take the mark the first one was about to show, so one
        press gives them one meaning instead of a spectrum.
        """
        ids = self.selected_ids
        if not ids:
            return
        self._push_undo()
        mark = self.mm.next_mark(ids[0], self.marks)
        for node_id in ids:
            node = self.mm.find(node_id)
            if node is not None:
                node.mark = mark
        self._mark_dirty()

    def action_fold(self) -> None:
        """t — fold or unfold, following the lead cell's state across the run."""
        ids = self.selected_ids
        lead = self.mm.find(ids[0])
        if lead is None:
            return
        fold = not lead.collapsed
        targets = [node for node in map(self.mm.find, ids) if node is not None and node.children]
        if not targets:
            return
        self._push_undo()
        for node in targets:
            node.collapsed = fold
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
        if self.siblings_are_sideways:
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
        if self.siblings_are_sideways:
            self.select(nav.to_sibling(self.mm, self.selected, +1))
            return
        if self._at_root:
            self._from_root(+1)
        elif nav.side(self.mm, self.selected, self.mm.layout) < 0:
            self._to_parent()
        else:
            self._into_child()

    @property
    def siblings_are_sideways(self) -> bool:
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

    def action_extend_prev(self) -> None:
        """Shift + the arrow that walks back between siblings."""
        self._extend(UP_MEANING[self.mm.layout])

    def action_extend_next(self) -> None:
        self._extend(DOWN_MEANING[self.mm.layout])

    def action_extend_left(self) -> None:
        self._extend("prev" if self.siblings_are_sideways else None)

    def action_extend_right(self) -> None:
        self._extend("next" if self.siblings_are_sideways else None)

    def _extend(self, kind: str | None) -> None:
        """Grow or shrink the run by one sibling. Arrows that do not walk between
        siblings in this shape do nothing rather than jump somewhere else."""
        if kind not in ("prev", "next"):
            return
        parent = self.document.parent(self.selected)
        if parent is None:
            return
        order = [child.id for child in parent.children]
        target = order.index(self.selected) + (-1 if kind == "prev" else +1)
        if not 0 <= target < len(order):
            return
        if self.anchor is None:
            self.anchor = self.selected
        self.selected = order[target]
        self.view.refresh()

    def action_select_all(self) -> None:
        """^A — the whole text while a cell is being typed into, every sibling on
        the map (which is what a run is: siblings, never cousins)."""
        if self.editing:
            if self._buffer is not None:
                self._buffer.select_all()
                self._sync_preview()
            return
        parent = self.document.parent(self.selected)
        if parent is None or len(parent.children) < 2:
            return
        order = [child.id for child in parent.children]
        self.anchor = order[0]
        self.selected = order[-1]
        self.view.refresh()

    def action_clear_selection(self) -> None:
        """esc — back to one cell without moving it."""
        if self.anchor is None:
            return
        self.anchor = None
        self.view.refresh()

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

    def action_colours(self) -> None:
        """c — cycle the colouring: by depth, or by family.

        `depth` gives every level one colour, `family` gives every branch under the
        root one colour for its whole subtree. Like the shape and the spacing it is
        document state, and like them it is not an edit worth undoing.
        """
        self.mm.colours = "family" if self.mm.colours == "depth" else "depth"
        self._mark_dirty()
        self.notify(f"Colours by {self.mm.colours}", timeout=1)

    def action_layout(self) -> None:
        """^L — cycle the shape of the map: spider, pyramid, bush, branch."""
        order = LAYOUTS
        self.mm.layout = order[(order.index(self.mm.layout) + 1) % len(order)]
        # like spacing, the shape is document state but not an edit worth undoing
        self._mark_dirty()
        self.notify(f"Layout: {self.mm.layout}", timeout=1)

    def _reorder(self, delta: int) -> None:
        """alt+↑ / alt+↓ — move the run as one block, keeping its order."""
        ids = self.selected_ids
        parent = self.mm.parent(ids[0])
        if parent is None:
            return
        order = [child.id for child in parent.children]
        if (delta < 0 and order.index(ids[0]) == 0) or (
            delta > 0 and order.index(ids[-1]) == len(order) - 1
        ):
            return  # the block is against the edge
        self._push_undo()
        for node_id in ids if delta < 0 else list(reversed(ids)):
            self.mm.move_sibling(node_id, delta)
        self._mark_dirty()

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


def _standing_after(parent: Node, index: int) -> str:
    """Where the cursor goes when the cells at `index` and above are gone: the cell
    that slid into the gap, else the last one before it, else the parent."""
    if index < len(parent.children):
        return parent.children[index].id
    if parent.children:
        return parent.children[-1].id
    return parent.id


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
    SpoiderApp(path, demo=args.demo).run(mouse=False)


if __name__ == "__main__":
    main()
