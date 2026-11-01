from pathlib import Path

from spoider.model import MindMap, Node


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


def test_marks_roundtrip_through_json():
    mm = MindMap()
    node = mm.add_child(mm.root.id, "marked")
    mm.cycle_mark(node.id)

    clone = MindMap.from_dict(mm.to_dict())
    assert clone.find(node.id).mark == "✅"

    assert MindMap().root.mark is None


def test_navigation_helpers_use_visible_order():
    mm = MindMap()
    branch = mm.add_child(mm.root.id, "branch")
    leaf = mm.add_child(branch.id, "leaf")

    assert [n.id for n in mm.visible()] == [mm.root.id, branch.id, leaf.id]

    branch.collapsed = True
    assert [n.id for n in mm.visible()] == [mm.root.id, branch.id]

    assert mm.depth(leaf.id) == 2
    assert [n.text for n in mm.path(leaf.id)] == [mm.root.text, "branch", "leaf"]


def test_the_demo_says_what_a_mind_map_is_and_what_the_app_does():
    mm = MindMap.demo()
    texts = [node.text for node in mm.nodes()]

    assert mm.root.text == "spoider"
    assert any("mind map" in text for text in texts), "it names the thing"
    # what it is for, and what the keys do
    assert any("planning" in text or "thinking" in text for text in texts)
    assert any("tab" in text for text in texts) and any("^F" in text for text in texts)
    assert any("^S" in text for text in texts), "and where the map goes"

    # short enough to read at a glance, and one cell shows a mark rather than
    # only talking about them
    assert all(len(text) <= 32 for text in texts)
    assert any(node.mark for node in mm.nodes())
    assert 12 <= mm.count() <= 24


# -- cut and paste --------------------------------------------------------


def test_a_clone_brings_ids_of_its_own():
    branch = Node("a", children=[Node("b", children=[Node("c")])])
    copy = branch.clone()

    assert [node.text for node in copy.walk()] == ["a", "b", "c"]
    ids = [node.id for node in branch.walk()] + [node.id for node in copy.walk()]
    assert len(set(ids)) == 6, "no id is shared between the original and the copy"


def test_a_clone_keeps_the_mark_and_the_fold():
    branch = Node("a", collapsed=True, mark="✅", children=[Node("b")])
    copy = branch.clone()

    assert copy.mark == "✅"
    assert copy.collapsed is True
    assert copy.id != branch.id


def test_paste_appends_a_copy_and_leaves_the_original_alone():
    mm = MindMap()
    cut = mm.add_child(mm.root.id, "cut")
    cut.children.append(Node("under"))
    target = mm.add_child(mm.root.id, "target")

    pasted = mm.paste(target.id, cut)

    assert pasted is not None
    assert [child.text for child in target.children] == ["cut"]
    assert [child.text for child in pasted.children] == ["under"]
    # the original is where it was, and the index knows about the copies
    assert [child.text for child in mm.root.children] == ["cut", "target"]
    assert mm.find(pasted.id) is pasted
    assert mm.find(pasted.children[0].id) is pasted.children[0]


def test_the_same_cut_pastes_many_times_under_different_ids():
    mm = MindMap()
    cut = mm.add_child(mm.root.id, "cut")
    first = mm.paste(mm.root.id, cut)
    second = mm.paste(mm.root.id, cut)

    assert first is not None and second is not None
    assert first.id != second.id
    assert len(mm.root.children) == 3
    assert all(mm.find(node.id) is not None for node in (first, second))


def test_pasting_into_a_folded_cell_opens_it():
    mm = MindMap()
    cut = mm.add_child(mm.root.id, "cut")
    target = mm.add_child(mm.root.id, "target")
    mm.add_child(target.id, "existing")
    target.collapsed = True

    mm.paste(target.id, cut)

    assert target.collapsed is False, "a pasted branch you cannot see is a surprise"
