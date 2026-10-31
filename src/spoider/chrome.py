"""Footer chrome: key hints on the left, settings and help pinned to the right.

The pinned cluster is drawn from the right edge inwards and is never truncated;
the hints yield their space to it, dropping whole entries from the end so a cap is
never cut in half.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from rich.text import Text
from textual.widget import Widget

BINDING_LEGEND = {"ctrl+": "^", "alt+": "⌥"}

KEY_GLYPHS = {
    "tab": "⇥",
    "enter": "⏎",
    "space": "␣",
    "escape": "esc",
    # The spacing chords parse into names nobody wants to read in a bar, so they
    # are labelled as the keys people actually press.
    "ctrl+minus": "^-",
    "ctrl+shift+equals_sign": "^+",
    "ctrl+comma": "^,",
    "ctrl+slash": "^/",
}

#: Always visible, flush right. Order matters: last one sits closest to the edge.
PINNED: tuple[tuple[str, str], ...] = (
    ("ctrl+comma", "settings"),
    ("ctrl+slash", "help"),
)

DIVIDER = "│"


def key_cap(key: str) -> str:
    """One key as it appears in the bar: ⇥, ⏎, ^D, ⌥↑ …"""
    key = str(key).split(",")[0]
    if key in KEY_GLYPHS:
        return KEY_GLYPHS[key]
    for prefix, glyph in BINDING_LEGEND.items():
        if key.startswith(prefix):
            return glyph + key[len(prefix) :].upper()
    return key.upper()


def entry(key: str, label: str, *, literal: bool = False) -> Text:
    """`literal` prints the string as given — for caps like "esc/^C" that are not
    single keys and cannot be derived from a binding."""
    chunk = Text()
    chunk.append(f" {key if literal else key_cap(key)} ", style="bold reverse")
    chunk.append(f"{label} ")
    return chunk


def hint_chunks(bindings: Iterable, skip: frozenset[str] = frozenset()) -> list[Text]:
    """`skip` drops whole actions from the bar — autosave hides ^S, for instance."""
    return [
        entry(b.key, b.description) for b in bindings if b.show and b.action not in skip
    ]


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


def edit_chunks() -> list[Text]:
    return [entry(key, label, literal=True) for key, label in EDIT_HINTS]


class FooterBar(Widget):
    """The bottom line. Switches to typing hints while a node is being named."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.mode = "keys"

    def render(self) -> Text:
        width = self.size.width
        if width <= 0:
            return Text("")
        if self.mode == "edit":
            hints = edit_chunks()
        else:
            app = self.app
            # autosave makes ^S redundant, so it leaves the bar with it on
            skip = frozenset({"save"}) if getattr(app, "autosave", False) else frozenset()
            hints = hint_chunks(app.BINDINGS, skip)  # type: ignore[attr-defined]
        return compose_footer(width, hints)
