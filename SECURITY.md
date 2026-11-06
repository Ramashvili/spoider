# Security

spoider is a small editor that runs where your files are. It opens maps you may have been
sent, reads a configuration file you may not have written, and draws whatever those files
say onto your terminal. That is the whole surface, and it is what this document is about: a
map or a config should be free to be strange, broken or deliberately malicious without
being able to reach past the screen.

## Reporting a problem

If you have found something that could harm a person's machine or their work, please use
GitHub's private channel rather than the issue tracker:
**Security → Advisories → Report a vulnerability** on
[Ramashvili/spoider](https://github.com/Ramashvili/spoider).

Say what you did, what happened, and what you expected instead. A map, a config or a file
name that triggers it is worth more than any description, so attach one if you can share
it. You will get an answer either way, and if a fix is what it needs, the fix goes into the
next patch release.

## What spoider does about it

**Text is cleaned twice: once when it is read, and again when it is drawn.** A cell can
hold anything at all, including the escape sequences that move a cursor, clear a screen or
rename a window. spoider strips control characters as it loads a map and again as it paints
one, and it treats a file's own name the same way, because a directory listing is not a
safer source than a file. What you see in a cell is the text that is in the cell, and
nothing a map contains can drive your terminal.

**A file that could not be read is never written over.** If a map fails to load, spoider
keeps no path for it, so `^S` and autosave have nowhere to go and a damaged file stays
exactly as it was for you to repair. The same care applies on the way out: a write refuses
a target that is not a spoider map, which is what stops a mistyped name from becoming a way
to bury a file.

**Writes are atomic.** A map is written to a temporary file beside its target and renamed
into place, so an interrupted save leaves the old file whole rather than half of a new one.

**Sizes are bounded.** Nesting stops at 400 levels, a cell at 10 000 characters and the
mark palette at 64 entries. A file cannot ask for more memory than an editor needs to stay
responsive, and a load that had to refuse something says so instead of failing quietly.

**The configuration belongs to you.** `spoider.conf` is written once, when there is none,
and from then on only the lines spoider owns are rewritten, so your comments and your
ordering survive an upgrade. A line that names neither a setting nor a chord is dropped
rather than guessed at, which is what keeps a leftover from quietly rebinding a key.

**Nothing leaves the machine, and nothing becomes a shell.** spoider contains no networking
code at all. It starts two kinds of process, each with an argument list rather than through
a shell: your `$EDITOR`, when you ask to edit the configuration, and the desktop cache
tools, when you accept the offer to register `.spoider` files. Neither is ever chosen by
something inside a map.

**Registering the file type is opt-in.** The MIME type and the desktop entry are installed
only after you say yes, once, and the entry names the binary that is actually running, so a
launcher does not depend on what happens to be on your PATH that day.

## What it leaves in your hands

- A `.spoider` file is data, not a program: opening one cannot run anything it contains.
  Two editors on the same map is a different matter, since there is no locking, and the
  last save wins.
- Saving through a symbolic link replaces the link with a regular file.
- Anything you open in `$EDITOR`, the configuration included, is your editor's business.
- A map wider than your terminal is clipped at the edges. That is a limit of the display
  rather than a risk, and it is worth knowing when a map arrives from a wider screen.

## Versions

The latest release is the supported one. Older versions are not patched, so a report is
most useful against the newest tag you can reproduce it on.
