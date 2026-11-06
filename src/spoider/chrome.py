"""Footer chrome: key hints on the left, the config and help pinned to the right.

The pinned cluster is drawn from the right edge inwards and is never truncated;
the hints yield their space to it, dropping whole entries from the end so a cap is
never cut in half.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, cast

from rich.text import Text
from textual.widget import Widget

if TYPE_CHECKING:
    from .app import SpoiderApp

#: nano's shorthand: ctrl is ^, meta (alt) is M-, and shift gets the S- that
#: nano never needed, in the same shape. Letters and dashes, not glyphs nobody
#: can name.
BINDING_LEGEND = {"ctrl+": "^", "alt+": "M-", "shift+": "S-"}

#: The caret is not a character: it inverts the cell it is on, here and in the
#: inline editor alike, so it never widens what it is sitting in.
CARET_STYLE = "reverse"

#: The one line that says the program cannot go on: red, filled, unmissable. ANSI names
#: only, like every other colour here.
ERROR_STYLE = "black on red"

#: Caps are coloured text, never a block: the colour comes from the terminal
#: palette like everything else in the app.
CAP_STYLE = "cyan"

KEY_GLYPHS = {
    "tab": "⇥",
    "enter": "⏎",
    "space": "␣",
    "escape": "esc",
    "ctrl+/": "^/",
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
    "mark",
    "set_marks",
    "justify",
    "delete",
    "cut",
    "paste",
    "toggle_stack",
    "fold",
    "select_all",
    "layout",
    "colours",
    "spacing_more",
    "spacing_less",
)

#: Bare keys need their own caps: `=` and `-` do not spell themselves.
BAR_GLYPHS = {
    # a punctuation key is drawn as itself, whichever name the table carries it by
    "equals_sign": "=",
    "minus": "-",
    "grave_accent": "`",
    "comma": ",",
    "question_mark": "?",
    "full_stop": ".",
    "ctrl+slash": "^/",
    # named keys keep the spelling a keyboard uses, not the terminal's
    "home": "Home",
    "end": "End",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "delete": "Del",
    "insert": "Ins",
    "escape": "esc",
}

#: Always visible, flush right: binding id, the chord it has by default, and its
#: label. Order matters — the last one sits closest to the edge. Rebinding either in
#: the config moves the label with it: a pinned key that no longer exists is worse
#: than no hint at all.
PINNED: tuple[tuple[str, str, str], ...] = (
    ("toggle_properties", ",", "debug"),
    ("settings", ".", "config"),
    ("help", "?", "help"),
)

DIVIDER = "│"


ARROWS = {"up": "↑", "down": "↓", "left": "←", "right": "→"}


def key_cap(key: str) -> str:
    """One chord as it appears in the bar: ⇥, ⏎, ^D, M-↑, h …

    It takes one chord and never a list: the keymap spells a chord the way it is
    pressed, so a comma in there is the key itself. Splitting it here emptied the cap
    of the debug box and left the bar reading "debug" with nothing in front of it.
    `chord_of` is what picks the chord out of a binding.
    """
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


def chord_of(binding, keymap: dict[str, str] | None = None) -> str:
    """The chord to show for a binding: the keymap's, else the first of its own.

    A keymap value is one chord in the spelling a person presses, so a comma there is
    the key itself and must not be split. A binding's own key is Textual's spelling,
    where a comma separates several keys, so that one is split — a comma key is
    written `comma` there and has no other way to be said.
    """
    chosen = (keymap or {}).get(binding.id or "")
    if chosen:
        return str(chosen)
    return str(binding.key).split(",")[0]


def hint_chunks(
    bindings: Iterable,
    skip: frozenset[str] = frozenset(),
    keymap: dict[str, str] | None = None,
    *,
    rename: dict[str, str] | None = None,
    first: str | None = None,
) -> list[Text]:
    """`skip` drops whole actions from the bar — autosave hides ^S, for instance.
    `keymap` holds the chords in force after the config has had its say."""
    from textual.binding import Binding

    keymap = keymap or {}
    shown: list[tuple[str, Text]] = []
    for binding in bindings:
        if not isinstance(binding, Binding) or not binding.show or binding.action in skip:
            continue
        key = chord_of(binding, keymap)
        label = (rename or {}).get(binding.action, binding.description)
        shown.append((binding.id or "", entry(key, label)))

    def rank(pair: tuple[str, Text]) -> int:
        # anything missing from the ranking goes after it, in binding order
        return BAR_ORDER.index(pair[0]) if pair[0] in BAR_ORDER else len(BAR_ORDER)

    shown.sort(key=rank)
    if first is not None:  # stable: the rest keep their ranking
        shown.sort(key=lambda pair: 0 if pair[0] == first else 1)
    return [chunk for _, chunk in shown]


def pinned_chunks(keymap: dict[str, str] | None = None) -> list[Text]:
    keymap = keymap or {}
    return [entry(keymap.get(ident, default), label) for ident, default, label in PINNED]


def pinned_bar(keymap: dict[str, str] | None = None) -> Text:
    bar = Text()
    for chunk in pinned_chunks(keymap):
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


#: Ranked, like the map's bar: finishing the cell first, then the keys that do
#: something the arrows cannot. A narrow bar drops the tail.
EDIT_HINTS = (
    ("⏎", "done"),
    ("S-⏎", "new line"),
    ("esc/^C", "cancel"),
    ("^K", "cut"),
    ("^U", "paste"),
    ("^J", "justify"),
    ("ins", "overwrite"),
    ("←→", "move"),
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


def ask_chunks(affirm: str = "save", deny: str = "discard") -> list[Text]:
    """The keys a yes/no question accepts, worded the way that question asked it."""
    return [
        entry("y", affirm, literal=True),
        entry("n", deny, literal=True),
        entry("esc", "cancel", literal=True),
    ]


def error_chunks() -> list[Text]:
    """The bar while an error is up: one way out, and nothing else to press."""
    return [entry("⏎/esc", "close", literal=True)]


def help_chunks(scrollable: bool = False) -> list[Text]:
    """The bar while help is open: how to close it, and how to read the rest.

    Any key closes it, so the closing word is always there; the scroll keys are named
    only when the page runs past the screen.
    """
    chunks = [entry("esc", "close", literal=True)]
    if scrollable:
        chunks.append(entry("pgup/pgdn", "scroll", literal=True))
    return chunks


def stack_chunks(bindings: Iterable, keymap: dict[str, str] | None = None) -> list[Text]:
    """The bar while the cut stack has the keys: the map's own bar.

    The panel is the map with one difference, so its bar is the map's with one word
    changed: the key that closes it says "hide stack". It keeps its place next to cut and
    paste, because a key that moves around the bar is a key the reader has to find twice.
    """
    return hint_chunks(bindings, keymap=keymap, rename={"toggle_stack": "hide stack"})


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
        spoider = cast("SpoiderApp", self.app)
        if self.mode == "edit":
            hints = edit_chunks()
        elif self.mode == "stack":
            spoider = cast("SpoiderApp", self.app)
            hints = stack_chunks(spoider.BINDINGS, spoider.keymap)
        elif self.mode == "search":
            hints = search_chunks()
        elif self.mode == "custom":
            hints = self.custom
        else:
            # autosave makes ^S redundant, so it leaves the bar with it on
            skip = frozenset({"save"}) if getattr(self.app, "autosave", False) else frozenset()
            hints = hint_chunks(spoider.BINDINGS, skip, spoider.keymap)
        # the pinned cluster is two keys the user may have rebound: it reads the
        # same keymap the hints do, in every mode
        return compose_footer(width, hints, pinned_bar(spoider.keymap))
