"""Per-user editor settings, in TOML: one thing per line, comments allowed.

The map file holds what makes a map look the same everywhere (tree, marks,
spacing). How the *editor* behaves belongs to whoever is using it, so it lives in
the XDG config directory and never travels with the file.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .model import MARKS

#: More than this and ^G takes too long to come back around.
MAX_MARKS = 8


@dataclass
class Config:
    autosave: bool = False
    marks: tuple[str, ...] = field(default_factory=lambda: tuple(MARKS))
    # binding id -> chord(s). Only what was actually changed; the defaults live in
    # the app, and the file shows them commented out.
    keys: dict[str, str] = field(default_factory=dict)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "spoider"


def default_config_path() -> Path:
    return config_dir() / "config.toml"


def _parse(data: dict) -> Config:
    marks: tuple[str, ...] = tuple(MARKS)
    raw_marks = data.get("marks")
    if isinstance(raw_marks, list):
        cleaned = tuple(str(mark) for mark in raw_marks if str(mark).strip())
        if cleaned:
            marks = cleaned[:MAX_MARKS]

    keys: dict[str, str] = {}
    raw_keys = data.get("keys")
    if isinstance(raw_keys, dict):
        keys = {
            str(name): str(chord).strip()
            for name, chord in raw_keys.items()
            if isinstance(chord, str) and chord.strip()
        }

    return Config(autosave=bool(data.get("autosave", False)), marks=marks, keys=keys)


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path is not None else default_config_path()
    try:
        with path.open("rb") as handle:
            return _parse(tomllib.load(handle))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        pass

    # A config written before the move to TOML: read it once so nobody loses
    # their settings, and the next save rewrites it in the new shape.
    legacy = path.with_name("config.json")
    if legacy != path:
        try:
            data = json.loads(legacy.read_text())
        except (OSError, ValueError):
            return Config()
        if isinstance(data, dict):
            return _parse(data)
    return Config()


def _quote(text: str) -> str:
    """TOML basic string, with emoji left as emoji rather than as escapes."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_config(
    config: Config, key_entries: Sequence[tuple[str, str, str]]
) -> str:
    """The file as the user reads it: overrides live, everything else commented."""
    lines = [
        "# spoider — editor settings",
        "#",
        "# Text after # is a comment. To change a chord, uncomment its line and",
        '# write the keys you want, e.g. save = "ctrl+w".',
        "",
        f"autosave = {'true' if config.autosave else 'false'}",
        "marks = [" + ", ".join(_quote(mark) for mark in config.marks) + "]",
        "",
        "[keys]",
    ]
    for ident, default, description in key_entries:
        lines.append(f"# {description}")
        if ident in config.keys:
            lines.append(f"{ident} = {_quote(config.keys[ident])}")
        else:
            lines.append(f"# {ident} = {_quote(default)}")
    return "\n".join(lines).rstrip() + "\n"


def write_config(
    config: Config,
    path: Path | None = None,
    key_entries: Sequence[tuple[str, str, str]] = (),
) -> None:
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(render_config(config, key_entries))
    tmp.replace(path)
