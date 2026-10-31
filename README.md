# tagger

A mind map editor that lives in your terminal. Branches fan out on both sides of
a central idea, the view follows your selection, and the map is a plain JSON file
you can diff and version.

```
╭───────────────────────────────────────────────────────────────╮
│                          ╭────────────╮                       │
│            ╭─────────────┤  tagger    ├──────────────╮        │
│            │             ╰────────────╯              │        │
│    ╭───────┴──────╮                          ╭───────┴──────╮ │
│    │   canvas     │                          │    keys      │ │
│    ╰──────────────╯                          ╰──────────────╯ │
╰───────────────────────────────────────────────────────────────╯
```

## Run it

```bash
cd ~/Projects/tagger
uv run tagger                 # opens ~/.local/share/tagger/map.json
uv run tagger my-ideas.json   # or any path
uv run tagger --empty notes.json
```

## Keys

| Key | Action |
| --- | --- |
| `←` `h` | go to parent |
| `→` `l` | go to first child (expands a folded branch) |
| `↑` `k` / `↓` `j` | previous / next sibling, climbing to the nearest cousin |
| `tab` | add child, then name it |
| `enter` | add sibling, then name it |
| `e` / double-click | edit the selected node |
| `d` | delete branch |
| `space` | fold / unfold branch |
| `K` / `J` | move the node among its siblings |
| `u` / `ctrl+r` | undo / redo |
| `ctrl+s` | save (every edit autosaves anyway) |
| `q` | quit |

Mouse: click a node to select it, scroll to walk siblings.

## Layout

- Root's children alternate sides: index 0 right, 1 left, 2 right, …
- Each subtree owns a vertical band; a parent is centred on its children.
- Boxes are drawn with rounded box-drawing characters and joined by elbow
  connectors that merge into a shared spine per branch.

## Code map

| File | Role |
| --- | --- |
| `src/tagger/model.py` | `Node` / `MindMap`: the tree, mutations by id, JSON load/save |
| `src/tagger/layout.py` | places every visible node on a character grid |
| `src/tagger/render.py` | grid → styled cells (boxes, connectors) → `rich.Text` |
| `src/tagger/nav.py` | selection movement rules |
| `src/tagger/widgets.py` | `MindMapView`: camera, hit-testing, clicks |
| `src/tagger/screens.py` | modal text prompt |
| `src/tagger/app.py` | key bindings, undo history, autosave |

## Test

```bash
uv run pytest
```
