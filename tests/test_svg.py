"""The map as an SVG: what it holds, what it refuses, and what it names."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from spoider.palettes import by_name, fonts, is_truetype
from spoider.svg import GAP, MARGIN, ExportError, compose, export_map, svg

SVG = {"s": "http://www.w3.org/2000/svg"}
MANUAL = Path(__file__).parent.parent / "src/spoider/data/manual.spoider"


def palette(name: str = "paper"):
    found = by_name(name)
    assert found is not None
    return found


def a_font():
    face = next((font for font in fonts() if font.available and is_truetype(str(font.path))), None)
    assert face is not None, "the tests need one monospace face on this machine"
    return face


@pytest.fixture
def manual():
    from spoider.model import MindMap

    return MindMap.load(MANUAL)


def sheet_of(document, with_stack: bool = True, palette_name: str = "paper"):
    return compose(
        document=document, palette=palette(palette_name), font=a_font(), with_stack=with_stack
    )


def test_every_cell_lands_inside_the_canvas(manual):
    """A layout may put a left branch at negative coordinates; the picture must not clip it."""
    for shape in ("spider", "branch", "branch_left", "pyramid", "bush"):
        manual.layout = shape
        sheet = sheet_of(manual)
        xs = [x for x, _y in sheet.grid.cells]
        ys = [y for _x, y in sheet.grid.cells]
        assert min(xs) == MARGIN and min(ys) == MARGIN, shape
        assert max(xs) < sheet.width and max(ys) < sheet.height, shape


def test_the_caption_counts_cells_and_cuts(manual):
    assert sheet_of(manual).caption == f"{manual.count()} cells"
    cut = next(node for node in manual.nodes() if node is not manual.root)
    manual.cut_stack.append(cut)
    with_stack = sheet_of(manual)
    assert with_stack.caption.endswith("1 cut"), "one cut, not one cuts"


def test_the_stack_column_sits_beside_the_map_and_can_be_left_out(manual):
    cut = next(node for node in manual.nodes() if node is not manual.root)
    manual.cut_stack.append(cut)
    alone = sheet_of(manual, with_stack=False)
    together = sheet_of(manual)
    assert together.width > alone.width + GAP, "the column takes room to the right"
    assert "cut" not in alone.caption


def test_the_picture_is_the_maps_colour_mode(manual):
    family = sheet_of(manual)
    manual.colours = "depth"
    assert svg(family) != svg(sheet_of(manual))


def test_the_svg_is_well_formed_and_keeps_awkward_text(manual):
    manual.root.text = "cells <with> & signs"
    tree = ET.fromstring(svg(sheet_of(manual)))
    written = "".join(text.text or "" for text in tree.findall(".//s:text", SVG))
    assert "<with>" in written and "& signs" in written


def test_every_run_carries_its_cell_span(manual):
    """A face whose advance is not 0.6 em still lands on the grid."""
    text = svg(sheet_of(manual))
    assert 'lengthAdjust="spacing"' in text
    assert text.count("textLength=") == text.count("<text ")


def test_the_face_travels_inside_the_file(manual):
    text = svg(sheet_of(manual))
    assert "@font-face" in text and "base64," in text, "a named face can be substituted"
    assert "Spoider Export," in text


def test_a_palette_decides_the_colours(manual):
    white = svg(sheet_of(manual, palette_name="paper"))
    black = svg(sheet_of(manual, palette_name="ink"))
    assert palette("paper").background in white
    assert palette("ink").background in black
    assert white != black


def test_export_map_writes_the_file_and_says_what_it_holds(tmp_path: Path):
    target = tmp_path / "picture.svg"
    written, sheet = export_map(MANUAL, output=target, palette_name="coloured-paper")
    assert written == target and target.read_text(encoding="utf-8").startswith("<?xml")
    assert sheet.caption.endswith("cells")


def test_a_palette_or_face_that_is_not_there_is_an_error(tmp_path: Path):
    with pytest.raises(ExportError) as bad_palette:
        export_map(MANUAL, output=tmp_path / "x.svg", palette_name="purple")
    assert "no palette called purple" in str(bad_palette.value)
    with pytest.raises(ExportError) as bad_font:
        export_map(MANUAL, output=tmp_path / "x.svg", font_name="no-such-face")
    assert "no typeface called no-such-face" in str(bad_font.value)


def test_the_folder_has_to_exist(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        export_map(MANUAL, output=tmp_path / "missing" / "x.svg")
    assert not (tmp_path / "missing").exists(), "nothing was created to put it in"


def test_only_truetype_travels(tmp_path: Path):
    """A CFF face embeds, loads, and then draws nothing: refused rather than hoped for."""
    assert is_truetype(str(MANUAL)) is False, "a map file is not a font"
    offered = [face for face in fonts() if face.available and is_truetype(str(face.path))]
    assert offered, "this machine has a TrueType monospace to draw with"

    cff = next(
        (face for face in fonts() if face.available and not is_truetype(str(face.path))), None
    )
    if cff is None:
        pytest.skip("this machine has no CFF face to refuse")
    with pytest.raises(ExportError) as refused:
        export_map(MANUAL, output=tmp_path / "x.svg", font_name=cff.label)
    assert "not a TrueType face" in str(refused.value)
    assert not (tmp_path / "x.svg").exists(), "and nothing is written"


def test_the_picture_takes_the_faces_own_metrics():
    """A cell is as wide as the glyphs and as tall as the lines, so nothing has to be stretched."""
    from spoider.palettes import metrics

    assert metrics(str(MANUAL)) == (0.6, 1.4), "an unreadable file falls back, it does not raise"
    face = a_font()
    advance, line = metrics(str(face.path))
    assert 0.4 < advance < 1.2, (face.label, advance)
    assert 0.9 < line < 2.2, (face.label, line)


def test_the_canvas_is_the_cells_times_the_faces_own_metrics(manual):
    """The one place the metrics are used: page size. If this drifts, the grid drifts."""
    from spoider.palettes import metrics
    from spoider.svg import FONT_SIZE

    sheet = sheet_of(manual)
    advance, line = metrics(str(sheet.font.path))
    text = svg(sheet)
    assert f'width="{sheet.width * FONT_SIZE * advance:.2f}"' in text
    assert f'height="{sheet.height * FONT_SIZE * line:.2f}"' in text


def test_a_run_is_measured_in_cells_not_characters():
    """An emoji is one character and two cells: counting characters came up a cell short."""
    from spoider.model import MindMap
    from spoider.text import cell_len

    document = MindMap()
    document.root.text = "x ⭐ y"
    document.root.mark = "⭐"
    text = svg(sheet_of(document))
    runs = re.findall(r'<text x="[0-9.]+"[^>]*textLength="([0-9.]+)"[^>]*>([^<]*)</text>', text)
    for width, run in runs:
        assert abs(float(width) / (12.0 * 0.6) - sum(cell_len(ch) for ch in run)) < 1e-6, run
    assert any("⭐" in run for _width, run in runs), "the star is drawn"
