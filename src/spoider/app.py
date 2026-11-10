"""The spoider application: key handling, inline editing, write/quit flow."""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import ClassVar, cast

from textual import events
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding, BindingType
from textual.notifications import SeverityLevel
from textual.screen import Screen

from .actions_edit import EditActions
from .actions_map import MapActions
from .actions_stack import StackActions
from .addressing import parse as parse_address
from .addressing import resolve as resolve_address
from .chrome import (
    FAILURE,
    NOTE,
    NOTICE_STYLES,
    QUICK,
    FooterBar,
    ask_chunks,
    error_chunks,
    help_chunks,
    prompt_chunks,
)
from .config import (
    Config,
    default_config_path,
    load_config,
    update_config,
    write_config,
)
from .desktop import desktop_available, install_desktop
from .drawers import AskBar, ErrorBar, NoticeBar, PanelBar, PromptBar
from .editing import Buffer
from .files import SUFFIX
from .formats import EXPORT_FORMATS
from .keys import (
    BINDINGS,
    action_chords,
    build_binding_keymap,
    build_keymap,
    resolve,
)
from .layout import label
from .model import MapFileError, MindMap, Node, marks_of
from .nav import to_end, to_extreme_sibling, to_home
from .screens import help_text
from .text import clean, find_all, one_line, set_tab_width
from .widgets import MindMapView, TopBar

# No colours here on purpose: the app runs on Textual's ansi theme, so every
# surface inherits the terminal's palette. `ansi_default` means "whatever the
# terminal already uses", and `reverse` swaps its own fg/bg.
APP_CSS = """
Screen {
    layers: base floating;
    /* A bar is placed outside the flow; the screen itself never scrolls, so it must not
       grow a scrollbar for one either. */
    overflow: hidden;
}
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
/* One-row bars do not take a row: they are painted on a layer over the map's last row,
   which is the air above the bar when the window is tall enough to keep it, so a prompt
   or a notice cannot move anything. Absolute keeps them out of the screen's own layout,
   and the layer puts them above the map. */
#ask, #prompt, #error, #notice {
    width: 100%;
    height: 1;
    margin: 0;
    layer: floating;
    position: absolute;
}
/* A panel's last row is air: the bar is never hard against its text. A prompt cannot
   afford that row, because a prompt is one row tall. */
#panel {
    padding: 0 1 1 1;
}
/* A prompt is part of the footer, not part of the map: one blank row keeps the
   map off it, the way the bar itself keeps a line of air. */
#ask, #prompt {
    height: 1;
    margin-top: 1;
}
/* The error line: red, and the only thing that takes keys while it is up. */
#error {
    padding: 0 1;
    display: none;
    text-wrap: nowrap;
    text-overflow: clip;
}
/* The notice: what just happened, in the colour of its meaning. It draws its own single
   column of air, so the band is the sentence plus two and not a stripe across the screen. */
#notice {
    padding: 0;
    display: none;
    text-wrap: nowrap;
    text-overflow: clip;
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


#: What ↑ and ↓ do in each shape. The siblings always sit side by side; it is the
#: level that moves. A pyramid hangs its children below the parent, so down goes
#: deeper; a bush hangs them above it, so up goes deeper and down goes home.


def editor_command() -> list[str]:
    raw = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
    try:
        return shlex.split(raw) or ["nano"]
    except ValueError:  # unbalanced quotes in $EDITOR / $VISUAL
        return ["nano"]


#: A file larger than this is not a map, and is not worth reading to find out.
_NOT_A_MAP_LIMIT = 64 * 1024 * 1024


def _not_a_map(path: Path) -> str | None:
    """Why this existing file is not a spoider map, or None when it is one."""
    try:
        if path.stat().st_size > _NOT_A_MAP_LIMIT:
            return "too large"
        MindMap.load(path)
    except MapFileError as exc:
        return str(exc)
    except OSError as exc:
        return exc.strerror or str(exc)
    return None


def desktop_notes(config_path: Path) -> tuple[str, ...]:
    """What the first-run question says it will touch, in the order it touches it.

    The settings file is written whichever way the answer goes, so the question says so:
    a person who reads this line knows where the editor keeps its preferences before they
    have opened anything.
    """
    return (
        "spoider wrote its settings to",
        f"  {config_path}",
        "",
        "Your system can also learn to recognise that a .spoider file should always open in spoider.",
        "That needs two files created:",
        "",
        "  ~/.local/share/mime/packages/x-spoider.xml",
        "  ~/.local/share/applications/spoider.desktop",
    )


def ask_desktop(config: Config, config_path: Path, key_entries: list[tuple[str, str, str]]) -> bool:
    """Ask, before the screen exists, whether to register .spoider with the desktop.

    Nothing is written to a terminal that is not one: a program launching a map gets no
    question. A machine without the freedesktop tools that would honour the answer is not
    asked either, and only a question that was put is recorded, so the question comes back
    on a machine that gains them.
    """
    if config.desktop_asked or not sys.stdin.isatty() or not desktop_available():
        return False
    print("\n".join(desktop_notes(config_path)))
    try:
        reply = input("Do it now? [y/N] ")
    except EOFError:
        return False
    if not config_path.exists():
        write_config(config, config_path, key_entries)
    if reply.strip().lower() in ("y", "yes"):
        install_desktop()
    update_config(config_path, {"desktop_asked": "true"})
    return True


def edit_in_editor(path: Path) -> None:
    """Run the user's editor on a file, in the foreground."""
    subprocess.run([*editor_command(), str(path)], check=False)


class UnknownCell(Exception):
    """`--id` named a cell the map does not hold.

    A program that launches a map wants to know that, so this leaves the process with a
    non-zero code rather than opening the file at the root.
    """


#: Every config complaint starts with this, which is how the next reading finds and
#: clears the last one.
WARNING = "Warning: "


class SpoiderApp(MapActions, StackActions, EditActions, App[None]):
    CSS = APP_CSS
    TITLE = "spoider"
    # Textual declares its table as `list[BindingType]`, the union with the tuple form
    # it also accepts. Ours only ever holds Binding, and the cast is the one place the
    # two shapes have to meet.
    BINDINGS: ClassVar[list[BindingType]] = cast("list[BindingType]", BINDINGS)
    ENABLE_COMMAND_PALETTE = False

    def __init__(
        self,
        path: Path | None = None,
        *,
        demo: bool = False,
        config_path: Path | None = None,
        position: str | None = None,
        cell_id: str | None = None,
    ) -> None:
        super().__init__()
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.config: Config = load_config(self.config_path, self._binding_ids())
        set_tab_width(self.config.tab_width)
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
        #: The cell `--id` named, in the map or on the cut stack. Checked before the
        #: screen exists, so a wrong id never opens a window.
        self.start_id = cell_id
        if cell_id is not None:
            found, _in_stack = self._find_saved_cursor(cell_id)
            if found is None:
                raise UnknownCell(f"{cell_id} is not a cell in this map")
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
        #: keys | search | write | marks | ask | help
        self._mode = "keys"
        #: What acknowledging the red line does, while it is on screen. It lives here
        #: rather than on the drawer, because a drawer hears keys only while it has focus.
        self._error_ack: Callable[[], None] | None = None
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
        # The one-row bars are placed by an offset and painted on their own layer, so a
        # question or a notice is drawn over the map's last row instead of taking a row
        # from it: nothing moves when one of them comes or goes.
        yield AskBar(id="ask")
        yield PromptBar(id="prompt")
        # the red line sits above the bar of keys, so the way out stays the bottom row
        # of the screen in every state
        yield ErrorBar(id="error")
        yield NoticeBar(id="notice")
        yield TopBar(id="topbar")
        yield MindMapView(self)
        # whatever the app has to ask is asked here, above the bar, and never in
        # a window over the map: one bar, and it says what the question accepts
        yield PanelBar(id="panel")
        yield FooterBar(id="footer")

    #: Rows a window needs before it can afford air around the map: below this,
    #: two rows of map are worth more than the tidier picture.
    ROOMY_HEIGHT = 30

    def on_resize(self, event: events.Resize) -> None:
        """Give the bars a row of air each while the window can spare them."""
        self.screen.set_class(event.size.height > self.ROOMY_HEIGHT, "roomy")
        self._place_bars()

    def on_mount(self) -> None:
        self._place_bars()
        # A config is the reader's file: written once when it is missing, then only ever
        # edited line by line. Deleting it brings the commented template back.
        self._save_config()
        self.set_keymap(build_binding_keymap(self.config.keys))
        self._report_clashes()
        if self.load_error is not None:
            # the file is not a map: there is nothing to edit, so there is no canvas,
            # no title and no cursor — one red line, and the only key leaves
            # the bar stays for its name and version: it is how a reader says which build
            # refused the file. The canvas has nothing to draw, so it takes its rows with
            # it and the red line and the keys come up under the bar, on an otherwise
            # empty screen: there is no map here, and the screen says so.
            self.query_one(MindMapView).display = False
            self._show_error(self.load_error, self._leave_refused_file)
            return
        self._set_terminal_title()
        self._apply_start_position()
        self.query_one(MindMapView).focus()
        self._sync_footer()

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
        if self.start_id is not None:
            found, in_stack = self._find_saved_cursor(self.start_id)
        elif self.start_position is not None:
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
        """What just happened goes on one line above the bar of keys, the way nano says it.

        Some of what goes into one is untrusted — a file name, a cell's text, a parse error
        quoting the file — so it is cleaned here, once, and flattened: the line is one row, and
        a line break in a cell's text becomes a space instead of joining two words. The
        severity picks the colour of the band; a prompt, when one opens, takes the line and the
        notice goes.
        """
        notice = self.query_one(NoticeBar)
        notice.show(
            one_line(message), NOTICE_STYLES.get(severity, NOTICE_STYLES["information"]), timeout
        )
        self._place_bars()  # the band is as wide as the sentence, so it is centred again

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
        # A cell owns every character while it is being typed into: a full stop and a
        # question mark are how sentences end, so `.` and `?` are text there, not keys.
        # Leave the cell with esc to reach the help.
        if self.editing:
            return None
        return True

    @staticmethod
    def _plain_action(action: str) -> str:
        """Textual's own ids read `app.focus_next`; the interesting half is the verb."""
        return action.split(".")[-1].replace("_", " ")

    @staticmethod
    def _foreign_chords(chords: dict[str, list[str]]) -> dict[str, str]:
        """Chords Textual answers before us, and what it does with them.

        The binding chain runs from the focused widget up through the screen to the
        app, so a chord the screen binds (`tab` for focus, `ctrl+c`) is taken before
        an ordinary app binding of ours ever sees it. `Tab` works here only because
        the cell-insert binding is `priority=True`, which outranks the screen — so a
        chord counts as ours only while a priority binding actually holds it, and any
        other line naming it will not do what it says.
        """
        priority = {
            b.action for b in BINDINGS if b.priority
        }
        held = {chord for action in priority for chord in chords.get(action, [])}
        foreign: dict[str, str] = {}
        for table in (App, Screen):
            for binding in table.BINDINGS:
                if not isinstance(binding, Binding):
                    continue  # Textual's own table may hold the tuple form
                for key in str(binding.key).split(","):
                    if key and key not in held:
                        foreign.setdefault(key, binding.action)
        return foreign

    def _report_clashes(self) -> None:
        """Say what the config asked for and could not have.

        Two things can go wrong in the file and neither is visible in it: one chord
        given to two actions, and one name given two lines. `resolve` refuses the
        second claim (a key that runs one of two actions at random is worse than a key
        that does nothing) and `parse` lets the last line stand, as any rc file does;
        both are reported here, in red, once per reading of the file.
        """
        chords, clashes = resolve(self.config.keys)
        said: list[str] = [f"{WARNING}collision in config. {text}." for _chord, text in clashes]
        said += [
            f"{WARNING}{name} is set twice, the first line is ignored."
            for name in self.config.repeated
        ]
        # A chord Textual answers to itself is one spoider cannot hand to you: the
        # widget or the app takes it first. Only for chords the defaults do not use,
        # so the keys spoider already owns (tab, escape) are not called a problem.
        foreign = self._foreign_chords(chords)
        mine = {f"{chord}" for chord in (c for listed in chords.values() for c in listed)}
        for chord in sorted(mine & foreign.keys()):
            said.append(
                f"{WARNING}{chord} is one Textual uses for {self._plain_action(foreign[chord])}, "
                "so a line binding it will not do what it says."
            )
        # the file has just been read, so a mistake that is no longer there must go with it
        notice = self.query_one(NoticeBar)
        if notice.message.startswith(WARNING):
            notice.close()
        if said:
            # one line holds one reading of the file, so the complaints are said together
            # rather than the last of them winning; no timeout, because a config that
            # fights itself is the reader's to fix and a warning that fades is not read
            self.notify(" ".join(said), severity="error", timeout=float("inf"))

    @property
    def mode(self) -> str:
        """Who has the keys: the map, a cell being typed into, or a drawer."""
        if self._mode == "keys" and self.editing:
            return "edit"
        return self._mode

    def on_key(self, event: events.Key) -> None:
        """A refused file has one way out, and the focus must not decide whether it works.

        The red line is a drawer, and a drawer hears keys only while it holds the focus:
        a terminal that left the focus on the hidden canvas swallowed every key, and the
        program looked hung while it was alive and repainting. So the acknowledgement is
        answered here, at the top, before any widget can claim the key.
        """
        if self._mode == "error" and self._error_ack is not None:
            event.stop()
            event.prevent_default()
            ack, self._error_ack = self._error_ack, None
            ack()

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

    @property
    def keymap(self) -> dict[str, str]:
        """binding id -> chord(s) in force: the defaults with the config on top."""
        return build_keymap(self.config.keys)

    @staticmethod
    def _binding_ids() -> set[str]:
        """Every id the config file may name: the chords this build can bind."""
        return {binding.id for binding in BINDINGS if binding.id}

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
            if not binding.id or binding.action in seen:
                continue
            seen.add(binding.action)
            if not chords[binding.action]:
                continue  # refused by a collision, so it has no chord to offer
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
            self.notify(f"could not start an editor: {exc}", severity="error", timeout=FAILURE)
            return

        self._reload_config()
        self.notify("config reloaded", timeout=NOTE)

    def _reload_config(self) -> None:
        """Read the file again and put it into force.

        The mistakes it contains are worth saying again: a reader who has just edited
        the file by hand is exactly the one who needs to hear that two actions share a
        chord, so the memory of what was already reported is cleared with each read.
        """
        self.config = load_config(self.config_path, self._binding_ids())
        set_tab_width(self.config.tab_width)  # a new tab stop redraws the map
        self.set_keymap(build_binding_keymap(self.config.keys))  # new chords at once
        self._report_clashes()
        # hide_footer is a decision _sync_footer makes about the bar's box, so a reload
        # that skips it leaves the bar standing until the next mode change
        self._sync_footer()
        self._refresh_chrome()

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
        """Write the template where the file is missing; an existing one is the reader's."""
        try:
            if not self.config_path.exists():
                write_config(self.config, self.config_path, self._key_entries())
        except OSError as exc:
            self.notify(f"could not write config: {exc}", severity="error", timeout=FAILURE)

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
                f"no match for {query!r}" if query else "nothing to find",
                severity="warning",
                timeout=NOTE,
            )
            return
        self._jump_to_match(include_current=not repeat)
        # the count has made its point: back to the cell count shortly
        self._stop_count_timer()
        self._count_timer = self.set_timer(self.MATCH_COUNT_SECONDS, self._settle_count)

    def action_next_match(self) -> None:
        """^N — the next cell the last search found, wrapping at the end."""
        self._walk_matches(1)

    def action_previous_match(self) -> None:
        """^P — the cell before this one in the last search, wrapping at the start."""
        self._walk_matches(-1)

    def _walk_matches(self, direction: int) -> None:
        if not self.search_query.strip():
            self.notify("nothing to find: ^F searches first", severity="warning", timeout=NOTE)
            return
        self._refresh_matches()  # the document with the keys may have changed since
        if not self.matches:
            self.notify(f"no match for {self.search_query!r}", severity="warning", timeout=NOTE)
            return
        self._show_matches = True
        self._jump_to_match(direction=direction)
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

    def _search_order(self) -> list[str]:
        """Every cell a search looks at: the map first, then what waits on the stack."""
        return [node.id for node in self.mm.nodes()] + [
            node.id for node in self._stack_doc().nodes() if node.text.strip()
        ]

    def _refresh_matches(self) -> None:
        query = self.search_query.strip()
        hits = {
            node.id
            for node in [*self.mm.nodes(), *self._stack_doc().nodes()]
            if node.text.strip() and find_all(label(node), query)
        }
        self.matches = [node_id for node_id in self._search_order() if node_id in hits]
        self.view.refresh_map()
        self._refresh_chrome()

    def _jump_to_match(self, *, direction: int = 1, include_current: bool = False) -> None:
        """Select a match from here, wrapping: `direction` 1 forward, -1 back.

        The walk is over whichever document has the keys, so a search inside an open
        stack panel steps through the cuts rather than the map behind them.
        """
        order = self._search_order()
        if not order or not self.matches:
            return
        try:
            start = order.index(self.focus)
        except ValueError:
            start = 0
        first = 0 if include_current else 1
        for step in range(first, len(order) + first):
            candidate = order[(start + step * direction) % len(order)]
            if candidate in self.matches:
                self._show_document_of(candidate)
                self._reveal(candidate)
                return

    def _show_document_of(self, node_id: str) -> None:
        """Bring the document holding a hit into view: the panel for a cut, the map for a cell.

        A search looks in both places, so a walk that crosses them has to cross the
        panel too, or the hit it just found would be off screen.
        """
        on_stack = any(node.id == node_id for node in self._stack_doc().nodes())
        if on_stack != self.stack_open:
            self.action_toggle_stack()

    def _reveal(self, node_id: str) -> None:
        """Open the folds above a match, so that selecting it actually shows it."""
        opened = False
        for node in self.document.path(node_id)[:-1]:
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
        self._place_bars()

    def _place_bars(self) -> None:
        """Put the one-row bars on the row above the bar of keys.

        They are on their own layer, inside a container with no height, so this row is not
        taken from the map: with a tall window it lands on the air above the bar, and on a
        short one it lands on the map's last row, which is the price of not moving anything.
        """
        if not self.is_mounted:
            return
        row = self.size.height - 1
        if self.query_one("#footer", FooterBar).display:
            row -= 1
        for selector in ("#ask", "#prompt", "#error"):
            for bar in self.query(selector):
                bar.styles.offset = (0, max(0, row))
        # the notice is as wide as its sentence, so it is centred rather than stretched
        for notice in self.query("#notice"):
            band = min(self.size.width, notice.band)  # type: ignore[attr-defined]
            notice.styles.offset = (max(0, (self.size.width - band) // 2), max(0, row))

    def _autosave(self) -> bool:
        """Write silently to the current path. False when the write failed, which
        matters to ^X: quitting after a failed autosave would lose the buffer."""
        if self.path is None:  # a new buffer has nowhere to go yet
            return False
        try:
            self.mm.save(self.path)
        except OSError as exc:
            self.notify(f"could not write {self.path}: {exc}", severity="error", timeout=FAILURE)
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
        """Write the map, refusing to bury a file that is not one."""
        if path.exists() and path.is_file():
            reason = _not_a_map(path)
            if reason is not None:
                self.notify(
                    f"{clean(path.name)} is not a spoider map ({reason}); "
                    "write somewhere else",
                    severity="error",
                    timeout=FAILURE,
                )
                return False
        # the file remembers where the cursor was, so opening it returns there
        self.mm.cursor = self.selected
        try:
            self.mm.save(path)
        except (OSError, ValueError) as exc:
            # ValueError is a path the filesystem cannot even look at: a NUL in a name, which
            # the paste handler no longer makes, and anything else this build has not met
            self.notify(f"could not write {clean(str(path))}: {exc}", severity="error", timeout=FAILURE)
            return False
        self.path = path
        self.has_file = True
        self.dirty = False
        self._set_terminal_title()
        self._refresh_chrome()
        self.notify(f"wrote {self.mm.count()} nodes to {clean(path.name)}", timeout=NOTE)
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
        name = str(self.path) if self.path is not None else SUFFIX
        if name.endswith(SUFFIX):
            return name, len(name) - len(SUFFIX)
        # a name with no suffix of its own gets one; an existing file of any other kind
        # is left exactly as the reader named it
        if Path(name).suffix:
            return name, len(name)
        return f"{name}{SUFFIX}", len(name)

    def _write_submitted(self, value: str) -> None:
        self._close_drawers()
        if not value.strip() or Path(value.strip()).name in ("", SUFFIX):
            self.notify("name the file, then the suffix follows it", severity="warning", timeout=NOTE)
            return
        target = Path(value).expanduser()
        if target.is_dir():
            self.notify(f"{target} is a directory", severity="error", timeout=FAILURE)
            return
        if self._write(target) and self._write_then_quit:
            self.exit()

    def _restore(self, snapshot: dict) -> None:
        try:
            self.mm = MindMap.from_dict(snapshot, marks=self.mm.marks)
        except MapFileError as exc:  # only reachable if a snapshot were corrupt
            self.notify(f"cannot restore that state: {exc}", severity="error", timeout=FAILURE)
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
        elif mode == "error":
            footer.mode = "custom"
            footer.custom = error_chunks()
        else:  # help
            footer.mode = "custom"
            footer.custom = help_chunks(self.query_one(PanelBar).scrollable)
        # hidden by preference while the map, the stack panel or a cell has the keys;
        # it comes back for a drawer, because a drawer's keys are named in the bar
        hiding = self.config.hide_footer and self._mode in ("keys", "edit")
        footer.display = not hiding
        footer.refresh()
        self._place_bars()  # the bars sit above the footer, wherever that row now is

    # -- the drawers themselves ------------------------------------------

    def _leave_refused_file(self) -> None:
        """A file that could not be read is left behind, not opened."""
        self.exit()

    def _show_error(self, message: str, on_ack) -> None:
        """Refuse and explain: one line, red, and nothing to do but acknowledge it."""
        self._mode = "error"
        self._error_ack = on_ack
        self._hide_drawers(ErrorBar)
        self.query_one(ErrorBar).show(message)
        self._sync_footer()
        self._refresh_chrome()

    def _hide_drawers(self, *keep: type) -> None:
        """Only one drawer is ever on screen: they share the bottom lines."""
        for drawer in (PromptBar, AskBar, PanelBar, ErrorBar):
            if drawer not in keep:
                self.query_one(drawer).close()
        # a question outranks a notice: it needs the line, so what just happened goes
        self.query_one(NoticeBar).close()

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
        # the cell's frame steps aside while a prompt has the keys, so the map redraws
        self.view.refresh()
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
        self._error_ack = None
        # the map comes back with the keys, unless there is no map to show at all
        self.view.display = self.load_error is None
        self._sync_footer()
        self.view.focus()
        self.view.refresh()
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
        """? — every key and option, with a line of explanation."""
        self._mode = "help"
        self._hide_drawers(PanelBar)
        # the help is a page, not an overlay: a map half-visible behind a wall of text
        # competes with what is being read, and nothing about it can be acted on while
        # any key closes the page
        self.view.display = False
        self.query_one(PanelBar).show(help_text(self), self._help_key)
        self._sync_footer()

    def _help_key(self, key: str) -> None:
        """Scroll the help a screen at a time; any other key closes it."""
        panel = self.query_one(PanelBar)
        if key in ("pagedown", "ctrl+f"):
            panel.scroll_by(panel.rows)
        elif key == "pageup":
            panel.scroll_by(-panel.rows)
        elif key in ("down", "j"):
            panel.scroll_by(1)
        elif key in ("up", "k"):
            panel.scroll_by(-1)
        elif key == "end":
            panel.jump_to("bottom")
        elif key == "home":
            panel.jump_to("top")
        else:
            self._close_drawers()

    def action_settings(self) -> None:
        """`.` — the editor's settings, in your editor: the config file itself."""
        self.open_config()

    def _ask_to_save(self) -> None:
        self._ask_words = ("save", "discard")
        self._mode = "ask"
        self._hide_drawers(AskBar)
        self.query_one(AskBar).ask("Save modified buffer?", self._save_answered)
        self._sync_footer()

    # -- movement -------------------------------------------------------


    # -- history and files ----------------------------------------------

    def action_undo(self) -> None:
        if not self._undo:
            self.notify("nothing to undo", severity="warning", timeout=QUICK)
            return
        self._redo.append(self.mm.to_dict())
        self._restore(self._undo.pop())

    def action_redo(self) -> None:
        if not self._redo:
            self.notify("nothing to redo", severity="warning", timeout=QUICK)
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


class _Help(argparse.HelpFormatter):
    """Wrap the option help as argparse does, and leave an example's line breaks alone."""

    def _fill_text(self, text: str, width: int, indent: str) -> str:
        filled: list[str] = []
        for paragraph in text.split("\n\n"):
            lines = paragraph.splitlines()
            if any(line.startswith("  ") for line in lines):
                # an indented line is a command: break it and the reader cannot copy it
                filled.append("\n".join(indent + line for line in lines))
            else:
                filled.append(argparse.HelpFormatter._fill_text(self, paragraph, width, indent))
        return "\n\n".join(filled)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="spoider",
        description="TUI mind map editor: one map, one bar of keys, your terminal's colours.",
        epilog=(
            "EXAMPLES\n"
            "  spoider notes.spoider --export svg -o notes.svg\n"
            "  spoider notes.spoider --export svg -o notes.svg --palette ink "
            '--font "JetBrainsMono Nerd Font"\n'
            "  spoider notes.spoider --export markdown -o notes.md\n"
            "  spoider notes.spoider --export text -o notes.txt\n"
            "  spoider notes.spoider --export mermaid -o notes.mmd"
        ),
        formatter_class=_Help,
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

    opening = parser.add_argument_group("opening a map at a cell")
    opening.add_argument(
        "-p",
        "--position",
        default=None,
        metavar="ADDRESS",
        help="open the map with the cursor on this cell: 0 is the root, 9 the ninth child, "
        "7.4.9 a path down, s2 or s2.1 a cell on the cut stack; anything else starts at the root",
    )
    opening.add_argument(
        "--id",
        dest="cell_id",
        default=None,
        metavar="ID",
        help="open the map with the cursor on the cell with this id; a cut's id opens the cut "
        "stack",
    )

    exporting = parser.add_argument_group("exporting a map")
    exporting.add_argument(
        "--export",
        default=None,
        choices=EXPORT_FORMATS,
        metavar="FORMAT",
        help="write the map in this format, then exit: "
        f"{', '.join(EXPORT_FORMATS)}",
    )
    exporting.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help="where to write it; required with --export",
    )
    exporting.add_argument(
        "--palette",
        default=None,
        metavar="NAME",
        help="paper, coloured-paper, coloured-ink or ink; paper without it; svg only",
    )
    exporting.add_argument(
        "--font",
        default=None,
        metavar="NAME",
        help="a monospace family, by slug or by name; the first one here without it; svg only",
    )
    exporting.add_argument(
        "--no-stack",
        action="store_true",
        help="leave the cut stack out of the file",
    )
    exporting.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="write over the file at -o if it is already there",
    )

    parser.add_argument(
        "--install-desktop",
        action="store_true",
        help="register .spoider files with the desktop, then exit",
    )
    args = parser.parse_args(argv)
    if args.position is not None and not args.position.strip():
        parser.error("-p/--position needs an address: 0 for the root, 7.4.9 for a path")
    if args.cell_id is not None and not args.cell_id.strip():
        parser.error("--id needs a cell id")
    if args.position is not None and args.cell_id is not None:
        parser.error("choose --position or --id, not both")
    if args.output is not None and not args.export:
        parser.error("-o names where a map is written; use it with --export svg")
    if args.export and args.output is None:
        parser.error("--export needs -o/--output to name the file")
    if args.install_desktop:
        raise SystemExit(install_desktop())
    path = Path(args.path).expanduser() if args.path else None
    if args.export:
        from .formats import TEXT_FORMATS, ExportError

        if args.export in TEXT_FORMATS and (args.palette or args.font):
            # a document has no colours and no face; naming them would only mislead
            parser.error(
                f"{args.export} writes the map as a document: no --palette and no --font"
            )
        if path is None:
            parser.error("--export needs a map to read")
        assert args.output is not None, "--export is refused without -o above"
        target = Path(args.output).expanduser()
        try:
            if args.export == "svg":
                from .svg import export_map

                written, sheet = export_map(
                    path,
                    output=target,
                    palette_name=args.palette,
                    font_name=args.font,
                    with_stack=not args.no_stack,
                    overwrite=args.force,
                )
                caption = sheet.caption
            else:
                from .outline import export_document

                written, caption = export_document(
                    path,
                    form=args.export,
                    output=target,
                    overwrite=args.force,
                    with_stack=not args.no_stack,
                )
        except ExportError as exc:
            print(f"spoider: {exc}", file=sys.stderr)
            raise SystemExit(2) from None
        except OSError as exc:
            where = exc.filename or args.output
            print(f"spoider: cannot write {where}: {exc.strerror or exc}", file=sys.stderr)
            raise SystemExit(2) from None
        print(f"wrote {written} ({caption})")
        raise SystemExit(0)
    try:
        app = SpoiderApp(path, demo=args.demo, position=args.position, cell_id=args.cell_id)
    except UnknownCell as exc:
        # a program that launched this map asked for a cell that is not there; say so
        # on stderr and leave with a code it can test
        print(f"spoider: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    ask_desktop(app.config, app.config_path, app._key_entries())
    app.run(mouse=False)
    if app.load_error is not None:
        # a program that launched this map gets a code it can test, as with a bad --id
        raise SystemExit(2)


if __name__ == "__main__":
    main()
