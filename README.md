# spoider

A mind map editor that lives in your terminal. Branches fan out on both sides of
a central idea, the view follows your selection, and the map is a plain JSON file
you can diff and version.

```
 spoider 0.1.0                    ~/Projects/spoider/map.json                    14 cells

                      ╭────────────╮
         ╭────────────┤   spoider  ├────────────╮
         │            ╰────────────╯            │
    ╭────┴─────╮                          ╭─────┴────╮
    │  canvas  │                          │   keys   │
    ╰──────────╯                          ╰──────────╯

  ^A child  ^J sib  ^E edit  ^D del  ^T fold  ^P prev  ^N next  ^B out  ^F in  ^S save ...
```

## Run it

```bash
cd ~/Projects/spoider
uv run spoider                 # opens ~/.local/share/spoider/map.json
uv run spoider my-ideas.json   # or any path
uv run spoider --empty notes.json
```

The top line is chrome and nothing more: `spoider` and its version on the left,
the file path centred (`New Buffer` until the first write), and the total cell
count on the right. The terminal title carries the same path plus a `*` while the
buffer has unsaved changes.

Nothing is written until you ask for it: edits stay in memory, `^S` writes them
to the current file, `^O` writes them wherever you name, and `^X` refuses to throw
them away silently.

## Keys

`Tab` and `Return` do the two things you do constantly; everything else is a ctrl
chord in the spirit of nano (`^A` and `^J` remain as aliases for those two). Arrow
keys work too, since they are the cursor keys of the terminal itself.

| Keys | Action | Why that key |
| --- | --- | --- |
| `Tab` | add a child under the selection and type its name in place | indenting in, like an outliner |
| `Return` | add a sibling after the selection and type its name in place | the next line |
| `^A` / `^J` | aliases for those two, for when your hands are already on ctrl | |
| `^E` | edit the selected node in place | **e**dit |
| `^C` | escape everywhere: closes a dialog, abandons the node being typed, otherwise inert | |
| `^D` | delete the branch | nano's delete |
| `^T` | fold / unfold the branch | **t**oggle |
| `^P` / `↑` | previous sibling | nano: previous line |
| `^N` / `↓` | next sibling | nano: next line |
| `^B` / `←` | left — out to the parent on a right-hand branch, into the first child on a left-hand one | nano: back a character |
| `^F` / `→` | right — the mirror of the above (unfolds a collapsed branch) | nano: forward a character |
| `^Z` | undo | |
| `^Y` | redo | |
| `^S` | save straight to the current file, no questions | the universal save |
| `^O` | write out — asks which file to write, pre-filled with the current one | nano: write out (save as) |
| `^X` | quit; if the buffer is modified it asks `y save / n discard / esc cancel` | nano: exit |

Horizontal movement is **spatial, not genealogical**: a branch on the right of the
root has its children further right, and a branch on the left has its children
further left, so `←`/`→` always move the selection the way the screen moves.

Reordering a node among its siblings is on `alt+↑` / `alt+↓` — rare enough to stay
off the shortcut bar.

Mouse: click a node to select it, double-click to rename it in place, scroll to
walk siblings.

### Typing

Names are typed straight onto the canvas — no dialog. The box widens as you type,
the caret is a block, and the bar swaps to `⏎ done · esc/^C cancel · ←→ move · ⌫ erase`.
`Enter` commits, `esc` or `^C` abandons, and a node you abandon before naming it
never existed. While typing, every other chord is swallowed, so `^D` cannot delete
the node you are halfway through naming.

## Colours

spoider ships no palette and no theme switcher. It runs on Textual's `ansi` theme,
so every box, link and the shortcut bar use whatever your terminal is already
using: depth picks ANSI colour names (cyan, green, yellow, magenta, blue, red),
the root stays on the default foreground, links are dim, and the selection is
reverse video. That means it looks right on a dark theme, a light theme, or a
16-colour tty.

## Layout

- Root's children alternate sides: index 0 right, 1 left, 2 right, …
- Each subtree owns a vertical band; a parent is centred on its children.
- Boxes are drawn with rounded box-drawing characters and joined by elbow
  connectors that merge into a shared spine per branch.

## Code map

| File | Role |
| --- | --- |
| `src/spoider/model.py` | `Node` / `MindMap`: the tree, mutations by id, JSON load/save |
| `src/spoider/layout.py` | places every visible node on a character grid |
| `src/spoider/render.py` | grid → styled cells (boxes, connectors) → `rich.Text` |
| `src/spoider/nav.py` | selection movement rules |
| `src/spoider/widgets.py` | `MindMapView`: camera, hit-testing, clicks |
| `src/spoider/screens.py` | modal text prompt + yes/no confirm |
| `src/spoider/app.py` | key bindings, shortcut bar, undo history, write/quit flow |

## Test

```bash
uv run pytest
```
