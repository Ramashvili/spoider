"""The README's key table is documentation, so it has to name chords that exist.

Help is checked against the binding table in test_app.py; this is the other surface a
newcomer reads first. A key that is renamed or removed here would otherwise go on being
advertised in the README until somebody tried it.
"""

from __future__ import annotations

import re
from pathlib import Path

from spoider.keys import action_chords

README = Path(__file__).resolve().parents[1] / "README.md"

#: How the README spells a key, and what the binding table calls it.
NAMED = {
    "Tab": "tab",
    "Return": "enter",
    "↑": "up",
    "↓": "down",
    "←": "left",
    "→": "right",
    "=": "equals_sign",
    "-": "minus",
    "^,": "ctrl+comma",
    "^/": "ctrl+slash",
    ".": "full_stop",
    ",": "comma",
    "?": "question_mark",
}
ARROWS = "↑↓←→"
VIM = "hjkl"


def key_names(token: str) -> list[str]:
    """The chords a backticked token in the table stands for.

    A token can hold several keys: `hjkl` is four, `↑↓←→` is four, `^K` is one ctrl
    chord spelled the way nano spells it. Anything else is prose and yields nothing.
    """
    if token in NAMED:
        return [NAMED[token]]
    if token and all(char in ARROWS for char in token):
        return [NAMED[char] for char in token]
    if token and all(char in VIM for char in token):
        return list(token)
    if len(token) == 2 and token.startswith("^"):
        return [f"ctrl+{token[1].lower()}"]
    if token == "`":
        return ["grave_accent"]
    if len(token) == 1 and token.isascii():
        return [token]
    return []


def test_every_chord_in_the_readme_key_table_exists() -> None:
    section = README.read_text(encoding="utf-8").split("## Keys", 1)[1].split("\n## ", 1)[0]
    tokens = re.findall(r"`([^`]+)`", section)
    assert tokens, "the Keys section should have a table"

    known = {chord for chords in action_chords().values() for chord in chords}
    unknown = [(token, name) for token in tokens for name in key_names(token) if name not in known]
    assert not unknown, f"the README names keys nothing answers to: {unknown}"


def test_the_readme_key_table_still_covers_the_common_actions() -> None:
    """The table is a summary, not the whole keymap, but the everyday keys belong in it."""
    section = README.read_text(encoding="utf-8").split("## Keys", 1)[1].split("\n## ", 1)[0]
    chords = {name for token in re.findall(r"`([^`]+)`", section) for name in key_names(token)}
    for chord in ("tab", "enter", "e", "ctrl+k", "ctrl+u", "p", "ctrl+d", "w", "t", "ctrl+f"):
        assert chord in chords, f"the README key table no longer mentions {chord}"


def test_the_example_config_is_the_template(tmp_path: Path):
    """The example a reader looks at must be what this build writes, key for key."""
    from spoider.app import SpoiderApp
    from spoider.config import Config, render_config

    app = SpoiderApp(None, config_path=tmp_path / "c.conf", demo=False)
    expected = render_config(Config(), app._key_entries())
    example = Path(__file__).resolve().parent.parent / "examples" / "spoider.conf"
    assert example.read_text(encoding="utf-8") == expected
