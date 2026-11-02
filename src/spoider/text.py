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
    """`value` with control characters removed, except the line break.

    A cell holds more than one line now, so a newline is content. Tabs and the rest
    are still stripped: a tab in a box would land the following text wherever the
    terminal's tab stops happen to be, and nothing here needs that.
    """
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not any(unicodedata.category(ch) in _UNSAFE and ch != "\n" for ch in text):
        return text
    return "".join(
        ch for ch in text if ch == "\n" or unicodedata.category(ch) not in _UNSAFE
    )


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
