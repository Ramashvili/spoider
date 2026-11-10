"""What the loader and the writer do with untrusted input."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from spoider import properties
from spoider.app import SpoiderApp
from spoider.files import WriteRefused
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


def test_saving_through_a_link_keeps_the_link(tmp_path: Path):
    """The link is the name the reader gave, so the file it names receives the map."""
    real = tmp_path / "real.spoider"
    real.write_text("old", encoding="utf-8")
    link = tmp_path / "link.spoider"
    link.symlink_to(real)

    MindMap().save(link)

    assert link.is_symlink(), "a rename would have replaced the link itself"
    assert real.read_text(encoding="utf-8") != "old", "and the map landed where the link points"


def test_a_read_only_file_is_not_written_over(tmp_path: Path):
    """A rename needs only the directory, so a chmod 444 file would be rewritten anyway."""
    path = tmp_path / "map.spoider"
    MindMap().save(path)
    path.chmod(0o444)
    before = path.read_bytes()

    with pytest.raises(WriteRefused):
        MindMap().save(path)

    assert path.read_bytes() == before
    path.chmod(0o644)


def test_something_that_is_not_a_regular_file_is_left_alone(tmp_path: Path):
    pipe = tmp_path / "pipe.spoider"
    os.mkfifo(pipe)

    with pytest.raises(WriteRefused):
        MindMap().save(pipe)

    assert stat.S_ISFIFO(pipe.stat().st_mode), "the pipe is still a pipe"
    pipe.unlink()


def test_a_name_near_the_filesystems_limit_can_be_saved(tmp_path: Path):
    """The temp file used to carry the whole target name, so a legal name could not be saved."""
    path = tmp_path / (("n" * 240) + ".spoider")
    MindMap().save(path)
    assert path.exists()
    assert [entry.name for entry in tmp_path.iterdir()] == [path.name], "and no temp left"


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
    from spoider.app import SpoiderApp
    from spoider.drawers import NoticeBar

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        app.notify("bad \x1b]52;c;aGVsbG8=\x07 name", severity="error", timeout=8)
        await pilot.pause()
        rendered = app.query_one(NoticeBar).render().plain
        assert "\x1b" not in rendered and "\x07" not in rendered
        assert "name" in rendered


async def test_a_notification_holds_one_line_whatever_it_is_given(tmp_path):
    from spoider.app import SpoiderApp
    from spoider.drawers import NoticeBar

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        app.notify("one\ntwo\n\nthree\tfour", timeout=8)
        await pilot.pause()
        rendered = app.query_one(NoticeBar).render().plain
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


# -- the three findings of the audit ---------------------------------------


async def test_a_file_that_is_not_a_map_is_never_overwritten(tmp_path: Path):
    """An unreadable file must lose its path, or ^S would replace it with a map."""
    path = tmp_path / "notes.txt"
    path.write_text("my precious notes, not a map\n", encoding="utf-8")
    app = SpoiderApp(path, config_path=tmp_path / "a.conf")
    assert app.load_error is not None, "the load failed"
    assert app.path is None, "the failed path is forgotten, so save cannot reach it"
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert path.read_text(encoding="utf-8") == "my precious notes, not a map\n"


async def test_a_broken_map_is_not_clobbered_by_saving(tmp_path: Path):
    path = tmp_path / "broken.spoider"
    path.write_text('{"version": 1, "root": ', encoding="utf-8")
    app = SpoiderApp(path, config_path=tmp_path / "a.conf")
    assert app.path is None
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert path.read_text(encoding="utf-8") == '{"version": 1, "root": '


def test_an_infinite_spacing_is_a_wrong_type_not_a_crash(tmp_path: Path):
    """1e400 is valid JSON, parses to infinity, and int() refuses it."""
    path = tmp_path / "inf.spoider"
    path.write_text(
        '{"version": 1, "spacing": 1e400, "root": {"id": "r", "text": "x",'
        ' "collapsed": false, "mark": null, "children": []}}',
        encoding="utf-8",
    )
    mm = MindMap.load(path)
    assert mm.spacing == 0, "an impossible number falls back to the default"


def test_a_file_name_cannot_drive_the_terminal(tmp_path: Path):
    """A map arrives with its name; the name is a way into the terminal."""
    evil = tmp_path / "evil\x1b]0;PWNED\x07\x1b[2J.spoider"
    evil.write_text(
        '{"version": 1, "root": {"id": "r", "text": "x", "collapsed": false,'
        ' "mark": null, "children": []}}',
        encoding="utf-8",
    )
    app = SpoiderApp(evil, config_path=tmp_path / "a.conf")
    app.mm = MindMap.load(evil)
    rows = dict(dict(properties.sections(
        app.mm, evil, app.mm.root.id, 1, None, dirty=False, autosave=False
    ))["file state"])
    for shown in (rows["file"], app._title()):
        assert "\x1b" not in shown and "\x07" not in shown, f"escape survived in {shown!r}"


def test_a_write_over_another_map_is_allowed(tmp_path: Path):
    """Replacing a file that is a spoider map needs no ceremony."""
    from spoider.app import _not_a_map

    other = tmp_path / "other.spoider"
    MindMap(Node("root")).save(other)
    assert _not_a_map(other) is None, "a map is a fine target"


def test_a_write_over_a_foreign_file_is_refused(tmp_path: Path):
    """^O with a typed name must not bury a text file."""
    from spoider.app import _not_a_map

    notes = tmp_path / "README.md"
    notes.write_text("# my readme\n", encoding="utf-8")
    assert _not_a_map(notes) is not None


def test_an_over_long_cell_is_refused_at_the_door(tmp_path: Path):
    from spoider.model import MAX_CELL_CHARS

    path = tmp_path / "long.spoider"
    path.write_text(
        json.dumps({"version": 1, "root": {"id": "r", "text": "A" * (MAX_CELL_CHARS + 1),
                    "collapsed": False, "mark": None, "children": []}}),
        encoding="utf-8",
    )
    with pytest.raises(MapFileError):
        MindMap.load(path)


def test_a_cell_holds_exactly_the_cap(tmp_path: Path):
    from spoider.model import MAX_CELL_CHARS

    path = tmp_path / "at.spoider"
    path.write_text(
        json.dumps({"version": 1, "root": {"id": "r", "text": "A" * MAX_CELL_CHARS,
                    "collapsed": False, "mark": None, "children": []}}),
        encoding="utf-8",
    )
    assert len(MindMap.load(path).root.text) == MAX_CELL_CHARS


def test_typing_stops_at_the_cap():
    from spoider.editing import Buffer
    from spoider.model import MAX_CELL_CHARS

    buffer = Buffer()
    buffer.insert("A" * (MAX_CELL_CHARS + 500))
    assert len(buffer.text) == MAX_CELL_CHARS
    buffer.insert("B")
    assert len(buffer.text) == MAX_CELL_CHARS, "a full cell takes no more"


def test_a_mark_is_capped():
    from spoider.model import MAX_MARK_CHARS, marks_of

    marks = marks_of(["⭐" * 40, "ok"])
    assert all(len(mark) <= MAX_MARK_CHARS for mark in marks)


def test_the_config_keeps_its_comments(tmp_path: Path):
    """An existing config is the user's text: only the lines spoider owns change."""
    from spoider.config import update_config

    conf = tmp_path / "spoider.conf"
    conf.write_text(
        "# my careful note\nautosave = false\n\n# a block I turned off\n# prev = k up\n",
        encoding="utf-8",
    )
    update_config(conf, {"autosave": "true", "desktop_asked": "true"})
    text = conf.read_text(encoding="utf-8")
    assert "# my careful note" in text and "# a block I turned off" in text
    assert "# prev = k up" in text
    assert "autosave = true" in text
    assert "desktop_asked = true" in text, "a missing key is appended, not regenerated"


def test_an_existing_config_is_not_rewritten_on_start(tmp_path: Path):
    conf = tmp_path / "spoider.conf"
    conf.write_text("# hands off\nprev = k up\n", encoding="utf-8")
    before = conf.read_text(encoding="utf-8")
    SpoiderApp(tmp_path / "m.spoider", config_path=conf, demo=False)
    assert conf.read_text(encoding="utf-8") == before
