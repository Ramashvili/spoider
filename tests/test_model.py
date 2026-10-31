from pathlib import Path

from tagger.model import MindMap, Node


def test_add_child_and_sibling():
    mm = MindMap()
    first = mm.add_child(mm.root.id, "first")
    second = mm.add_child(mm.root.id, "second")
    assert [c.text for c in mm.root.children] == ["first", "second"]
    assert mm.parent(first.id) is mm.root

    sibling = mm.add_sibling(first.id, "between")
    assert sibling is not None
    assert [c.text for c in mm.root.children] == ["first", "between", "second"]
    assert second.id == mm.root.children[2].id


def test_delete_picks_next_sibling_then_previous_then_parent():
    mm = MindMap()
    a = mm.add_child(mm.root.id, "a")
    b = mm.add_child(mm.root.id, "b")

    mm.add_child(a.id, "a1")
    removed, successor = mm.delete(a.id)
    assert removed.text == "a"
    assert successor == b.id

    removed, successor = mm.delete(b.id)
    assert removed.text == "b"
    assert successor == mm.root.id


def test_root_cannot_be_deleted():
    mm = MindMap()
    assert mm.delete(mm.root.id) is None


def test_move_sibling_stops_at_edges():
    mm = MindMap()
    a = mm.add_child(mm.root.id, "a")
    mm.add_child(mm.root.id, "b")

    assert mm.move_sibling(a.id, 1) is True
    assert [c.text for c in mm.root.children] == ["b", "a"]
    assert mm.move_sibling(a.id, 1) is False
    assert mm.move_sibling(a.id, -1) is True
    assert [c.text for c in mm.root.children] == ["a", "b"]


def test_roundtrip_preserves_tree():
    mm = MindMap()
    branch = mm.add_child(mm.root.id, "branch")
    leaf = mm.add_child(branch.id, "leaf")
    branch.collapsed = True

    clone = MindMap.from_dict(mm.to_dict())

    assert clone.root.text == mm.root.text
    assert clone.root.children[0].collapsed is True
    assert clone.find(leaf.id) is not None
    assert clone.find(leaf.id).text == "leaf"


def test_save_and_load(tmp_path: Path):
    path = tmp_path / "nested" / "map.json"
    mm = MindMap()
    mm.add_child(mm.root.id, "saved node")
    mm.save(path)

    assert path.exists()
    loaded = MindMap.load(path)
    assert loaded.root.children[0].text == "saved node"


def test_navigation_helpers_use_visible_order():
    mm = MindMap()
    branch = mm.add_child(mm.root.id, "branch")
    leaf = mm.add_child(branch.id, "leaf")

    assert [n.id for n in mm.visible()] == [mm.root.id, branch.id, leaf.id]

    branch.collapsed = True
    assert [n.id for n in mm.visible()] == [mm.root.id, branch.id]

    assert mm.depth(leaf.id) == 2
    assert [n.text for n in mm.path(leaf.id)] == [mm.root.text, "branch", "leaf"]
