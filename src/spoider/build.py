"""Which build this is: the version, and only when it needs one, the commit behind it.

The version is what a build *is*. A local label says the thing on disk is **not** the release the
number names, so it appears exactly then::

    spoider 0.5.14                  the tag's own tree, clean: this is the release, and the tag names
                                    the commit for anyone who wants it
    spoider 0.5.15+2f1c9ab          commits have landed on top of the last release
    spoider 0.5.15+2f1c9ab.dirty    and the source holds changes no commit has
    spoider 0.5.14                  a wheel from an index: no commit to name, and nothing claims one

Three places can answer, and they are tried in this order:

* ``_commit.py``, which ``scripts/build-pyz`` writes into the release archive: a reader who
  downloaded the archive has neither git nor an install record to ask
* ``direct_url.json``, the PEP 610 file that uv and pip write when a package is installed from git,
  which also records the revision that was asked for
* git itself, when this module is running out of a working tree

A build is the release when the tag it was made from is the one the version names and the source is
clean. Everything else is something on top of the release, and says so.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module, metadata
from pathlib import Path

from . import __version__

#: What a build is made of. A map lying in the working directory is the user's work, not the build,
#: and it must not be able to mark every dev run as dirty.
SOURCE_PATHS = ("src", "pyproject.toml", "uv.lock")


@dataclass(frozen=True)
class Build:
    """Where a copy came from: the commit, whether the tree was clean, and the tag it sat on."""

    commit: str
    dirty: bool = False
    #: The exact tag the commit carried when the build was made, `""` when it carried none.
    tag: str = ""

    @property
    def is_the_release(self) -> bool:
        """True when this is the tree the version names, which is when no label belongs on it."""
        return self.tag == f"v{__version__}" and not self.dirty


@lru_cache(maxsize=1)
def version_string() -> str:
    """The version as the bar prints it, settled once per process: a running build does not change."""
    return _describe(_baked() or _installed_from_git() or _checkout())


def _describe(found: Build | None) -> str:
    """The version, with a local label exactly when the copy is not the release it would claim."""
    if found is None or found.is_the_release:
        return __version__
    # A candidate may already carry a label of its own (`0.5.15+redraw`); PEP 440 allows one local
    # label only, so the commit joins it with a dot rather than a second plus.
    join = "." if "+" in __version__ else "+"
    return f"{__version__}{join}{found.commit}" + (".dirty" if found.dirty else "")


def _baked() -> Build | None:
    """What the release script left in the tree, when this copy came from an archive."""
    try:
        module = import_module(f"{__package__}._commit")
    except ImportError:
        return None
    commit = getattr(module, "COMMIT", "")
    if not commit:
        return None
    return Build(
        commit=commit[:7],
        dirty=bool(getattr(module, "DIRTY", False)),
        tag=getattr(module, "TAG", ""),
    )


def _installed_from_git() -> Build | None:
    """What uv or pip recorded when it installed this package from a repository."""
    try:
        raw = metadata.distribution("spoider").read_text("direct_url.json")
    except (metadata.PackageNotFoundError, FileNotFoundError, OSError):
        return None
    if not raw:
        return None
    try:
        info = json.loads(raw).get("vcs_info") or {}
    except ValueError:
        return None
    commit = info.get("commit_id")
    if not commit:
        return None
    # `requested_revision` is what the reader asked for: a tag, a branch, or a commit. Only a tag is
    # the release; a branch name is something that moves, and never names one.
    return Build(
        commit=commit[:7],
        dirty=bool(info.get("uncommitted")),
        tag=str(info.get("requested_revision") or ""),
    )


def _checkout() -> Build | None:
    """The working tree this file sits in, if it sits in one."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return None
    commit = _git(root, "rev-parse", "--short=7", "HEAD")
    if not commit:
        return None
    # Untracked files count: a module added but not committed is part of the build and no commit
    # holds it. Ignored files (`__pycache__`, a build's own output) do not appear here at all.
    changes = _git(root, "status", "--porcelain", "--untracked-files=normal", "--", *SOURCE_PATHS)
    # `describe --exact-match` prints nothing at all unless HEAD is precisely the tagged commit.
    tag = _git(root, "describe", "--tags", "--exact-match", "HEAD")
    return Build(commit=commit, dirty=bool(changes), tag=tag)


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()
