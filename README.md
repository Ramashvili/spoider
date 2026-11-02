# spoider

A mind map editor for the terminal. One map, one bar of keys, no floating
windows, no colours of its own: every colour comes from your terminal. The map is
a plain JSON file you can read, diff and version.

```
 ╭─────────────╮      ╭──────╮      ╭─────────╮      ╭────────╮      ╭─────────────────╮
 │ nano chords ├──────┤ keys ├──────┤ spoider ├──────┤ canvas ├──────┤ boxes and links │
 ╰─────────────╯      ╰──────╯      ╰─────────╯      ╰────────╯      ╰─────────────────╯
```

Ninety-six seconds of it in use: [media/spoider-tour.mp4](media/spoider-tour.mp4).

## Install

```bash
uv tool install git+https://github.com/OWNER/spoider
```

That puts `spoider` on your PATH. To try it first without keeping anything:

```bash
uvx --from git+https://github.com/OWNER/spoider spoider --demo
```

A map is a `.spoider` file. To have the desktop open them for you, run once:

```bash
spoider --install-desktop
```

## Run

```bash
spoider                # a new, empty map
spoider ideas.spoider  # open that map, or start one there
spoider --demo         # the manual, as a map
```

Nothing is written until you ask: `^S` saves over the current file and asks for a
name when there is none, `^O` writes a copy, `^X` asks before throwing edits away.

## Keys

| Key | Does |
| --- | --- |
| `Tab` / `Return` | a child, a sibling |
| `e` | rename on the canvas |
| `↑↓←→` `hjkl` | move |
| `^K` / `^U` | cut a branch onto the stack, paste it back |
| `^I` | open the cut stack and work inside it |
| `^D` | delete the branch |
| `m` | cycle the cell's mark |
| `t` | fold or unfold |
| `^J` | justify the cell's text to a width you type |
| `^F` | search |
| `^L` / `c` | change the shape, change the colouring |
| `=` / `-` | more or less air |
| `^Z` `^Y` | undo, redo |
| `^S` `^O` `^X` | save, write out, quit |
| `^,` `^/` | settings, help |

`^/` has the whole list with a line of explanation, and the bar at the bottom always
shows the keys that work where you are. Everything rebinds, and a commented vim block
sits at the end of the config if that is your hand.

## Editing

A cell holds as many lines as you give it, and the box grows with them. Inside one,
the usual keys work: arrows and `Home`/`End`, word delete with `Alt+Backspace`,
`Insert` for overwrite, `Shift` with an arrow to select (then `^K` cuts, `M-6`
copies, `^U` pastes), and `^Z`/`^Y` undo the cell's text alone. `Shift+Return` starts
a new line, and `^J` reflows the paragraphs to a width it asks for and remembers.

## Shapes and colour

`^L` cycles four drawings of the same tree and the arrows follow the drawing:

| Shape | Root sits | Children |
| --- | --- | --- |
| `spider` | in the middle | fan out both sides |
| `pyramid` | at the top | stack below it |
| `bush` | at the bottom | grow upwards |
| `branch` | at the left | hang right, like a contents page |

`c` colours the cells either by branch, one colour for each whole subtree (how a new
map starts), or by depth, one colour per level. The shape and the colouring are saved
in the file.

## Cutting and pasting

`^K` lifts the whole branch onto a stack, where cuts wait last-in-first-out, and `^U`
hangs the newest cut under whatever is selected: cut, walk to the new parent, paste.
`^I` opens the stack as a column of its own, where you can rename, mark, fold,
reorder, cut again, or nest one cut inside another. The stack is saved in the map
file, so you will not lose it when the editor closes.

## Settings

`^,` toggles autosave and opens your config, a flat rc file at
`~/.config/spoider/spoider.conf`:

```
autosave = false
marks_default = ⭐ 💡 ❓ ⚠️ ✅ 📌 ⌛ 🤡
justify_width_default = 66
```

Everything about how the editor behaves lives there (`marks_default`,
`justify_width_default`, every chord). Everything about how the map looks lives in the
map and travels with it: spacing, shape, colouring, its marks, its cut stack.

## Limits

- A map wider than the window is clipped at the edges; there is no zoom out.
- `^K` and `^U` are the only way to reparent a branch.
- Nothing locks the map file: two editors on one map, last save wins.
- On a terminal without the kitty keyboard protocol, `^I` arrives as `Tab` and `^M`
  as `Return`. Rebind the keys that overlap if that is your terminal.

## Development

```bash
git clone https://github.com/OWNER/spoider && cd spoider
uv sync && uv run spoider     # run it
uv run pytest                 # test it
```

[AGENTS.md](AGENTS.md) has the layout, the rules and the traps, for people and for
coding agents alike.

## Licence

MIT, see [LICENSE](LICENSE).