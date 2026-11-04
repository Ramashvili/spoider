# Security

spoider runs on your machine and reads files you may have got from somewhere else, so it
treats them as untrusted.

## Reporting

For anything that could hurt someone, use GitHub's private report:
**Security → Advisories → Report a vulnerability** on
[Ramashvili/spoider](https://github.com/Ramashvili/spoider). Ordinary bugs belong in the
issue tracker.

Please say what you did, what happened, and what you expected, with the map or config that
triggers it if you can share it.

## What is in scope

- `.spoider` maps: cell text, marks, ids, the palette, the cursor, the cut stack.
- `spoider.conf`: keys and chords.
- The screen: text that reaches the terminal, including the file's own name.
- The files it writes: the map, the config, and the desktop entry it installs.

## What spoider already does

- Strips control characters from map and config text when reading and when drawing, so a
  file cannot send escape sequences to your terminal.
- Saves through a temporary file and a rename, so a failed write leaves the old file whole,
  and refuses to write over a file that is not a spoider map.
- Caps nesting, palette size and cell length.
- Creates the config once, then edits only the lines it owns.
- Has no network code and starts no shell.
- Installs the desktop entry and MIME type only after you answer yes.

## Versions

The latest release is supported. Older ones are not patched.
