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
| `render.py` | grid → styled cells (boxes, connectors) → `rich.Text` |
| `nav.py` | selection movement rules |
| `widgets.py` | `MindMapView`: camera, hit-testing, the stack column, clicks |
| `drawers.py` | bottom drawers: prompt, question, panel |
| `screens.py` | the text help and settings show |
| `chrome.py` | the shortcut bar: ranking, chunks, pinned cluster |
| `config.py` | editor preferences in `~/.config/spoider/config.conf` |
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
  `mark`, `spacing`, `layout` and `cut_stack`. `config.conf` holds autosave, the mark
  set and chord overrides. Anything that changes how a map looks belongs to the
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
- The caret is a style, not a character: `Node.preview` holds the plain buffer and
  `Node.caret` an index into it, and the renderer inverts that one cell. Never insert
  a cursor glyph into the text — it splits the word it is sitting in.

## Known limits

- A map wider than the terminal is clipped at the edges; there is no zoom out.
- No drag-to-reparent — that is cut and paste.
- Undo history is in memory for the session and not capped.
- Autosave is off by default and there is no backup file.
- No file locking: two editors on one map, last save wins.
