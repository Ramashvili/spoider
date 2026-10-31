"""Per-user editor preferences — things that are not part of the document.

The map file holds what makes the map look the same everywhere (the tree, marks,
spacing). How the *editor* behaves belongs to whoever is using it, so it lives in
the XDG config directory instead, and never travels with the file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .model import MARKS

#: More than this and ^G takes too long to come back around.
MAX_MARKS = 8


@dataclass
class Config:
    autosave: bool = False
    marks: tuple[str, ...] = field(default_factory=lambda: tuple(MARKS))
    # binding id -> its chord(s); filled with the full map on the first save so
    # the file always lists everything you can rebind
    keys: dict[str, str] = field(default_factory=dict)


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "spoider" / "config.json"


def load_config(path: Path | None = None) -> Config:
    path = Path(path) if path is not None else default_config_path()
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return Config()
    if not isinstance(data, dict):
        return Config()

    marks: tuple[str, ...] = tuple(MARKS)
    raw_marks = data.get("marks")
    if isinstance(raw_marks, list):
        cleaned = tuple(str(mark) for mark in raw_marks if str(mark).strip())
        if cleaned:
            marks = cleaned[:MAX_MARKS]

    raw_keys = data.get("keys")
    keys = (
        {str(k): str(v) for k, v in raw_keys.items() if isinstance(v, str)}
        if isinstance(raw_keys, dict)
        else {}
    )
    return Config(autosave=bool(data.get("autosave", False)), marks=marks, keys=keys)


def save_config(config: Config, path: Path | None = None) -> None:
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(config), indent=2) + "\n")
    tmp.replace(path)
