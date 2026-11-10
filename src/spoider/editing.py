"""The text inside a cell being renamed: lines, a caret, a selection, overwrite.

Deliberately small and text-only. It knows nothing about cells, keys or the
screen: the app hands it characters and commands, and it says what the text looks
like now. That keeps the awkward parts (line joins, word boundaries, wrapping) in
one place, where they can be tested without a terminal.

Positions are plain indices into `text`, so a newline is one character like any
other and a selection is a pair of indices.
"""

from __future__ import annotations

from rich.cells import cell_len

from .model import MAX_CELL_CHARS
from .text import tab_width, text_width

#: Where a word ends, for a jump as well as for a deletion: a space, a mark of punctuation,
#: or a sign a line of code leans on. Anything else is part of the word, which is what a
#: person means by "word" either way round: `don't` is two words, and `welcome.` is one word
#: and a full stop.
_BREAK = set(" \t\n.,;:!?()[]{}<>\"'`/\\|-—…_=+*&%$@~^#")


def _is_word_char(ch: str) -> bool:
    return ch not in _BREAK


class Buffer:
    """One cell's text, with a caret and optionally a selection."""

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.caret = len(text)
        self.anchor: int | None = None
        self.overwrite = False
        #: The column `up`/`down` try to keep, so a run of vertical moves through
        #: short lines does not drift left.
        self.goal: int | None = None
        #: How much text a cell may hold, from the model's cap.
        self.limit = MAX_CELL_CHARS
        #: True when the last insert dropped text because the cell was full.
        self.clipped = False
        #: History of (text, caret). A run of one kind of change is one step, whether it is
        #: typed characters or backspaces; a change of another kind, or a move, starts the
        #: next, which is what makes ^Z feel like an editor's.
        self._undo: list[tuple[str, int]] = []
        self._redo: list[tuple[str, int]] = []
        self._run: str | None = None

    # -- geometry --------------------------------------------------------------

    def line_bounds(self, index: int | None = None) -> tuple[int, int]:
        """(start, end) of the line holding `index`; `end` excludes the newline."""
        index = self.caret if index is None else index
        start = self.text.rfind("\n", 0, index) + 1
        end = self.text.find("\n", index)
        return start, (len(self.text) if end == -1 else end)

    def line_number(self, index: int | None = None) -> int:
        index = self.caret if index is None else index
        return self.text.count("\n", 0, index)

    def column(self, index: int | None = None) -> int:
        """How far into its line the caret sits, in cells, so a tab counts as its width."""
        index = self.caret if index is None else index
        start, _ = self.line_bounds(index)
        return text_width(self.text[start:index])

    def lines(self) -> list[str]:
        return self.text.split("\n")

    # -- selection -------------------------------------------------------------

    def selection(self) -> tuple[int, int] | None:
        if self.anchor is None or self.anchor == self.caret:
            return None
        return (min(self.anchor, self.caret), max(self.anchor, self.caret))

    def selected_text(self) -> str:
        span = self.selection()
        return "" if span is None else self.text[span[0] : span[1]]

    def start_selection(self) -> None:
        if self.anchor is None:
            self.anchor = self.caret

    def drop_selection(self) -> None:
        self.anchor = None

    def select_all(self) -> None:
        self.anchor = 0
        self.caret = len(self.text)

    def _replace_selection(self, replacement: str) -> bool:
        """Swap the selection for `replacement`; False when there was none."""
        span = self.selection()
        if span is None:
            return False
        self.text = self.text[: span[0]] + replacement + self.text[span[1] :]
        self.caret = span[0] + len(replacement)
        self.anchor = None
        return True

    # -- editing ---------------------------------------------------------------

    def _remember(self, run: str | None = None) -> None:
        """Snapshot before a change. A burst of one kind of change is one step, so holding
        backspace across a word is undone by one ^Z rather than one per letter."""
        if run is not None and run == self._run:
            return
        self._undo.append((self.text, self.caret))
        self._redo.clear()
        self._run = run

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append((self.text, self.caret))
        self.text, self.caret = self._undo.pop()
        self.anchor = None
        self._run = None
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append((self.text, self.caret))
        self.text, self.caret = self._redo.pop()
        self.anchor = None
        self._run = None
        return True

    @property
    def selection_length(self) -> int:
        """How many characters a typed chunk would replace."""
        if self.anchor is None:
            return 0
        return abs(self.caret - self.anchor)

    def insert(self, chunk: str) -> None:
        chunk = chunk.replace("\r\n", "\n").replace("\r", "\n")
        room = self.limit - len(self.text) + self.selection_length
        if room <= 0:
            self.clipped = bool(chunk)
            return
        if len(chunk) > room:
            chunk = chunk[:room]
            self.clipped = True
        single = len(chunk) == 1 and chunk != "\n"
        self._remember("typing" if single else None)
        if self._replace_selection(chunk):
            return
        if self.overwrite and self.caret < len(self.text) and self.text[self.caret] != "\n":
            end = self.caret + 1
            self.text = self.text[: self.caret] + chunk + self.text[end:]
        else:
            self.text = self.text[: self.caret] + chunk + self.text[self.caret :]
        self.caret += len(chunk)

    def backspace(self) -> None:
        self._remember("backspace")
        if self._replace_selection(""):
            return
        if self.caret == 0:
            return
        self.text = self.text[: self.caret - 1] + self.text[self.caret :]
        self.caret -= 1

    def delete(self) -> None:
        self._remember("delete")
        if self._replace_selection(""):
            return
        if self.caret >= len(self.text):
            return
        self.text = self.text[: self.caret] + self.text[self.caret + 1 :]

    def _word_before(self) -> int:
        index = self.caret
        while index > 0 and not _is_word_char(self.text[index - 1]):
            index -= 1
        while index > 0 and _is_word_char(self.text[index - 1]):
            index -= 1
        return index

    def _word_after(self) -> int:
        index = self.caret
        while index < len(self.text) and not _is_word_char(self.text[index]):
            index += 1
        while index < len(self.text) and _is_word_char(self.text[index]):
            index += 1
        return index

    def delete_word_before(self) -> None:
        self._remember()
        if self._replace_selection(""):
            return
        start = self._word_before()
        self.text = self.text[:start] + self.text[self.caret :]
        self.caret = start

    def delete_word_after(self) -> None:
        self._remember()
        if self._replace_selection(""):
            return
        end = self._word_after()
        self.text = self.text[: self.caret] + self.text[end:]

    # -- movement --------------------------------------------------------------

    def _begin_move(self, extend: bool) -> None:
        """Anchor the selection before the caret moves, or drop it."""
        if extend:
            if self.anchor is None:
                self.anchor = self.caret
        else:
            self.anchor = None
        # a move ends the run: the next change is a new step
        self._run = None

    def left(self, *, extend: bool = False) -> None:
        span = self.selection()
        self._begin_move(extend)
        if span is not None and not extend:
            self.caret = span[0]
        else:
            self.caret = max(0, self.caret - 1)
        self.goal = None

    def right(self, *, extend: bool = False) -> None:
        span = self.selection()
        self._begin_move(extend)
        if span is not None and not extend:
            self.caret = span[1]
        else:
            self.caret = min(len(self.text), self.caret + 1)
        self.goal = None

    def up(self, *, extend: bool = False) -> None:
        start, _ = self.line_bounds()
        if start == 0:
            return
        column = self.goal if self.goal is not None else self.column()
        self._begin_move(extend)
        previous_end = start - 1
        previous_start = self.text.rfind("\n", 0, previous_end) + 1
        self.caret = self._clamp_to_column(previous_start, previous_end, column)
        self.goal = column

    def down(self, *, extend: bool = False) -> None:
        _, end = self.line_bounds()
        if end >= len(self.text):
            return
        column = self.goal if self.goal is not None else self.column()
        self._begin_move(extend)
        next_start = end + 1
        next_end = self.text.find("\n", next_start)
        next_end = len(self.text) if next_end == -1 else next_end
        self.caret = self._clamp_to_column(next_start, next_end, column)
        self.goal = column

    def _clamp_to_column(self, start: int, end: int, column: int) -> int:
        """The index in [start, end] closest to `column` cells in.

        A tab is as wide here as it is drawn, expanding to the next stop of `tab_width`
        from the line's start, so a caret that goes down a line keeps the column it had
        rather than one counted without the tabs.
        """
        used = 0
        index = start
        stop = tab_width()
        while index < end and used < column:
            used += stop - used % stop if self.text[index] == "\t" else cell_len(self.text[index])
            index += 1
        return index

    def home(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = self.line_bounds()[0]
        self.goal = None

    def end(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = self.line_bounds()[1]
        self.goal = None

    #: How many lines a page key moves. A cell does not know the screen it is drawn on,
    #: so this is a fixed, comfortable jump rather than a measured one.
    PAGE_LINES = 10  # replaced by `page_lines` from the config when a cell opens

    def page_up(self, *, extend: bool = False) -> None:
        for _ in range(self.PAGE_LINES):
            before = self.caret
            self.up(extend=extend)
            if self.caret == before:
                break

    def page_down(self, *, extend: bool = False) -> None:
        for _ in range(self.PAGE_LINES):
            before = self.caret
            self.down(extend=extend)
            if self.caret == before:
                break

    def word_left(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = self._word_before()
        self.goal = None

    def word_right(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = self._word_after()
        self.goal = None

    def document_home(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = 0
        self.goal = None

    def document_end(self, *, extend: bool = False) -> None:
        self._begin_move(extend)
        self.caret = len(self.text)
        self.goal = None

    # -- caret position in lines ----------------------------------------------

    def caret_position(self) -> tuple[int, int]:
        """(line, column in cells) for drawing."""
        return self.line_number(), self.column()

    def set_caret_from(self, line: int, column: int) -> None:
        lines = self.lines()
        line = max(0, min(line, len(lines) - 1))
        start = sum(len(part) + 1 for part in lines[:line])
        self.caret = self._clamp_to_column(start, start + len(lines[line]), column)
        self.goal = None


def reflow(text: str, width: int) -> str:
    """`text` wrapped to `width` cells, a blank line keeping paragraphs apart.

    Every run of lines between blank lines is one paragraph: its words are joined
    and filled greedily, which is what nano's justify does. A word longer than the
    width is left on a line of its own rather than broken.
    """
    width = max(1, width)
    paragraphs = text.split("\n\n")
    wrapped: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            wrapped.append("")
            continue
        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if cell_len(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        wrapped.append("\n".join(lines))
    return "\n\n".join(wrapped)
