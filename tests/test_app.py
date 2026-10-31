from pathlib import Path

from textual.widgets import Input

from spoider.app import SpoiderApp, footer_bar
from spoider.screens import TextPrompt


def test_every_shortcut_uses_a_modifier():
    allowed_plain = {"enter", "escape", "up", "down", "left", "right", "space"}
    for binding in SpoiderApp.BINDINGS:
        for key in str(binding.key).split(","):
            assert key.startswith(("ctrl+", "alt+")) or key in allowed_plain, key


def test_footer_only_lists_visible_bindings():
    import re

    bar = footer_bar(SpoiderApp.BINDINGS)
    text = bar.plain
    assert "^A" in text and "^X" in text
    assert "^Y" not in text  # redo stays out of the bar
    assert bar.plain.count("  ") < len(text)
    assert re.search(r"ctrl|alt", text) is None


def test_no_header_and_no_command_palette():
    assert SpoiderApp.ENABLE_COMMAND_PALETTE is False
    assert SpoiderApp().theme == "textual-ansi"


async def test_add_child_through_the_prompt(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        app.screen.query_one(Input).value = "first idea"
        await pilot.press("enter")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["first idea"]
        assert app.selected == app.mm.root.children[0].id
        assert path.exists()


async def test_typing_replaces_the_placeholder(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("h", "i")
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.root.children[0].text == "hi"


async def test_escape_leaves_the_node_untouched(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert len(app.mm.root.children) == 1
        assert app.mm.root.children[0].text == "New idea"


async def test_mutations_are_blocked_while_a_dialog_is_open(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.select(branch.id)
        app.view.refresh_map()

        await pilot.press("ctrl+e")  # rename dialog opens
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        await pilot.press("ctrl+d")  # must not delete the node being renamed
        await pilot.pause()
        assert app.mm.find(branch.id) is not None


async def test_editing_an_existing_node(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "old")
        app.select(node.id)
        app.view.refresh_map()

        await pilot.press("ctrl+e")
        await pilot.pause()
        app.screen.query_one(Input).value = "new"
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.find(node.id).text == "new"


async def test_navigation_moves_through_the_tree(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        app.view.refresh_map()
        app.select(first.id)

        await pilot.press("ctrl+n")  # next sibling
        assert app.selected == second.id
        await pilot.press("ctrl+b")  # back out to the parent
        assert app.selected == app.mm.root.id
        await pilot.press("ctrl+f")  # forward into the first child
        assert app.selected == first.id
        await pilot.press("ctrl+p")  # no previous sibling -> stays at the edge
        assert app.selected == first.id


async def test_arrow_keys_alias_the_ctrl_chords(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        app.mm.add_child(app.mm.root.id, "second")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("down")
        assert app.selected != first.id
        await pilot.press("left")
        assert app.selected == app.mm.root.id


async def test_delete_then_undo(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("ctrl+d")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["second"]
        assert app.selected == second.id

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["first", "second"]
        assert app.mm.find(first.id) is not None


async def test_fold_toggles_a_branch(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.mm.add_child(branch.id, "leaf")
        app.select(branch.id)
        app.view.refresh_map()

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert app.mm.find(branch.id).collapsed is True

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert app.mm.find(branch.id).collapsed is False


async def test_changes_are_persisted(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "persisted")
        app._changed()
        await pilot.pause()

    reopened = SpoiderApp(path)
    assert [child.text for child in reopened.mm.root.children] == ["persisted"]
