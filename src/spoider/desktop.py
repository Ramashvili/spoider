"""Registering .spoider with the desktop: the MIME type, the entry, the default.

Two files copied where the system looks for them, then the tools that rebuild its caches.
The launcher is written with the program's real path, because a desktop session does not
always have ~/.local/bin on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path


def _run_tool(argv: list[str]) -> bool:
    """Run a system tool that may be missing or may fail; say whether it worked.

    The exit code is the answer, not the fact that something was spawned:
    `update-mime-database` given XML it rejects exits non-zero, and calling that a
    success is how a desktop quietly stops knowing about .spoider.
    """
    try:
        done = subprocess.run(argv, check=False, capture_output=True)
    except OSError:
        return False
    return done.returncode == 0


def _quoted(command: str) -> str:
    """A path the way the desktop entry's `Exec` key wants it.

    `Exec` is parsed like a shell command line, so a path containing a space becomes
    two arguments unless it is quoted — and a launcher whose command is two arguments
    does nothing at all when the file is double-clicked.
    """
    escaped = command.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def install_desktop() -> int:
    """Register `.spoider` with the desktop: the MIME type, the entry, the default.

    Two files copied where the system looks for them, then the tools that rebuild
    its caches. Nothing is written anywhere the user did not ask for, and running it
    twice is harmless.
    """
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    mime_dir = data_home / "mime" / "packages"
    apps_dir = data_home / "applications"
    mime_dir.mkdir(parents=True, exist_ok=True)
    apps_dir.mkdir(parents=True, exist_ok=True)

    source = resources.files("spoider").joinpath("data")
    (mime_dir / "x-spoider.xml").write_bytes(source.joinpath("x-spoider.xml").read_bytes())
    entry = source.joinpath("spoider.desktop").read_text(encoding="utf-8")
    # the launcher is told where the program is, not just its name: a desktop
    # session does not always have ~/.local/bin on PATH
    command = shutil.which("spoider") or "spoider"
    (apps_dir / "spoider.desktop").write_text(
        entry.replace("Exec=spoider ", f"Exec={_quoted(command)} "), encoding="utf-8"
    )

    _run_tool(["update-mime-database", str(data_home / "mime")])
    _run_tool(["update-desktop-database", str(apps_dir)])
    if _run_tool(["xdg-mime", "default", "spoider.desktop", "application/x-spoider"]):
        print("Success! Mind maps with the .spoider extension now open with spoider.")
    else:
        print("The type is installed; set the default with xdg-mime when it is available.")
    return 0


def entry_path() -> Path:
    """Where the desktop entry lives when it is installed."""
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return data_home / "applications" / "spoider.desktop"


def registered() -> bool:
    return entry_path().exists()
