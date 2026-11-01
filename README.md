# spoider

A minimalist mind map editor for the terminal. One map, one bar of keys, no
windows, no mouse menus, no colours of its own — it borrows every colour from your
terminal. The map is a plain JSON file you can read, diff and version.

```
 ╭─────────────╮      ╭──────╮      ╭─────────╮      ╭────────╮      ╭─────────────────╮
 │ nano chords ├──────┤ keys ├──────┤ spoider ├──────┤ canvas ├──────┤ boxes and links │
 ╰─────────────╯      ╰──────╯      ╰─────────╯      ╰────────╯      ╰─────────────────╯
```

## Install

```bash
uv tool install git+https://github.com/OWNER/spoider
```

That puts `spoider` on your PATH with its own copy of its dependencies, so it cannot
disturb anything else you have installed — and `uv tool uninstall spoider` takes it
away again. If you use pipx rather than uv, the same command with `pipx` in front of
it does the same thing.

To look before installing, run it once and leave nothing behind:

```bash
uvx --from git+https://github.com/OWNER/spoider spoider --demo
```

To work on it instead, clone and use the checkout's own environment:

```bash
git clone https://github.com/OWNER/spoider && cd spoider
uv sync && uv run spoider
```

Python 3.11 or newer; uv will fetch one if you have none. Upgrade a tool install
with `uv tool upgrade spoider`.

## Run

```bash
spoider                # a new, empty map
spoider ideas.json     # open that map, or start one there
spoider --demo         # the manual, as a map
```

Nothing is written until you ask: `^S` writes to the current file and asks for a
name when there is none, `^O` writes a copy, `^X` asks before throwing edits away.

## Keys

| Key | Does |
| --- | --- |
| `Tab` | add a child and type its name |
| `Return` | add a sibling and type its name |
| `e` | rename the selected cell |
| `^D` | delete the branch |
| `m` | cycle the cell's mark |
| `t` | fold or unfold the branch |
| `^K` | cut the branch onto the stack |
| `^U` | paste the newest cut under the selection |
| `^I` | show the stack |
| `↑↓←→` `hjkl` | move |
| `shift` + sibling arrow | select a run of siblings |
| `alt` + `↑` `↓` | move the cell among its siblings |
| `=` `-` | more or less air between cells |
| `^F` | search |
| `^L` | change the shape of the map |
| `c` | colour by depth, or by branch |
| `^Z` `^Y` | undo, redo |
| `^S` `^O` `^X` | save, write out, quit |
| `^,` `^/` | settings, help |
| `esc` `^C` | cancel, or drop a selection |

`^/` has the whole list with a line of explanation, and the bar at the bottom
always shows the keys that work where you are.

## Shapes

`^L` cycles four drawings of the same tree, and the arrows follow the drawing:
whatever is *above* the selected cell is what `↑` goes to. The choice is saved in
the file.

| Shape | Root sits | Children |
| --- | --- | --- |
| `spider` | in the middle | fan out both sides, right filled first |
| `pyramid` | at the top | stack below it |
| `bush` | at the bottom | grow upwards |
| `branch` | at the left margin | hang to the right, like a contents page |

`c` switches how the cells are coloured. By **depth**, every level wears one colour
and a row of the map matches all the way across. By **family**, every branch under
the root wears one colour for its whole subtree — the cells under `canvas` agree
whatever their depth, and cells at the same depth under different branches do not.
The root and the first level look the same either way, and the choice is saved in
the file with the shape and the spacing.

## Cutting and pasting

`^K` takes a branch out of the map and puts it on a stack, last in first out;
`^U` pastes the newest one under whatever is selected. That is how a branch moves:
cut it, walk to its new parent, paste it.

`^I` opens the stack itself as a column on the right. Its cells are worked on with
the map's own keys — rename, mark, fold, move them up and down, cut and paste them
among themselves — without touching the map. The stack is saved in the file with
the map, so a cut you did not paste is still waiting tomorrow.

## Settings

`^,` holds autosave, the set of marks, and a shortcut to your config file:
`~/.config/spoider/config.conf`, a flat rc file — one setting per line, `#` for
comments, every chord listed and commented out until you want it.

```
autosave = false
marks = ✅ ❌ ❓ ❔ 🕐

# save = ctrl+w
# edit = ctrl+e
```

Editor preferences live there and stay out of the map. Spacing, shape, marks and
the cut stack belong to the map and travel with it, so a file looks the same
wherever it is opened.

## Limits

- A map wider than the window is clipped at the edges — there is no zoom out.
- `^K` and `^U` are the only way to reparent a branch.
- Undo history lives in memory for the session, and is not capped.
- Nothing locks the map file: two editors on one map, last save wins.
- `^I` is `Tab` on terminals that do not speak the kitty keyboard protocol.

## Development

```bash
uv run pytest
```

Changing it? [AGENTS.md](AGENTS.md) has the layout, the rules the code is held to and
the traps — written for people and for coding agents alike.

## Licence

MIT — see [LICENSE](LICENSE).
