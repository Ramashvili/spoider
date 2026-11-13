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

from .chrome import ERROR_STYLE, FAILURE
from .editing import Buffer
from .model import MAX_PROMPT_CHARS
from .text import clean, clip_head, clip_tail


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


def _shown_value(value: str, caret: int, room: int) -> tuple[str, int]:
    """What the prompt draws of its value, and where the caret sits in what it draws.

    A value that fits is drawn whole. A longer one is drawn from its end, which is the useful
    half of a path, and the window moves with the caret: walking left, or pressing Home, brings
    the front of it into view instead of leaving it out of reach, and an ellipsis stands at each
    end that has text hidden behind it.
    """
    if room <= 0:
        return "", 0
    if cell_len(value) <= room:
        return value, caret

    # the end of the value, with a column kept for the head's ellipsis
    tail_start = max(0, len(value) - (room - 1))
    start = tail_start if caret >= tail_start else caret
    head = "…" if start else ""
    budget = room - cell_len(head)

    index = start
    used = 0
    while index < len(value) and used + cell_len(value[index]) <= budget:
        used += cell_len(value[index])
        index += 1
    tail = index < len(value)
    while tail and used + 1 > budget and index > start:
        index -= 1
        used -= cell_len(value[index])
    drawn = head + value[start:index] + ("…" if tail else "")
    return drawn, cell_len(head + value[start:caret])


class PromptBar(Drawer):
    """One line that asks for a word: a search, a file name, a set of marks.

    The editing is the cell editor's: a `Buffer` holds the text, so a word jump, a
    deletion, an undo or a paste behaves here exactly as it does in a cell. The keys that
    need a second line are simply not offered: enter answers, esc or ^C backs out, and up
    and down recall earlier answers when the prompt was given a list to keep.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.label = ""
        self.buffer = self._fresh_buffer()
        self.recall: list[str] | None = None
        self._submit: Callable[[str], None] = lambda value: None
        self._cancel: Callable[[], None] = lambda: None
        self._change: Callable[[str], None] | None = None
        self._history_index = -1
        self._draft = ""
        self._fresh = False

    def _fresh_buffer(self, value: str = "") -> Buffer:
        """A prompt's buffer: the cell editor's, holding a word rather than a paragraph."""
        buffer = Buffer(value)
        buffer.limit = MAX_PROMPT_CHARS
        return buffer

    # -- the two words the rest of the app speaks ------------------------

    @property
    def value(self) -> str:
        return self.buffer.text

    @value.setter
    def value(self, text: str) -> None:
        self.buffer.text = text
        self.buffer.caret = len(text)

    @property
    def cursor(self) -> int:
        return self.buffer.caret

    @cursor.setter
    def cursor(self, index: int) -> None:
        self.buffer.caret = max(0, min(index, len(self.buffer.text)))

    # -- opening -------------------------------------------------------

    def ask(
        self,
        label: str,
        value: str = "",
        *,
        cursor: int | None = None,
        preselect: bool = False,
        recall: list[str] | None = None,
        submit: Callable[[str], None],
        cancel: Callable[[], None],
        change: Callable[[str], None] | None = None,
    ) -> None:
        self.label = label
        # a fresh buffer, so the undo history starts with this question rather than the last
        self.buffer = self._fresh_buffer(value)
        # a caret position when the caller has one, the end of the value otherwise
        self.cursor = len(value) if cursor is None else max(0, min(cursor, len(value)))
        self.recall = recall
        self._submit = submit
        self._cancel = cancel
        self._change = change
        # when the prompt offers the newest answer, that is where the walk back
        # starts: up moves to the one before it
        self._history_index = 0 if recall and values_match(value, recall) else -1
        self._draft = value
        self._fresh = preselect and bool(value)
        self.open()

    # -- keys ----------------------------------------------------------

    def on_key(self, event: events.Key) -> None:
        """The prompt owns every key while it is open: a stray ^D must not delete
        the cell behind it, and a stray ^X must not quit.

        Everything that edits the text is the buffer's, so it behaves the way the cell
        editor does: word jumps stop at punctuation, a run of one kind of change is one
        undo step, and alt+backspace takes a word.
        """
        event.stop()
        event.prevent_default()

        key = event.key
        buffer = self.buffer
        if key == "enter":
            self._answer()
        elif key in ("escape", "ctrl+c"):
            self._cancel()
        elif key == "ctrl+z":
            if buffer.undo():
                self._changed()
        elif key == "ctrl+y":
            if buffer.redo():
                self._changed()
        elif key in ("backspace", "alt+backspace"):
            if key == "backspace":
                buffer.backspace()
            else:
                buffer.delete_word_before()
            self._changed()
        elif key in ("delete", "alt+d"):
            if key == "delete":
                buffer.delete()
            else:
                buffer.delete_word_after()
            self._changed()
        elif key in ("left", "ctrl+b"):
            buffer.left()
        elif key in ("right", "ctrl+f"):
            buffer.right()
        elif key == "ctrl+left":
            buffer.word_left()
        elif key == "ctrl+right":
            buffer.word_right()
        elif key in ("home", "ctrl+a", "ctrl+home"):
            buffer.home()
        elif key in ("end", "ctrl+e", "ctrl+end"):
            buffer.end()
        elif key == "pageup":
            self.cursor = max(0, self.cursor - self.page_width())
        elif key == "pagedown":
            self.cursor = min(len(buffer.text), self.cursor + self.page_width())
        elif key in ("up", "down") and self.recall:
            self._recall(+1 if key == "up" else -1)
        elif event.character and event.character.isprintable():
            if self._fresh:
                # typing replaces what the prompt offered rather than appending
                buffer.select_all()
            buffer.insert(event.character)
            self._capped()
            self._changed()
        self.refresh()

    def on_paste(self, event: events.Paste) -> None:
        """Text the terminal pasted lands at the caret, on one line: a prompt is one row,
        so a line break in the chunk becomes the space between two words."""
        event.stop()
        # A clipboard can be megabytes long, and a prompt holds 512 characters: the work
        # below happens on a bounded prefix, so nothing pays for text that is dropped.
        # Breaks become the space between two words, and the chunk is cleaned on the way in
        # the way a cell's is: a control character in a one-line prompt is never content.
        chunk = clean(_fold_breaks(event.text[: MAX_PROMPT_CHARS * 4]))
        if not clean(chunk).strip():
            return
        if self._fresh:
            # the offered value is replaced by what was pasted, as it is by typing
            self.buffer.select_all()
        self.buffer.insert(chunk)
        self._capped()
        self._changed()
        self.refresh()

    def _capped(self) -> None:
        """Say when the prompt could not keep all of what arrived, rather than cut it quietly."""
        if not self.buffer.clipped:
            return
        self.buffer.clipped = False
        self.app.notify(
            f"a prompt holds {MAX_PROMPT_CHARS} characters, so the end was dropped",
            severity="error",
            timeout=FAILURE,
        )

    def _changed(self) -> None:
        """The text was edited: the history walk is over and the offered value is gone."""
        self._history_index = -1
        self._fresh = False
        if self._change is not None:
            self._change(self.buffer.text)

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
        if self._change is not None:
            self._change(self.value)

    # -- drawing -------------------------------------------------------

    def page_width(self) -> int:
        """How far a page key moves: the room the value has on the line."""
        return max(1, self.size.width - len(self.label) - 2)

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        # Cleaned on the way out only: the value itself is what gets written.
        value = clean(self.value)
        caret = len(clean(self.value[: self.cursor]))
        room = max(1, width - cell_len(self.label) - 2)
        value, caret = _shown_value(value, caret, room)
        if caret >= len(value):
            value += " "  # past the last character the caret sits on a blank
        caret = max(0, min(caret, len(value) - 1))
        # The whole line is a band, so the question is visible against the map above it.
        # The caret is the one cell of that band left plain: a hole you can see, where a
        # reversed caret on a reversed background would vanish.
        bar = Text()
        bar.append(self.label, "reverse")
        if self._fresh:
            # what the prompt offered is *drawn plain*, the way a selection shows in a
            # reversed bar: typing over it is the obvious thing, and the caret returns
            # as a hole once the first key has replaced it
            offered = value.rstrip(" ")
            bar.append(offered)
            bar.append(value[len(offered) :], "reverse")
        else:
            bar.append(value[:caret], "reverse")
            bar.append(value[caret : caret + 1])
            bar.append(value[caret + 1 :], "reverse")
        used = cell_len(self.label) + cell_len(value)
        bar.append(" " * max(0, width - used), "reverse")
        return bar


def _fold_breaks(text: str) -> str:
    """A pasted chunk on one line: every break, and the blanks around it, is one space.

    Split and join rather than a pattern. The regex this replaces was
    `[ \t]*(?:\r\n|\r|\n)[ \t]*`, and a run of blanks with no break in it made the greedy
    group backtrack at every column: a paste of a hundred thousand spaces froze the screen
    for over a minute. Folding the breaks by hand cannot do that.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if len(lines) == 1:
        return lines[0]
    first = lines[0].rstrip(" \t")
    last = lines[-1].lstrip(" \t")
    middle = [line.strip(" \t") for line in lines[1:-1] if line.strip(" \t")]
    return " ".join([first, *middle, last])


class NoticeBar(Drawer):
    """What just happened, on one line above the bar of keys, where nano puts its messages.

    A temporary notice steps in front of a standing one and gives the line back when its time
    is up. A notice with no time is the one the reader has to act on, a config that fights
    itself, so it is kept rather than said once and lost. A prompt opens over the line and the
    notice goes; it comes back when the question does. The line is a band in the colour of its
    meaning, centred, and it takes no row from the map.
    """

    can_focus = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = ""
        self.style = ""
        #: How wide the band is: the sentence plus one column of air each side.
        self.band = 1
        self._timer: object | None = None
        #: What has no time of its own and waits for its fix: the config's complaints.
        self._standing: tuple[str, str] | None = None
        #: Called after every change of what is drawn, so the band is centred again.
        self.on_change: Callable[[], None] | None = None

    def show(self, message: str, style: str, timeout: float | None) -> None:
        """Say one thing, and take it back after its time.

        A notice with no time is kept: a temporary notice written over it is the later thing
        to read, not a reason to forget the older one, and the line goes back when the newer
        one's time is up.
        """
        standing = timeout == float("inf")
        if standing:
            self._standing = (message, style)
        self._draw(message, style)
        self._stop_timer()
        if message and not standing and timeout is not None:
            self._timer = self.set_timer(timeout, self._expire)

    def restore(self) -> None:
        """Give the line back to what is standing, or clear it when nothing is."""
        if self._standing is None:
            self._draw("", "")
        else:
            self._draw(*self._standing)

    def close(self) -> None:
        """A question needs the line: the notice goes, and what is standing waits for it."""
        self._stop_timer()
        self._draw("", "")

    def forget(self) -> None:
        """Nothing is standing any more: the file that complained has been read again."""
        self._standing = None
        self.close()

    def _expire(self) -> None:
        self._timer = None
        self.restore()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()  # type: ignore[attr-defined]
            self._timer = None

    def _draw(self, message: str, style: str) -> None:
        self.message = message
        self.style = style
        self.band = min(self.app.size.width, cell_len(message) + 2) if message else 1
        self.styles.width = self.band
        self.display = bool(message)
        if self.on_change is not None:
            self.on_change()
        self.refresh()

    def render(self) -> Text:
        """A band the width of the sentence, one column of air each side of it.

        The bar is placed by the app, which centres it and knows the screen, so this draws
        only what it says and the air around it.
        """
        width = self.band
        if width <= 0 or not self.message:
            return Text("")
        text = clean(self.message)
        if cell_len(text) > width - 2:
            # clip_head keeps the start and ends with its own ellipsis, so the band stays
            # the width it asked for
            text = clip_head(text, max(1, width - 2))
        line = Text()
        line.append(f" {text} ", self.style)  # a span, which the screen paints
        return line


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
        # a question is a band too: it has to be seen against the map behind it
        ask = clip_tail(clean(self.question), width - 1)
        line = Text(ask, "reverse")
        line.append(" " * max(0, width - cell_len(ask)), "reverse")
        return line


class ErrorBar(Drawer):
    """A red line at the bottom that says what went wrong and how to leave.

    For states where nothing else may be done: a file that could not be read, and
    whatever the program has to refuse outright. Any of its keys goes.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.message = ""

    def show(self, message: str) -> None:
        """Show the line. The key that acknowledges it is the app's business.

        A drawer sees keys only while it holds focus, and this is the state where nothing
        else may be done: a terminal that leaves the focus elsewhere left the program with
        no way out at all. `SpoiderApp.on_key` answers for it, whatever has the focus.
        """
        self.message = message
        self.open()

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        shown = clip_head(clean(self.message), width - 1)
        line = Text(shown, ERROR_STYLE)
        line.append(" " * max(0, width - cell_len(shown)), ERROR_STYLE)
        return line


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
        self._offset = 0
        self._key_handler: Callable[[str], None] = lambda key: None

    def show(self, text: Text, on_key: Callable[[str], None]) -> None:
        self._text = text
        self._offset = 0
        self._key_handler = on_key
        rows = max(1, text.plain.count("\n") + 1)
        # the page takes every row between the top line and the bar of keys, so the bar is
        # the last row of the screen and the text scrolls inside the page, not the screen
        room = max(3, self.app.size.height - 2)
        self._rows = min(rows, room)
        self.styles.height = room
        self.open()

    @property
    def rows(self) -> int:
        """How many lines the panel is showing."""
        return self._rows

    @property
    def scrollable(self) -> bool:
        """True when the panel holds more than the screen shows."""
        return self._text.plain.count("\n") + 1 > self._rows

    def scroll_by(self, rows: int) -> None:
        """Move the window over the text, stopping at both ends.

        Not `scroll`: Textual already has one with a different signature.
        """
        total = self._text.plain.count("\n") + 1
        highest = max(0, total - self._rows)
        self._offset = max(0, min(self._offset + rows, highest))
        self.refresh()

    def jump_to(self, where: str) -> None:
        total = self._text.plain.count("\n") + 1
        highest = max(0, total - self._rows)
        self._offset = 0 if where == "top" else highest
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        self._key_handler(event.key)

    def render(self) -> Text:
        width = self.size.width
        if width <= 0 or not self.display:
            return Text("")
        panel = Text()
        # allow_blank keeps a trailing empty line: a panel that asks for air
        # above the bar gets it, rather than being silently trimmed
        lines = self._text.split("\n", allow_blank=True)
        for index, line in enumerate(lines[self._offset : self._offset + self._rows]):
            if index:
                panel.append("\n")
            if cell_len(line.plain) > width:
                panel.append(clip_tail(line.plain, width - 1), style=str(line.spans[0].style) if line.spans else "")
            else:
                panel.append_text(line)
        return panel
