## Known limits

- On a narrow terminal a wide map is clipped at the edges — the view always
  keeps the selected node centred and does not zoom out. Use a wider window, or
  fold branches you are not working on.
- No search, multi-select, or drag-to-reparent yet.
- Undo history lives in memory for the session (the file on disk is only the
  current state, and only after a `^O` write).
- There is no autosave and no backup file: quitting with `n` discards changes.
