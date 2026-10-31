"""Modal screens: a one-line text prompt and a yes/no confirm."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label


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
