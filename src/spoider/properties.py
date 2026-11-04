"""The properties overlay: the file on disk, and the state of this editing session.

Read-only and cheap: it looks at the document, the path and a few session fields, and turns
them into titled sections of `(label, value)` rows. Nothing here draws; `render.paint_box`
puts the sections in a box over the map, which is the one place in the program where
something floats, because a panel that pushed the cells around would cost the space it
exists to describe.

The split is deliberate: **file state** is what a person opening the JSON would find, and
**editor state** is where this session is looking. Autosave is a setting of the editor, so
it belongs in the second; the cursor is not in the file at all unless the file has been
saved.
"""

from __future__ import annotations

import time
from pathlib import Path

from .addressing import address_of
from .model import MindMap
from .text import clip_head, one_line

Section = tuple[str, list[tuple[str, str]]]

FILE_TITLE = "file state"
EDITOR_TITLE = "editor state"


def _size(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _written(path: Path) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))


def state_text(path: Path | None, *, dirty: bool) -> str:
    """saved, unsaved, or new unsaved when the buffer has no file behind it yet."""
    if path is None or not path.exists():
        return "new unsaved"
    return "unsaved" if dirty else "saved"


def file_rows(mm: MindMap, path: Path | None, *, dirty: bool) -> list[tuple[str, str]]:
    """The values in the file that are about the whole file."""
    if path is None:
        rows = [("file", "not named yet")]
    elif path.exists():
        rows = [("file", str(path)), ("size", f"{_size(path)}, written {_written(path)}")]
    else:
        rows = [("file", f"{path}  (not on disk)")]
    rows.append(("format", f"{1}, spacing {mm.spacing}, {mm.layout}, {mm.colours}"))
    deepest = max((mm.depth(node.id) for node in mm.nodes()), default=1)
    rows.append(("totals", f"{mm.count()} cells, {deepest} deep, {len(mm.cut_stack)} cuts"))
    rows.append(("marks", " ".join(mm.marks) if mm.marks else "-"))
    rows.append(("justify", str(mm.justify) if mm.justify else "-"))
    rows.append(("state", state_text(path, dirty=dirty)))
    return rows


def editor_rows(
    mm: MindMap,
    selected: str,
    run: int,
    last_edited: str | None,
    *,
    autosave: bool,
) -> list[tuple[str, str]]:
    """Where this session is looking, and what it has touched."""
    cursor = f"{address_of(mm, selected)}  id {selected}"
    if run > 1:
        cursor += f"  run of {run}"
    rows = [("cursor", cursor)]
    node = mm.find(last_edited) if last_edited else None
    if node is None:
        rows.append(("edited", "-"))
    else:
        text = one_line(node.text) or "(empty)"
        rows.append(("edited", f'{address_of(mm, node.id)}  "{clip_head(text, 22)}"'))
    rows.append(("autosave", "on" if autosave else "off"))
    return rows


def sections(
    mm: MindMap,
    path: Path | None,
    selected: str,
    run: int,
    last_edited: str | None,
    *,
    dirty: bool,
    autosave: bool,
) -> list[Section]:
    return [
        (FILE_TITLE, file_rows(mm, path, dirty=dirty)),
        (EDITOR_TITLE, editor_rows(mm, selected, run, last_edited, autosave=autosave)),
    ]
