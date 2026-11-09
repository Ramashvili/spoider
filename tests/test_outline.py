"""The map as a document: two shapes, a tree walked once, and the file checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from spoider.formats import ExportError
from spoider.model import MindMap, Node
from spoider.outline import export_document, markdown, mermaid, plain


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


def test_an_empty_cell_leaves_a_bare_marker():
    """A document has no placeholder: an empty cell is a heading with nothing after it."""
    mm = MindMap()
    mm.root.text = ""
    mm.add_child(mm.root.id, "")

    text = markdown(mm)

    assert text.splitlines()[0] == "#", "the root's heading, with no text"
    assert "##" in text.splitlines()


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


def test_a_mark_is_printed_before_the_text_of_its_cell():
    """The order the cell is drawn in, so the document says what the screen says."""
    document = _dish()
    document.root.mark = "⭐"
    document.root.children[0].mark = "✅"

    text = markdown(document)
    assert "# ⭐ Chilli" in text
    assert "## ✅ Ingredients" in text
    assert "⭐ Chilli" in plain(document)
    assert "\t✅ Ingredients" in plain(document)


def test_a_mark_with_no_text_is_the_whole_cell():
    branch = Node("items")
    branch.children = [Node("", mark="!")]
    root = Node("root")
    root.children = [branch]
    assert "- !" in markdown(MindMap(root)), "a list item that is only a mark"
    assert "\t\t!" in plain(MindMap(root))


def test_an_unmarked_cell_is_just_its_text():
    assert "## Ingredients" in markdown(_dish())


def test_mermaid_is_a_mindmap_with_two_spaces_per_level():
    """The renderer's own shape: a keyword, a root in a circle, then the tree."""
    text = mermaid(_dish())

    assert text.startswith("mindmap\n")
    assert '  root(("Chilli"))' in text
    assert "    Ingredients\n      beef\n      beans" in text
    assert "    Method\n      brown the beef\n        in a wide pan" in text


def test_mermaid_leaves_the_stack_out():
    """A published mind map is the map: the cuts are a working list, not a branch."""
    text = mermaid(_dish())

    assert "paprika" not in text
    assert "cumin" not in text
    assert text.count("mindmap") == 1


def test_mermaid_carries_the_colour_mode_it_was_saved_with():
    depth = _dish()
    depth.colours = "depth"
    assert mermaid(depth).startswith("---\nconfig:\n  mindmap:\n    colorBy: depth\n---\n")

    family = _dish()
    family.colours = "family"
    assert not mermaid(family).startswith("---"), "the default needs no block"


def test_mermaid_breaks_lines_with_br():
    map_ = MindMap(Node("two\nlines\n\nand a blank one"))
    text = mermaid(map_)

    assert 'root(("two<br/>lines<br/>and a blank one"))' in text


def test_mermaid_quotes_a_label_that_would_end_the_line():
    """`(` opens a shape, so a cell holding one is quoted and given an id to hold them."""
    root = Node("the root")
    root.children = [Node("a plain sentence"), Node("has (brackets) and [some]"), Node('a "quote"')]
    text = mermaid(MindMap(root))

    lines = text.splitlines()
    assert "    a plain sentence" in lines, "safe text stays bare"
    assert '    n2["has (brackets) and [some]"]' in lines
    assert '    n3["a #quot;quote#quot;"]' in lines


def test_mermaid_gives_an_empty_cell_something_to_draw():
    """The parser refuses a label with nothing in it, so an empty cell holds a space."""
    root = Node("root")
    root.children = [Node("")]
    text = mermaid(MindMap(root))

    assert '    n1[" "]' in text


def test_mermaid_keeps_a_mark_before_its_text():
    root = Node("root")
    marked = Node("idea")
    marked.mark = "⭐"
    root.children = [marked]

    assert "    ⭐ idea" in mermaid(MindMap(root))


def test_mermaid_is_a_document_format_on_the_command_line(tmp_path: Path):
    """`--export mermaid` writes the file and says what it holds, with no stack count."""
    source = tmp_path / "map.spoider"
    _dish().save(source)
    target = tmp_path / "map.mmd"

    written, caption = export_document(source, form="mermaid", output=target)

    assert written == target
    assert caption == "9 cells", "no cuts mentioned: the format does not write them"
    assert target.read_text(encoding="utf-8").startswith("mindmap")


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
