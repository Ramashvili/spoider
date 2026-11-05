"""Atomic file writes, shared by the map and the config.

A half-written map is worse than no map: write to a sibling temp file, flush it
to disk, then rename over the target. The rename is atomic on POSIX, so a reader
sees either the old file or the new one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: The suffix a map is offered when it is written: the label that says what
#: the JSON is, and nothing the app itself reads.
SUFFIX = ".spoider"

def write_atomic(path: Path, text: str) -> None:
    """Write `text` to `path`, keeping the old contents until the write succeeds."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():  # a rename replaces the inode, so carry the mode across
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
