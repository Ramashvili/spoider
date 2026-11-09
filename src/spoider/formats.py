"""What `--export` can name, and what a format is allowed to need.

One tuple, because the command line, the help text and the dispatch all have to agree:
a writer that exists in a module but not in the tuple is a feature nobody can reach, and
a name in the tuple with no branch behind it is a promise that fails at run time.
"""

from __future__ import annotations

#: The formats the command line offers.
EXPORT_FORMATS: tuple[str, ...] = ("svg", "markdown", "text", "mermaid")

#: A document rather than a drawing: no palette, no typeface, nothing to embed.
TEXT_FORMATS: frozenset[str] = frozenset({"markdown", "text", "mermaid"})


class ExportError(Exception):
    """Something about this export cannot be done, said in words a person can act on."""
