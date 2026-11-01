"""Modal screens: text prompt, confirm, help, and settings."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static

from .chrome import key_cap
from .text import clip_tail

if TYPE_CHECKING:
    from .app import SpoiderApp


#: (heading, ((actions, explanation), …))
HelpRow = tuple[tuple[str, ...], str]
HelpSection = tuple[str, tuple[HelpRow, ...]]

# The chords are not written here: they are read from the keymap, so a rebound
# key cannot leave the help lying. Every binding action must appear — the tests
# enforce that in both directions.
HELP: tuple[HelpSection, ...] = (
    (
        "Making cells",
        (
            (("add_child",), "add a child and type its name"),
            (("add_sibling",), "add a sibling after the selection"),
            (("edit",), "rename the selected cell in place"),
            (("delete",), "delete the cell and everything under it"),
            (("mark",), "cycle the mark, then off (set them in ^,)"),
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
        ),
    ),
    (
        "View",
        (
            (("search",), "find cells by their words; ↑ in the prompt recalls one"),
            (("layout",), "cycle the shape: spider, pyramid, bush, branch"),
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
            if action in actions:
                return explanation
    return fallback or action


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
    return "  ".join(caps)


def help_text(app: SpoiderApp) -> Text:
    text = Text()
    text.append("spoider — keys and options\n", style="bold")
    for heading, rows in HELP:
        text.append(f"\n{heading}\n", style="bold reverse")
        for actions, explanation in rows:
            text.append(f"  {_pad(keys_for(app, actions), 16)}", style="bold")
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
        ("marks", _fit_tokens(app.marks, 20), "the emojis ^G cycles"),
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
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "cancel"),
        Binding("ctrl+c", "cancel", "cancel", show=False),
        Binding("ctrl+z", "undo", "", show=False),
        Binding("ctrl+y", "redo", "", show=False),
    ]

    def __init__(
        self, prompt: str, value: str = "", *, preselect: bool = False
    ) -> None:
        super().__init__()
        self._prompt = prompt
        self._value = value
        self._preselect = preselect
        # Textual's Input has no undo of its own, and ^Z must not reach the map
        # behind a dialog, so the field keeps its own small history.
        self._history: list[str] = [value]
        self._index = 0

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

    def on_input_changed(self, event: Input.Changed) -> None:
        # Compare rather than guard with a flag: Textual delivers Changed after
        # the handler returns, so a flag would already be cleared and every undo
        # would push its own result back onto the stack.
        if event.value == self._history[self._index]:
            return
        self._history = [*self._history[: self._index + 1], event.value]
        self._index = len(self._history) - 1

    def _restore(self, index: int) -> None:
        if not 0 <= index < len(self._history):
            return
        self._index = index
        field = self.query_one(Input)
        field.value = self._history[index]
        field.cursor_position = len(field.value)

    def action_undo(self) -> None:
        self._restore(self._index - 1)

    def action_redo(self) -> None:
        self._restore(self._index + 1)

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

    BINDINGS: ClassVar[list[Binding]] = [
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

    # No bindings: any key at all closes this, so there is nothing to learn and
    # nothing to spell out at the bottom.
    def on_key(self, event) -> None:
        event.stop()
        self.dismiss(None)

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="panel"):
            yield Static(help_text(cast("SpoiderApp", self.app)))


class SettingsScreen(ModalScreen[None]):
    """The handful of editor settings there are."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }
    SettingsScreen #panel {
        width: 68;
        max-width: 96%;
        height: auto;
        padding: 1 2;
        background: $surface;
        border: round $accent;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "close"),
        Binding("ctrl+c", "close", "close", show=False),
        Binding("ctrl+x", "close", "close", show=False),
        Binding("ctrl+comma", "close", "close", show=False),
        Binding("up,k", "move(-1)", "", show=False),
        Binding("down,j", "move(+1)", "", show=False),
        Binding("enter,space", "activate", "activate"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.row = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="panel"):
            yield Static(self._body(), id="settings-body")

    def _body(self) -> Text:
        return settings_text(cast("SpoiderApp", self.app), self.row)

    def _redraw(self) -> None:
        self.query_one("#settings-body", Static).update(self._body())

    def action_move(self, delta: int) -> None:
        self.row = max(0, min(2, self.row + delta))
        self._redraw()

    def action_activate(self) -> None:
        app = cast("SpoiderApp", self.app)
        if self.row == 0:
            app.set_autosave(not app.autosave)
            self._redraw()
            return
        if self.row == 1:
            app.push_screen(self._marks_prompt(), self._apply_marks)
            return
        app.open_config()
        self._redraw()

    def _marks_prompt(self) -> TextPrompt:
        app = cast("SpoiderApp", self.app)
        return TextPrompt(
            "Marks, in the order ^G cycles (space separated)", " ".join(app.marks)
        )

    def _apply_marks(self, value: str | None) -> None:
        if value is None:
            return
        app = cast("SpoiderApp", self.app)
        app.set_marks(value.split())
        self._redraw()

    def action_close(self) -> None:
        self.dismiss(None)
