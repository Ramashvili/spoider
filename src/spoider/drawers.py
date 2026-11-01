"""The bottom drawers: prompts, questions and panels, all above the one bar.

Nothing in this app opens a window over the map. Whatever it needs to ask, it
asks on the last lines and leaves the shortcut bar below saying what the answer
accepts, which is where nano puts its prompts too — and it means there is never a
second footer to keep in step with the first.
"""

from __future__ import annotations

from collections.abc import Callable

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.widget import Widget

from .chrome import CARET
from .text import clip_tail


class Drawer(Widget, can_focus=True):
    """A line (or a few) at the bottom of the screen, shown one at a time."""

    def open(self) -> None:
        self.display = True
        self.focus()
        self.refresh()

    def close(self) -> None:
        self.display = False


def values_match(value: str, recall: list[str]) -> bool:
    return bool(recall) and value == recall[0]


class PromptBar(Drawer):
    """One line that asks for a word: a search, a file name, a set of marks.

    Enter answers, esc or ^C backs out, ^Z and ^Y walk the edits, and up and down
    recall earlier answers when the prompt was given a list to keep.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = ""
        self.value = ""
        self.cursor = 0
        self.recall: list[str] | None = None
        self._submit: Callable[[str], None] = lambda value: None
        self._cancel: Callable[[], None] = lambda: None
        self._change: Callable[[str], None] | None = None
        self._history_index = -1
        self._draft = ""
        self._fresh = False
        self._undo: list[tuple[str, int]] = []
        self._redo: list[tuple[str, int]] = []

    # -- opening -------------------------------------------------------

    def ask(
        self,
        label: str,
        value: str = "",
        *,
        preselect: bool = False,
        recall: list[str] | None = None,
        submit: Callable[[str], None],
        cancel: Callable[[], None],
        change: Callable[[str], None] | None = None,
    ) -> None:
        self.label = label
        self.value = value
        self.cursor = len(value)
        self.recall = recall
        self._submit = submit
        self._cancel = cancel
        self._change = change
        # when the prompt offers the newest answer, that is where the walk back
        # starts: up moves to the one before it
        self._history_index = 0 if recall and values_match(value, recall) else -1
        self._draft = value
        self._fresh = preselect and bool(value)
        self._undo.clear()
        self._redo.clear()
        self.open()

    # -- keys ----------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """The prompt owns every key while it is open: a stray ^D must not delete
        the cell behind it, and a stray ^X must not quit."""
        event.stop()
        event.prevent_default()

        key = event.key
        if key == "enter":
            self._answer()
        elif key in ("escape", "ctrl+c"):
            self._cancel()
        elif key == "ctrl+z":
            self._undo_edit()
        elif key == "ctrl+y":
            self._redo_edit()
        elif key == "backspace" and self.cursor:
            self._edit(self.value[: self.cursor - 1] + self.value[self.cursor :], self.cursor - 1)
        elif key == "delete":
            self._edit(self.value[: self.cursor] + self.value[self.cursor + 1 :], self.cursor)
        elif key in ("left", "ctrl+b"):
            self.cursor = max(0, self.cursor - 1)
        elif key in ("right", "ctrl+f"):
            self.cursor = min(len(self.value), self.cursor + 1)
        elif key in ("home", "ctrl+a"):
            self.cursor = 0
        elif key in ("end", "ctrl+e"):
            self.cursor = len(self.value)
        elif key in ("up", "down") and self.recall:
            self._recall(+1 if key == "up" else -1)
        elif event.character and event.character.isprintable():
            character = event.character
            if self._fresh:
                # typing replaces what the prompt offered rather than appending
                self._edit(character, len(character))
            else:
                self._edit(
                    self.value[: self.cursor] + character + self.value[self.cursor :],
                    self.cursor + len(character),
                )
        self.refresh()

    def _edit(self, value: str, cursor: int) -> None:
        self._undo.append((self.value, self.cursor))
        self._redo.clear()
        self._history_index = -1
        self._fresh = False
        self.value = value
        self.cursor = cursor
        if self._change is not None:
            self._change(value)

    def _restore(self, state: tuple[str, int]) -> None:
        self.value, self.cursor = state
        self._fresh = False
        if self._change is not None:
            self._change(self.value)

    def _undo_edit(self) -> None:
        if not self._undo:
            return
        self._redo.append((self.value, self.cursor))
        self._restore(self._undo.pop())

    def _redo_edit(self) -> None:
        if not self._redo:
            return
        self._undo.append((self.value, self.cursor))
        self._restore(self._redo.pop())

    def _answer(self) -> None:
        value = self.value.strip()
        if self.recall is not None and value:
            if value in self.recall:
                self.recall.remove(value)
            self.recall.insert(0, value)
        self._submit(value)

    def _recall(self, step: int) -> None:
        """step +1 walks back through older answers, -1 returns towards the draft."""
        assert self.recall is not None
        if not self.recall:
            return
        if self._history_index == -1:
            self._draft = self.value
        target = self._history_index + step
        if target < -1 or target >= len(self.recall):
            return
        self._history_index = target
        self._fresh = False
        self.value = self._draft if target == -1 else self.recall[target]
        self.cursor = len(self.value)
        if self._change is not None:
            self._change(self.value)

    # -- drawing -------------------------------------------------------

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        line = self.value[: self.cursor] + CARET + self.value[self.cursor :]
        room = max(0, width - cell_len(self.label) - 2)
        if cell_len(line) > room:
            line = clip_tail(line, room)
        bar = Text(self.label, style="bold")
        bar.append(line)
        return bar


class AskBar(Drawer):
    """One line that asks a yes/no question; the bar below spells out the keys."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.question = ""
        self._answer: Callable[[str | None], None] = lambda choice: None

    def ask(self, question: str, answer: Callable[[str | None], None]) -> None:
        self.question = question
        self._answer = answer
        self.open()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if event.key in ("y", "Y"):
            self._answer("yes")
        elif event.key in ("n", "N"):
            self._answer("no")
        elif event.key in ("escape", "ctrl+c"):
            self._answer(None)

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        return Text(clip_tail(self.question, width - 1))


class PanelBar(Drawer):
    """A few lines at the bottom: the settings list, or the help page.

    It grows upwards from the bar and never covers the whole screen; whatever it
    cannot show is left out rather than scrolled, because a panel is a reference,
    not a document.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._text = Text("")
        self._rows = 0
        self._key_handler: Callable[[str], None] = lambda key: None

    def show(self, text: Text, on_key: Callable[[str], None]) -> None:
        self._text = text
        self._key_handler = on_key
        rows = max(1, text.plain.count("\n") + 1)
        room = max(3, self.app.size.height - 4)  # the bar, the top line, a little map
        self._rows = min(rows, room)
        self.styles.height = self._rows
        self.open()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        self._key_handler(event.key)

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        panel = Text()
        for index, line in enumerate(self._text.split("\n")[: self._rows]):
            if index:
                panel.append("\n")
            if cell_len(line.plain) > width:
                panel.append(clip_tail(line.plain, width - 1), style=str(line.spans[0].style) if line.spans else "")
            else:
                panel.append_text(line)
        return panel
