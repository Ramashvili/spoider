"""The map as a document: markdown, or plain text indented with tabs.

The saved JSON is already the document; these two functions decide only how a level looks
on a page. Nothing here knows about the screen, the palette or the typeface, which is why a
text export cannot come out looking wrong on another machine.

Markdown: the root is `#`, its children are `##`, and everything below them is a list with
a dash, one level of nesting per step down. Plain text: the same tree with no headings and
no dashes, one tab for every level, because the point of that format is that a person can
paste it anywhere and see the shape without counting spaces.

The cut stack follows the map, oldest cut first, the way the list holds it. Markdown gives
it a heading; plain text separates it with a blank line and nothing else, since a label
would be the heading that format does not have. Mermaid is the one written for a renderer
rather than a reader: one tree under one root, no stack, because a published mind map is
the map.
"""

from __future__ import annotations

import errno
import os
from collections.abc import Iterator
from pathlib import Path

from .files import write_atomic
from .formats import EXPORT_FORMATS, ExportError
from .model import MindMap, Node

#: One level in plain text.
TAB = "\t"

#: One nested list level in markdown. Two spaces, which CommonMark reads as a child list
#: at any depth; four also works and doubles the width of a deep map for nothing.
STEP = "  "

#: The heading the cut stack gets in markdown, at the same level as the map's own title: it
#: is a second part of the document, not another child of the map, and nothing follows it.
STACK_HEADING = "Cut stack"

#: The keyword Mermaid's mindmap parser wants on the line above the tree.
MINDMAP = "mindmap"

#: What ends a label the moment that parser meets it, because it opens or closes a shape.
SHAPE_CHARS = frozenset('()[]{}"')

#: What a label holds when the cell holds nothing: the parser refuses an empty one, and a
#: published map still has to draw the cell that is there.
EMPTY_LABEL = " "

#: Mermaid's own spelling of a quote inside a label.
QUOTED = "#quot;"


def _line(text: str) -> str:
    """A cell's text on one line, because a heading with a newline in it stops being one."""
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _label(node: Node) -> str:
    """A cell as the document shows it: its mark, a space, then its text.

    The same order the cell is drawn in, so a map read on paper says what it says on the
    screen. A mark with no text is the whole label, and an empty cell stays empty.
    """
    text = _line(node.text)
    mark = _line(node.mark or "")
    if not mark:
        return text
    return f"{mark} {text}".strip()


def _forest(nodes: list[Node]) -> Iterator[tuple[Node, int]]:
    """Every node under these, depth first, with its depth below the first level.

    Iterative on purpose: a map may be four hundred deep, and a recursive walk would end in
    a `RecursionError` instead of a file.
    """
    stack: list[tuple[Node, int]] = [(node, 0) for node in reversed(nodes)]
    while stack:
        node, depth = stack.pop()
        yield node, depth
        stack.extend((child, depth + 1) for child in reversed(node.children))


def _document(lines: list[str]) -> str:
    """The finished file: one blank line where a break was asked for, none at either end."""
    tidy: list[str] = []
    for line in lines:
        if not line and (not tidy or not tidy[-1]):
            continue
        tidy.append(line)
    while tidy and not tidy[-1]:
        tidy.pop()
    return "\n".join(tidy) + "\n"


def markdown(document: MindMap, *, with_stack: bool = True) -> str:
    """The map as markdown: a heading for the root and its children, lists below."""
    root = document.root
    lines = [f"# {_label(root)}".rstrip(), ""]
    for child in root.children:
        lines.append(f"## {_label(child)}".rstrip())
        lines.append("")
        lines.extend(
            f"{STEP * depth}- {_label(node)}".rstrip()
            for node, depth in _forest(child.children)
        )
        lines.append("")
    if with_stack and document.cut_stack:
        lines.append(f"# {STACK_HEADING}")
        lines.append("")
        lines.extend(
            f"{STEP * depth}- {_label(node)}".rstrip()
            for node, depth in _forest(document.cut_stack)
        )
    return _document(lines)


def plain(document: MindMap, *, with_stack: bool = True) -> str:
    """The same tree with no headings and no dashes, one tab per level."""
    lines = [
        f"{TAB * depth}{_label(node)}"
        for node, depth in _forest([document.root])
    ]
    if with_stack and document.cut_stack:
        lines.append("")
        lines.extend(
            f"{TAB * depth}{_label(node)}"
            for node, depth in _forest(document.cut_stack)
        )
    return _document(lines)


def _mermaid_label(node: Node) -> str:
    """A cell as one Mermaid label: its mark, a space, the text, lines broken by `<br/>`.

    Mermaid has no second line inside a label, so a paragraph becomes `<br/>` breaks; blank
    lines go, as they do in the other two documents.
    """
    text = "<br/>".join(part.strip() for part in (node.text or "").splitlines() if part.strip())
    mark = " ".join(part.strip() for part in (node.mark or "").splitlines() if part.strip())
    return f"{mark} {text}".strip() if mark else text


def _mermaid_node(node: Node, number: int) -> str:
    """A label as the parser takes it: bare when that is safe, shaped and quoted when not.

    A bare line is what a mind map should look like when its text is a sentence, but a
    bracket in it ends the line the moment the parser meets it. Quoting alone is not enough:
    the renderer takes `"a (label)"` as a parse error, and `n1["a (label)"]` as a cell. So
    those few carry an id that exists only to hold the quotes, and a square.
    """
    label = _mermaid_label(node)
    if label and not (SHAPE_CHARS & set(label)):
        return label
    return f'n{number}["{label.replace(chr(34), QUOTED) or EMPTY_LABEL}"]'


def mermaid(document: MindMap) -> str:
    """The map as a Mermaid mind map: one root, every cell, no cut stack."""
    # Mermaid's own layout draws the nodes of a wide map over one another; the tidy tree
    # keeps them apart, so every export asks for it. The map's colour mode rides along,
    # because Mermaid colours a branch at a time unless told otherwise.
    head = ["---", "config:", "  layout: tidy-tree"]
    if document.colours == "depth":
        head.extend(["  mindmap:", "    colorBy: depth"])
    head.append("---")
    # the root is always inside its circle, so it is always quoted; an empty one needs the
    # space too, since the parser refuses a label with nothing in it
    root = _mermaid_label(document.root).replace('"', QUOTED) or EMPTY_LABEL
    lines = [*head, MINDMAP, f'{STEP}root(("{root}"))']
    for number, (node, depth) in enumerate(_forest(document.root.children), start=1):
        lines.append(f"{STEP * (depth + 2)}{_mermaid_node(node, number)}")
    return _document(lines)


def export_document(
    path: Path,
    *,
    form: str,
    output: Path,
    overwrite: bool = False,
    with_stack: bool = True,
) -> tuple[Path, str]:
    """Read a map and write it as `form` (`markdown` or `text`), saying what it holds.

    The care the picture gets, for the same reasons: the folder has to exist, an existing
    file is not replaced unless asked by name, and the map is never written over by its own
    export. The write is atomic, so an interrupted export leaves the old file whole.
    """
    try:
        document = MindMap.load(path)
    except Exception as exc:  # MapFileError and anything else the reader raises
        raise ExportError(str(exc)) from None

    if form == "markdown":
        body = markdown(document, with_stack=with_stack)
    elif form == "text":
        body = plain(document, with_stack=with_stack)
    elif form == "mermaid":
        body = mermaid(document)
    else:
        raise ExportError(f"no such form: {form}; there is {', '.join(EXPORT_FORMATS)}")

    target = output.expanduser()
    if target.exists() and target.resolve() == Path(path).expanduser().resolve():
        raise ExportError(f"{target} is the map itself; choose another name")
    if not target.parent.is_dir():
        # the atomic writer would build the road; an export writes the file and no more
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), str(target))
    if target.exists() and not overwrite:
        raise ExportError(f"{target} already exists; use --force to allow replace")
    write_atomic(target, body)

    summary = f"{document.count()} cells"
    if form != "mermaid" and with_stack and document.cut_stack:
        summary += f", {len(document.cut_stack)} cuts"
    return target, summary
