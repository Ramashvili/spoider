"""Registering .spoider with the desktop: the MIME type, the entry, the default.

Two files copied where the system looks for them, then the tools that rebuild its caches.
The launcher is written with the program's real path, because a desktop session does not
always have ~/.local/bin on PATH.

Every failure here is a sentence and an exit code, never a traceback: the command runs on
a first launch, in front of someone who did not ask for a debugging session.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from .files import write_atomic

#: The sizes the icon ships in, in the columns a theme asks for them by. A desktop can scale any of
#: them to fit, and scaling a 256 into a 16 px slot is the blur these sizes exist to avoid: menus and
#: title bars take 16 and 24, toolbars 32, launchers 48, and the app grid 128 or 256.
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: The name both the launcher and the file type wear. It is the icon's name in the theme, never a
#: path: a path in `Icon=` is right until the file moves.
ICON_NAME = "spoider"

#: The line in the packaged entry that names the command; the launcher's path is
#: substituted into it, and a template without it is a packaging mistake worth saying.
EXEC_MARKER = "Exec=spoider "


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


def data_home() -> Path:
    """Where the desktop's own files go.

    `XDG_DATA_HOME` has to be absolute; a relative one would scatter `mime/` and
    `applications/` into whatever directory spoider was started from, so it is ignored
    — which is what the specification says to do with it.
    """
    given = os.environ.get("XDG_DATA_HOME")
    if given:
        path = Path(given).expanduser()
        if path.is_absolute():
            return path
    return Path.home() / ".local" / "share"


def _shown(path: Path) -> str:
    """A path the way it is read: the home directory as `~`, anything else whole."""
    home = str(Path.home())
    text = str(path)
    if text.startswith(home + os.sep):
        return "~" + text[len(home) :]
    return text


def desktop_available() -> bool:
    """Whether this machine has a desktop that reads the files at all.

    The two files are half of it: shared-mime-info's `update-mime-database` reads the MIME
    type and builds the database the desktop consults, so a machine without that tool has
    no use for either file. macOS and Windows are such machines; so is a BSD with no
    desktop packages installed. The test is the tool, not the platform, because the
    freedesktop tools are packaged on the BSDs as much as on Linux.
    """
    return shutil.which("update-mime-database") is not None


def _write_icons(source, icon_root: Path) -> list[Path]:
    """Copy the icon into the theme, one file per size, and say where each landed.

    `hicolor` is the theme every desktop falls back to, so a program that knows nothing about the
    user's theme still has its icon found. The files are written the way the two entries are, so a
    half-written icon is not something an interrupted run can leave behind.
    """
    written: list[Path] = []
    for size in ICON_SIZES:
        data = source.joinpath("icons").joinpath(f"{ICON_NAME}-{size}.png").read_bytes()
        target = icon_root / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        write_atomic(target, data)
        written.append(target)
    return written


def install_desktop() -> int:
    """Register `.spoider` with the desktop: the MIME type, the entry, the default.

    Two files written where the system looks for them, then the tools that rebuild its
    caches. Nothing is written anywhere the user did not ask for, running it twice is
    harmless, and the return code says whether the association was actually made: 0 when
    a `.spoider` file would now open in spoider, 1 when it would not.
    """
    if not desktop_available():
        print(
            "spoider: the desktop learns about .spoider from shared-mime-info, whose "
            "update-mime-database is not on this machine; nothing was written."
        )
        return 1

    home = data_home()
    mime_dir = home / "mime" / "packages"
    apps_dir = home / "applications"

    source = resources.files("spoider").joinpath("data")
    try:
        mime_xml = source.joinpath("x-spoider.xml").read_text(encoding="utf-8")
        template = source.joinpath("spoider.desktop").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"spoider: cannot read the files it ships: {exc}")
        return 1

    if EXEC_MARKER not in template:
        print(f"spoider: the packaged entry has no {EXEC_MARKER!r} line to fill in; nothing registered.")
        return 1

    command = shutil.which("spoider")
    if command is None:
        # the entry is still written, but it names a command the desktop may not find
        print("spoider: warning: spoider is not on your PATH, so the entry may not start it.")

    entry = template.replace(EXEC_MARKER, f"Exec={_quoted(command or 'spoider')} ")

    icon_root = home / "icons" / "hicolor"
    try:
        write_atomic(mime_dir / "x-spoider.xml", mime_xml)
        write_atomic(apps_dir / "spoider.desktop", entry)
        icons = _write_icons(source, icon_root)
    except OSError as exc:
        # an unwritable home, a read-only mount, a full disk: say which, and stop
        print(f"spoider: cannot write to {home}: {exc}")
        return 1

    # name what was written: a reader who wants to remove it, or to see why the desktop
    # still does not know the type, needs the paths more than a summary sentence
    print(f"wrote {_shown(mime_dir / 'x-spoider.xml')} (the MIME type)")
    print(f"wrote {_shown(apps_dir / 'spoider.desktop')} (the launcher)")
    for path in icons:
        print(f"wrote {_shown(path)} (the icon)")

    _run_tool(["update-mime-database", str(home / "mime")])
    _run_tool(["update-desktop-database", str(apps_dir)])
    # the theme's cache, so the desktop sees the icon without a restart; a machine without the tool
    # is no worse off, because the files are where the lookup looks for them anyway
    _run_tool(["gtk-update-icon-cache", "-f", "-t", str(icon_root)])
    if _run_tool(["xdg-mime", "default", "spoider.desktop", "application/x-spoider"]):
        print("Success! Mind maps with the .spoider extension now open with spoider.")
        return 0
    print(
        "The type is installed, but xdg-mime could not make it the default. Run\n"
        "  xdg-mime default spoider.desktop application/x-spoider\n"
        "when it is available."
    )
    return 1


def entry_path() -> Path:
    """Where the desktop entry lives when it is installed."""
    return data_home() / "applications" / "spoider.desktop"


def registered() -> bool:
    return entry_path().exists()
