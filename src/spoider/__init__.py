"""spoider — a TUI mind map editor."""

from importlib.metadata import version

#: Read from the installed package metadata, so `pyproject.toml` is the only place a
#: version is written. Running from a source tree still works because `uv run` installs
#: the project into its environment first.
__version__ = version("spoider")
