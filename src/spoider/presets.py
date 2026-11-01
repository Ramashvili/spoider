"""Keyboard presets: whole layouts for fingers that already know an editor.

Each preset maps a binding id to a chord and is laid over the app's own defaults:
anything a preset does not name keeps its default, and a chord set in the config
file still wins over both.

They are idioms, not emulations. A binding here is one chord, so emacs' `C-x C-s`
and vim's `dd` cannot be expressed at all, and each preset keeps the shape of the
habit rather than its exact spelling — vim gets `i` for insert and `p` for paste,
emacs gets `C-y` for yank and `M-s` for search, and the ctrl forms of the untouched
keys keep working because that is what this editor does everywhere else.
"""

from __future__ import annotations

#: The app's own defaults, which are nano's wherever nano has an answer.
DEFAULT_PRESET = "nano"

PRESETS: dict[str, dict[str, str]] = {
    "nano": {},
    "vim": {
        "edit": "i",
        "cut": "x",
        "paste": "p",
        "undo": "u",
        "redo": "ctrl+r",
        "search": "slash",
        "mark": "m",
        "fold": "z",
    },
    "emacs": {
        "paste": "ctrl+y",
        "search": "alt+s",
        "undo": "ctrl+underscore",
        "redo": "alt+underscore",
    },
    "mcedit": {
        "help": "f1",
        "save": "f2",
        "search": "f7",
        "delete": "f8",
        "quit": "f10",
    },
}

#: One line each, for the settings list.
DESCRIPTIONS: dict[str, str] = {
    "nano": "^K cut, ^U paste, ^X quit",
    "vim": "h j k l move, i edit, x cut, p paste, u undo",
    "emacs": "^K kill, ^Y yank, ^_ undo, M-s search",
    "mcedit": "F1 help, F2 save, F7 search, F8 delete, F10 quit",
}


def chords_for(preset: str) -> dict[str, str]:
    """The chords a preset puts in force; unknown names fall back to the default,
    so a typo in the config file cannot leave the editor without a keymap."""
    return PRESETS.get(preset, PRESETS[DEFAULT_PRESET])
