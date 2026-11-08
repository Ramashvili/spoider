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
| `addressing.py` | reading `-p/--position`: a path of 1-based children, `s` for the stack |
| `properties.py` | the `i` overlay: the file's own values, the cursor's address and id |
| `widgets.py` | `MindMapView`: camera, hit-testing, the stack column, clicks |
| `drawers.py` | bottom drawers: prompt, question, panel |
| `screens.py` | the text the help shows |
| `chrome.py` | the shortcut bar: ranking, chunks, pinned cluster |
| `config.py` | editor preferences in `~/.config/spoider/spoider.conf` |
| `keys.py` | `BINDINGS` and the keymap built from it |
| `desktop.py` | registering `.spoider`: the MIME type, the entry, the default |
| `actions_map.py` | `MapActions`: cells, marks, folding, navigation, spacing, shape, ordering |
| `actions_stack.py` | `StackActions`: cut, paste, the panel, and the stack's own history |
| `actions_edit.py` | `EditActions`: typing in a cell, the clipboard, justify |
| `app.py` | the app object: lifecycle, focus and the document, chrome, files, search |
| `text.py`, `files.py` | cleaning untrusted text; atomic writes |

`SpoiderApp` is three action mixins plus the app itself. The mixins hold no state and no
bindings: they read `self.mm`, `self.selected`, `self.focus` and the helpers the app
keeps, which is why each one opens with a pyright note that the rest of the object comes
from `SpoiderApp`. A new key's action goes in the mixin that owns that area and its
binding goes in `keys.py`; a binding that lives anywhere else is invisible to the bar and
to help.

## Rules the code is held to

- **No palette.** Textual's `ansi` theme, ANSI colour names, reverse video for
  selection, search hits and the drawer bands. No hex, no RGB, no fixed named colour —
  `orange1` does not parse at all and `orange` is a hard-coded RGB.
- **Reverse says "you are here", one place at a time.** The cursor's cell wears it while
  the map has the keys; a prompt or the stack panel takes it over and the cell's frame
  steps aside. The top line is plain, except the cut count, which turns yellow while the
  panel is open.
- **Document vs editor state.** The map file holds the tree, text, `collapsed`,
  `mark`, `marks`, `spacing`, `layout`, `colours` and `cut_stack`. `spoider.conf` holds
  autosave, `marks_default` and chord overrides. Anything that changes how a map looks belongs to the
  document, so a file looks the same wherever it is opened.
- **Chords are spelled nano's way** everywhere — `^` ctrl, `M-` alt, `S-` shift — never
  `⌥`/`⇧` glyphs. Ctrl chords first; a bare key only where it collides with nothing
  and the action is used constantly. One chord per job.
- **The bar describes what has the keys, and comes back for it.** It can be hidden from
  the config file (`hide_footer`); it returns whenever something is asking for keys —
  a prompt, a question, help, the stack panel, or a cell being typed into. No modal
  screens: prompts, questions, help and the stack are drawers or columns.
  Panels keep one blank line above the bar. The one thing that floats is the `` ` ``
  debug box in the top-left corner, drawn over cells: it is read-only and costs no
  space, where a drawer or a column would take the space it exists to describe.
- **A notification's colour is its meaning.** Green when something worked, yellow for a
  neutral note (a cut, a paste), red when something did not: a refusal, a paste cut short,
  a file that would not write.
- **Same words everywhere.** Bar labels come from the binding table and chords from
  the keymap, so `^K` says "cut" on the map, in the panel and in help.
- **No compatibility shims.** Young project: no legacy key aliases, no old config
  readers, no migration paths. Ask before adding one.
- **A tab is content.** `clean_text` keeps `\t`; `expand_tabs` turns it into spaces to the
  next stop of `tab_width` from the config, and `lines_of` expands once so the box is
  measured and drawn against the same columns. Nothing may measure a cell with a bare
  `cell_len` on text that can hold a tab.
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

**Every editor-facing choice is a setting, with the bindings beside it.** Nothing a person
might want to change stays a constant in the code, because a constant is a choice they
cannot reach: the page size inside a cell is `page_lines`, the tab stop is `tab_width`. What
is not a preference (a safety cap, the shape of the format) stays a constant.
`examples/spoider.conf` is the template verbatim, and `test_docs.py` keeps the two
identical, so a setting added in a release is visible to a reader whose own file predates it.

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
separated (`go_left = left ctrl+b h`). `action_chords` is the one table: the file is
rendered from it, `_action_for` matches a pressed key against it, the bars show the
first chord of the list, and `build_binding_keymap` joins them into the comma form
Textual's own `App.set_keymap` expects.

**One binding per action, carrying every chord.** An alias is a second chord on that
binding's key string (`Binding("e,ctrl+e", "edit", id="edit")`), never a binding of its
own: Textual splits the list on commas itself, so `"up,ctrl+p,k"` is legal even though a
bare comma would be read as the separator. The separate ids that used to carry the
aliases (`edit_alt`, `left_vim`, `delete_key`, …) are gone, and a config that still
names one has that line dropped as unknown.

**Every binding is named after its action.** `go_left` moves the cursor left, `go_up`
walks to the previous sibling, `go_end` goes to the deepest cell. The two used to
disagree (`left` was `go_left`, `prev` was `prev`), which made the file read
`left = left` and left the reader guessing which of the two names a line takes; a test
now asserts `binding.id == binding.action` for every binding, so they cannot drift.

**The keymap is keyed by binding id**, because that is what `App.set_keymap` and
`BindingsMap.apply_keymap` look a binding up by (`keymap.get(binding.id)`) and what the
file names. An action-keyed map agrees with that only where an id happens to equal its
action name, so passing one left `left`, `right` and every alias line changing the bar
and nothing else — the bug that made a rebind look applied and do nothing.

**Two actions on one chord is refused, not resolved.** `keys.resolve` gives every chord
one owner. A *line* competes only with another line: between two lines the earlier one
wins — "the second line is refused" — and the loser keeps its other chords. A *default*
is a placeholder and gives way to any line without a word, which is what makes `cut = ,`
take the comma off the debug key quietly; complaining there would make the ordinary case
noisy. The losing action keeps its other chords and loses that one, and
`SpoiderApp._report_clashes` says which two actions were fighting, in red, on every
reading of the file. Textual's own `handle_bindings_clash` is no use here: its body does
nothing and its set holds only the binding that was already there, one side of the story.

**A name given two lines** keeps the last, as any rc file does; `parse` records the
name in `Config.repeated` and the same report names it, because the first line dying
quietly is the kind of thing a reader never finds.

**The report does not fade.** Those toasts are `timeout=float("inf")`: a config that
fights itself is the reader's to fix, and a warning that expires is a warning nobody
acts on. Each reading of the file removes the previous ones (`_notifications`, then
`_refresh_notifications`) and says again only what is still wrong, so a fixed mistake
takes its toast with it and a repeated one is not stacked twice.

**Six actions carry a fallback chord** (`FALLBACKS`: help F1, save F2, undo F3, settings
F9, quit F10, write F12). They are added to the dispatch keymap only, so neither the bar
nor the template offers them: a net is not a choice, and the point is that a line which
rebinds `save` cannot lock the reader out of saving. `build_binding_keymap` appends them
and `screens.keys_for` lists them in help, because help is where every key can be looked
up; `action_chords` stays the user-facing list.

**An unbound action keeps its place in the bar**, dimmed and without a cap (`unbound()`),
rather than vanishing: a key that was taken away is worth seeing.

**A chord Textual binds for itself** (`ctrl+q` for its quit, `tab` for focus) cannot be
handed to an action of ours: the widget or the app answers first. `_foreign_chords`
compares against Textual's own tables, minus the chords spoider already owns, and the
report names those too — a line that will not do what it says.

A search looks in both documents: `_search_order` puts the map first and then the stack, and
walking to a hit on the stack opens the panel to show it, which is what "switch between them"
means here. `matches` is a list of ids in that order, so `alt+f`/`alt+b` cross the boundary
in both directions.

A chord is written as the character a person presses: the file says `,` and `.` and `?`,
not `comma` and `full_stop`. Textual's own names stay in `keys.py`, and `PRESSED`/`WANTED`
there is the single place the two vocabularies meet — a comma cannot even be a Textual
binding, because its keymap reads a comma as the separator between two keys. A test takes
every line the template prints, settings block and vim block alike, and asserts it parses
back unchanged; that is what keeps the file from offering a spelling the parser drops.

A chord left off the line stops working — the line is the truth, not a patch over the
defaults. `VIM_BINDS` in `config.py` is a *complete* keymap: every id the template offers has a line,
with a vim chord where vim has one and the default restated where it does not, because a
partial block would silently drop the chords it omits. A test asserts that, and another
asserts no chord appears twice in it. It is written into the file commented out, at the end,
so switching keymaps is uncommenting a block; it keeps the arrow keys on the movement
lines, because arrows are not a convention anyone chose. A token that is not a key is dropped from the line rather than read as a
chord, which is what keeps a leftover setting from rebinding a key.

## Traps

- `App.clipboard` already exists (Textual's OSC 52 bridge) — shadowing it raises at
  construction. The cut cell is `cut_cell`.
- `^M` arrives as `Return` on any terminal, and `^I` as `Tab` wherever the kitty keyboard
  protocol is missing, which is most terminals. Neither is bound: marks are bare `w` and
  `^W`, and the stack panel is bare `p`, so all three survive a plain terminal.
- Installing cannot do anything: `uv tool install` and a wheel run no code at install
  time, so the offer to register `.spoider` with the desktop happens on the first launch
  instead, once, recorded in the config as `desktop_asked`.
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
  protocol. In a plain terminal both arrive as Enter.

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
- `p` opens the stack panel, which takes every key the map takes; closing it puts the
  map cursor back where it was before it opened.
- The arrows keep the hierarchy's answer when it names a parent, a child or a sibling.
  Otherwise the canvas decides: the closest cell in the direction pressed, measured
  between nearest edges (a wide neighbour is near, however long), preferring our own
  level, then a cell whose parent sits beside our parent. That is what crossing a gap
  means, and `nav.towards` is the only place it is decided.
- `^L` cycles the shape spider, branch right, branch left, pyramid, bush, spider. Build in
  branch right (stored as `branch`), show the
  others, and step back to branch to keep building.
- While a cell is being typed into, `Home` puts the caret at column 0, so `Home` then
  `BackSpace` clears nothing; send forward-delete (`\x1b[3~`) instead.

Two habits follow from this. Anchor every block on a known count of `←` from the place
the previous block left the cursor, and verify the map instead of the picture: the map is
ground truth for whether the keys did what the scene meant.

## The tour video

Screenshots and recordings are the last step, never part of a change: the human runs the
program first, says the change is good, and approves the picture before it is committed. A
still taken mid-work shows a state nobody asked for.

The tour is delivered as an uploaded attachment, so no video is committed: the mp4s are
ignored and live on disk only. `media/tour/record.py` records it from a real terminal
window, not repainted by hand: it runs the program in a kitty window on an empty desktop,
pins the tmux window to 150x50, captures that pane's pixel box and burns in the chords it
sent. `media/tour/check_scene.py` plays the same keys through a pty at reduced speed and
prints the map they build, which is how a mis-anchored scene is caught in twenty seconds.

The recording is lossless and the published file is the only encode. `wf-recorder -c
libx264rgb -p crf=0 -r 30 -D` writes the master (about 3.7 MB for 137 s of a 1197x802
pane), the chords are drawn and the mp4 encoded from it at crf 20. Every take's master goes to
`~/Videos/spoider/` with its timestamp in the name: the user watches candidates there, and
a later encode starts from them without re-filming. `-D` is required: with damage tracking a still
screen produces no frames at all. `media/tour/fidelity.py` measures how far a file is from
the screen, which is how the flag and the settings were settled: the master differs by 0 on
every pixel, while the gpu-screen-recorder path changed all of them, worst case 219 levels.

Run the check before recording, and read the map it prints: a fold on a leaf, a cell that
landed a level too high or a missing cell are all invisible in a thumbnail and obvious in
the tree.

## Known limits

- A map wider than the terminal is clipped at the edges; there is no zoom out.
- No drag-to-reparent — that is cut and paste.
- Undo history is in memory for the session and not capped.
- Autosave is off by default and there is no backup file.
- No file locking: two editors on one map, last save wins.
