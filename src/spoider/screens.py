"""Modal screens: text prompt, confirm, help, and settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from .chrome import key_cap

if TYPE_CHECKING:
    from .app import SpoiderApp


# (heading, ((actions, keys as printed, explanation), …))
# Every binding action must appear here — tests/test_app.py enforces it, so the
# help cannot drift away from the keymap.
HELP: tuple[tuple[str, tuple[tuple[tuple[str, ...], str, str], ...]], ...] = (
    (
        "Making cells",
        (
            (("add_child",), "⇥  ^A", "add a child and type its name"),
            (("add_sibling",), "⏎  ^J", "add a sibling after the selection"),
            (("edit",), "^E", "rename the selected cell in place"),
            (("delete",), "^D", "delete the cell and everything under it"),
            (("mark",), "^G", "cycle the mark: ✅ ❌ ❓ ❗ 🕐 then off"),
            (("toggle",), "^T", "fold or unfold the branch"),
        ),
    ),
    (
        "Moving",
        (
            (("prev",), "^P  ↑  k", "previous sibling"),
            (("next",), "^N  ↓  j", "next sibling"),
            (("go_left",), "^B  ←  h", "left: out to parent, or deeper on a left branch"),
            (("go_right",), "^F  →  l", "right: the mirror of the above"),
            (("move_up",), "⌥↑", "move the cell up among its siblings"),
            (("move_down",), "⌥↓", "move it down"),
        ),
    ),
    (
        "View",
        (
            (("spacing_more",), "^+", "more air between cells — saved with the map"),
            (("spacing_less",), "^-", "less air, down to cells sharing a border row"),
        ),
    ),
    (
        "File",
        (
            (("save",), "^S", "write straight back to the current file"),
            (("write",), "^O", "write out: asks which file, so it saves as"),
            (("quit",), "^X", "quit; asks y / n / esc if unsaved"),
        ),
    ),
    (
        "History",
        (
            (("undo",), "^Z", "undo the last edit"),
            (("redo",), "^Y", "redo the last undone edit"),
        ),
    ),
    (
        "This screen",
        (
            (("help",), "^/", "this help"),
            (("settings",), "^,", "editor settings"),
        ),
    ),
)

NOTES = (
    ("Typing", "⏎ keeps the name, esc/^C discards it"),
    ("Dirty", "a * in the terminal title means unsaved work"),
    ("Saving", "nothing is written until ^S or ^O"),
    ("Spacing", "saved in the file, so maps look alike everywhere"),
    ("Mouse", "click selects, double-click renames"),
    ("Colours", "inherited from your terminal; no palette"),
)


def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - cell_len(text))


def help_text() -> Text:
    text = Text()
    text.append("spoider — keys and options\n", style="bold")
    for heading, rows in HELP:
        text.append(f"\n{heading}\n", style="bold reverse")
        for _, keys, explanation in rows:
            text.append(f"  {_pad(keys, 14)}", style="bold")
            text.append(f"{explanation}\n")
    text.append("\nAlso\n", style="bold reverse")
    for head, tail in NOTES:
        text.append(f"  {_pad(head, 14)}", style="bold")
        text.append(f"{tail}\n")
    text.append("\nesc closes this", style="dim")
    return text


def _clip(text: str, width: int) -> str:
    """Keep the tail of a long path; the leaf is the useful half."""
    if cell_len(text) <= width:
        return text
    return "…" + text[-(width - 1) :]


def settings_text(app: "SpoiderApp") -> Text:
    where = _clip(str(app.path), 18) if app.path.exists() else "New Buffer"
    text = Text()
    text.append("editor settings\n", style="bold")
    rows = [
        ("spacing", f"{app.spacing:+d}", "^- / ^+ to change, saved with the map"),
        ("colours", "terminal", "inherited from your terminal"),
        ("file", where, "^O writes it somewhere else"),
        ("cells", str(app.mm.count()), ""),
        ("version", __import__("spoider").__version__, ""),
    ]
    for label, value, note in rows:
        text.append("\n" + _pad(label, 10), style="bold")
        text.append(_pad(value, 18))
        text.append(note, style="dim")
    text.append("\n\nesc closes this", style="dim")
    return text


class TextPrompt(ModalScreen[str | None]):
    """Ask for one line of text. Dismisses with the value, or None on escape."""

    DEFAULT_CSS = """
    TextPrompt {
        align: center middle;
    }
    TextPrompt #dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    TextPrompt #prompt-label {
        padding-bottom: 1;
        color: $text-muted;
    }
    """

    # ^C is escape everywhere in spoider
    BINDINGS = [
        Binding("escape", "cancel", "cancel"),
        Binding("ctrl+c", "cancel", "cancel", show=False),
    ]

    def __init__(
        self, prompt: str, value: str = "", *, preselect: bool = False
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._value = value
        self._preselect = preselect

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt, id="prompt-label")
            yield Input(value=self._value, id="prompt-input")

    def on_mount(self) -> None:
        field = self.query_one(Input)
        field.cursor_blink = False  # a steady block, like a terminal caret
        field.focus()
        if self._preselect:
            field.select_all()
        else:
            field.cursor_position = len(field.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Confirm(ModalScreen[str | None]):
    """A one-question dialog answering "yes", "no", or None for cancelled."""

    DEFAULT_CSS = """
    Confirm {
        align: center middle;
    }
    Confirm #dialog {
        width: 56;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    Confirm #prompt-label {
        padding-bottom: 1;
    }
    Confirm #hint {
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("y", "answer('yes')", "yes"),
        Binding("n", "answer('no')", "no"),
        Binding("escape", "cancel", "cancel"),
        Binding("ctrl+c", "cancel", "cancel", show=False),
    ]

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Label(self._prompt, id="prompt-label")
            yield Label("[b]y[/] save  [b]n[/] discard  [b]esc[/] cancel", id="hint")

    def action_answer(self, answer: str) -> None:
        self.dismiss(answer)

    def action_cancel(self) -> None:
        self.dismiss(None)


class HelpScreen(ModalScreen[None]):
    """Everything the app can do, with a line of explanation each."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen #panel {
        width: 74;
        max-width: 96%;
        height: auto;
        max-height: 92%;
        padding: 0 2;
        background: $surface;
        border: round $accent;
    }
    HelpScreen Static {
        width: 100%;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("ctrl+c", "close", "close", show=False),
        Binding("ctrl+slash", "close", "close", show=False),
        Binding("question_mark", "close", "close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="panel"):
            yield Static(help_text())

    def action_close(self) -> None:
        self.dismiss(None)


class SettingsScreen(ModalScreen[None]):
    """The handful of editor settings there are."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen #panel {
        width: 76;
        max-width: 96%;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "close"),
        Binding("ctrl+c", "close", "close", show=False),
        Binding("ctrl+comma", "close", "close", show=False),
        # the spacing chords stay live in here so the settings can be nudged
        Binding("ctrl+minus,ctrl+underscore,alt+minus", "narrow", "tighter"),
        Binding(
            "ctrl+shift+equals_sign,ctrl+equals_sign,ctrl+plus,ctrl+shift+plus,"
            "alt+equals_sign,alt+plus",
            "widen",
            "looser",
        ),
    ]

    def compose(self) -> ComposeResult:
        app: "SpoiderApp" = self.app  # type: ignore[assignment]
        with Vertical(id="panel"):
            yield Static(settings_text(app), id="settings-body")

    def _redraw(self) -> None:
        app: "SpoiderApp" = self.app  # type: ignore[assignment]
        self.query_one("#settings-body", Static).update(settings_text(app))

    def action_narrow(self) -> None:
        self.app.nudge_spacing(-1)  # type: ignore[attr-defined]
        self._redraw()

    def action_widen(self) -> None:
        self.app.nudge_spacing(+1)  # type: ignore[attr-defined]
        self._redraw()

    def action_close(self) -> None:
        self.dismiss(None)
