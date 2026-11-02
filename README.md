# spoider

A minimalist mind map editor for the terminal. One map, one bar of keys, no
floating windows, no colours of its own: it borrows every colour from your terminal.
The map is a plain JSON file you can read, diff and version.

```
 ╭─────────────╮      ╭──────╮      ╭─────────╮      ╭────────╮      ╭─────────────────╮
 │ nano chords ├──────┤ keys ├──────┤ spoider ├──────┤ canvas ├──────┤ boxes and links │
 ╰─────────────╯      ╰──────╯      ╰─────────╯      ╰────────╯      ╰─────────────────╯
```

Ninety-six seconds of it in use: [media/spoider-tour.mp4](media/spoider-tour.mp4), a
map built cell by cell, marks and folds, both colourings, cutting and pasting through
the LIFO stack, the help screen, all four shapes, and a recipe in the bush.

## Install

```bash
uv tool install git+https://github.com/OWNER/spoider
```

That puts `spoider` on your PATH with its own copy of its dependencies, so it cannot
disturb anything else you have installed, and `uv tool uninstall spoider` takes it
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

### Opening a map by double-click

A map is a `.spoider` file. To have the desktop hand it to the editor, install the two
files from a clone and tell the system about the type:

```bash
install -Dm644 packaging/x-spoider.xml ~/.local/share/mime/packages/x-spoider.xml
install -Dm644 packaging/spoider.desktop ~/.local/share/applications/spoider.desktop
update-mime-database ~/.local/share/mime
update-desktop-database ~/.local/share/applications
xdg-mime default spoider.desktop application/x-spoider
```

`gio info map.spoider` should then report `application/x-spoider`, and a file manager
shows the map with the editor's name on it. This needs `spoider` on `PATH`, which the
`uv tool install` above takes care of.

## Run

```bash
spoider                # a new, empty map
spoider ideas.spoider   # open that map, or start one there
spoider --demo         # the manual, as a map
```

Nothing is written until you ask: `^S` writes to the current file and asks for a
name when there is none, `^O` writes a copy, `^X` asks before throwing edits away.

## Keys

| Key | Does |
| --- | --- |
| `Tab` | add a child and type its name |
| `Return` | add a sibling and type its name |
| `e` | rename the selected cell, on the canvas |
| `^D` | delete the branch |
| `m` | cycle the cell's mark |
| `t` | fold or unfold the branch |
| `^K` | cut the branch onto the stack |
| `^U` | paste the newest cut under the selection |
| `^I` | show the cut stack, and work inside it |
| `↑↓←→` `hjkl` | move |
| `shift` + sibling arrow | select a run of siblings |
| `^A` | select every sibling of the selected cell, or all the text while typing |
| `alt` + `↑` `↓` | move the cell among its siblings |
| `=` `-` | more or less air between cells |
| `^J` | justify the selected cell's text to a width you type (the map remembers it) |
| `^F` | search |
| `^M` | set the marks this map cycles through |
| `^L` | change the shape of the map |
| `c` | colour by depth, or by branch |
| `^Z` `^Y` | undo, redo |
| `^S` `^O` `^X` | save, write out, quit |
| `^,` `^/` | settings, help |
| `esc` `^C` | cancel, or drop a selection |

`^/` has the whole list with a line of explanation, and the bar at the bottom
always shows the keys that work where you are.

## Writing in a cell

A cell holds as many lines as you give it, and the box grows with them; the widest
line decides how wide it is. `Tab` or `e` starts typing, `Return` finishes, and
`Shift+Return` starts a new line. Inside the cell the usual editing keys work: arrows
and `Home`/`End` (with `Ctrl` for the whole text), `Backspace`/`Del` at a line end join
lines, `Alt+Backspace` and `Alt+Delete` eat whole words, `Insert` switches to
overwriting the character under the caret, and `Shift` with an arrow selects text,
`^A` selects all of it, and `^K` cuts what is selected while `M-6` copies it; `^U`
pastes.

`^J` justifies: it asks for a width, remembers the answer, and reflows the cell one
paragraph at a time, a blank line keeping paragraphs apart. It works on the selected
cell from the map as well as while you are typing in it, and every one of these keys
answers to whatever chord you bound it to: the bar under the cell names the ones that
matter and the cell's own `^Z`/`^Y` undo its text, not the map.

The caret says which mode you are in: a filled block while inserting, an underline
while overwriting. Selected text is drawn reversed, the way a search hit is.

Two of those keys need a terminal that speaks the kitty keyboard protocol, `Shift+Return`
and `^J`; a plain terminal sends them as `Return`, so both become "finish the cell".

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

`c` switches how the cells are coloured. By **family**, which is how a new map
starts, every branch under the root wears one colour for its whole subtree: the cells
under `canvas` agree whatever their depth, and cells at the same depth under different
branches do not. By **depth**, every level wears one colour and a row of the map
matches all the way across. The root and the first level look the same either way, and
the choice is saved in the file with the shape and the spacing.

## Cutting and pasting

`^K` lifts the whole branch (the cell and everything under it) out of the map and onto
a stack, where cuts wait last-in-first-out: the most recent is on top. `^U` takes the
newest cut and hangs it under whatever is selected, which is how a branch moves: cut
it, walk to the new parent, paste it there. `^I` opens that stack as a column of its
own, where the map's keys keep their meaning: rename, mark, fold, reorder, cut again
(which returns a cell to the top), nest one cut inside another, and `Tab`/`Return` to
grow a cut or start a new one. The stack is saved in the map file, so you will
not lose it when the editor closes.

## Settings

`^,` holds autosave and a shortcut to your config file:
`~/.config/spoider/spoider.conf`, a flat rc file: one setting per line, `#` for
comments, every chord listed and commented out until you want it.

```
autosave = false
marks_default = ⭐ 💡 ❓ ⚠️ ✅ 📌 ⌛ 🤡
justify_width_default = 66

# save = ctrl+w
# edit = e ctrl+e
```

A chord line lists every chord that action answers to, separated by spaces, so
`edit = e ctrl+e` binds both and a chord left off the line stops working.

At the end of the file sits a commented vim block: uncomment it and the keys are
`hjkl` for moving, `i` to rename, `d` cut, `p` paste, `x` delete, `y` copy, `u` undo,
`^R` redo, `o` and `O` for a new sibling and child, `/` to search. The arrow keys stay
bound either way.

Editor preferences live there and stay out of the map: `marks_default` is the set a
new map starts with, and `justify_width_default` is the width `^J` offers before a map
has been justified once. Everything the map looks like belongs to the map and travels
with it: spacing, shape, colouring, the marks it cycles with `^M`, the cut stack and
the width it was last justified to, so a file reads the same wherever it is opened.

## Limits

- A map wider than the window is clipped at the edges; there is no zoom out.
- Below 31 rows the map keeps the row of air the bars would otherwise get.
- `^K` and `^U` are the only way to reparent a branch.
- Undo history lives in memory for the session, and is not capped.
- Nothing locks the map file: two editors on one map, last save wins.
- On terminals that do not speak the kitty keyboard protocol, `^I` arrives as `Tab`
  and `^M` as `Return`. Rebind either in the config if that is your terminal.

## Development

```bash
uv run pytest
```

Changing it? [AGENTS.md](AGENTS.md) has the layout, the rules the code is held to and
the traps, written for people and for coding agents alike.

## Licence

MIT, see [LICENSE](LICENSE).
