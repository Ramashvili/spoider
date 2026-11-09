"""The map as a document: two shapes, a tree walked once, and the file checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from spoider.formats import ExportError
from spoider.model import MindMap, Node
from spoider.outline import export_document, markdown, plain


def _dish() -> MindMap:
    """A small map with two branches and a stack, the shape a person would read."""
    root = Node("Chilli")
    ingredients = Node("Ingredients")
    ingredients.children = [Node("beef"), Node("beans")]
    method = Node("Method")
    brown = Node("brown the beef")
    brown.children = [Node("in a wide pan")]
    method.children = [brown, Node("add the beans"), Node("simmer")]
    root.children = [ingredients, method]
    paprika = Node("paprika")
    paprika.children = [Node("smoked")]
    return MindMap(root, cut_stack=[paprika, Node("cumin")])


EXPECTED_MARKDOWN = """\
# Chilli

## Ingredients

- beef
- beans

## Method

- brown the beef
  - in a wide pan
- add the beans
- simmer

# Cut stack

- paprika
  - smoked
- cumin
"""

EXPECTED_PLAIN = """\
Chilli
\tIngredients
\t\tbeef
\t\tbeans
\tMethod
\t\tbrown the beef
\t\t\tin a wide pan
\t\tadd the beans
\t\tsimmer

paprika
\tsmoked
cumin
"""


def test_markdown_is_a_heading_for_two_levels_then_lists():
    assert markdown(_dish()) == EXPECTED_MARKDOWN


def test_plain_text_is_tabs_and_nothing_else():
    assert plain(_dish()) == EXPECTED_PLAIN


def test_the_stack_can_be_left_out():
    without = markdown(_dish(), with_stack=False)
    assert "Cut stack" not in without
    assert "paprika" not in without
    assert without.endswith("- simmer\n")
    assert "paprika" not in plain(_dish(), with_stack=False)


def test_a_deep_map_is_written_without_recursing():
    """A map may be four hundred deep; a recursive walk would end in a RecursionError."""
    root = Node("root")
    node = root
    for level in range(399):
        child = Node(f"level {level + 1}")
        node.children = [child]
        node = child

    document = MindMap(root)
    # one line per cell: the blank lines markdown puts around headings are not cells
    assert len(plain(document).splitlines()) == 400
    assert len([line for line in markdown(document).splitlines() if line]) == 400


def test_a_folded_branch_is_still_exported():
    """The file is the map, not the screen: collapsing a branch hides it, not loses it."""
    document = _dish()
    document.root.children[0].collapsed = True
    assert "- beef" in markdown(document)
    assert "\t\tbeef" in plain(document)


def test_an_empty_cell_keeps_its_place():
    root = Node("root")
    root.children = [Node("")]
    assert markdown(MindMap(root)) == "# root\n\n##\n"
    assert plain(MindMap(root)) == "root\n\t\n"


def test_a_cell_holding_several_lines_becomes_one():
    """A heading with a newline in it stops being a heading, so the line is flattened."""
    root = Node("root")
    child = Node("first line\nsecond line")
    child.children = [Node("below")]
    root.children = [child]
    assert "## first line second line" in markdown(MindMap(root))
    assert "\tfirst line second line" in plain(MindMap(root))


def test_the_stack_comes_after_the_map_oldest_first():
    text = plain(_dish())
    assert text.index("simmer") < text.index("paprika")
    assert text.index("paprika") < text.index("cumin")


def test_the_stack_section_starts_at_the_highest_heading_and_ends_the_file():
    """A second part of the document, not another child of the map."""
    text = markdown(_dish())
    assert text.index("# Cut stack") > text.index("## Method")
    assert text.count("# Cut stack") == 1
    assert text.rstrip().endswith("cumin"), "and nothing follows it"


# -- the file, and the command line ----------------------------------------


def _saved(tmp_path: Path) -> Path:
    path = tmp_path / "map.spoider"
    _dish().save(path)
    return path


def test_an_export_never_replaces_a_file_without_being_asked(tmp_path: Path):
    source = _saved(tmp_path)
    target = tmp_path / "out.md"
    target.write_text("something valuable", encoding="utf-8")

    with pytest.raises(ExportError, match="already exists"):
        export_document(source, form="markdown", output=target)
    assert target.read_text(encoding="utf-8") == "something valuable"

    export_document(source, form="markdown", output=target, overwrite=True)
    assert target.read_text(encoding="utf-8").startswith("# Chilli")


def test_the_map_is_never_written_over_by_its_own_export(tmp_path: Path):
    source = _saved(tmp_path)
    with pytest.raises(ExportError, match="is the map itself"):
        export_document(source, form="text", output=source, overwrite=True)
    assert source.exists(), "and the map is still there"


def test_a_missing_folder_is_not_built(tmp_path: Path):
    source = _saved(tmp_path)
    with pytest.raises(FileNotFoundError):
        export_document(source, form="text", output=tmp_path / "nope" / "out.txt")


def test_the_command_line_writes_markdown_and_text(tmp_path: Path, capsys):
    from spoider.app import main

    source = _saved(tmp_path)
    for form, name in (("markdown", "out.md"), ("text", "out.txt")):
        target = tmp_path / name
        with pytest.raises(SystemExit) as done:
            main([str(source), "--export", form, "-o", str(target)])
        assert done.value.code == 0
        assert target.exists()
        assert f"{target}" in capsys.readouterr().out


def test_a_document_refuses_a_palette_and_a_face(tmp_path: Path, capsys):
    """A heading has no colour and no typeface; naming one would only mislead."""
    from spoider.app import main

    source = _saved(tmp_path)
    for flag, value in (("--palette", "ink"), ("--font", "mono")):
        with pytest.raises(SystemExit) as done:
            main([str(source), "--export", "markdown", "-o", str(tmp_path / "x.md"), flag, value])
        assert done.value.code == 2
        assert "no --palette and no --font" in capsys.readouterr().err
