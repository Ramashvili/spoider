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
uv run spoider                 # a new, empty buffer
uv run spoider my-ideas.json   # opens that map (or starts one there)
uv run spoider --demo          # a new buffer with the demo map in it
```

Without a file named, spoider starts a new buffer and never goes looking for one:
where it ends up is your decision, and `^S` asks for a name the way nano does. If
`~/.local/share/spoider/map.json` is still free it is offered as the answer; if
something already lives there, the prompt is left empty rather than inviting you
to write over it.

The top line is chrome and nothing more: `spoider` and its version on the left,
the file path centred (`New Buffer` until the first write), and what it counts on
the right — the cells, or the matches of a search — with the map's shape beside
it. The terminal title carries the same path plus a `*` while the buffer has
unsaved changes.

Nothing is written until you ask for it: edits stay in memory, `^S` writes them
to the current file, `^O` writes them wherever you name, and `^X` refuses to throw
them away silently — unless you turn autosave on (see below).

## Keys

`Tab` and `Return` do the two things you do constantly, and five more keys are
bare because they are reached for just as often and collide with nothing: `e`,
`t`, `g`, `=` and `-`. Everything else is a ctrl chord in the spirit of nano, and
the ctrl forms of those five (`^E`, `^T`, `^G`, `^=`, `^-`) still work as aliases.
Movement also answers to the arrow keys and, for vim users, to `h` `j` `k` `l` —
all aliases of the same four actions, so the spatial flipping applies to every
one of them.

| Keys | Action | Why that key |
| --- | --- | --- |
| `Tab` | add a child under the selection and type its name in place | indenting in, like an outliner |
| `Return` | add a sibling after the selection and type its name in place | the next line |
| `^A` / `^J` | aliases for those two, for when your hands are already on ctrl | |
| `e` | edit the selected node in place (`^E` also works) | **e**dit |
| `^C` | escape everywhere: closes a dialog, abandons the node being typed, otherwise inert | |
| `^K` | cut the branch — it leaves the map and waits for `^U`, as often as you like | nano's cut |
| `^U` | paste it under the selected cell, as its last child | nano's paste |
| `^D` | delete the branch for good | nano's delete |
| `t` | fold / unfold the branch (`^T` also works) | **t**oggle |
| `g` | cycle the cell's mark and then off again — the set is editable in `^,` (`^G` also works) | **g**lyph |
| `^P` / `↑` | previous sibling | nano: previous line |
| `^N` / `↓` | next sibling | nano: next line |
| `^B` / `←` | left — from the root, its left-hand branch; on a right-hand branch, out to the parent; on a left-hand one, into the first child | nano: back a character |
| `→` | right — from the root, its right-hand branch; the mirror of the above elsewhere (unfolds a collapsed branch) | nano: forward a character |
| `^F` | search the cells: the prompt opens on the last line, matches are underlined as you type, `↑` recalls an earlier search | nano's find |
| `h` `j` `k` `l` | vim cursor keys — aliases for `←` `↓` `↑` `→` | |
| `^Z` | undo | |
| `^Y` | redo | |
| `^S` | save straight to the current file, no questions | the universal save |
| `^O` | write out — asks which file to write, pre-filled with the current one | nano: write out (save as) |
| `^X` | quit; if the buffer is modified it asks `y save / n discard / esc cancel` | nano: exit |
| `=` | widen the gaps between cells — one column and one row per press (saved with the map) | |
| `-` | tighten them again, down to boxes that almost touch | |
| `^L` | cycle the shape of the map: spider → pyramid → bush → branch (saved with the map) | **l**ayout |
| `^/` | help: every key, with a line of explanation — any key closes it | |
| `^,` | editor settings — the autosave switch | like every other preferences chord |

Horizontal movement is **spatial, not genealogical**: a branch on the right of the
root has its children further right, and a branch on the left has its children
further left, so `←`/`→` always move the selection the way the screen moves. The
root itself branches both ways, so from it `←` and `→` each enter the branch drawn
on that side.

Reordering a node among its siblings is on `alt+↑` / `alt+↓` — rare enough to stay
off the shortcut bar.

Marks are part of the document — they are written into the JSON with the node, so
a ✅ survives closing the editor and shows up in a diff as `"mark": "✅"`.

Spacing (`^=` / `^-`) is part of the document: it is written into the file as
`"spacing"`, so a map looks the same wherever it is opened — a 40-cell map and a
4-cell map want different amounts of air. Changing it makes the buffer dirty, and
`^S` writes it. It stays out of the undo stack, because nudging the air three
times should not bury the edit you actually want to back out.

At the tight end the boxes end up sharing a border row: they touch, but every
cell keeps its own text row. A box border is not drawn as a finished glyph but as
the set of directions that cell continues in, so two boxes meeting on one row
join into `├` / `┤` / `┬` / `┴` instead of one box's rounded corner overwriting
the other's. A stack of siblings reads as a table of cells, not as a pile of
corners.

## Shapes

`^L` cycles four ways of drawing the same tree. The choice is written into the
file as `"layout"`, next to `"spacing"`, for the same reason: a map should open
looking the way it was left, wherever it is opened.

| Shape | Where the root sits | Children |
| --- | --- | --- |
| `spider` | in the middle | fan out both ways, alternating right and left |
| `pyramid` | at the top | stack below it, side by side |
| `bush` | at the bottom | grow upwards |
| `branch` | at the left margin | hang to the right, like a table of contents |

The arrow keys follow the drawing, not the structure: whatever is *above* the selected
cell is what `↑` goes to. In `pyramid` that is the parent and in `bush` it is the
children; in `spider` and `branch` the levels run sideways, so `←` / `→` cross a
level and `↑` / `↓` step between siblings. A map is drawn in `spider` unless the
file says otherwise, so maps written before this existed open exactly as they
did.

The bar never goes away, and nothing opens a window over the map. Every prompt,
question and list — the search line, a file name, the save question, the settings
rows, the help page — appears on the lines just above the bar, the way nano does
it. The bar underneath then says what that drawer accepts, because it is the only
footer there is and it always describes what has the keys. Even the help page,
which accepts one thing, leaves `esc close` there: a bar with nothing in it looks
like a bug, and the panels keep a line of air above it so the last row is not
glued to the edge.

Its order is a ranking, and a narrow terminal drops the tail: the two inserts
first, because that is what you do most; then `^X quit`, so a cramped bar never
strands you; then saving, writing, undo, search, the editing keys, the shape; and
the spacing nudges last of all.

It carries the keys you cannot guess — inserts, edits, spacing, file, undo.
The four navigation chords are deliberately absent: arrows and `hjkl` cover
movement without spending that space.

`^, settings` and `^/ help` sit pinned to the right edge behind a divider and are
never dropped: as the window narrows, whole hint entries disappear from the end
first, so the pair that gets you to the documentation and the preferences is
always reachable. Both stay live while you are typing a name.

Those two chords are one chord each: `^=` and `^-`. Terminals encode them oddly
— under the kitty keyboard protocol `^=` arrives as `ctrl+equals_sign`, and a
plain terminal sends `^-` as the `^_` control character — but only the canonical
spelling is bound, so the bar, the help and the config all show the same single
key. If your terminal cannot send one of them, rebind it in the config file.

Mouse: click a node to select it, double-click to rename it in place, scroll to
walk siblings.

### Typing

Names are typed straight onto the canvas — no dialog. The box widens as you type,
the caret is a block, and the bar swaps to `⏎ done · esc/^C cancel · ←→ move · ⌫ erase`.
`Enter` commits, `esc` or `^C` abandons, and a node you abandon before naming it
never existed. While typing, every other chord is swallowed, so `^D` cannot delete
the node you are halfway through naming.

## Cutting and pasting

`^K` lifts a branch out of the map and `^U` puts it back under whatever is
selected. It is the way to reparent something: cut a branch, walk to its new
parent, paste.

The cut cell leaves the map immediately and the selection goes to its parent, so
you are standing where the branch came from. `^U` appends copies as the last
child, and the selection stays on the target — pasting is how you build a list of
the same thing, so a second `^U` adds a sibling of the first rather than nesting
inside it. The original stays on the clipboard, so one cut can be pasted as many
times as you like; a pasted branch arrives with its own ids, its marks, its
folds and its whole subtree. Pasting into a folded cell opens it, since a branch
you cannot see is a surprise.

The clipboard lives in the session, not in the file: it is editor state like the
undo stack, and it does not survive a restart.

## Searching

`^F` adds a prompt line above the shortcut bar, the way nano does — the map stays
on screen, the matches light up as you type, and the bar keeps saying what the
prompt accepts. The top bar counts the matches in place of the cell count.

`Enter` takes the search and selects the first match; `^F` then `Enter` again
moves to the next one, wrapping round the map. A match inside a folded branch
unfolds it, because a match you cannot see is no use. `Esc` drops the search
entirely. The match count steps aside for the cell count again two seconds after
the search is taken — it has made its point — while the marks themselves stay.

A match is drawn as a reverse block in its cell's own colour, like a selection.
Inside the selected cell the two blocks cancel out and you see none of it; the
count is what tells you it is there. The count is cells, not occurrences: a cell
holding "one one" is one match.

## Settings

`^,` opens the editor settings, as a panel at the bottom of the screen with the
map still visible above it:

| Row | What it does |
| --- | --- |
| `autosave` | write after every cell edit, rearrangement or spacing change, and on exit — so `^X` never stops to ask. While it is on, `^S` leaves the shortcut bar (the chord still works) |
| `marks` | the emoji `^G` cycles through, space separated and in order, up to eight. Cells that already carry a mark keep it, even if that emoji later leaves the set |
| `config` | hand the terminal to `$EDITOR` (then `$VISUAL`, then `nano`) on `config.conf`, and reload it when you close it |

Autosave and the mark set are *editor* preferences, not document state: they live
in `~/.config/spoider/config.conf` and do not travel with the map. Spacing is the
opposite — it does travel, so a map looks the same wherever you open it.

## Settings file

`~/.config/spoider/config.conf` is a flat rc file — one setting per line, `#`
starts a comment, no sections, no quotes, no brackets. Every rebindable chord is
listed and **commented out**, so the defaults apply until you uncomment one:

```
# spoider — editor settings
#
# One setting per line. Text after # is a comment, so a line that starts
# with # is doing nothing.

autosave = false
marks = ✅ ❌ ❓ ❗ 🕐

# Chords. Uncomment a line to change it, e.g.  save = ctrl+w

# add a child and type its name
# add_child = tab

# rename the selected cell in place
# edit = ctrl+e
```

Rebinding is then one edit away:

```
save = ctrl+w
mark = ctrl+m
```

A chord is any key string Textual understands (`ctrl+w`, `alt+up`, `f2`), and one
line can take several, comma separated (`tab,ctrl+a`). Unknown names and blank
values are ignored, so a typo costs you one chord rather than the keymap. The
shortcut bar and the help screen both read the chords in force, so they never
advertise a key you no longer have.

A `config.json` or `config.toml` from an older build is read once, so nothing is
lost; the next save writes `config.conf` beside it.

## Colours

spoider ships no palette and no theme switcher. It runs on Textual's `ansi` theme,
so every box, link and the shortcut bar use whatever your terminal is already
using: depth picks ANSI colour names (cyan, green, yellow, magenta, blue, red),
the root stays on the default foreground, links are dim, and the selection is
reverse video. That means it looks right on a dark theme, a light theme, or a
16-colour tty.

## Placement

- Every shape is the same problem: place a subtree, then centre the parent over
  it. `spider` and `branch` pack bands vertically (children stack down a column,
  to the left and right or only to the right) and centre a parent on its band.
- `pyramid` and `bush` solve the columns only, since a level is a fixed row: a
  subtree is packed against the **outline** of the subtrees already placed — its
  leftmost and rightmost cell at each level — rather than against a reserved
  rectangle. A branch with two children no longer leaves an empty band beside
  its own narrow box; the sibling after it moves in. On a lopsided map that is
  about a third of the width, on an even one a few columns.
- In `spider` the root's children alternate sides by index: 0 right, 1 left,
  2 right, …, and a whole branch keeps its side.
- Stacked shapes start with a narrower column gap than the sideways ones. A
  sideways shape has to fit a connector run between a box and its children; a
  stacked one only needs its siblings not to touch, and a column is the scarcer
  resource when the tree grows down the page. `^=` still widens both.
- Tightening a stacked shape walks down 2 columns → **shared wall** → shared
  wall *and* shared rows. At both tight settings neighbouring siblings occupy one
  column between them, so a run of them reads as a single row of cells with
  partitions rather than as cells that happen to sit together. Cells from
  *different* parents always keep a blank column, so cousins never merge into a
  group that is not theirs. Each step draws differently; `^-` stops at the last
  one.
- A box border is stored as the directions that cell continues in, not as a
  finished glyph, so boxes that end up sharing a row join with `├ ┤ ┬ ┴` instead
  of overwriting each other's corners.
- Connectors leave the parent's edge and arrive at the child's, and both cells
  become a T pointing along the line (`├` / `┤` / `┬` / `┴`) rather than the line
  stopping a column short of a plain wall.

## Code map

| File | Role |
| --- | --- |
| `src/spoider/model.py` | `Node` / `MindMap`: the tree, mutations by id, JSON load/save |
| `src/spoider/layout.py` | places every visible node on a character grid |
| `src/spoider/render.py` | grid → styled cells (boxes, connectors) → `rich.Text` |
| `src/spoider/nav.py` | selection movement rules |
| `src/spoider/text.py` | strips control characters; one-line truncation helpers |
| `src/spoider/files.py` | atomic write: temp file, fsync, rename |
| `src/spoider/widgets.py` | `MindMapView`: camera, hit-testing, clicks |
| `src/spoider/drawers.py` | the bottom drawers: one-line prompt, question, panel |
| `src/spoider/screens.py` | the text the help and settings panels show |
| `src/spoider/app.py` | key bindings, undo history, write/quit flow |
| `src/spoider/chrome.py` | shortcut bar layout, pinned settings/help cluster |
| `src/spoider/config.py` | per-user editor preferences: autosave, marks, keymap |

## Test

```bash
uv run pytest
```
