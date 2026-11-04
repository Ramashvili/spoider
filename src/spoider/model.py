"""Document model: a tree of idea nodes, plus load/save."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .files import write_atomic
from .text import clean, clean_text

DEFAULT_ROOT_TEXT = "Mind map"

#: The marks a map cycles through, in press order, before anyone changes them. A
#: map carries its own list; `marks_default` in the config is what a new one starts
#: from. "None" always comes first in the cycle, so a press can end it.
MARKS = ('⭐', '💡', '❓', '⚠️', '✅', '📌', '⌛', '🤡')

#: A guard against a runaway list, not a design limit: nobody cycles sixty-four
#: marks. A mark may be more than one character, so the cap counts items.
MAX_MARKS = 64

#: The demo's own vocabulary: it is teaching, so its marks say what to do with a
#: cell rather than what state it is in.
DEMO_MARKS = ("👀", "🧪", "🎯", "🚀", "💡")


def marks_of(tokens: Iterable[object]) -> tuple[str, ...]:
    """A palette from whatever was typed or read: cleaned, capped, never empty."""
    cleaned = tuple(
        seen for token in tokens if (seen := clean(token).strip()[:MAX_MARK_CHARS])
    )
    return cleaned[:MAX_MARKS] or MARKS

#: A map nested deeper than this is either a mistake or an attack: the loader is
#: recursive, so an unbounded document would exhaust the stack (RecursionError).
MAX_DEPTH = 400

#: A cell holds prose, not a novel. The renderer spends about three screen cells per
#: character, so this is the difference between a large map and a gigabyte of memory.
MAX_CELL_CHARS = 10_000

#: A mark is one glyph, so this is generous; it stops a palette entry being a paragraph.
MAX_MARK_CHARS = 16

#: The shapes a map can be drawn in. The name is stored in the file, like the
#: spacing, so a map opens looking the way it was left.
LAYOUTS = ("spider", "pyramid", "bush", "branch")
DEFAULT_LAYOUT = "spider"
#: `depth`: one colour per level. `family`: one colour per branch under the root.
COLOURS = ("depth", "family")
DEFAULT_COLOURS = "family"


class MapFileError(Exception):
    """A map file that cannot be read: bad JSON, wrong shape, or far too deep."""


def new_id() -> str:
    """A node id. Twelve hex characters: short enough to read, long enough that
    a document with a few thousand cells will not collide."""
    return uuid.uuid4().hex[:12]


@dataclass
class Node:
    text: str = DEFAULT_ROOT_TEXT
    id: str = field(default_factory=new_id)
    collapsed: bool = False
    children: list[Node] = field(default_factory=list)
    mark: str | None = None
    # Live inline-edit buffer. Rendering reads it when set; never serialised.
    preview: str | None = field(default=None, compare=False, repr=False)
    # Live inline-edit caret: an index into `preview`. It does not take a column —
    # the renderer hangs it over the character it is on. Never serialised.
    caret: int | None = field(default=None, compare=False, repr=False)
    #: Overwrite mode while renaming: the caret underlines itself so the two modes
    #: are told apart on screen. Editor state, never serialised.
    overwrite: bool = field(default=False, compare=False, repr=False)
    #: Selected span of `preview`, as (start, end) indices, while renaming. Drawn as
    #: reverse video inside the cell. Editor state, never serialised.
    sel: tuple[int, int] | None = field(default=None, compare=False, repr=False)

    def walk(self) -> Iterator[Node]:
        """Depth-first, without recursion: a deep map must not blow the stack."""
        stack: list[Node] = [self]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(reversed(node.children))

    def clone(self) -> Node:
        """A detached copy carrying ids of its own.

        Pasting the same cell twice must not put two nodes with the same id in
        one map, so a copy is a copy all the way down.
        """
        copy = Node(text=self.text, collapsed=self.collapsed, mark=self.mark)
        copy.children = [child.clone() for child in self.children]
        return copy

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "collapsed": self.collapsed,
            "mark": self.mark,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        """Build a tree from parsed JSON.

        Tolerant of a hand-edited file: a node that is not a mapping, a missing
        or duplicated id, a `mark` that is not a string, and `children` that is
        not a list are all repaired rather than raised. Text is cleaned of
        control characters here, at the door, because it is untrusted input.
        """
        root = cls._build(data, 0)
        assert root is not None
        return root

    @classmethod
    def _build(cls, data: object, depth: int, seen: set[str] | None = None) -> Node | None:
        seen = set() if seen is None else seen
        if not isinstance(data, dict):
            return None
        if depth >= MAX_DEPTH:  # depth 0 is the root, so this caps the chain at MAX_DEPTH
            raise MapFileError(f"the map is nested more than {MAX_DEPTH} levels deep")

        node_id = clean(data.get("id") or "")
        if not node_id or node_id in seen:
            node_id = new_id()
        seen.add(node_id)

        raw_text = data.get("text")
        raw_mark = data.get("mark")
        text = clean_text("" if raw_text is None else raw_text)
        if len(text) > MAX_CELL_CHARS:
            raise MapFileError(
                f"a cell holds more than {MAX_CELL_CHARS} characters"
            )
        node = cls(
            text=text,
            id=node_id,
            collapsed=bool(data.get("collapsed", False)),
            mark=(clean(raw_mark)[:MAX_MARK_CHARS] or None)
            if isinstance(raw_mark, str)
            else None,
        )
        children = data.get("children")
        if isinstance(children, list):
            for child in children:
                built = cls._build(child, depth + 1, seen)
                if built is not None:
                    node.children.append(built)
        return node


class MindMap:
    """The whole document. Mutations are by node id so the UI can stay stateless."""

    def __init__(
        self,
        root: Node | None = None,
        spacing: int = 0,
        layout: str = DEFAULT_LAYOUT,
        cut_stack: list[Node] | None = None,
        colours: str = DEFAULT_COLOURS,
        justify: int | None = None,
        marks: Sequence[str] | None = None,
    ) -> None:
        self.root = root if root is not None else Node(clean_text(DEFAULT_ROOT_TEXT))
        #: The width this map was last justified to, or None before the first
        #: justify. Document state: the same file reflows the same way wherever it
        #: is opened, and the config only offers a default to start from.
        self.justify = justify
        #: The marks m cycles through, in order. Document state: two maps can have
        #: different vocabularies, and a map keeps its own wherever it is opened.
        self.marks = marks_of(marks) if marks is not None else MARKS
        #: How the cells are coloured: `depth` gives every level one colour, `family`
        #: gives every branch under the root one colour for its whole subtree.
        self.colours = colours if colours in COLOURS else DEFAULT_COLOURS
        #: The stack cuts go on: a cell cut out of the map is kept here, last in
        #: first out, and any of them can be pasted back under whatever cell is
        #: selected — anywhere in the map, not only where it came from. Document
        #: state, written into the file, so a map carries the scraps you took from
        #: it and closing the editor does not lose a cut.
        self.cut_stack: list[Node] = list(cut_stack or [])
        #: Where the cursor was when this map was last written: a cell id, which may
        #: name a cell in the map or one waiting on the cut stack. Document state,
        #: because opening a file should put you back where you left it.
        self.cursor: str | None = None
        # Presentation that belongs to the document: a map with 40 cells wants a
        # different amount of air than one with 4, and it should look the same
        # wherever it is opened.
        self.spacing = spacing
        self._layout = DEFAULT_LAYOUT
        self.layout = layout
        # Lookups by id, so a keystroke does not walk the tree. `_reindex` is
        # also the repair path: `find`/`parent` rebuild when they miss, which
        # covers any caller that appends to `node.children` behind our back.
        self._by_id: dict[str, Node] = {}
        self._parent_of: dict[str, Node] = {}
        self._reindex()

    def _reindex(self) -> None:
        self._by_id.clear()
        self._parent_of.clear()
        for node in self.root.walk():
            self._by_id[node.id] = node
            self._parent_of.update({child.id: node for child in node.children})

    @property
    def layout(self) -> str:
        """How the map is drawn; one of LAYOUTS."""
        return self._layout

    @layout.setter
    def layout(self, value: str) -> None:
        self._layout = value if value in LAYOUTS else DEFAULT_LAYOUT

    # -- lookup ---------------------------------------------------------

    def nodes(self) -> list[Node]:
        return list(self.root.walk())

    def find(self, node_id: str) -> Node | None:
        node = self._by_id.get(node_id)
        if node is None:
            self._reindex()
            node = self._by_id.get(node_id)
        return node

    def parent(self, node_id: str) -> Node | None:
        parent = self._parent_of.get(node_id)
        if parent is None:
            self._reindex()
            parent = self._parent_of.get(node_id)
        return parent

    def visible(self) -> list[Node]:
        out: list[Node] = []
        stack = [self.root]
        while stack:
            node = stack.pop()
            out.append(node)
            if not node.collapsed:
                stack.extend(reversed(node.children))
        return out

    def depth(self, node_id: str) -> int:
        depth = 0
        current = self.parent(node_id)
        while current is not None:
            depth += 1
            current = self.parent(current.id)
        return depth

    def path(self, node_id: str) -> list[Node]:
        """Root-first chain of ancestors ending at the node itself."""
        node = self.find(node_id)
        if node is None:
            return []
        chain = [node]
        current = self.parent(node_id)
        while current is not None:
            chain.append(current)
            current = self.parent(current.id)
        return list(reversed(chain))

    def count(self) -> int:
        return len(self._by_id)

    # -- mutation -------------------------------------------------------

    def add_child(self, parent_id: str, text: str = "") -> Node:
        parent = self.find(parent_id) or self.root
        node = Node(text=clean_text(text))
        parent.children.append(node)
        parent.collapsed = False
        self._by_id[node.id] = node
        self._parent_of[node.id] = parent
        return node

    def add_sibling(self, node_id: str, text: str = "") -> Node | None:
        parent = self.parent(node_id)
        if parent is None:
            return None
        node = Node(text=clean_text(text))
        index = self._index(parent, node_id)
        parent.children.insert(index + 1, node)
        self._by_id[node.id] = node
        self._parent_of[node.id] = parent
        return node

    def push_cut(self, cells: Sequence[Node]) -> None:
        """Put cells on the stack, last in first out.

        A run is pushed newest-first so it pastes back in document order: the
        first cell cut is the first one a ^U brings back.
        """
        self.cut_stack.extend(reversed(list(cells)))

    def pop_cut(self) -> Node | None:
        """Take the most recent cut off the stack — this is the LIFO end of it —
        or None when it is empty."""
        return self.cut_stack.pop() if self.cut_stack else None

    def paste(self, parent_id: str, node: Node) -> Node | None:
        """Append a copy of `node` under `parent_id`. The original is untouched,
        so the same cut can be pasted again and again."""
        parent = self.find(parent_id)
        if parent is None:
            return None
        copy = node.clone()
        parent.children.append(copy)
        parent.collapsed = False  # a pasted branch you cannot see is a bad surprise
        self._reindex()
        return copy

    def delete(self, node_id: str) -> tuple[Node, str] | None:
        """Remove a node and its subtree. Returns (removed, next selection)."""
        parent = self.parent(node_id)
        if parent is None:
            return None
        index = self._index(parent, node_id)
        removed = parent.children.pop(index)
        for node in removed.walk():
            self._by_id.pop(node.id, None)
            self._parent_of.pop(node.id, None)
        if index < len(parent.children):
            successor = parent.children[index]
        elif index > 0:
            successor = parent.children[index - 1]
        else:
            successor = parent
        return removed, successor.id

    def next_mark(self, node_id: str, marks: Sequence[str] = MARKS) -> str | None:
        """What the cycle would move this cell to, without moving it — so a run of
        cells can all be given the same next mark."""
        node = self.find(node_id)
        cycle: tuple[str | None, ...] = (None, *marks)
        try:
            index = cycle.index(node.mark if node is not None else None)
        except ValueError:
            index = 0  # a mark this document used that is no longer in the set
        return cycle[(index + 1) % len(cycle)]

    def cycle_mark(self, node_id: str, marks: Sequence[str] = MARKS) -> str | None:
        """Advance this node's mark: none, then each mark in turn, then none."""
        node = self.find(node_id)
        if node is None:
            return None
        node.mark = self.next_mark(node_id, marks)
        return node.mark

    def range_between(self, first: str, last: str) -> list[str]:
        """The run of siblings from one cell to another, endpoints included, in
        document order whichever way it was dragged out.

        Only siblings may be selected together; anything else is just the cell
        you are standing on.
        """
        parent = self.parent(last)
        if parent is None:
            return [last]
        order = [child.id for child in parent.children]
        try:
            a, b = order.index(first), order.index(last)
        except ValueError:
            return [last]
        low, high = sorted((a, b))
        return order[low : high + 1]

    def move_sibling(self, node_id: str, delta: int) -> bool:
        parent = self.parent(node_id)
        if parent is None:
            return False
        index = self._index(parent, node_id)
        target = index + delta
        if not 0 <= target < len(parent.children):
            return False
        parent.children.insert(target, parent.children.pop(index))
        return True

    @staticmethod
    def _index(parent: Node, node_id: str) -> int:
        for index, child in enumerate(parent.children):
            if child.id == node_id:
                return index
        raise ValueError(f"{node_id} is not a child of {parent.id}")

    # -- serialisation --------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "spacing": self.spacing,
            "layout": self.layout,
            "colours": self.colours,
            "marks": list(self.marks),
            **({"justify": self.justify} if self.justify else {}),
            "root": self.root.to_dict(),
            "cut": [node.to_dict() for node in self.cut_stack],
            "cursor": self.cursor or "",
        }

    @classmethod
    def from_dict(cls, data: dict, marks: Sequence[str] | None = None) -> MindMap:
        if not isinstance(data, dict):
            raise MapFileError("a map file must hold a JSON object at the top level")
        root_data = data.get("root")
        if not isinstance(root_data, dict):
            raise MapFileError("the map has no root node")
        root = Node.from_dict(root_data)
        try:
            # 1e400 is valid JSON and parses to infinity, which int() refuses
            spacing = int(data.get("spacing") or 0)
        except (TypeError, ValueError, OverflowError):
            spacing = 0
        layout = data.get("layout")
        cut: list[Node] = []
        raw_cut = data.get("cut")
        if isinstance(raw_cut, list):
            for entry in raw_cut:  # a hand-edited file may hold anything here
                built = Node._build(entry, 0)
                if built is not None:
                    cut.append(built)
        colours = data.get("colours")
        justify = data.get("justify")
        if not isinstance(justify, int) or isinstance(justify, bool) or not 1 <= justify <= 4000:
            justify = None
        mm = cls(
            root,
            spacing,
            layout if isinstance(layout, str) else DEFAULT_LAYOUT,
            cut,
            colours if isinstance(colours, str) else DEFAULT_COLOURS,
            justify,
            data.get("marks") if isinstance(data.get("marks"), list) else marks,
        )
        cursor = data.get("cursor")
        mm.cursor = clean(cursor) if isinstance(cursor, str) and cursor else None
        return mm

    def save(self, path: Path) -> None:
        write_atomic(path, json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: Path, marks: Sequence[str] | None = None) -> MindMap:
        """Read a map file, raising MapFileError for anything the app can report
        instead of crashing on: unreadable, not JSON, wrong shape, too deep.

        `marks` is the palette to use when the file records none of its own, which
        is how the editor's default reaches a map written before marks were
        document state."""
        path = Path(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MapFileError(f"cannot read {clean(path.name)}: {exc.strerror or exc}") from exc
        except UnicodeDecodeError as exc:
            raise MapFileError(f"{clean(path.name)} is not UTF-8 text") from exc
        try:
            data = json.loads(raw)
        except RecursionError as exc:
            raise MapFileError(f"{clean(path.name)} is nested far too deeply") from exc
        except ValueError as exc:
            raise MapFileError(f"{clean(path.name)} is not valid JSON: {exc}") from exc
        try:
            return cls.from_dict(data, marks=marks)
        except RecursionError as exc:  # belt and braces: _build is bounded too
            raise MapFileError(f"{clean(path.name)} is nested far too deeply") from exc

    # -- fixtures -------------------------------------------------------

    @classmethod
    def demo(cls) -> MindMap:
        """The map `--demo` opens: the manual, as a map.

        It ships inside the package, at `data/manual.spoider`, so `--demo` works the same
        from a wheel as from a checkout, and it is edited like any other map rather than
        built by hand in code.
        """
        return cls.load(Path(__file__).resolve().parent / "data" / "manual.spoider")
