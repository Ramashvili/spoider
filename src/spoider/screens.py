"""What the help and settings drawers put on screen.

Plain data and builders only: the drawers themselves live in spoider.drawers, so a
screen never draws its own footer and there is only ever the one bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.text import Text
from textual.binding import Binding

from .chrome import key_cap
from .text import clip_tail

if TYPE_CHECKING:
    from .app import SpoiderApp


#: (heading, ((actions, explanation), …))
#: A row is either binding ids, or literal keys for the editor (see `Literal`).
HelpRow = tuple["tuple[str, ...] | Literal", str]
HelpSection = tuple[str, tuple[HelpRow, ...]]

# The chords are not written here: they are read from the keymap, so a rebound
# key cannot leave the help lying. Every binding action must appear — the tests
# enforce that in both directions.
@dataclass(frozen=True)
class Literal:
    """Keys that belong to the editor rather than to a binding: they are handled
    while a cell is being typed into, so they have no id for `keys_for` to find."""

    keys: str


HELP: tuple[HelpSection, ...] = (
    (
        "Making cells",
        (
            (("add_child",), "add a child and type its name"),
            (("add_sibling",), "add a sibling after the selection"),
            (("edit",), "rename the selected cell in place"),
            (("cut",), "cut the cells into a LIFO stack, to paste back anywhere"),
            (("paste",), "paste the newest cut; the older ones stay on the stack"),
            (("toggle_stack",), "open the cut stack: its keys are the map's own"),
            (("delete",), "delete the cell and everything under it"),
            (("mark",), "cycle the mark, then off (the set is in settings)"),
            (("justify",), "reflow the cell's text to a width you type"),
            (("copy",), "copy the cell's text to the clipboard"),
            (("fold",), "fold or unfold the branch"),
        ),
    ),
    (
        "Moving",
        (
            (("prev",), "previous sibling"),
            (("next",), "next sibling"),
            (("go_left",), "left: out to parent, or deeper on a left branch"),
            (("go_right",), "right: the mirror of the above"),
            (("move_up",), "move the cell up among its siblings"),
            (("move_down",), "move it down"),
            (
                ("extend_prev", "extend_next", "extend_left", "extend_right"),
                "hold shift and an arrow: select a run of siblings",
            ),
            (("clear_selection",), "back to a single cell, without moving"),
            (("select_all",), "select every sibling of the selected cell"),
        ),
    ),
    (
        "View",
        (
            (("search",), "find cells by their words; ↑ in the prompt recalls one"),
            (("layout",), "cycle the shape: spider, pyramid, bush, branch"),
            (("colours",), "colour by depth, or by family — one colour per branch"),
            (("spacing_more",), "more air between cells — saved with the map"),
            (("spacing_less",), "less air, down to cells sharing a border row"),
        ),
    ),
    (
        "File",
        (
            (("save",), "write straight back to the current file"),
            (("write",), "write out: asks which file, so it saves as"),
            (("quit",), "quit; asks y / n / esc if unsaved"),
        ),
    ),
    (
        "History",
        (
            (("undo",), "undo the last edit"),
            (("redo",), "redo the last undone edit"),
        ),
    ),
    (
        "While typing",
        (
            (Literal("⏎"), "done: keep the text and leave the cell"),
            (Literal("S-⏎"), "start a new line"),
            (Literal("^J"), "justify to a width you type; the width is remembered"),
            (Literal("^K  M-6  ^U"), "cut, copy and paste the text"),
            (Literal("ins"), "overwrite: typing replaces the character under the caret"),
            (Literal("M-⌫  M-d"), "delete a word back, or forward"),
            (Literal("S-←↑↓→"), "select text; home and end keep to the line"),
            (Literal("^A"), "select all the text in the cell"),
        ),
    ),
    (
        "This screen",
        (
            (("help",), "this help"),
            (("settings",), "editor settings"),
        ),
    ),
)

def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - cell_len(text))


def describe_action(action: str, fallback: str = "") -> str:
    """The one-line explanation for an action, as used by the help screen."""
    for _, rows in HELP:
        for actions, explanation in rows:
            if isinstance(actions, Literal):
                continue
            if action in actions:
                return explanation
    return fallback or action


#: Arrows read in this order on a keyboard, so a grouped cap does too.
ARROW_CHARS = "←↑↓→"


def keys_for(app: SpoiderApp, actions: tuple[str, ...]) -> str:
    """Every chord bound to these actions, in binding order, as caps."""
    caps: list[str] = []
    for action in actions:
        for binding in app.BINDINGS:
            if not isinstance(binding, Binding):
                continue
            if binding.action != action:
                continue
            chord = app.keymap.get(binding.id or "", binding.key) or binding.key
            for key in chord.split(","):
                cap = key_cap(key)
                if cap not in caps:
                    caps.append(cap)
    return "  ".join(_group_arrows(caps))


def _group_arrows(caps: list[str]) -> list[str]:
    """Arrow caps that share a prefix read better as one: M-↑↓, S-←↑↓→.

    Only when every cap is an arrow, so a row like `^P  ↑  k` keeps its shape.
    """
    if len(caps) < 2 or caps[0][-1] not in ARROW_CHARS:
        return caps
    prefix = caps[0][:-1]
    if not all(cap.startswith(prefix) and cap[-1] in ARROW_CHARS for cap in caps):
        return caps
    arrows = sorted((cap[-1] for cap in caps), key=ARROW_CHARS.index)
    return [prefix + "".join(arrows)]


def help_text(app: SpoiderApp) -> Text:
    text = Text()
    text.append("spoider — keys and options\n", style="bold")
    for heading, rows in HELP:
        text.append(f"\n{heading}\n", style="bold reverse")
        for actions, explanation in rows:
            keys = actions.keys if isinstance(actions, Literal) else keys_for(app, actions)
            text.append(f"  {_pad(keys, 16)}", style="bold")
            text.append(f"{explanation}\n")
    return text


def _fit_tokens(tokens: tuple[str, ...], width: int) -> str:
    """Keep whole tokens while they fit, then an ellipsis — never half an emoji."""
    shown: list[str] = []
    for token in tokens:
        candidate = " ".join([*shown, token])
        if cell_len(candidate) > width - 1:
            break
        shown.append(token)
    joined = " ".join(shown)
    return joined + ("…" if len(shown) < len(tokens) else "")


def settings_text(app: SpoiderApp, row: int = 0) -> Text:
    rows = [
        ("autosave", "on" if app.autosave else "off", "after every edit, and exit"),
        (
            "marks",
            _fit_tokens(app.marks, 20),
            # the chord is read, never written: a rebound key must not leave this lying
            f"the emojis {key_cap(app.keymap.get('mark', 'g'))} cycles",
        ),
        ("config", clip_tail(str(app.config_path), 20), "⏎ opens it in your editor"),
    ]
    text = Text()
    text.append("editor settings\n", style="bold")
    for index, (label, value, note) in enumerate(rows):
        selected = index == row
        text.append("\n " + ("▸" if selected else " "))
        text.append(_pad(label, 11), style="bold" if selected else "")
        text.append(_pad(value, 22))
        text.append(note, style="dim")
    return text
