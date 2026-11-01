## Known limits

- On a narrow terminal a wide map is clipped at the edges — the view always
  keeps the selected node centred and does not zoom out. Use a wider window, or
  fold branches you are not working on.
- No drag-to-reparent: reparenting is cut and paste (`^K`, then `^U` under the
  new parent).
- Undo history lives in memory for the session (the file on disk is only the
  current state, and only after a `^O` write). It is not capped, so a very long
  session on a very large map keeps growing.
- Autosave is off by default; with it off there is no backup file either, so
  quitting with `n` discards changes for good.
- Nothing locks the map file. Two editors on the same map means the last save
  wins.

## Where the next work should go

- `app.py` is a third of the code and one class: state, drawers, search, inline
  editing, movement, files. The seams are marked with section comments and each
  section is small, but it is the file that will rot first. The two pieces most
  ready to leave are the search machinery and the history/quit machinery.
- `MindMap.find()` rebuilds its index whenever an id misses. That is what lets
  paste and delete stay simple; it also means a stale id costs an index rebuild
  rather than raising, so a future bug would show up as slowness, not a traceback.
- Only the flat rc file is read. The `config.json` / `config.toml` reader from the
  build before it is gone on purpose: no migration shims in a young project.

## What happens to a file it cannot read

A map is untrusted input, so `MindMap.load` reports rather than raises:

- not UTF-8, not JSON, not an object with a `root`, or nested deeper than
  `MAX_DEPTH` (400) → the editor opens an empty map and says why in a
  notification. The unreadable file is left untouched.
- control characters in cell text, marks and ids are stripped when the file is
  read *and* again when a cell is drawn (`spoider.text.clean`). Without that, a
  cell could carry an escape sequence into the terminal: clear the screen,
  recolour the app, or write to the clipboard through OSC 52.
- duplicate ids are regenerated, so `find()` can never point at the wrong node.

Writes go through `spoider.files.write_atomic`: a sibling temp file, fsync,
then rename — a crash mid-write leaves the previous map intact.
