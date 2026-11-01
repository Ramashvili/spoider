## Known limits

- On a narrow terminal a wide map is clipped at the edges — the view always
  keeps the selected node centred and does not zoom out. Use a wider window, or
  fold branches you are not working on.
- No search, multi-select, or drag-to-reparent yet.
- Undo history lives in memory for the session (the file on disk is only the
  current state, and only after a `^O` write). It is not capped, so a very long
  session on a very large map keeps growing.
- Autosave is off by default; with it off there is no backup file either, so
  quitting with `n` discards changes for good.
- Nothing locks the map file. Two editors on the same map means the last save
  wins.

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
