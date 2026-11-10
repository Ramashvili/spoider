"""Small text helpers shared by the renderer, the chrome and the model.

Everything on screen ends up in the terminal, and a map file is untrusted input:
a cell whose text contains an escape sequence would otherwise let the file clear
the screen, recolour the app or drive the clipboard (OSC 52) the moment it is
opened. `clean` is applied both when a document is read and when it is drawn.
"""

from __future__ import annotations

import re
import unicodedata

from rich.cells import cell_len

#: How wide a tab is: spaces up to the next stop, counted from the start of a line, so a
#: cell shows the tab stops a text field would. The column is measured in cells. The
#: editor takes `tab_width` from the config at startup and calls `set_tab_width`.
DEFAULT_TAB_WIDTH = 4
_tab_width = DEFAULT_TAB_WIDTH


def tab_width() -> int:
    """The stop a tab is drawn to, in cells."""
    return _tab_width


def set_tab_width(width: int) -> None:
    """Take the tab stop from the editor's settings. Clamped by the caller and here."""
    global _tab_width
    _tab_width = max(1, min(int(width), 16))

#: Cc = control characters (ESC, BEL, newline, …), Cs = lone surrogate halves.
#: Both are dropped rather than replaced: a cell holds one line of visible text,
#: and a zero-width replacement would still be a character the terminal acts on.
#: Cf (ZWJ, variation selectors, bidi marks) is kept — stripping it would break
#: emoji sequences such as 👨‍👩‍👧 into their separate parts.
_UNSAFE = frozenset({"Cc", "Cs"})


def clean(value: object) -> str:
    """`value` as a string with control characters removed, line breaks included.

    For anything that must stay on one line: ids, marks, file names, the top bar.
    Cell text uses `clean_text`, which keeps the line breaks a cell may hold.
    """
    text = value if isinstance(value, str) else str(value)
    if not any(unicodedata.category(ch) in _UNSAFE for ch in text):
        return text
    return "".join(ch for ch in text if unicodedata.category(ch) not in _UNSAFE)


def clean_text(value: object) -> str:
    """`value` with control characters removed, except the line break and the tab.

    A cell holds more than one line, so a newline is content; it holds a tab too, because
    a tab is one of the things a person pastes out of a table. Both are kept, and
    `expand_tabs` decides how wide the tab is drawn. The rest of Cc goes.
    """
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    keep = ("\n", "\t")
    if not any(unicodedata.category(ch) in _UNSAFE and ch not in keep for ch in text):
        return text
    return "".join(
        ch for ch in text if ch in keep or unicodedata.category(ch) not in _UNSAFE
    )


def expand_tabs(text: str) -> str:
    """`text` with each tab replaced by the spaces up to the next tab stop.

    Stops are counted per line from its first cell, in cells, so a tab after one
    character is three columns wide and a tab at the start of a line is four. A tab is
    never zero columns: that is what put the text after it out of alignment with the
    box drawn around it.
    """
    if "\t" not in text:
        return text
    stop = _tab_width
    lines: list[str] = []
    for line in text.split("\n"):
        column = 0
        out: list[str] = []
        for ch in line:
            if ch == "\t":
                width = stop - column % stop
                out.append(" " * width)
                column += width
            else:
                out.append(ch)
                column += cell_len(ch)
        lines.append("".join(out))
    return "\n".join(lines)


def text_width(text: str) -> int:
    """How many cells `text` occupies once its tabs are drawn."""
    return cell_len(expand_tabs(text))


def one_line(value: object) -> str:
    """`value` as one line, for the surfaces that hold a single row.

    A cell may hold several lines, and a notice, a prompt or a top bar shows what was
    taken from it. Cleaning alone would delete the line break and leave the words
    fused, so every run of whitespace becomes one space first.
    """
    text = value if isinstance(value, str) else str(value)
    return clean(" ".join(text.split()))


def clip_head(text: str, limit: int) -> str:
    """Keep the start of `text`, ellipsised, never wider than `limit` cells."""
    if limit <= 0:
        return ""
    if cell_len(text) <= limit:
        return text
    kept: list[str] = []
    used = 0
    for char in text:
        width = cell_len(char)
        if used + width > limit - 1:
            break
        kept.append(char)
        used += width
    return "".join(kept) + "…"


def clip_tail(text: str, limit: int) -> str:
    """Keep the end of `text` — a path's leaf is the useful half."""
    if limit <= 0:
        return ""
    if cell_len(text) <= limit:
        return text
    kept: list[str] = []
    used = 0
    for char in reversed(text):
        width = cell_len(char)
        if used + width > limit - 1:
            break
        kept.append(char)
        used += width
    return "…" + "".join(reversed(kept))


def find_all(haystack: str, needle: str) -> list[tuple[int, int]]:
    """Spans where `needle` occurs in `haystack`, case-insensitively.

    An empty needle matches nothing — a search prompt with nothing typed in it is
    not a search for everything. The spans index the original string, so they can
    be used to mark up exactly what was found.
    """
    if not needle:
        return []
    return [(hit.start(), hit.end()) for hit in re.finditer(re.escape(needle), haystack, re.IGNORECASE)]
