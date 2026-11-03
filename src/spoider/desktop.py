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
    """Run a system tool that may not be installed; say whether it ran."""
    try:
        subprocess.run(argv, check=False, capture_output=True)
    except OSError:
        return False
    return True
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
        entry.replace("Exec=spoider ", f"Exec={command} "), encoding="utf-8"
    )

    _run_tool(["update-mime-database", str(data_home / "mime")])
    _run_tool(["update-desktop-database", str(apps_dir)])
    if _run_tool(["xdg-mime", "default", "spoider.desktop", "application/x-spoider"]):
        print("A .spoider map now opens with spoider.")
    else:
        print("The type is installed; set the default with xdg-mime when it is available.")
    return 0
