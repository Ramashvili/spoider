# Notes for whoever edits spoider

The README is for people using it. This is for people — and coding agents — changing
it: the layout, the rules the code is held to, and the traps that have already cost
time once.

Python 3.11, one runtime dependency (Textual), `src/` layout, tests in `tests/`.

## Commands

```bash
uv run spoider                                          # run it
uv run pytest                                           # asyncio_mode=auto, no markers needed
uv run ruff check src tests                             # lint
uvx pyright --pythonpath .venv/bin/python src/spoider    # types
```

A change is not done until all three are clean and there is a test that fails without
it.

## Layout

| File | Role |
| --- | --- |
| `model.py` | `Node`, `MindMap`: the tree, mutations by id, the cut stack, JSON load/save |
| `layout.py` | places every visible node on a character grid |
| `render.py` | grid → styled cells (boxes, connectors, the two colourings) → `rich.Text` |
| `nav.py` | selection movement rules |
| `widgets.py` | `MindMapView`: camera, hit-testing, the stack column, clicks |
| `drawers.py` | bottom drawers: prompt, question, panel |
| `screens.py` | the text help and settings show |
| `chrome.py` | the shortcut bar: ranking, chunks, pinned cluster |
| `config.py` | editor preferences in `~/.config/spoider/spoider.conf` |
| `app.py` | bindings, modes, the stack panel, undo history, write/quit |
| `text.py`, `files.py` | cleaning untrusted text; atomic writes |

`app.py` is a third of the code and one class. Its seams are marked with section
comments; the search machinery and the history/quit machinery are the two pieces most
ready to move out.

## Rules the code is held to

- **No palette.** Textual's `ansi` theme, ANSI colour names, reverse video for
  selection and search hits, `\e[7m` blocks in the top bar. No hex, no RGB, no fixed
  named colour — `orange1` does not parse at all and `orange` is a hard-coded RGB.
- **Document vs editor state.** The map file holds the tree, text, `collapsed`,
  `mark`, `marks`, `spacing`, `layout`, `colours` and `cut_stack`. `spoider.conf` holds
  autosave, `marks_default` and chord overrides. Anything that changes how a map looks belongs to the
  document, so a file looks the same wherever it is opened.
- **Chords are spelled nano's way** everywhere — `^` ctrl, `M-` alt, `S-` shift — never
  `⌥`/`⇧` glyphs. Ctrl chords first; a bare key only where it collides with nothing
  and the action is used constantly. One chord per job.
- **The bar never disappears** and always describes what has the keys. No modal
  screens: prompts, questions, settings, help and the stack are drawers or columns.
  Panels keep one blank line above the bar.
- **Same words everywhere.** Bar labels come from the binding table and chords from
  the keymap, so `^K` says "cut" on the map, in the panel and in help.
- **No compatibility shims.** Young project: no legacy key aliases, no old config
  readers, no migration paths. Ask before adding one.
- **Untrusted input.** Clean text at ingest *and* at draw (`spoider.text.clean`), cap
  nesting at `MAX_DEPTH`, regenerate duplicate ids, write through
  `spoider.files.write_atomic`. A map that cannot be read is reported, never half
  loaded.
- **Don't invent scope.** Build what was asked for; propose the rest and wait.

## The map and the stack panel are one document

The panel is an ordinary `MindMap` built over the same `Node` objects, not a list view
beside the map. Actions therefore ask `SpoiderApp.document` (the panel's view of the
cuts while it is open, else the map) and `SpoiderApp.focus` (the cell the keys are on
in whichever of them has them) instead of reaching for `self.mm` and `self.selected`.
Anything that only knows about `self.mm` works on the map and silently does nothing in
the panel, which is exactly how the panel came to be missing justify, copy and new
cells while editing happened to work. The bars are one bar too: `stack_chunks` is
`hint_chunks` with the toggle renamed and moved to the head. `check_action` must not
block the app's bindings while the panel is open: the panel consumes the keys it
implements in `handle_stack_key`, and whatever is left (save, quit, colours, shape,
spacing, help) means the same thing in both places. Keep the *actions* document-aware
rather than the key routing, because `Tab` and `Return` reach the app bindings without
passing through `MindMapView.on_key` at all.

## One cursor, one selection

`selected`/`anchor` point into whichever document has the keys: opening the panel
stashes the map's pair and closing puts it back. `selected_ids` reads the run from
`document`, so `^A`, shift+arrows, mark, fold, cut and delete behave identically on
the map and inside a cut, and the panel draws the run through the same `build_grid`.
Anything that reaches for `self.mm` instead of `self.document` is a bug in the panel.

`_drawer_owner` answers "who holds the keys" by asking which drawer is *displayed*,
never by matching mode names: a new prompt mode keeps the keys on return without anyone
remembering to list it, which is how `justify` came to be left open with the map taking
its keys after the terminal regained focus.

The mouse is deliberately off (`run(mouse=False)` and no click handlers): a click that
moved focus away from a drawer left the reader typing into the map with a question on
screen, and terminal-native selection is worth more than click-to-select.

## The map file, the config file

A new map is coloured by family (`DEFAULT_COLOURS` in `model.py`); depth is the other
choice and the key cycles between them, saving the choice in the file.

Anything that decides how a map *looks* goes in the map file: tree, text, marks,
folds, spacing, layout, colouring, the cut stack, and the width the map was last
justified to (`justify`). Anything about how the *editor* behaves goes in the rc file
(`autosave`, `marks`, `justify_width_default`, chord overrides). The rc file is read
through `parse(text, known)`: a name that is not a setting and not a binding id, or a
value that is not a chord (`is_chord`), is a leftover and is dropped, so a stale line
cannot silently rebind a key and cannot be written back.

## Maps are `.spoider` files

Content stays plain JSON — strict, round-trips exactly, one parser — and the extension is
only the label that says what the JSON is. The app never looks at an extension, so any
path opens. Import and export in other formats are separate jobs from the file.

`src/spoider/data/` holds the MIME type and the desktop entry, inside the package so a
wheel carries them; `spoider --install-desktop` copies both into the XDG directories,
runs the cache rebuilders and sets the default. It writes nothing unless asked, and it
resolves the launcher's `Exec=` to the real binary path because a desktop session does
not always have `~/.local/bin` on PATH.

## Tests

`uv run pytest` runs twelve at a time (pytest-xdist): one test drives one app through
its message loop, so the suite waits far more than it computes — serially it spends 56 s
of wall clock on 10 s of CPU — and workers past the core count fill that waiting instead
of fighting over it. Twelve is twice the cores of the machine this is developed on, and
the curve is flat between 12 and 24. `-n 0` runs serially, under a debugger.

If two tests ever look like they are treading on each other, run `-n 0` before believing
it is a real failure: nothing is shared — every test gets its own `tmp_path` and, from
the autouse fixture, its own `XDG_CONFIG_HOME`.

Each test gets its own `XDG_CONFIG_HOME` from the autouse fixture in `conftest.py`, so
the suite neither reads nor writes the real `~/.config/spoider/spoider.conf`.

## Chords: one line per action

The rc file names an action and lists *every* chord that action answers to, space
separated (`left = ctrl+b left h`). `action_chords` is the one table: the file is
rendered from it, `_action_for` matches a pressed key against it, the bars show the
first chord of the list, and `build_action_keymap` joins them into the comma form
Textual's own `App.set_keymap` expects. Aliases are extra bindings with the same
action, so they never get a line of their own and cannot drift out of step.

A chord left off the line stops working — the line is the truth, not a patch over the
defaults. `VIM_BINDS` in `config.py` is written into the file commented out, at the end,
so switching keymaps is uncommenting a block; it keeps the arrow keys on the movement
lines, because arrows are not a convention anyone chose. A token that is not a key is dropped from the line rather than read as a
chord, which is what keeps a leftover setting from rebinding a key.

## Traps

- `App.clipboard` already exists (Textual's OSC 52 bridge) — shadowing it raises at
  construction. The cut cell is `cut_cell`.
- `^M` arrives as `Return` on any terminal, and `^I` as `Tab` where the kitty keyboard
  protocol is missing. That is why `m` is bare and `ctrl+m` is not bound at all.
- `run_test` suppresses notifications unless you pass `notifications=True`.
- `Text.split("\n")` drops blank lines — pass `allow_blank=True` when splicing
  rendered text back together.
- A binding that is not in `BINDINGS` is invisible to the bar and to help.
- The stack panel is an ordinary `MindMap` built over the *same* `Node` objects, but
  its top-level list is a copy: mutations have to be written back to `cut_stack`.
- `MindMap.find()` rebuilds its index on a miss. That is what keeps paste and delete
  simple, and it means a stale id costs an index rebuild rather than raising.
- While a drawer or the stack panel has the keys, clicks and scrolls on the map are
  ignored, and `_restore_focus()` puts the keys back when the terminal regains focus.
- The map draws no cursor while the stack panel is open: one cursor on screen means
  one place the keys are.
- The caret is a style, not a character: `Node.preview` holds the plain buffer,
  `Node.caret` an index into it and `Node.overwrite` whether it replaces or inserts.
  The renderer inverts that one cell, underlining it in overwrite mode. Never insert a
  cursor glyph into the text: it splits the word it is sitting in.
- `Shift+Return` and `^J` are only separable from `Return` under the kitty keyboard
  protocol, like `^I` and `^M`. In a plain terminal both arrive as Enter.

## Navigating the map from a script

Driving spoider from a key sequence is how the tour video and its checks are built, and
the arrows are the part that surprises everyone. In the **branch** shape, which is where
a tree is easiest to build:

- `←` climbs to the parent, but on the root it goes **into the last child**. So never
  press `←` "until it stops": count the levels you came down and press exactly that many.
- `→` goes into the first child. On a leaf it stays put.
- `↑` and `↓` walk siblings, and climb out of the branch at either end.
- Building: `Tab` makes a child and starts typing, `Return` makes a sibling and starts
  typing, and one `Return` commits. Two Enters in a row therefore name a cell and then
  open another one.
- `^A` selects every sibling of the cell under the cursor and leaves the cursor on the
  last of the run; `esc` drops the run. A shift-arrow grows the run one cell at a time.
- `^D` deletes whatever is selected as a single undo step, and a run leaves the cursor on
  the parent it hung from. That parent is the most reliable anchor in the whole keymap.
- `^K` cuts the selection to the stack and leaves the cursor on the cell that closes the
  gap, or on the one before it when the run ended the branch, or on the parent when the
  cell was an only child.
- `^U` pastes under the selected cell and **keeps the selection there**, so a `Tab` right
  after a paste adds a child to the cell that received it.
- `^I` opens the stack panel, which takes every key the map takes; closing it puts the
  map cursor back where it was before it opened.
- `^L` cycles the shape spider, pyramid, bush, branch, spider. Build in branch, show the
  others, and step back to branch to keep building.
- While a cell is being typed into, `Home` puts the caret at column 0, so `Home` then
  `BackSpace` clears nothing; send forward-delete (`\x1b[3~`) instead.

Two habits follow from this. Anchor every block on a known count of `←` from the place
the previous block left the cursor, and verify the map instead of the picture: the map is
ground truth for whether the keys did what the scene meant.

## The tour video

`media/spoider-tour.mp4` is recorded from a real terminal window, not repainted by hand:
`media/tour/record.py` runs the program in a kitty window on an empty desktop, pins the
tmux window to 150x50, captures that pane's pixel box and burns in the chords it sent.
`media/tour/check_scene.py` plays the same keys through a pty at reduced speed and prints
the map they build, which is how a mis-anchored scene is caught in twenty seconds.

Run the check before recording, and read the map it prints: a fold on a leaf, a cell that
landed a level too high or a missing cell are all invisible in a thumbnail and obvious in
the tree.

## Known limits

- A map wider than the terminal is clipped at the edges; there is no zoom out.
- No drag-to-reparent — that is cut and paste.
- Undo history is in memory for the session and not capped.
- Autosave is off by default and there is no backup file.
- No file locking: two editors on one map, last save wins.
