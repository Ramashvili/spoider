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
chord in the spirit of nano (`^A` and `^J` remain as aliases for those two).
Movement also answers to the arrow keys and, for vim users, to `h` `j` `k` `l` —
all aliases of the same four actions, so the spatial flipping applies to every
one of them.

| Keys | Action | Why that key |
| --- | --- | --- |
| `Tab` | add a child under the selection and type its name in place | indenting in, like an outliner |
| `Return` | add a sibling after the selection and type its name in place | the next line |
| `^A` / `^J` | aliases for those two, for when your hands are already on ctrl | |
| `^E` | edit the selected node in place | **e**dit |
| `^C` | escape everywhere: closes a dialog, abandons the node being typed, otherwise inert | |
| `^D` | delete the branch | nano's delete |
| `^T` | fold / unfold the branch | **t**oggle |
| `^G` | cycle the cell's mark: `✅ ❌ ❓ ❗ 🕐` and then off again | **g**lyph |
| `^P` / `↑` | previous sibling | nano: previous line |
| `^N` / `↓` | next sibling | nano: next line |
| `^B` / `←` | left — from the root, its left-hand branch; on a right-hand branch, out to the parent; on a left-hand one, into the first child | nano: back a character |
| `^F` / `→` | right — from the root, its right-hand branch; the mirror of the above elsewhere (unfolds a collapsed branch) | nano: forward a character |
| `h` `j` `k` `l` | vim cursor keys — aliases for `←` `↓` `↑` `→` | |
| `^Z` | undo | |
| `^Y` | redo | |
| `^S` | save straight to the current file, no questions | the universal save |
| `^O` | write out — asks which file to write, pre-filled with the current one | nano: write out (save as) |
| `^X` | quit; if the buffer is modified it asks `y save / n discard / esc cancel` | nano: exit |
| `^+` | widen the gaps between cells — one column and one row per press (saved with the map) | |
| `^-` | tighten them again, down to boxes that almost touch | |
| `^/` | help: every key and option, with a line of explanation | |
| `^,` | editor settings — spacing, colours, file, cell count | like every other preferences chord |

Horizontal movement is **spatial, not genealogical**: a branch on the right of the
root has its children further right, and a branch on the left has its children
further left, so `←`/`→` always move the selection the way the screen moves. The
root itself branches both ways, so from it `←` and `→` each enter the branch drawn
on that side.

Reordering a node among its siblings is on `alt+↑` / `alt+↓` — rare enough to stay
off the shortcut bar.

Marks are part of the document — they are written into the JSON with the node, so
a ✅ survives closing the editor and shows up in a diff as `"mark": "✅"`.

Spacing (`^+` / `^-`) is part of the document: it is written into the file as
`"spacing"`, so a map looks the same wherever it is opened — a 40-cell map and a
4-cell map want different amounts of air. Changing it makes the buffer dirty, and
`^S` writes it. It stays out of the undo stack, because nudging the air three
times should not bury the edit you actually want to back out.

At the tight end the boxes end up sharing a border row: they touch, but every
cell keeps its own text row, and the two rules are merged into one so a stack of
siblings still reads as a table rather than a pile of corners.

The bar carries the keys you cannot guess — inserts, edits, spacing, file, undo.
The four navigation chords are deliberately absent: arrows and `hjkl` cover
movement without spending that space.

`^, settings` and `^/ help` sit pinned to the right edge behind a divider and are
never dropped: as the window narrows, whole hint entries disappear from the end
first, so the pair that gets you to the documentation and the preferences is
always reachable. Both stay live while you are typing a name.

A note on those two chords, because they are the fiddliest keys in the app: they
are bound by the names Textual's key parser *actually produces*, not by the names
you would expect. Under the kitty keyboard protocol (which Textual enables, and
which kitty, ghostty and wezterm speak) `^+` arrives as `ctrl+shift+equals_sign`;
on a plain terminal `^-` arrives as the `^_` control character
(`ctrl+underscore`). Every spelling is bound, with `alt+=` / `alt+-` as fallbacks
for terminals that swallow the ctrl form — `tests/test_app.py` feeds the real
escape sequences through the parser and asserts the resulting names are bound.

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
| `src/spoider/screens.py` | modals: text prompt, confirm, help, settings |
| `src/spoider/app.py` | key bindings, undo history, write/quit flow |
| `src/spoider/chrome.py` | shortcut bar layout, pinned settings/help cluster |

## Test

```bash
uv run pytest
```
