"""The binding table and the keymap built from it.

Every chord each action answers to lives here, so a config line, the bar and the help
screen all read the same source.
"""

from __future__ import annotations

from textual.binding import Binding, BindingType

BINDINGS: list[BindingType] = [
    # tab/enter are the primary keys here; the ctrl chords stay as aliases.
    # tab needs priority to beat Textual's focus-next binding.
    Binding("tab", "add_child", "child", priority=True, id="add_child"),
    # ^A selects: the whole text while typing, every sibling on the map
    Binding("ctrl+a", "select_all", show=False, id="select_all"),
    Binding("enter", "add_sibling", "sib", id="add_sibling"),
    Binding("ctrl+j", "justify", "justify", id="justify"),
    Binding("alt+6", "copy", "copy", show=False, id="copy"),
    # Six of these have earned a bare key: they are reached for constantly and
    # collide with nothing, since h/j/k/l are the only bare letters spoken for. The
    # stack is `p` because ^I is Tab on a terminal without the kitty protocol.
    Binding("e", "edit", "edit", id="edit"),
    Binding("ctrl+e", "edit", "edit", show=False, id="edit_alt"),
    Binding("ctrl+k", "cut", "cut", id="cut"),
    Binding("ctrl+u", "paste", "paste", id="paste"),
    Binding("p", "toggle_stack", "show stack", id="toggle_stack"),
    Binding("ctrl+d", "delete", "del", id="delete"),
    Binding("t", "fold", "fold", id="fold"),
    Binding("ctrl+t", "fold", "fold", show=False, id="fold_alt"),
    Binding("w", "mark", "mark", id="mark"),
    Binding("ctrl+w", "set_marks", "set marks", id="set_marks"),
    # search sits with the other editing keys: it is what you reach for while
    # reading a map, and the bar has room for one more
    Binding("ctrl+f", "search", "search", id="search"),
    # rendered as the pinned cluster at the right edge, not among the hints
    Binding("ctrl+comma", "settings", "settings", show=False, id="settings"),
    Binding("ctrl+slash", "help", "help", show=False, id="help"),
    # nano's cursor keys, kept spatial: ^P/^N walk the branch, ^B/^F move away
    # from the root or towards it — whichever way that happens to be drawn.
    # Arrows and, further down, hjkl are aliases for the same four actions.
    Binding("ctrl+p,up", "prev", "prev", show=False, id="prev"),
    Binding("ctrl+n,down", "next", "next", show=False, id="next"),
    Binding("ctrl+b,left", "go_left", "left", show=False, id="left"),
    Binding("right", "go_right", "right", show=False, id="right"),
    # vim cursor keys. Hidden from the bar because the ctrl chords already own
    # those labels; nothing else on any screen binds a bare h/j/k/l.
    Binding("k", "prev", "prev", show=False, id="prev_vim"),
    Binding("j", "next", "next", show=False, id="next_vim"),
    Binding("h", "go_left", "left", show=False, id="left_vim"),
    Binding("l", "go_right", "right", show=False, id="right_vim"),
    # shift walks the same arrows the layout uses for siblings, so the run grows
    # in the direction the cells are drawn
    Binding("shift+up", "extend_prev", "select", show=False, id="extend_prev"),
    Binding("shift+down", "extend_next", "select", show=False, id="extend_next"),
    Binding("shift+left", "extend_left", "select", show=False, id="extend_left"),
    Binding("shift+right", "extend_right", "select", show=False, id="extend_right"),
    Binding("escape", "clear_selection", "clear", show=False, id="clear_selection"),
    Binding("alt+up", "move_up", "reorder up", show=False, id="move_up"),
    Binding("alt+down", "move_down", "reorder down", show=False, id="move_down"),
    # The spacing keys are bare = and -: the key names Textual produces for them
    # are the ones nobody would guess, and binding every spelling a terminal might
    # send made the bar, help and config list six keys for two jobs. If a terminal
    # cannot send these, rebind them in the config.
    Binding("equals_sign", "spacing_more", "looser", id="spacing_more"),
    Binding("minus", "spacing_less", "tighter", id="spacing_less"),

    # file first, history last: on a narrow terminal the bar clips its tail,
    # and ^X matters more than ^Z
    Binding("ctrl+s", "save", "save", id="save"),
    Binding("ctrl+o", "write", "write", id="write"),
    Binding("ctrl+x", "quit", "quit", id="quit"),
    Binding("ctrl+z", "undo", "undo", id="undo"),
    Binding("ctrl+y", "redo", "redo", show=False, id="redo"),
    # Last on purpose: the bar drops its tail on a narrow terminal, and a shape
    # toggle matters less than saving or quitting. Help still lists it.
    Binding("ctrl+l", "layout", "layout", id="layout"),
    # how the cells are coloured is a property of the document, so it sits with the
    # shape rather than in the settings
    Binding("c", "colours", "colours", id="colours"),
]


def action_chords(overrides: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Every chord each action answers to, in the order the bindings list them.

    A config line names one action and lists the chords it answers to, so the line
    is the whole truth for that action: a chord left off it stops working, which is
    what "the file says what the keys are" means. Defaults come from the binding
    table, split where a single binding already carries several keys ("ctrl+p,up").
    """
    chords: dict[str, list[str]] = {}
    action_of: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        action_of[binding.id] = binding.action
        keys = [part for part in binding.key.split(",") if part]
        chords.setdefault(binding.action, []).extend(keys)
    for ident, value in (overrides or {}).items():
        action = action_of.get(ident)
        listed = [part for part in (value or "").split() if part]
        if action is not None and listed:
            chords[action] = listed
    return chords
def build_action_keymap(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """action -> "a,b", which is the shape Textual's own keymap wants."""
    return {action: ",".join(chords) for action, chords in action_chords(overrides).items()}
def default_keymap() -> dict[str, str]:
    """id -> the first chord that action was born with; the whole of it in
    `action_chords`, so the two cannot drift apart."""
    return build_keymap()
def build_keymap(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """id -> the first chord its action answers to, which is what the bars show.

    Unknown ids and blank lines are ignored, so a typo in the config cannot take a
    key away from you. The whole list lives in `action_chords`."""
    chords = action_chords(overrides)
    keymap: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        keymap.setdefault(binding.id, chords.get(binding.action, [binding.key])[0])
    return keymap
