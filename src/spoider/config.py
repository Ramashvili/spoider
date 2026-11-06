"""Per-user editor settings: a flat rc file.

One `key = value` per line, `#` starts a comment, no sections and no quoting —
the shape of /etc/os-release or a .nanorc. The map file holds what makes a map
look the same everywhere; how the *editor* behaves lives here.

```
autosave = false
marks_default = ⭐ 💡 ❓ ⚠️ ✅ 📌 ⌛ 🤡

# add a child and type its name
# add_child = tab
```
"""

from __future__ import annotations

import os
from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .files import write_atomic
from .model import MARKS, marks_of

TRUE_WORDS = frozenset({"1", "true", "yes", "on"})

#: The vim keymap, written into the file commented out so switching is a matter of
#: uncommenting a block. The arrow keys stay on the movement lines: they are not a
#: vim or a nano convention but what every keyboard has, and dropping them would
#: take a hand off the home row for nothing.
VIM_BINDS: tuple[tuple[str, str], ...] = (
    ("prev", "k up"),
    ("next", "j down"),
    ("left", "h left"),
    ("right", "l right"),
    ("edit", "i"),
    ("copy", "y"),
    ("cut", "d"),
    ("paste", "p"),
    ("delete", "x"),
    ("undo", "u"),
    ("redo", "ctrl+r"),
    ("add_sibling", "o"),
    ("add_child", "O"),
    ("search", "/"),  # the character itself: "slash" is not a chord the loader takes
)


@dataclass
class Config:
    autosave: bool = False
    #: What ^J asks for by default: the width last used, or this. Named apart from
    #: the `justify` binding, which may also live in this file as a chord.
    justify_width_default: int = 40
    #: Hide the bar along the bottom. Drawers bring it back while they are open.
    hide_footer: bool = False
    #: How wide a tab is drawn in a cell: spaces up to the next stop, in cells.
    tab_width: int = 4
    marks_default: tuple[str, ...] = field(default_factory=lambda: tuple(MARKS))
    #: Whether the first-run question about registering .spoider with the desktop has
    #: been answered. Asking once is the point: a "no" is an answer, not a delay.
    desktop_asked: bool = False
    # binding id -> chord(s). Only what was actually changed; the defaults live in
    # the app, and the file shows them commented out.
    keys: dict[str, str] = field(default_factory=dict)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "spoider"


def default_config_path() -> Path:
    return config_dir() / "spoider.conf"


def _without_comment(line: str) -> str:
    """`#` starts a comment at the start of a line or after whitespace, so a
    value may still contain one (a chord like `f#` would survive)."""
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].strip()
    return line.strip()


_MODIFIERS = frozenset({"ctrl", "alt", "shift", "meta", "super", "hyper"})
_KEYS = frozenset(
    {
        "tab", "enter", "escape", "space", "up", "down", "left", "right",
        "home", "end", "insert", "delete", "backspace", "pageup", "pagedown",
        "pause", "print_screen", "scroll_lock", "menu", "caps_lock", "num_lock",
        *(f"f{number}" for number in range(1, 25)),
    }
)


def is_chord(text: str) -> bool:
    """Whether the right-hand side of a line could ever be pressed.

    A chord is a single character, a key by name, or either behind modifiers. This
    keeps a line that was once a setting — `justify = 12`, from before that setting
    was named `justify_width` — from silently rebinding a key to "12", which no
    keyboard sends, and then writing itself back into the file on every save.
    """
    parts = text.strip().lower().split("+")
    *modifiers, key = parts
    if not all(modifier in _MODIFIERS for modifier in modifiers):
        return False
    return len(key) == 1 or key in _KEYS


def parse(text: str, known: Collection[str] | None = None) -> Config:
    """Read the rc file. `known` is the set of binding ids this build has: a name
    that is neither a setting nor one of them is a leftover, not a chord, and must
    not be read back and written out again."""
    config = Config()
    for raw in text.splitlines():
        line = _without_comment(raw)
        if not line or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        if name == "tab_width":
            try:
                config.tab_width = max(1, min(int(value), 16))
            except ValueError:
                pass
        elif name == "justify_width_default":
            try:
                config.justify_width_default = max(10, min(int(value), 400))
            except ValueError:
                pass
        elif name == "autosave":
            config.autosave = value.lower() in TRUE_WORDS
        elif name == "desktop_asked":
            config.desktop_asked = value.lower() in TRUE_WORDS
        elif name == "hide_footer":
            config.hide_footer = value.lower() in TRUE_WORDS
        elif name == "marks_default":
            marks = marks_of(value.split())
            if marks:
                config.marks_default = marks
        elif value and (known is None or name in known):
            # a line lists every chord for that action, separated by spaces; one
            # that is not a key at all is dropped rather than read as a chord
            chords = [token for token in value.split() if is_chord(token)]
            if chords:
                config.keys[name] = " ".join(chords)
    return config


def load_config(path: Path | None = None, known: Collection[str] | None = None) -> Config:
    """The flat rc file, or the defaults when there is none to read."""
    path = Path(path) if path is not None else default_config_path()
    try:
        return parse(path.read_text(), known)
    except (OSError, UnicodeDecodeError):
        return Config()


def render_config(config: Config, key_entries: Sequence[tuple[str, str, str]]) -> str:
    """The file as the user reads it: overrides live, everything else commented."""
    lines = [
        "# spoider — editor settings",
        "#",
        "# One setting per line. Text after # is a comment, so a line that starts",
        "# with # is doing nothing.",
        "",
        f"autosave = {'true' if config.autosave else 'false'}",
        "marks_default = " + " ".join(config.marks_default),
        f"justify_width_default = {config.justify_width_default}",
        f"tab_width = {config.tab_width}",
        f"hide_footer = {'true' if config.hide_footer else 'false'}",
        f"desktop_asked = {'true' if config.desktop_asked else 'false'}",
        "",
        "# Chords. An action can have more than one chord: they are separated by a",
        "# space. Uncomment a line to change it.",
    ]
    for ident, default, description in key_entries:
        lines.append("")
        lines.append(f"# {description}")
        if ident in config.keys:
            lines.append(f"{ident} = {config.keys[ident]}")
        else:
            lines.append(f"# {ident} = {default}")
    lines.append("")
    lines.append("# --- vim binds: uncomment these to switch ---")
    lines.extend(f"# {ident} = {chords}" for ident, chords in VIM_BINDS)
    return "\n".join(lines).rstrip() + "\n"


def write_config(
    config: Config,
    path: Path | None = None,
    key_entries: Sequence[tuple[str, str, str]] = (),
) -> None:
    path = Path(path) if path is not None else default_config_path()
    write_atomic(path, render_config(config, key_entries))


#: The keys spoider writes itself, with how each one is spelled in the file.
_OWNED = (
    "autosave",
    "marks_default",
    "justify_width_default",
    "desktop_asked",
    "hide_footer",
    "tab_width",
)


def update_config(path: Path, changes: dict[str, str]) -> None:
    """Set the given keys, leaving every other line in the file exactly as it was.

    A config is the user's text: comments, ordering and commented-out blocks survive an
    editor setting here. Missing keys are appended, not regenerated.
    """
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        lines = []
    pending = dict(changes)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in pending:
            lines[index] = f"{key} = {pending.pop(key)}"
    for key, value in pending.items():
        lines.append(f"{key} = {value}")
    write_atomic(path, "\n".join(lines).rstrip() + "\n")
