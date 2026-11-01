"""Footer chrome: key hints on the left, settings and help pinned to the right.

The pinned cluster is drawn from the right edge inwards and is never truncated;
the hints yield their space to it, dropping whole entries from the end so a cap is
never cut in half.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import TYPE_CHECKING, cast

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.widget import Widget

from .text import clip_tail

if TYPE_CHECKING:
    from .app import SpoiderApp

BINDING_LEGEND = {"ctrl+": "^", "alt+": "⌥"}

#: The block that stands in for a cursor, here and in the inline editor.
CARET = "▊"

#: Caps are coloured text, never a block: the colour comes from the terminal
#: palette like everything else in the app.
CAP_STYLE = "bold cyan"

KEY_GLYPHS = {
    "tab": "⇥",
    "enter": "⏎",
    "space": "␣",
    "escape": "esc",
    # The spacing chords parse into names nobody wants to read in a bar, so they
    # are labelled as the keys people actually press.
    "ctrl+minus": "^-",
    # both the plain and the shifted form of the key are the same chord for the
    # person pressing it, so they share one label
    "ctrl+equals_sign": "^=",
    "ctrl+shift+equals_sign": "^=",
    "ctrl+comma": "^,",
    "ctrl+slash": "^/",
}

#: The bar shows its hints in this order, and that is a ranking: a narrow
#: terminal drops the tail of the bar first. Making cells comes first because it
#: is what you do most; leaving is next, so a cramped bar never strands you;
#: nudging the air comes last of all.
BAR_ORDER: tuple[str, ...] = (
    "add_child",
    "add_sibling",
    "quit",
    "save",
    "write",
    "undo",
    "search",
    "edit",
    "delete",
    "fold",
    "mark",
    "layout",
    "spacing_more",
    "spacing_less",
)

#: Bare keys need their own caps: `=` and `-` do not spell themselves.
BAR_GLYPHS = {"equals_sign": "=", "minus": "-"}

#: Always visible, flush right. Order matters: last one sits closest to the edge.
PINNED: tuple[tuple[str, str], ...] = (
    ("ctrl+comma", "settings"),
    ("ctrl+slash", "help"),
)

DIVIDER = "│"


ARROWS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}


def key_cap(key: str) -> str:
    """One key as it appears in the bar: ⇥, ⏎, ^D, ⌥↑, h …"""
    key = str(key).split(",")[0]
    if key in KEY_GLYPHS:
        return KEY_GLYPHS[key]
    if key in BAR_GLYPHS:
        return BAR_GLYPHS[key]
    for prefix, glyph in BINDING_LEGEND.items():
        if key.startswith(prefix):
            body = key[len(prefix) :]
            return glyph + ARROWS.get(body, body.upper())
    if len(key) == 1 and key.isalpha():
        return key  # h/j/k/l are letters, not shifted capitals
    return ARROWS.get(key, key.upper())


def entry(key: str, label: str, *, literal: bool = False) -> Text:
    """`literal` prints the string as given — for caps like "esc/^C" that are not
    single keys and cannot be derived from a binding."""
    chunk = Text()
    chunk.append(f" {key if literal else key_cap(key)} ", style=CAP_STYLE)
    chunk.append(f"{label} ")
    return chunk


def hint_chunks(
    bindings: Iterable,
    skip: frozenset[str] = frozenset(),
    keymap: dict[str, str] | None = None,
) -> list[Text]:
    """`skip` drops whole actions from the bar — autosave hides ^S, for instance.
    `keymap` holds the chords in force after the config has had its say."""
    from textual.binding import Binding

    keymap = keymap or {}
    shown: list[tuple[str, Text]] = []
    for binding in bindings:
        if not isinstance(binding, Binding) or not binding.show or binding.action in skip:
            continue
        key = keymap.get(binding.id or "", binding.key) or binding.key
        shown.append((binding.id or "", entry(key, binding.description)))

    def rank(pair: tuple[str, Text]) -> int:
        # anything missing from the ranking goes after it, in binding order
        return BAR_ORDER.index(pair[0]) if pair[0] in BAR_ORDER else len(BAR_ORDER)

    shown.sort(key=rank)
    return [chunk for _, chunk in shown]


def pinned_chunks() -> list[Text]:
    return [entry(key, label) for key, label in PINNED]


def pinned_bar() -> Text:
    bar = Text()
    for chunk in pinned_chunks():
        bar.append_text(chunk)
    return bar


def compose_footer(width: int, hints: Sequence[Text], pinned: Text | None = None) -> Text:
    """Left hints first, then the pinned cluster hard against the right edge."""
    pinned = pinned if pinned is not None else pinned_bar()
    cluster_width = pinned.cell_len + len(DIVIDER) + 1
    avail = width - cluster_width - 1  # one blank column always separates the two
    line = Text()
    used = 0
    for chunk in hints:
        if used + chunk.cell_len > avail:
            break
        line.append_text(chunk)
        used += chunk.cell_len
    line.append(" " * max(1, width - cluster_width - used))
    line.append(f"{DIVIDER} ", style="dim")
    line.append_text(pinned)
    return line


EDIT_HINTS = (
    ("⏎", "done"),
    ("esc/^C", "cancel"),
    ("←→", "move"),
    ("⌫", "erase"),
)


#: What the bar offers while the search prompt has the keys.
SEARCH_HINTS = (
    ("⏎", "search"),
    ("esc/^C", "cancel"),
    ("↑↓", "earlier searches"),
)


def edit_chunks() -> list[Text]:
    return [entry(key, label, literal=True) for key, label in EDIT_HINTS]


def search_chunks() -> list[Text]:
    return [entry(key, label, literal=True) for key, label in SEARCH_HINTS]


def prompt_chunks(verb: str) -> list[Text]:
    """The keys of a one-line prompt: answer it, back out, or undo the typing."""
    return [
        entry("⏎", verb, literal=True),
        entry("esc/^C", "cancel", literal=True),
        entry("^Z", "undo", literal=True),
    ]


def ask_chunks() -> list[Text]:
    return [
        entry("y", "save", literal=True),
        entry("n", "discard", literal=True),
        entry("esc", "cancel", literal=True),
    ]


def settings_chunks() -> list[Text]:
    return [
        entry("↑↓", "move", literal=True),
        entry("⏎", "change", literal=True),
        entry("esc", "close", literal=True),
    ]


class FooterBar(Widget):
    """The bottom line, which never goes away.

    Whatever has the keys, the bar says what can be done right now: the map's
    keys, the keys of the cell being typed into, the keys of the search prompt.
    A mode that hid it would leave the reader with no way out.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = "keys"
        #: hints for the drawer modes, which know their own keys
        self.custom: list[Text] = []

    def render(self) -> Text:
        width = self.size.width
        if width <= 0:
            return Text("")
        if self.mode == "edit":
            hints = edit_chunks()
        elif self.mode == "search":
            hints = search_chunks()
        elif self.mode == "custom":
            hints = self.custom
        else:
            app = self.app
            # autosave makes ^S redundant, so it leaves the bar with it on
            skip = frozenset({"save"}) if getattr(app, "autosave", False) else frozenset()
            spoider = cast("SpoiderApp", app)
            hints = hint_chunks(spoider.BINDINGS, skip, spoider.keymap)
        return compose_footer(width, hints)


SEARCH_PROMPT = "Search: "


class SearchBar(Widget, can_focus=True):
    """Nano's search prompt: the bottom line becomes the prompt, the map stays.

    It is a prompt and not a dialog because the point of searching here is to see
    the matches light up while you type. Up and down walk the searches already
    made, newest first, with the draft you had before kept at the bottom.
    """

    def __init__(
        self,
        *,
        on_change: Callable[[str], None],
        on_submit: Callable[[str], None],
        on_cancel: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._on_change = on_change
        self._on_submit = on_submit
        self._on_cancel = on_cancel
        self.value = ""
        self.cursor = 0
        self.history: list[str] = []
        self._history_index = -1  # -1 is the line being typed, not a recall
        self._draft = ""
        self._fresh = False  # the offered search has not been edited yet

    # -- opening and closing ------------------------------------------

    def start(self) -> None:
        """Open the prompt, offering the last search again."""
        self.value = self.history[0] if self.history else ""
        self.cursor = len(self.value)
        # the offered search *is* the newest history entry, so that is where the
        # walk starts: up moves to the one before it
        self._history_index = 0 if self.value else -1
        self._draft = ""
        self._fresh = bool(self.value)
        self.display = True
        self.focus()
        self.refresh()

    def stop(self) -> None:
        self.display = False

    # -- keys ---------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """The prompt owns every key while it is open: a stray ^D must not
        delete the cell behind it, and a stray ^X must not quit."""
        event.stop()
        event.prevent_default()

        key = event.key
        if key == "enter":
            self._submit()
        elif key in ("escape", "ctrl+c"):
            self._on_cancel()
        elif key == "backspace" and self.cursor:
            self._replace(self.value[: self.cursor - 1] + self.value[self.cursor :], self.cursor - 1)
        elif key == "delete":
            self._replace(self.value[: self.cursor] + self.value[self.cursor + 1 :], self.cursor)
        elif key in ("left", "ctrl+b"):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("right", "ctrl+f"):
            self.cursor = min(len(self.value), self.cursor + 1)
        elif key in ("home", "ctrl+a"):
            self.cursor = 0
        elif key in ("end", "ctrl+e"):
            self.cursor = len(self.value)
        elif key == "up":
            self._recall(+1)
        elif key == "down":
            self._recall(-1)
        elif event.character and event.character.isprintable():
            character = event.character
            if self._fresh:
                # typing replaces the search it offered, rather than appending to
                # it; Enter alone is what repeats the search
                self._replace(character, len(character))
            else:
                self._replace(
                    self.value[: self.cursor] + character + self.value[self.cursor :],
                    self.cursor + len(character),
                )
        self.refresh()

    def _replace(self, value: str, cursor: int) -> None:
        self.value = value
        self.cursor = cursor
        self._history_index = -1  # editing starts a new line, not a recall
        self._fresh = False
        self._on_change(value)

    def _submit(self) -> None:
        query = self.value.strip()
        if query:
            if query in self.history:
                self.history.remove(query)
            self.history.insert(0, query)
        self._on_submit(query)

    def _recall(self, step: int) -> None:
        """step +1 walks back through older searches, -1 returns towards the draft."""
        if not self.history:
            return
        if self._history_index == -1:
            self._draft = self.value
        target = self._history_index + step
        if target < -1 or target >= len(self.history):
            return
        self._history_index = target
        self._fresh = False
        self.value = self._draft if target == -1 else self.history[target]
        self.cursor = len(self.value)
        self._on_change(self.value)

    # -- drawing -------------------------------------------------------

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        line = self.value[: self.cursor] + CARET + self.value[self.cursor :]
        room = max(0, width - cell_len(SEARCH_PROMPT) - 2)
        if cell_len(line) > room:
            line = clip_tail(line, room)
        bar = Text(SEARCH_PROMPT, style="bold")
        bar.append(line)
        return bar
