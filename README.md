# spoider

A mind map editor that lives in your terminal. Branches fan out on both sides of
a central idea, the view follows your selection, and the map is a plain JSON file
you can diff and version.

```
                    ╭────────────╮
       ╭────────────┤   spoider  ├────────────╮
       │            ╰────────────╯            │
  ╭────┴─────╮                          ╭─────┴────╮
  │  canvas  │                          │   keys   │
  ╰──────────╯                          ╰──────────╯
```

## Run it

```bash
cd ~/Projects/spoider
uv run spoider                 # opens ~/.local/share/spoider/map.json
uv run spoider my-ideas.json   # or any path
uv run spoider --empty notes.json
```

There is no header bar — the map gets the whole screen and the file name lives in
your terminal's window title.

## Keys

Everything is a ctrl chord, in the spirit of nano. Arrow keys work too, since they
are the cursor keys of the terminal itself.

| Keys | Action | Why that key |
| --- | --- | --- |
| `^A` | add a child under the selection, then name it | **a**dd |
| `^S` | add a sibling after the selection, then name it | **s**ibling |
| `^E` / `Enter` | edit the selected node | **e**dit |
| `^D` | delete the branch | nano's delete |
| `^T` | fold / unfold the branch | **t**oggle |
| `^P` / `↑` | previous sibling | nano: previous line |
| `^N` / `↓` | next sibling | nano: next line |
| `^B` / `←` | out to the parent | nano: back a character |
| `^F` / `→` | into the first child (unfolds it) | nano: forward a character |
| `^Z` | undo | |
| `^Y` | redo | |
| `^O` | save | nano: write out |
| `^X` | quit | nano: exit |

Reordering a node among its siblings is on `alt+↑` / `alt+↓` — rare enough to stay
off the shortcut bar. Mouse: click a node to select it, double-click to rename,
scroll to walk siblings.

While a rename dialog is open only `^X` stays live, so `^D` can never delete the
node you are typing into.

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
| `src/spoider/screens.py` | modal text prompt |
| `src/spoider/app.py` | key bindings, shortcut bar, undo history, autosave |

## Test

```bash
uv run pytest
```
