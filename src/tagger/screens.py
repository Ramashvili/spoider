"""A modal one-line text prompt."""

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

    BINDINGS = [Binding("escape", "cancel", "cancel")]

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
