"""Per-user editor preferences — things that are not part of the document.

The map file holds what makes the map look the same everywhere (the tree, marks,
spacing). How the *editor* behaves belongs to whoever is using it, so it lives in
the XDG config directory instead, and never travels with the file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Config:
    autosave: bool = False


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
    return Config(autosave=bool(data.get("autosave", False)))


def save_config(config: Config, path: Path | None = None) -> None:
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(config), indent=2) + "\n")
    tmp.replace(path)
