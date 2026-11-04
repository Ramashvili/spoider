"""The properties overlay: what the file on disk holds, and where the cursor is.

Read-only and cheap: it looks at the document, the path and a few session fields, and turns
them into `(label, value)` rows. Nothing here draws; `render.overlay` puts the rows in a box
drawn over the map, which is the one place in the program where something floats, because a
properties panel that pushed the cells around would cost the space it exists to describe.
"""

from __future__ import annotations

import time
from pathlib import Path

from .addressing import address_of
from .model import MindMap
from .text import clip_head, one_line

LABEL_WIDTH = 7


def _size(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _written(path: Path) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))


def file_rows(mm: MindMap, path: Path | None) -> list[tuple[str, str]]:
    """The values in the file that are about the whole file."""
    rows = [("format", f"{1}, spacing {mm.spacing}, {mm.layout}, {mm.colours}")]
    deepest = max((mm.depth(node.id) for node in mm.nodes()), default=1)
    rows.append(("totals", f"{mm.count()} cells, {deepest} deep, {len(mm.cut_stack)} cuts"))
    marks = " ".join(mm.marks) if mm.marks else "-"
    rows.append(("marks", f"{marks}, justify {mm.justify or '-'}"))
    if path is not None and path.exists():
        rows.insert(0, ("file", str(path)))
        rows.insert(1, ("size", f"{_size(path)}, written {_written(path)}"))
    elif path is not None:
        rows.insert(0, ("file", f"{path}  (not on disk)"))
    else:
        rows.insert(0, ("file", "not named yet"))
    return rows


def cursor_rows(mm: MindMap, selected: str, run: int) -> list[tuple[str, str]]:
    address = address_of(mm, selected)
    row = f"{address}  id {selected}"
    if run > 1:
        row += f"  run of {run}"
    return [("cursor", row)]


def edited_row(mm: MindMap, last_edited: str | None) -> list[tuple[str, str]]:
    node = mm.find(last_edited) if last_edited else None
    if node is None:
        return [("edited", "-")]
    text = one_line(node.text) or "(empty)"
    return [("edited", f"{address_of(mm, node.id)}  \"{clip_head(text, 22)}\"")]


def rows_for(
    mm: MindMap,
    path: Path | None,
    selected: str,
    run: int,
    last_edited: str | None,
    *,
    dirty: bool,
    autosave: bool,
) -> list[tuple[str, str]]:
    rows = file_rows(mm, path)
    rows += cursor_rows(mm, selected, run)
    rows += edited_row(mm, last_edited)
    state = "autosave" if autosave else ("unsaved" if dirty else "saved")
    rows.append(("state", state))
    return rows
