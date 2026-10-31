"""Document model: a tree of idea nodes, plus load/save."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

NEW_NODE_TEXT = "New idea"
DEFAULT_ROOT_TEXT = "Mind map"


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Node:
    text: str = DEFAULT_ROOT_TEXT
    id: str = field(default_factory=new_id)
    collapsed: bool = False
    children: list["Node"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "collapsed": self.collapsed,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            text=str(data.get("text", "")),
            id=str(data.get("id") or new_id()),
            collapsed=bool(data.get("collapsed", False)),
            children=[cls.from_dict(child) for child in data.get("children", [])],
        )


class MindMap:
    """The whole document. Mutations are by node id so the UI can stay stateless."""

    def __init__(self, root: Node | None = None) -> None:
        self.root = root if root is not None else Node(DEFAULT_ROOT_TEXT)

    # -- lookup ---------------------------------------------------------

    def nodes(self) -> list[Node]:
        return list(self.root.walk())

    def find(self, node_id: str) -> Node | None:
        for node in self.root.walk():
            if node.id == node_id:
                return node
        return None

    def parent(self, node_id: str) -> Node | None:
        for node in self.root.walk():
            if any(child.id == node_id for child in node.children):
                return node
        return None

    def visible(self) -> list[Node]:
        out: list[Node] = []

        def visit(node: Node) -> None:
            out.append(node)
            if not node.collapsed:
                for child in node.children:
                    visit(child)

        visit(self.root)
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
        return len(self.nodes())

    # -- mutation -------------------------------------------------------

    def add_child(self, parent_id: str, text: str = NEW_NODE_TEXT) -> Node:
        parent = self.find(parent_id) or self.root
        node = Node(text=text)
        parent.children.append(node)
        parent.collapsed = False
        return node

    def add_sibling(self, node_id: str, text: str = NEW_NODE_TEXT) -> Node | None:
        parent = self.parent(node_id)
        if parent is None:
            return None
        node = Node(text=text)
        index = self._index(parent, node_id)
        parent.children.insert(index + 1, node)
        return node

    def delete(self, node_id: str) -> tuple[Node, str] | None:
        """Remove a node and its subtree. Returns (removed, next selection)."""
        parent = self.parent(node_id)
        if parent is None:
            return None
        index = self._index(parent, node_id)
        removed = parent.children.pop(index)
        if index < len(parent.children):
            successor = parent.children[index]
        elif index > 0:
            successor = parent.children[index - 1]
        else:
            successor = parent
        return removed, successor.id

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
        return {"version": 1, "root": self.root.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "MindMap":
        root = data.get("root") or {}
        return cls(Node.from_dict(root))

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path) -> "MindMap":
        return cls.from_dict(json.loads(Path(path).read_text()))

    # -- fixtures -------------------------------------------------------

    @classmethod
    def demo(cls) -> "MindMap":
        root = Node("spoider")
        ideas = {
            "keys": ["^A child · ^J sibling", "^E edits · ^D deletes", "^T folds a branch"],
            "canvas": ["auto-centres on selection", "click any node to select", "^P ^N ^B ^F move"],
            "data": ["json on disk", "^Z undoes · ^Y redoes", "^S saves · ^O writes as"],
        }
        for title, leaves in ideas.items():
            branch = Node(title, children=[Node(leaf) for leaf in leaves])
            root.children.append(branch)
        return cls(root)
