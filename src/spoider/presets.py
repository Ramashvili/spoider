"""Keyboard presets: whole layouts for fingers that already know an editor.

Each preset maps a binding id to a chord and is laid over the app's own defaults:
anything a preset does not name keeps its default, and a chord set in the config
file still wins over both.

They are idioms, not emulations. A binding here is one chord, so emacs' `C-x C-s`
and vim's `dd` cannot be expressed at all; each preset keeps the shape of the habit
and drops the part that cannot be spelled. Where a preset and the app disagree
about what a key means, the preset wins only for the keys it names — every other
key, including the ctrl form of the ones it moves, keeps working.

mcedit's row is taken from mc's own default keymap (misc/mc.default.keymap,
`[editor]`), so F1 is help, F5 is Copy, F6 is Move, F9 is the menu and F12 is
Save As — in this editor that is cut, paste, settings and write-out.
"""

from __future__ import annotations

#: The app's own defaults, which are nano's wherever nano has an answer.
DEFAULT_PRESET = "nano"

PRESETS: dict[str, dict[str, str]] = {
    "nano": {},
    "vim": {
        # i and a both start typing, as they do in vim; e keeps working
        "edit": "i,a",
        # o opens a line below, which is a sibling here
        "add_sibling": "enter,o",
        "cut": "x",  # x deletes into the register: exactly our cut
        "delete": "D",
        "paste": "p",
        "undo": "u",
        "redo": "ctrl+r",
        "search": "slash",
        "mark": "m",
        "fold": "z",
    },
    "emacs": {
        "cut": "ctrl+k",  # kill-line
        "paste": "ctrl+y",  # yank, and our cut stack is a kill ring
        "search": "alt+s",  # M-s is emacs' search prefix
        "undo": "ctrl+underscore",  # C-_
        "redo": "alt+underscore",  # emacs has no redo; this is the invention
        "clear_selection": "escape,ctrl+g",  # C-g is keyboard-quit
    },
    "mcedit": {
        "help": "f1",
        "save": "f2",
        "mark": "f3",
        "cut": "f5",  # Copy
        "paste": "f6",  # Move
        "search": "f7",
        "delete": "f8",  # Remove
        "settings": "f9",  # Menu
        "quit": "f10",
        "write": "f12",  # Save As
        "undo": "ctrl+u",
        "redo": "alt+r",
    },
}

#: One line each, for the settings list.
DESCRIPTIONS: dict[str, str] = {
    "nano": "^K cut, ^U paste, ^X quit",
    "vim": "h j k l move, i insert, x cut, p paste, u undo",
    "emacs": "^K kill, ^Y yank, ^_ undo, M-s search",
    "mcedit": "F1 help, F2 save, F5 cut, F6 paste, F10 quit",
}


def chords_for(preset: str) -> dict[str, str]:
    """The chords a preset puts in force; unknown names fall back to the default,
    so a typo in the config file cannot leave the editor without a keymap."""
    return PRESETS.get(preset, PRESETS[DEFAULT_PRESET])
