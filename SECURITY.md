# Security

spoider runs on your machine and reads files you may have got from somewhere else, so it
treats them as untrusted.

## Reporting

For anything that could hurt someone, use GitHub's private report:
**Security → Advisories → Report a vulnerability** on
[Ramashvili/spoider](https://github.com/Ramashvili/spoider). Ordinary bugs belong in the
issue tracker.

- Please say what you did, what happened, and what you expected.
- The map, config or file name that triggers it is worth more than any description, so
  attach one if you can share it.
- You will get an answer either way, and a fix goes into the next patch release.

## What is in scope

- **`.spoider` maps.** Cell text, marks, ids, the palette, the cursor and the cut stack.
- **`spoider.conf`.** Keys and chords, and the lines spoider writes there.
- **The screen.** Anything that reaches the terminal, including the name of the file you
  opened.
- **The files it writes.** The map itself, the config, and the desktop entry it installs.

## What spoider already does

- **Text from a file is cleaned as it is read.** A cell can hold the escape sequences that
  move a cursor, clear a screen or rename a window, so control characters are stripped
  before the text becomes part of a map. Names, marks and the properties box are cleaned
  again where they are drawn, because a directory listing is not a safer source than a
  file.
- **A file that could not be read is never written over.** If a map fails to load, spoider
  keeps no path for it, so `^S` and autosave have nowhere to go and the damaged file stays
  as it was for you to repair.
- **Writes are atomic, and they refuse a foreign target.** A map goes to a temporary file
  beside its target and is renamed into place, so an interrupted save leaves the old file
  whole. A write also refuses a file that is not a spoider map, which stops a mistyped name
  from becoming a way to bury something.
- **Sizes are bounded, and the bounds are reported.** A map deeper than 400 levels or a
  cell longer than 10 000 characters is refused with a message that says which, rather than
  truncated or half loaded. A paste that would run past the cell limit is cut short and
  tells you so. A mark palette longer than 64 entries is cut to its first 64.
- **The configuration belongs to you.** `spoider.conf` is written once, when there is none,
  and after that only the lines spoider owns are rewritten, so your comments and your
  ordering survive an upgrade. A line that names neither a setting nor a chord is dropped
  rather than guessed at.
- **Nothing leaves the machine, and nothing becomes a shell.** There is no networking code.
  spoider starts two kinds of process, each with an argument list rather than through a
  shell: your `$EDITOR` when you ask to edit the configuration, and the desktop cache tools
  when you accept the offer to register `.spoider` files.
- **Registering the file type is opt-in.** The MIME type and the desktop entry are
  installed only after you say yes, once, or when you run `spoider --install-desktop`
  yourself. The entry names the `spoider` that comes first on your PATH, which is the one a
  launcher could find without you.

## What it leaves in your hands

- A `.spoider` file is data, not a program: opening one cannot run what it contains.
- Two editors on the same map is a different matter, because there is no locking, and the
  last save wins.
- Saving through a symbolic link replaces the link with a regular file.
- Anything you open in `$EDITOR`, the configuration included, is your editor's business.
- A map wider than your terminal is clipped at the edges. That is a limit of the display
  rather than a risk, and it is worth knowing when a map arrives from a wider screen.

## Versions

The latest release is the supported one. Older versions are not patched, so a report is
most useful against the newest tag you can reproduce it on.
