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
    # Seven of these have earned a bare key: they are reached for constantly and
    # collide with nothing, since h/j/k/l are the only bare letters spoken for. The
    # stack is `p` because ^I is Tab on a terminal without the kitty protocol.
    #
    # One binding per action, carrying every chord it answers to: an alias is a
    # second chord on this line, not a second line. Textual splits the list on commas
    # itself, which is also why the punctuation keys are spelled by name here — a
    # bare comma would read as a separator.
    Binding("e,ctrl+e", "edit", "edit", id="edit"),
    Binding("ctrl+k", "cut", "cut", id="cut"),
    Binding("ctrl+u", "paste", "paste", id="paste"),
    Binding("p", "toggle_stack", "show stack", id="toggle_stack"),
    Binding("ctrl+d,delete", "delete", "del", id="delete"),
    Binding("comma,grave_accent", "toggle_properties", "debug", show=False,
            id="toggle_properties"),
    Binding("t,ctrl+t", "fold", "fold", id="fold"),
    Binding("w", "mark", "mark", id="mark"),
    Binding("ctrl+w", "set_marks", "set marks", id="set_marks"),
    # search sits with the other editing keys: it is what you reach for while
    # reading a map, and the bar has room for one more
    Binding("ctrl+f", "search", "search", id="search"),
    Binding("alt+f", "next_match", "next match", show=False, id="next_match"),
    Binding("alt+b", "previous_match", "prev match", show=False, id="previous_match"),
    # rendered as the pinned cluster at the right edge, not among the hints
    Binding("full_stop,f9", "settings", "config", show=False, id="settings"),
    # `?` is what people press to ask for help. There was a ^/ beside it for terminals
    # whose keyboard protocol cannot tell ? from /, but that is most of them and the
    # chord never arrived: a key that is listed and does nothing is worse than no key.
    Binding("question_mark,f1", "help", "help", show=False, id="help"),
    # nano's cursor keys, kept spatial: ^P/^N walk the branch, ^B/^F move away
    # from the root or towards it — whichever way that happens to be drawn.
    # Arrows, and the vim letters further down, are chords of the same bindings.
    Binding("up,ctrl+p,k", "go_up", "prev", show=False, id="go_up"),
    Binding("down,ctrl+n,j", "go_down", "next", show=False, id="go_down"),
    # the six keys that move by the tree rather than by the picture: they never care
    # where a cell happens to be drawn
    Binding("home", "go_home", "main cell", show=False, id="go_home"),
    Binding("end", "go_end", "deepest", show=False, id="go_end"),
    Binding("pageup", "top_sibling", "first sibling", show=False, id="top_sibling"),
    Binding("pagedown", "bottom_sibling", "last sibling", show=False, id="bottom_sibling"),
    # h/j/k/l are chords here rather than bindings of their own; hidden from the bar
    # because the ctrl chords already own those labels, and nothing else on any
    # screen binds a bare h/j/k/l.
    Binding("left,ctrl+b,h", "go_left", "left", show=False, id="go_left"),
    Binding("right,l", "go_right", "right", show=False, id="go_right"),
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
    Binding("ctrl+s,f2", "save", "save", id="save"),
    Binding("ctrl+o,f12", "write", "write", id="write"),
    Binding("ctrl+x,f10", "quit", "quit", id="quit"),
    Binding("ctrl+z,f3", "undo", "undo", id="undo"),
    Binding("ctrl+y", "redo", "redo", show=False, id="redo"),
    # Last on purpose: the bar drops its tail on a narrow terminal, and a shape
    # toggle matters less than saving or quitting. Help still lists it.
    Binding("ctrl+l", "layout", "layout", id="layout"),
    # how the cells are coloured is a property of the document, so it sits with the
    # shape rather than in the settings
    Binding("c", "colours", "colours", id="colours"),
]


#: What a pressed key and a config line have in common, and what Textual needs.
#:
#: A person writes the character they press, so the config says `,`. Textual calls that
#: key "comma" in an event and reads a bare comma in a binding as the separator between
#: two keys, so the name is what the table and the keymap must carry. This is the only
#: place the two vocabularies meet: `PRESSED` for what arrives, `WANTED` for what is set.
#: Given to a binding whose chords were all refused, so Textual releases the keys it
#: was born with. An empty string will not do: Textual reads `keymap.get(id)` for
#: truthiness and quietly leaves the binding on its default. No key event can ever be
#: this string, so the binding exists and is unreachable, which is what unbound means.
UNBOUND = "<unbound>"

PRESSED = {"comma": ",", "full_stop": ".", "question_mark": "?", "equals_sign": "=",
           "minus": "-", "grave_accent": "`", "ctrl+slash": "ctrl+/"}
WANTED = {value: name for name, value in PRESSED.items()}


def shown(chord: str) -> str:
    """A chord as a person would write it: `,` rather than `comma`."""
    return PRESSED.get(chord, chord)


def action_chords(overrides: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Every chord each action answers to, in the order the bindings list them.

    A config line names one action and lists the chords it answers to, so the line
    is the whole truth for that action: a chord left off it stops working, which is
    what "the file says what the keys are" means. Defaults come from the binding
    table, split where a single binding already carries several keys ("ctrl+p,up").
    """
    return resolve(overrides)[0]


def resolve(
    overrides: dict[str, str] | None = None,
) -> tuple[dict[str, list[str]], list[tuple[str, str]]]:
    """The chords each action answers to, and the ones that had to be refused.

    One chord belongs to one action. A file that gives `z` to both `mark` and `fold`
    is a mistake the format cannot express — the key would run whichever action the
    binding table happens to reach first — so the first claim stands, the later one
    is dropped from that action's list, and the pair is named. Refusing it is the
    point: a key that does one of two things silently is worse than one that does
    nothing and says so.
    """
    chords: dict[str, list[str]] = {}
    action_of: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        action_of[binding.id] = binding.action
        keys = [shown(part) for part in binding.key.split(",") if part]
        chords.setdefault(binding.action, []).extend(keys)
    for ident, value in (overrides or {}).items():
        action = action_of.get(ident)
        listed = [part for part in (value or "").split() if part]
        if action is not None and listed:
            chords[action] = listed

    owner: dict[str, str] = {}
    clashes: list[tuple[str, str]] = []
    # A line competes with another line; a default is a placeholder that gives way.
    # `cut = ,` takes the comma off the debug key without a word, because nothing in
    # the file disagreed — the default did, and the file is the deliberate act. Two
    # lines claiming one chord is a real mistake, and that is what gets refused.
    from_file = [
        action
        for action in (action_of.get(ident) for ident in overrides or {})
        if action in chords
    ]
    for action in from_file:
        kept: list[str] = []
        for chord in chords[action]:
            held = owner.get(chord)
            if held is None:
                owner[chord] = action
                kept.append(chord)
            elif held != action:
                clashes.append((chord, f"{chord} is bound to both {held} and {action}"))
        chords[action] = kept
    for action, listed in chords.items():
        if action in from_file:
            continue
        kept = [chord for chord in listed if chord not in owner]
        for chord in kept:
            owner.setdefault(chord, action)
        chords[action] = kept
    return chords, clashes
def build_binding_keymap(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """binding id -> "a,b", which is the shape `App.set_keymap` wants.

    Keyed by id, because that is what Textual looks a binding up by (`keymap.get(
    binding.id)`) and what a config line names. An action-keyed map agrees with that
    only where an id happens to equal its action name, so `left` and `right` moved
    the bar and nothing else for as long as it was passed.
    """
    chords = action_chords(overrides)
    keymap: dict[str, str] = {}
    for binding in BINDINGS:
        if not isinstance(binding, Binding) or not binding.id:
            continue
        listed = chords.get(binding.action)
        if listed is None:
            listed = [binding.key]
        # an action that lost every chord is bound to a string no key can spell, so
        # Textual lets go of the key it was born with instead of keeping it silently
        keymap[binding.id] = (
            ",".join(WANTED.get(chord, chord) for chord in listed) if listed else UNBOUND
        )
    return keymap
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
        listed = chords.get(binding.action, [binding.key])
        # a refused chord leaves its action with nothing to press: "" says unbound,
        # where a missing id would fall back to the default and lie about it
        keymap.setdefault(binding.id, listed[0] if listed else "")
    return keymap
