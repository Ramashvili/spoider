from pathlib import Path

from textual.widgets import Input

from tagger.app import TaggerApp
from tagger.screens import TextPrompt


async def test_add_child_through_the_prompt(tmp_path: Path):
    path = tmp_path / "map.json"
    app = TaggerApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        app.screen.query_one(Input).value = "first idea"
        await pilot.press("enter")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["first idea"]
        assert app.selected == app.mm.root.children[0].id
        assert path.exists()


async def test_escape_leaves_the_node_untouched(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

        assert app.screen is not None
        assert len(app.mm.root.children) == 1
        assert app.mm.root.children[0].text == "New idea"


async def test_typing_replaces_the_placeholder(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("h", "i")
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.root.children[0].text == "hi"


async def test_editing_an_existing_node(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "old")
        app.select(node.id)
        app.view.refresh_map()

        await pilot.press("e")
        await pilot.pause()
        app.screen.query_one(Input).value = "new"
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.find(node.id).text == "new"


async def test_navigation_moves_through_the_tree(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        app.view.refresh_map()
        app.select(first.id)

        await pilot.press("down")
        assert app.selected == second.id
        await pilot.press("left")
        assert app.selected == app.mm.root.id
        await pilot.press("right")
        assert app.selected == first.id
        await pilot.press("up")
        assert app.selected == first.id


async def test_delete_then_undo(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("d")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["second"]
        assert app.selected == second.id

        await pilot.press("u")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["first", "second"]
        assert app.mm.find(first.id) is not None


async def test_space_folds_a_branch(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.mm.add_child(branch.id, "leaf")
        app.select(branch.id)
        app.view.refresh_map()

        await pilot.press("space")
        await pilot.pause()
        assert app.mm.find(branch.id).collapsed is True

        await pilot.press("space")
        await pilot.pause()
        assert app.mm.find(branch.id).collapsed is False


async def test_palette_offers_no_theme_commands(tmp_path: Path):
    app = TaggerApp(tmp_path / "map.json", demo=False)
    async with app.run_test():
        assert app.theme == "textual-ansi"
        titles = [command.title.lower() for command in app.get_system_commands(app.screen)]
        assert titles, "palette should still offer tagger's own commands"
        assert not any("theme" in title for title in titles)


async def test_changes_are_persisted(tmp_path: Path):
    path = tmp_path / "map.json"
    app = TaggerApp(path, demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "persisted")
        app._changed()
        await pilot.pause()

    reopened = TaggerApp(path)
    assert [child.text for child in reopened.mm.root.children] == ["persisted"]
