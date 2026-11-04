# spoider

A mind map editor for the terminal. Start with one thought in the middle, branch
out with `Tab` and `Return`, and walk the tree with the arrow keys. Every colour
comes straight from your terminal theme.

It is a Python TUI built on [Textual](https://textual.textualize.io/), and it is vibecoded.

![a mind map in spoider](media/spoider.png)

https://github.com/user-attachments/assets/a8818b5e-8f63-490f-9e02-c3ee17aec757

Two minutes and twenty-three seconds of it working: the four layouts, marks, folds,
spacing, moving branches through the cut stack, and justifying a long note in place.

## Install

spoider needs [uv](https://docs.astral.sh/uv/), which also brings a matching Python. Install
it from your package manager where it is packaged:

```bash
sudo pacman -S uv     # Arch
sudo dnf install uv   # Fedora 43 and later
sudo apt install uv   # Debian and Ubuntu, from universe in their next releases
```

On releases without it, use the standalone installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install spoider itself:

```bash
uv tool install git+https://github.com/Ramashvili/spoider
```

That puts `spoider` on your PATH. On first launch, spoider asks whether your desktop should
always recognise `.spoider` files and open them in spoider when you open one from your file
browser; `spoider --install-desktop` does the same thing by hand, without the question.

## Try it without installing

```bash
uvx --from git+https://github.com/Ramashvili/spoider spoider --demo
```

`--demo` opens the built-in manual as a mind map you can explore and edit.

## Run

```bash
spoider                        # start a new map
spoider ideas.spoider          # open a map, or create one at that path
spoider --demo                 # open the interactive manual
spoider -p 7.4 map.spoider     # land the cursor on the fourth child of the seventh
spoider -p s2.1 map.spoider    # the first child of the second cut, panel open
```

## Keys

| Key | Does |
| --- | --- |
| `Tab` / `Return` | add a child, add a sibling |
| `e` | edit the cell's text |
| `↑↓←→` `hjkl` | walk the tree |
| `Alt+↑` / `Alt+↓` | reorder siblings |
| `^K` / `^U` | cut a branch to the stack, paste it under the current cell |
| `p` | open the cut stack panel to inspect or edit cut branches |
| `^D` | delete a branch |
| `w` / `^W` | cycle a cell's mark, or choose which marks this map uses |
| `t` | fold or unfold children |
| &#96; | the file's properties, drawn over the map |
| `Home` | the main cell of this tree |
| `End` | the deepest cell below this one |
| `PgUp` | the first sibling under the same parent |
| `PgDn` | the last sibling under the same parent |
| `Del` | delete the cell, as `^D` does |
| `^J` | wrap a cell's text to a chosen column width |
| `^F` | search cells |
| `^L` / `c` | cycle the layout shape, switch colour mode |
| `=` / `-` | loosen or tighten the spacing |
| `^Z` `^Y` | undo, redo |
| `^S` `^O` `^X` | save, save as, quit |
| `^,` `^/` | settings, full key list |

## How it works

### Writing in cells

A cell grows to fit as many lines as you type. `Shift+Return` adds a new line,
`Shift` with the arrow keys selects text, and `^J` wraps long notes into clean
paragraphs at whatever width you prefer.

### Four ways to draw the tree

Press `^L` to cycle through four shapes for the same map. The arrow keys adapt
automatically to match the drawing on screen:

- **spider:** root in the centre, branches fanning out left and right.
- **pyramid:** root at the top, children stacked below.
- **bush:** root at the bottom, growing upwards.
- **branch:** root on the left, unfolding to the right like an outline.

Press `c` to colour either by family (one colour per main branch) or by depth
(one colour per level).

### Moving branches with the stack

Cutting with `^K` places a branch onto a stack, and `^U` pastes the most recent
cut under whichever cell you select next. If you are reorganising a large map,
press `p` to open the stack side-by-side: you can browse what you cut, edit or
fold items inside it, or reorder them before pasting them back.

![the cut stack beside a large map](media/spoider-stack.png)

On the right you can see the LIFO stack, holding branches cut from the map.

### Maps that look the same everywhere

Your layout shape, spacing, colour mode, custom marks, and even unpasted branches
on the stack are saved inside the `.spoider` file itself, along with the cell you
were last on. Opening the same file on another machine gives you the exact same view,
with the cursor where you left it.

Editor preferences like autosave and custom keybindings live in
`~/.config/spoider/spoider.conf`, which you can open directly from `^,`.

## Development

```bash
git clone https://github.com/Ramashvili/spoider && cd spoider
uv sync && uv run spoider
uv run pytest
```

See [AGENTS.md](AGENTS.md) for the codebase layout and design notes.

## Licence

MIT, see [LICENSE](LICENSE).
