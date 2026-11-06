"""Colours for an export, and the typefaces it can carry.

The editor has no palette: every style it draws is an ANSI name, resolved by whichever terminal
is looking. A file has no terminal, so an export chooses, and this is where the choosing
happens. Four palettes ship, complete in themselves.
"""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

#: The ANSI order: the eight ordinary colours, then the eight bright ones.
ANSI_NAMES = (
    "black", "red", "green", "yellow", "blue", "magenta", "cyan", "white",
    "bright_black", "bright_red", "bright_green", "bright_yellow",
    "bright_blue", "bright_magenta", "bright_cyan", "bright_white",
)

_VIVID = (
    "#1c1c1c", "#c0392b", "#1f8a4c", "#a97b00", "#2a5fd0", "#8e44ad", "#0e7c86", "#8a8a8a",
    "#5c5c5c", "#e05a4b", "#2fae63", "#c99700", "#4a7ef0", "#a868cd", "#17a2ad", "#d0d0d0",
)

_INK_ON_PAPER = (
    "#000000", "#9b1c1c", "#12662f", "#7a5600", "#1b3fa0", "#6b1e8a", "#0a5b63", "#555555",
    "#3a3a3a", "#c02a2a", "#1a8442", "#9c7000", "#2a55c0", "#8a35a8", "#0e7480", "#777777",
)

_GREYS_ON_PAPER = (
    "#000000", "#222222", "#1b1b1b", "#2a2a2a", "#151515", "#262626", "#1f1f1f", "#333333",
    "#555555", "#3a3a3a", "#444444", "#4e4e4e", "#303030", "#474747", "#404040", "#666666",
)

_GREYS_ON_INK = (
    "#f2f2f2", "#d8d8d8", "#e0e0e0", "#cfcfcf", "#e8e8e8", "#d2d2d2", "#dcdcdc", "#b8b8b8",
    "#9a9a9a", "#c4c4c4", "#b0b0b0", "#a6a6a6", "#cccccc", "#aeaeae", "#b6b6b6", "#8e8e8e",
)


@dataclass(frozen=True)
class Palette:
    """Sixteen colours, a background, and a default foreground."""

    name: str
    label: str
    background: str
    foreground: str
    ansi: tuple[str, ...] = field(default_factory=lambda: _VIVID)

    def colour(self, name: str) -> str | None:
        """The hex a style name means, or None for the palette's own foreground."""
        if name in ANSI_NAMES:
            return self.ansi[ANSI_NAMES.index(name)]
        return None


PALETTES: tuple[Palette, ...] = (
    Palette("paper", "black on white", "#ffffff", "#111111", _GREYS_ON_PAPER),
    Palette("coloured-paper", "coloured on white", "#ffffff", "#111111", _INK_ON_PAPER),
    Palette("coloured-ink", "coloured on black", "#101014", "#e6e6e6", _VIVID),
    Palette("ink", "white on black", "#000000", "#f2f2f2", _GREYS_ON_INK),
)


def by_name(name: str) -> Palette | None:
    return next((palette for palette in PALETTES if palette.name == name), None)


@dataclass(frozen=True)
class Ink:
    """What one cell is drawn with: a foreground, a background, and two attributes."""

    foreground: str
    background: str
    reverse: bool = False
    underline: bool = False

    def resolved(self) -> tuple[str, str]:
        """(text colour, fill colour), with `reverse` already applied."""
        return (self.background, self.foreground) if self.reverse else (self.foreground, self.background)


def ink(palette: Palette, style: str | None) -> Ink:
    """The colours a grid style means in this palette.

    Grid styles are what the renderer wrote: an ANSI name, `None` for the terminal's own
    foreground, and the words `reverse` and `underline`.
    """
    words = (style or "").split()
    foreground = palette.foreground
    for word in words:
        colour = palette.colour(word)
        if colour is not None:
            foreground = colour
    return Ink(
        foreground=foreground,
        background=palette.background,
        reverse="reverse" in words,
        underline="underline" in words,
    )


# -- typefaces --------------------------------------------------------------


@dataclass(frozen=True)
class Font:
    """A typeface an export can carry: a family name, and the file behind it."""

    name: str
    label: str
    path: Path | None
    family: str = ""

    @property
    def available(self) -> bool:
        return self.path is not None and self.path.exists()

    @property
    def families(self) -> str:
        """What a `font-family` should say: this face's families, then a generic monospace.

        The generic comes last so a machine without the face still gets a monospace rather
        than the default sans, which would pull every cell off the grid it was drawn on.
        """
        names = [part.strip() for part in self.family.split(",") if part.strip()]
        return ", ".join([*names, "monospace"]) if names else "monospace"


def _fontconfig(*args: str) -> list[tuple[str, str]]:
    """(family, file) for each answer from fontconfig, or nothing when it cannot be asked."""
    try:
        done = subprocess.run(
            ["fc-list" if args[0] == "list" else "fc-match", "-f", "%{family}\t%{file}\n", *args[1:]],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    answers = []
    for line in done.stdout.splitlines():
        family, _, file = line.partition("\t")
        if file.strip():
            answers.append((family.strip(), file.strip()))
    return answers


@lru_cache(maxsize=1)
def fonts() -> tuple[Font, ...]:
    """Every monospace family this machine has, one face each, in alphabetical order.

    Asking fontconfig what is installed beats naming a favourite and calling the rest "the
    system": the machine the export runs on is the one that knows which faces are there.
    """
    chosen: dict[str, tuple[int, Font]] = {}
    for family_field, file in _fontconfig("list", ":spacing=mono"):
        family = family_field.split(",")[0].strip()
        path = Path(file)
        if not family or not path.exists():
            continue
        styling = path.name.casefold()
        rank = 0 if "regular" in styling or not any(
            word in styling for word in ("bold", "italic", "light", "medium", "thin", "black")
        ) else 1
        if family not in chosen or rank < chosen[family][0]:
            chosen[family] = (
                rank,
                Font(family.casefold().replace(" ", "-"), family, path, family_field),
            )
    return tuple(sorted((font for _rank, font in chosen.values()), key=lambda f: f.label.casefold()))


def font_by_name(name: str) -> Font | None:
    """A face by its slug (`liberation-mono`) or by the family as fontconfig spells it."""
    wanted = name.strip().casefold()
    return next((font for font in fonts() if wanted in (font.name, font.label.casefold())), None)


#: Table tags that hold outlines, and the ones that say the glyphs are pictures instead.
OUTLINE_TABLES = {b"glyf", b"CFF ", b"CFF2"}
BITMAP_TABLES = {b"CBDT", b"EBDT", b"sbix"}


def tables(path: str) -> set[bytes]:
    """The four-byte tags in a font file's table directory, which is all of it we need.

    A dozen bytes of header, then sixteen per table. Searched properly rather than by looking
    for the letters: `CFF ` appears inside the data of a file that has no CFF table at all,
    which is how a bitmap face came to be called scalable.
    """
    try:
        with Path(path).open("rb") as handle:
            header = handle.read(12)
            if len(header) < 12:
                return set()
            count = int.from_bytes(header[4:6], "big")
            directory = handle.read(count * 16)
    except OSError:
        return set()
    return {
        directory[at : at + 4]
        for at in range(0, len(directory) - 3, 16)
        if directory[at : at + 4].strip()
    }


def has_outlines(path: str) -> bool:
    """Whether a font file carries outlines, which is the only kind a viewer can scale.

    A bitmap face (Spleen's sizes, for instance) has no outlines to draw at twelve points, and
    a viewer told to use one draws nothing at all.
    """
    found = tables(path)
    if found & BITMAP_TABLES and not found & OUTLINE_TABLES:
        return False
    return bool(found & OUTLINE_TABLES)


@lru_cache(maxsize=8)
def embedded(path: str) -> tuple[str, str]:
    """(media type, base64) for a font file, as small as this machine can make it.

    A named font is a suggestion: viewers without it substitute one, which is how an export
    came to be drawn in a face nobody chose. Carrying the face inside the file removes the
    question. woff2 when the tools are here, the font itself otherwise.
    """
    source = Path(path)
    if shutil.which("woff2_compress"):
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / source.name
            shutil.copyfile(source, copy)
            done = subprocess.run(
                ["woff2_compress", str(copy)], capture_output=True, check=False, timeout=60
            )
            packed = copy.with_suffix(".woff2")
            if done.returncode == 0 and packed.exists():
                return "font/woff2", base64.b64encode(packed.read_bytes()).decode("ascii")
    media = "font/otf" if source.suffix.lower() == ".otf" else "font/ttf"
    return media, base64.b64encode(source.read_bytes()).decode("ascii")
