"""Which build this is: the version, and the commit behind it when one can be named.

A bug report is worth what its version is worth, so the bar and ``--version`` carry the commit as a
PEP 440 local version::

    spoider 0.5.13+3f2a1bc          built from that commit
    spoider 0.5.13+3f2a1bc.dirty    built from a tree that has changes no commit holds
    spoider 0.5.13                  nothing can name the commit, as with a wheel from PyPI

Three places can answer, and they are tried in this order:

* ``_commit.py``, which ``scripts/build-pyz`` writes into the release archive: a reader who
  downloaded the archive has neither git nor an install record to ask
* ``direct_url.json``, the PEP 610 file that uv and pip write when a package is installed from git
* git itself, when this module is running out of a working tree
"""

from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from importlib import import_module, metadata
from pathlib import Path

from . import __version__

#: What a build is made of. A map lying in the working directory is the user's work, not the build,
#: and it must not be able to mark every dev run as dirty.
SOURCE_PATHS = ("src", "pyproject.toml", "uv.lock")


@lru_cache(maxsize=1)
def version_string() -> str:
    """The version as the bar prints it, settled once per process: a running build does not change."""
    return _describe(_baked() or _installed_from_git() or _checkout())


def _describe(found: tuple[str, bool] | None) -> str:
    """`0.5.13` when the commit is unknown, `0.5.13+3f2a1bc` when it is, `.dirty` when it was built
    from a tree with changes no commit holds."""
    if found is None:
        return __version__
    commit, dirty = found
    # A candidate may already carry a label of its own (`0.5.13+redraw`); PEP 440 allows one local
    # label only, so the commit joins it with a dot rather than a second plus.
    if "+" in __version__:
        return f"{__version__}.{commit}" + (".dirty" if dirty else "")
    return f"{__version__}+{commit}" + (".dirty" if dirty else "")


def _baked() -> tuple[str, bool] | None:
    """The commit the release script left in the tree, when this copy came from an archive."""
    try:
        module = import_module(f"{__package__}._commit")
    except ImportError:
        return None
    commit = getattr(module, "COMMIT", "")
    if not commit:
        return None
    return commit[:7], bool(getattr(module, "DIRTY", False))


def _installed_from_git() -> tuple[str, bool] | None:
    """The commit uv or pip recorded when it installed this package from a repository."""
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
    return commit[:7], bool(info.get("uncommitted"))


def _checkout() -> tuple[str, bool] | None:
    """The commit of the working tree this file sits in, if it sits in one."""
    root = Path(__file__).resolve().parents[2]
    if not (root / ".git").exists():
        return None
    commit = _git(root, "rev-parse", "--short=7", "HEAD")
    if not commit:
        return None
    changes = _git(root, "status", "--porcelain", "--untracked-files=no", "--", *SOURCE_PATHS)
    return commit, bool(changes)


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return done.stdout.strip()
