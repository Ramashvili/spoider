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

class WriteRefused(OSError):
    """A write that must not happen, carrying the sentence to say in its place.

    An `OSError`, so every caller that already reports a failed write reports this one the
    same way, with the sentence rather than an errno.
    """


def write_atomic(path: Path, data: str | bytes) -> None:
    """Write `data` to `path`, keeping the old contents until the write succeeds.

    Text is written as UTF-8 and bytes as they are; the rest of the story is the same for both, and
    an icon needs the same care a map does.

    A link is written through rather than replaced: the reader keeps the link and the file it
    names receives the text, which is what saving to a name means. Nothing is written over
    that is not a regular file, and a file the reader made read-only stays read-only: the
    rename needs only the directory, so without that check a `chmod 444` map would be
    rewritten anyway.

    The temp name is short on purpose. It used to carry the whole target name, so a name near
    the filesystem's 255-byte limit could never be saved, because the temp name was the one
    that did not fit.
    """
    path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file():
            raise WriteRefused("it is not a regular file")
        if not os.access(path, os.W_OK):
            raise WriteRefused("the file is read-only; change its mode first")
    handle, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name[:120]}.", suffix=".tmp")
    try:
        # Two branches rather than one clever call: the mode decides the stream's type, and a bytes
        # icon written through a text stream is the mistake this shape makes impossible.
        if isinstance(data, bytes):
            with os.fdopen(handle, "wb") as binary_stream:
                binary_stream.write(data)
                binary_stream.flush()
                os.fsync(binary_stream.fileno())
        else:
            with os.fdopen(handle, "w", encoding="utf-8") as text_stream:
                text_stream.write(data)
                text_stream.flush()
                os.fsync(text_stream.fileno())
        if path.exists():  # a rename replaces the inode, so carry the mode across
            os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
