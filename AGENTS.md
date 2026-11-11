# Notes for whoever edits spoider

The README is for people using it. This is for people — and coding agents — changing
it: the layout, the rules the code is held to, and the traps that have already cost
time once.

Python 3.11, one runtime dependency (Textual), `src/` layout, tests in `tests/`.

`requires-python` says `>=3.11`, and the checks run on both ends of that: 3.11 because it is
the oldest a person might have installed, 3.14 because it is what the runner offers today.
There is no pin, here or in CI, so `uv run` on this machine uses the interpreter it was
installed with, and the matrix is what keeps the two honest. The versions do differ where
it matters: argparse lays an invocation out differently from 3.13 on, and a test that
reads a rendering passes on one and fails on the other. Write assertions against the
property, and run the version you are not on when the assertion touches output.

## Commands

```bash
uv run spoider                                          # run it
uv run pytest                                           # asyncio_mode=auto, no markers needed
uv run ruff check src tests                             # lint
uvx pyright --pythonpath .venv/bin/python src/spoider    # types
```

A change is not done until all three are clean and there is a test that fails without
it.

## Versions and tags

A version marks a state whose checks passed. Bump and tag in the same breath, after the
run is green, never on the way in:

```
change → commit → push → checks green → bump + tag → push --follow-tags
```

- **Repairing the check is not a version.** A test that failed on the runner, and a test
  rewritten so it stops failing, are a fix to the check rather than a change anyone can
  notice. Such a commit joins the next version instead of taking one of its own.
- **Repairing the app is a version**, even when a test is what found the fault, because a
  user can see the difference.
- **Patch, unless the saved map format changes, a setting that used to work stops working,
  or a default chord changes meaning for a config that already exists.** Those are the
  breaks that earn a minor, because each is something an existing file notices. A line that
  used to do something and now does nothing counts, even for a reader who never wrote it.
  The test is compatibility, not the word "config": a name a newer spoider adds and an older
  one ignores costs the reader nothing, so `created_by` was a patch and `0.5.0` was one number
  too many. Text takes no version of its own either: a comment in the config, a sentence in
  the docs, a test repaired to match the code. When such a change does need a number, it is a
  patch. While the major number is 0 the distinction promises nothing to anyone, so keep it
  simple and consistent rather than clever.
- **The tag message says what changed**, not the date. The date is already on the commit,
  and a tag that reads `v0.4.9 — 2026-11-09` says nothing a reader cannot get from the
  commit below it.
- **`pyproject` names the last released version.** Unreleased work sits in the tree under
  that number, which is why the bump is the release act and not the first act. Two builds
  in one session cannot be told apart by the number; that is accepted.

There are no GitHub Releases here, only tags, so the tags page is the whole history a
visitor sees. That makes a tag placed before the checks agreed the one mistake that costs
something: `v0.4.7` went out red on the runner, and `0.4.8` was spent repairing it instead
of shipping anything.

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
| `editing.py` | `Buffer`: the text inside a cell or a prompt, its caret, its selection,
  its undo runs, and the justify fill |
| `drawers.py` | bottom drawers: prompt, question, panel, and the notice line |
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
  neutral note (a cut, a paste, an empty stack), red when something did not: a refusal, a
  paste cut short, a file that would not write.
- **A notification's length is one of three.** `QUICK` (2 s) acknowledges a key, `NOTE`
  (6 s) reports what it did, `FAILURE` (10 s) is something that has to be read; the config
  complaints have no length at all and wait for the file to be fixed. The constants live
  in `chrome.py` and a test refuses a bare number at a call site, because a duration
  written where it is used is a duration nobody can retune.
- **Same words everywhere.** Bar labels come from the binding table and chords from
  the keymap, so `^K` says "cut" on the map, in the panel and in help.
- **No compatibility shims.** Young project: no legacy key aliases, no old config
  readers, no migration paths. Ask before adding one.
- **A tab is content.** `clean_text` keeps `\t`; `expand_tabs` turns it into spaces to the
  next stop of `tab_width` from the config, and `lines_of` expands once so the box is
  measured and drawn against the same columns. Nothing may measure a cell with a bare
  `cell_len` on text that can hold a tab.
- **A prompt edits with a cell's buffer.** `PromptBar` holds an `editing.Buffer`, so a word
  jump, a word deletion, an undo and a paste answer to the same code as a cell, and
  `MAX_PROMPT_CHARS` (512) is its limit rather than the cell's 10 000. The keys that would
  need a second line are simply not offered, and a prompt that cannot keep all of a paste
  says so.
- **One word rule.** `_BREAK` in `editing.py` decides where a word ends for both a jump
  (`ctrl+left`) and a deletion (`alt+backspace`). Two rules make the two disagree, which is
  what `_word_start` and `_word_end` did with a whitespace test until they were deleted.
- **Untrusted input.** Clean text at ingest *and* at draw (`spoider.text.clean`), cap
  nesting at `MAX_DEPTH`, regenerate duplicate ids, write through
  `spoider.files.write_atomic`. A map that cannot be read is reported, never half
  loaded.
- **Don't invent scope.** Build what was asked for; propose the rest and wait.
- **Nothing is left behind.** A mechanism that is removed or renamed takes its name with
  it in the same change: the function, its import, the test that pinned it, the sentence
  in the docs that promised it, and the glyph table entry that only it used. This project
  changes its mind quickly, so the debris is real — `_fit_tokens` outlived the settings
  screen by weeks, and `FALLBACKS` outlived its own meaning by an afternoon. Sweep for
  the identifier across `src`, `tests` and the docs before committing, and for a module
  function run this, which finds anything referenced only where it is defined:

  ```bash
  uv run python - <<'PY'
  import ast, pathlib, re
  src = pathlib.Path("src/spoider")
  texts = {p: p.read_text() for p in src.glob("*.py")}
  every = "\n".join(texts.values()) + "\n" + "\n".join(
      p.read_text() for p in pathlib.Path("tests").glob("*.py"))
  for path, text in texts.items():
      for node in ast.parse(text).body:
          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
              if len(re.findall(rf"\b{node.name}\b", every)) <= 1:
                  print(f"{path.name}:{node.lineno} {node.name}")
  PY
  ```

  Two leftovers from a batch are a smell that the batch was not finished, not bad luck.

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

## Export

Three writers, all reachable from `--export` on the command line and nowhere else: there is no
key and no drawer, because a smaller surface is easier to keep honest. `svg.py` writes the
picture the renderer already drew, with `palettes.py` owning the four palettes and the
typefaces. `outline.py` writes the same map as a document, in markdown or plain text, from the
saved JSON alone: no palette, no face, nothing embedded, which is why a text export cannot come
out looking wrong on another machine.

Markdown gives the root and its children headings and everything below them a nested list,
two spaces a level; the cut stack is a second part of the document, so its heading sits at the
title's level and ends the file. Plain text is the same tree with no headings and no dashes,
one tab a level. A cell is flattened to one line on the way out, because a heading with a
newline in it stops being a heading, and a collapsed branch is still written: the file is the
map, not the screen. A mark is printed before its cell's text, as the cell is drawn, and a
mark with no text is the whole label.

`--export` names the format and `-o` the file. The names live in `formats.EXPORT_FORMATS`,
which the parser reads for its choices, so a writer and the flag that reaches it cannot drift
apart; adding a format is one name in that tuple, one branch in `main`, and a dialect in
`outline.py` if it is a document rather than a picture. `formats.TEXT_FORMATS` is what makes
`--palette` and `--font` an error there instead of a lie.

`compose` normalises the origin, because a layout may place a left branch at negative
coordinates and a file has no camera to follow it. Runs carry `textLength`, so a face whose
advance is not 0.6 em still lands on the cell grid. The face is embedded, because a named one
is a suggestion a viewer may decline. Cell metrics come from the face: `metrics()` reads the advance from `hmtx` and the line from
`hhea`, so the grid the boxes are built on and the glyphs inside them agree. 0.6 by 1.4 stands
in only when the tables cannot be read. `svg` is the only place the numbers are used, which is
why one test checks the canvas against them and nothing else needs to.

Only `glyf` faces are allowed (`is_truetype`): a CFF face delivered through `@font-face`
renders nothing at all in a browser, which was Spleen, and a bitmap face cannot be scaled. The
check reads the font's table directory rather than searching the bytes for `CFF `, which appear
in files that have no such table.

Still unguarded: a TrueType face with no letters (an icon font) draws nothing either. The
character check the other branch had needs `fc-query --format %{charset}` here, and it is not
built yet.

## Export safety

`write_svg` and `outline.export_document` both refuse to replace an existing file without
`overwrite`, refuse a target that is the map itself, refuse a folder that is not there, and go
through `files.write_atomic`.
`write_atomic` creates parent folders, so the folder check has to happen first: an export
writes one file and builds no road to it.

Text is cleaned at ingest and escaped at write, so a map cannot inject XML. The embedded font
is a file fontconfig named, and it must carry a `glyf` table, so a hostile fontconfig entry
pointing at something that is not a font cannot be copied into a picture.
## Types

`pyright src/spoider` is clean and is part of the gate. `pyright tests` is **not**: about
ninety errors, almost all of them the checker asking "what if it is None?" about an
accessor a test already knows is not (`MindMap.find`, `Layout.get`, `_buffer`) or about
`.plain` on Textual's `RichCast`. They cost nothing at runtime and the whole file set
would have to be swept at once to clear them, so the choice is to keep the gate on
`src/` and say so here rather than leave it looking forgotten. One thing did get fixed
from that list: `BINDINGS` is `list[Binding]`, not Textual's union with the tuple form,
so `binding.id` and `binding.action` are strings everywhere in our code.

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

**The report does not fade.** That notice has `timeout=float("inf")`: a config that
fights itself is the reader's to fix, and a warning that expires is a warning nobody acts
on. Each reading of the file clears the line (`NoticeBar.close`) and says again only what
is still wrong, so a fixed mistake takes its warning with it.

**Notices are one line, not windows.** `NoticeBar` is a one-row band above the bar of
keys, where nano puts its messages, and it is placed by an offset on its own layer: it
takes no row from the map, so nothing moves when a notice comes or goes.

Two kinds of sentence share that row. A *temporary* notice has a time (`QUICK`, `NOTE`,
`FAILURE`) and goes when it is up. A *standing* one has none: `timeout=float("inf")`, and the
only thing that asks for it is a config that fights itself, because that is the reader's to
fix. A temporary notice steps in front of a standing one and the line goes back when its time
is up, so a warning is never lost to a later remark. The three words are `show` to say
something, `close` to lend the line to a question (which restores it when it closes), and
`forget` to drop what is standing when the file it complained about has been read again.

A prompt is placed the same way and takes the line while it is open. Textual's own toasts are
not used at all.

**Six actions carry a function key as a second chord** — help F1, save F2, undo F3,
settings F9, quit F10, write F12 — declared on the binding itself (`"ctrl+s,f2"`). They
are ordinary chords: the template lists them, the bar shows the first only, and a line
that names the action replaces the whole list, so `help = t` takes `F1` with it. There is
no net that survives a rebind; the point of the function keys is only that these six are
reachable without a chord at all.

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
- A Rich `Text("x", style)` puts the style on the **base** of the text, which Textual's
  compositor does not paint: the notice band lost its colour to exactly that. A segment
  goes in as a span (`line.append(chunk, style)`) and is drawn.
- Textual's input thread busy-loops when stdin reaches end of file: the read returns
  empty, the inner loop `break`s, and `select` reports the dead descriptor ready again for
  ever, so a process whose terminal has gone burns a whole core. Probe apps left on a
  closed pseudo-terminal are how this is met in practice, and they are killed by PID. We
  do not work around it: a real terminal closing sends SIGHUP, and the case that survives
  is a pipe or a harness.
- `files.write_atomic` resolves a link before writing, refuses a target that is not a
  regular file or that its owner cannot write, and raises `WriteRefused`, an `OSError`
  carrying the sentence to print. A failed `MindMap.save` is therefore not always an
  errno, and the callers that catch `OSError` report it unchanged.
- Overwriting an existing map is a question, and it lives in `_write_submitted`
  (`_would_bury`), not in `_write`, which only refuses. "No path" means "not our own
  file", so a buffer that has never been saved asks too.

## What drawing costs

Measured, process CPU per keystroke at 120x40, and worth knowing before touching the
renderer again:

| cells | paint a kept picture | rebuild it | typed character | arrow key |
| --- | --- | --- | --- | --- |
| 55 | 1.3 ms | 5.4 ms | 12.4 ms | 15.0 ms |
| 105 | 1.3 ms | 6.4 ms | 13.7 ms | 16.0 ms |
| 211 | 1.3 ms | 8.8 ms | 16.0 ms | 16.5 ms |

The picture, therefore, is about six of the fourteen milliseconds a keystroke costs at a
typical size. The rest is Textual's compositor chopping and writing the screen, and no change
of ours reaches it, which is why picture work is worth doing only where it removes a whole
category of work rather than a constant.

Three rules keep it that way, and each came from a measured fault:

- **The picture is only worth the window.** `build_grid(..., window=)` drops every write
  outside it and skips boxes it cannot reach, so a screen costs the screen. Drawing the whole
  document cost 50 ms a change on a 541-cell map, against 3.4 ms for a window. A window is the
  camera's view rounded out to blocks of 32 by 16 (`cache_window`), so a caret moving a column
  does not rebuild a page.
- **The caret is a style, not a cell.** `Grid.caret` records where it hangs, `render_text`
  applies it. Moving the caret repaints (`view.refresh()`), and rebuilding the map for it was
  most of what holding a key in a cell cost.
- **An unchanged box moves nothing.** `_sync_preview` measures the edited box and asks for a
  new picture (`refresh_picture()`, the arrangement kept) when it is still the size the layout
  gave it, or a new arrangement (`refresh_map()`) when it has grown. A character typed inside
  a line that is not the longest went from 22 to 11 ms on a 541-cell map.

The selection is still part of the picture, which is the one false dependency left: it adds
reverse video to a box's frame, so every cursor move rebuilds a page even when the camera stays
inside its block. Moving it to the assembly the way the caret went would be a cleanup worth
about 3 ms on a move, and it needs the frame/inside rule, the `lead` underline and the
search-hit cancellation carried across, so it is a change to weigh rather than a tidy-up.

Do not reach for the tail of the table. A map over 500 cells is rare, the layout is honest work
there (9 ms of the 20 a character costs, because its siblings really do move), and an
incremental layout or a per-cell patch buys a few milliseconds where nobody types fast enough
to feel them.

## What a keystroke costs

Measured on this machine, a 120x40 terminal, process CPU per keystroke:

| map | picture repainted | picture rebuilt | typed character | arrow key |
| --- | --- | --- | --- | --- |
| 55 cells | 1.3 ms | 4.2 ms | 11.8 ms | 13.9 ms |
| 105 cells | 1.3 ms | 5.1 ms | 12.9 ms | 15.4 ms |
| 541 cells | 1.5 ms | 3.4 ms | 20.4 ms | 14.5 ms |

About seven of those milliseconds are Textual's compositor chopping the screen and writing it.
The rest is ours, and the picture is the part we can make smaller:

- a picture is built only for the cells the camera can reach (`build_grid(..., window=...)`),
  so its cost is the screen rather than the document: 50 ms becomes 3.4 on 541 cells;
- the window is the screen rounded out to 32 by 4 cells, because typing creeps the camera
  sideways a column at a time and navigation moves it twenty rows at once. Tall blocks cost
  1.1 ms a rebuild (6.25 against 5.15 at 120x40) and are never hit;
- the caret is a style applied while the window is assembled (`Grid.caret`), not a cell in the
  picture, so moving it repaints instead of rebuilding;
- a box whose text changed without changing size keeps its arrangement: `refresh_picture`
  against `refresh_map`, decided in `_sync_preview` by measuring the box.

Two things were measured and deliberately not built. A layout that translates instead of
recomputing (`compute()` is 9.2 ms on 500 cells, 1.7 on 100) and a patch that redraws one box
inside the shared character grid (about 2 ms, and it has to re-merge the connectors that meet
the box's walls). Both pay off only on the very large maps, which are the rare ones, and both
live where the last two drawing bugs lived.

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
- Undo history is in memory for the session, capped at 200 steps.
- A prompt holds 512 characters, so a path longer than that cannot be typed or pasted into
  one.
- Autosave is off by default and there is no backup file.
- No file locking: two editors on one map, last save wins.
