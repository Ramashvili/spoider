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


def test_the_depth_cap_counts_nodes_on_the_path():
    def chain(depth: int) -> dict:
        node: dict = {"text": "leaf"}
        for index in range(depth - 1):
            node = {"text": f"level {index}", "children": [node]}
        return {"root": node}

    assert MindMap.from_dict(chain(MAX_DEPTH)).count() == MAX_DEPTH, "the cap itself must load"
    with pytest.raises(MapFileError):
        MindMap.from_dict(chain(MAX_DEPTH + 1))


async def test_a_map_named_with_escapes_does_not_write_them_out(tmp_path):
    from spoider.app import SpoiderApp
    from spoider.widgets import TopBar

    evil = tmp_path / "map\x1b]0;PWNED\x07.json"
    evil.write_text('{"version": 1, "root": {"text": "r"}}')
    app = SpoiderApp(evil, demo=False)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        bar = str(app.query_one(TopBar).render())
        assert "\x1b" not in bar and "\x07" not in bar, "the path is cleaned where it is drawn"
        assert "PWNED" in bar, "cleaned, not hidden"


async def test_notifications_are_cleaned_before_they_reach_the_terminal(tmp_path):
    from textual.widgets._toast import Toast

    from spoider.app import SpoiderApp

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        app.notify("bad \x1b]52;c;aGVsbG8=\x07 name", severity="error", timeout=8)
        await pilot.pause()
        toast = app.query(Toast).last()
        rendered = str(toast.render())
        assert "\x1b" not in rendered and "\x07" not in rendered
        assert "name" in rendered


async def test_a_notification_holds_one_line_whatever_it_is_given(tmp_path):
    from textual.widgets._toast import Toast

    from spoider.app import SpoiderApp

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        app.notify("one\ntwo\n\nthree\tfour", timeout=8)
        await pilot.pause()
        rendered = str(app.query(Toast).last().render())
        assert "one two three four" in rendered
        assert "onetwo" not in rendered


async def test_a_prompt_does_not_write_escapes_from_a_file_name(tmp_path):
    from spoider.app import SpoiderApp
    from spoider.drawers import PromptBar

    evil = tmp_path / "map\x1b]0;PWNED\x07.json"
    evil.write_text('{"version": 1, "root": {"text": "r"}}')
    app = SpoiderApp(evil, demo=False)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()
        line = str(app.query_one(PromptBar).render())
        assert "\x1b" not in line and "\x07" not in line
        assert "PWNED" in line
