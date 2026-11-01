"""What the loader and the writer do with untrusted input."""

from __future__ import annotations

import pytest

from spoider.model import MAX_DEPTH, MapFileError, MindMap, Node


def test_text_with_control_characters_is_cleaned_at_the_door():
    mm = MindMap.from_dict({"root": {"text": "a\x1b[2Jb", "mark": "\x07!"}})
    assert mm.root.text == "a[2Jb"
    assert mm.root.mark == "!"


def test_a_file_that_is_not_json_is_a_reportable_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")
    with pytest.raises(MapFileError):
        MindMap.load(path)


def test_a_file_that_is_not_a_map_is_a_reportable_error(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[1, 2, 3]")
    with pytest.raises(MapFileError):
        MindMap.load(path)


def test_a_missing_file_is_a_reportable_error(tmp_path):
    with pytest.raises(MapFileError):
        MindMap.load(tmp_path / "nope.json")


def test_a_file_that_is_not_utf8_is_a_reportable_error(tmp_path):
    path = tmp_path / "latin1.json"
    path.write_bytes(b'{"root": {"text": "\xe9"}}')
    with pytest.raises(MapFileError):
        MindMap.load(path)


def test_a_map_nested_past_the_limit_is_refused():
    node: dict = {"text": "leaf"}
    for index in range(MAX_DEPTH + 2):
        node = {"text": f"level {index}", "children": [node]}
    with pytest.raises(MapFileError):
        MindMap.from_dict({"root": node})


def test_duplicate_ids_are_repaired_so_lookups_stay_honest():
    mm = MindMap.from_dict(
        {"root": {"id": "same", "text": "root", "children": [{"id": "same", "text": "child"}]}}
    )
    assert mm.root.id != mm.root.children[0].id
    assert mm.find(mm.root.children[0].id) is mm.root.children[0]


def test_a_node_without_a_mark_does_not_invent_one():
    mm = MindMap.from_dict({"root": {"text": "x"}})
    assert mm.root.mark is None


def test_ids_are_wide_enough_to_collide_rarely():
    assert len(MindMap().root.id) == 12


def test_lookups_repair_themselves_if_children_are_appended_directly():
    mm = MindMap()
    stray = Node("stray")
    mm.root.children.append(stray)  # bypassing add_child on purpose
    assert mm.find(stray.id) is stray
    assert mm.parent(stray.id) is mm.root


def test_deleting_a_subtree_leaves_no_ids_behind():
    mm = MindMap()
    branch = mm.add_child(mm.root.id, "branch")
    leaf = mm.add_child(branch.id, "leaf")
    mm.delete(branch.id)
    assert mm.find(branch.id) is None
    assert mm.find(leaf.id) is None
    assert mm.count() == 1


def test_saving_keeps_the_mode_of_the_file_it_replaces(tmp_path):
    path = tmp_path / "map.json"
    path.write_text("{}")
    path.chmod(0o640)
    MindMap().save(path)
    assert path.stat().st_mode % 0o1000 == 0o640


def test_saving_leaves_no_temporary_files_behind(tmp_path):
    path = tmp_path / "map.json"
    MindMap().save(path)
    assert [entry.name for entry in tmp_path.iterdir()] == ["map.json"]
