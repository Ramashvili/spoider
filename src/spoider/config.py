"""Per-user editor settings: a flat rc file.

One `key = value` per line, `#` starts a comment, no sections and no quoting —
the shape of /etc/os-release or a .nanorc. The map file holds what makes a map
look the same everywhere; how the *editor* behaves lives here.

```
autosave = false
marks = ✅ ❌ ❓ ❗ 🕐

# add a child and type its name
# add_child = tab
```
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .files import write_atomic
from .model import MARKS
from .presets import DEFAULT_PRESET, PRESETS
from .text import clean

#: More than this and ^G takes too long to come back around.
MAX_MARKS = 8

#: Everything after this line is a chord the user set and a preset switch parked:
#: still in the file, still readable, not in force.
PARKED_MARKER = "# Chords put aside when a preset was chosen. Remove the # to use one again."

TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


@dataclass
class Config:
    autosave: bool = False
    marks: tuple[str, ...] = field(default_factory=lambda: tuple(MARKS))
    # binding id -> chord(s). Only what was actually changed; the defaults live in
    # the app, and the file shows them commented out.
    keys: dict[str, str] = field(default_factory=dict)
    #: Which preset's chords are in force (see presets.py).
    preset: str = DEFAULT_PRESET
    #: Chords a preset switch commented out. Kept here so the file round-trips:
    #: the app writes them back as comments instead of forgetting them.
    parked: dict[str, str] = field(default_factory=dict)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "spoider"


def default_config_path() -> Path:
    return config_dir() / "config.conf"


def _without_comment(line: str) -> str:
    """`#` starts a comment at the start of a line or after whitespace, so a
    value may still contain one (a chord like `f#` would survive)."""
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1].isspace()):
            return line[:index].strip()
    return line.strip()


def parse(text: str) -> Config:
    config = Config()
    parked = False
    for raw in text.splitlines():
        if raw.strip() == PARKED_MARKER:
            parked = True
            continue
        if parked and raw.lstrip().startswith("#"):
            restored = raw.lstrip("# ").strip()
            name, _, chord = restored.partition("=")
            if name.strip() and chord.strip():
                config.parked[name.strip()] = chord.strip()
            continue
        line = _without_comment(raw)
        if not line or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip()
        if not name:
            continue
        if name == "bindings":
            if value in PRESETS:
                config.preset = value
        elif name == "autosave":
            config.autosave = value.lower() in TRUE_WORDS
        elif name == "marks":
            marks = tuple(cleaned for token in value.split() if (cleaned := clean(token)))
            if marks:
                config.marks = marks[:MAX_MARKS]
        elif value:
            # anything else is a chord override; unknown names are ignored later
            config.keys[name] = value
    # a chord that is live again is no longer parked, so the file does not list
    # it twice
    for ident in config.keys:
        config.parked.pop(ident, None)
    return config


def _legacy(path: Path) -> Config | None:
    """Read a file from before the move to flat rc, once, so nothing is lost."""
    toml_path = path.with_name("config.toml")
    try:
        with toml_path.open("rb") as handle:
            return parse(_from_mapping(tomllib.load(handle)))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        pass

    json_path = path.with_name("config.json")
    try:
        data = json.loads(json_path.read_text())
    except (OSError, ValueError):
        return None
    return parse(_from_mapping(data)) if isinstance(data, dict) else None


def _from_mapping(data: dict) -> str:
    """Turn the old nested shape into the flat file the parser understands."""
    lines = [f"autosave = {str(bool(data.get('autosave', False))).lower()}"]
    marks = data.get("marks")
    if isinstance(marks, list) and marks:
        lines.append("marks = " + " ".join(str(mark) for mark in marks))
    keys = data.get("keys")
    if isinstance(keys, dict):
        for name, chord in keys.items():
            if isinstance(chord, str) and chord.strip():
                lines.append(f"{name} = {chord.strip()}")
    return "\n".join(lines)


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path is not None else default_config_path()
    try:
        return parse(path.read_text())
    except (OSError, UnicodeDecodeError):
        return _legacy(path) or Config()


def render_config(config: Config, key_entries: Sequence[tuple[str, str, str]]) -> str:
    """The file as the user reads it: overrides live, everything else commented."""
    lines = [
        "# spoider — editor settings",
        "#",
        "# One setting per line. Text after # is a comment, so a line that starts",
        "# with # is doing nothing.",
        "",
        f"autosave = {'true' if config.autosave else 'false'}",
        "marks = " + " ".join(config.marks),
        f"bindings = {config.preset}",
        "",
        "# Chords. Uncomment a line to change it, e.g.  save = ctrl+w",
    ]
    for ident, default, description in key_entries:
        lines.append("")
        lines.append(f"# {description}")
        if ident in config.keys:
            lines.append(f"{ident} = {config.keys[ident]}")
        else:
            lines.append(f"# {ident} = {default}")
    if config.parked:
        lines.extend(["", PARKED_MARKER])
        for ident, chord in config.parked.items():
            lines.append(f"# {ident} = {chord}")
    return "\n".join(lines).rstrip() + "\n"


def is_stale(
    path: Path, config: Config, key_entries: Sequence[tuple[str, str, str]]
) -> bool:
    """True when the file's lines do not match the bindings this build has.

    Only the lines the app writes are checked, so a file that is already current
    is left untouched — along with any comments the user added themselves."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return True
    lines = {line.strip() for line in text.splitlines()}
    if f"bindings = {config.preset}" not in lines:
        return True
    for ident, chord in config.parked.items():
        if f"# {ident} = {chord}" not in lines:
            return True
    for ident, default, _ in key_entries:
        wanted = (
            f"{ident} = {config.keys[ident]}"
            if ident in config.keys
            else f"# {ident} = {default}"
        )
        if wanted not in lines:
            return True
    return False


def write_config(
    config: Config,
    path: Path | None = None,
    key_entries: Sequence[tuple[str, str, str]] = (),
) -> None:
    path = Path(path) if path is not None else default_config_path()
    write_atomic(path, render_config(config, key_entries))
