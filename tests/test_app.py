from pathlib import Path

from textual.widgets import Input

from spoider.app import SpoiderApp, footer_bar
from spoider.widgets import TopBar, compose_top_bar
from spoider.screens import Confirm, TextPrompt


def test_every_shortcut_uses_a_modifier():
    allowed_plain = {"tab", "enter", "escape", "up", "down", "left", "right", "space"}
    for binding in SpoiderApp.BINDINGS:
        for key in str(binding.key).split(","):
            assert key.startswith(("ctrl+", "alt+")) or key in allowed_plain, key


def test_footer_only_lists_visible_bindings():
    bar = footer_bar(SpoiderApp.BINDINGS).plain
    assert "⇥" in bar and "⏎" in bar and "^X" in bar
    assert "^Y" not in bar  # redo stays out of the bar
    assert "^A" not in bar and "^J" not in bar  # aliases stay off the bar
    assert "ctrl" not in bar and "alt" not in bar


def test_top_bar_layout():
    bar = compose_top_bar(80, "0.1.0", "/tmp/map.json", 7).plain
    assert bar.startswith("spoider 0.1.0")
    assert bar.endswith("7 cells")
    assert "/tmp/map.json" in bar
    assert len(bar) == 80

    assert compose_top_bar(70, "0.1.0", "New Buffer", 1).plain.endswith("1 cell")
    # too narrow for three fields: the location is the one that goes
    narrow = compose_top_bar(24, "0.1.0", "/tmp/map.json", 3).plain
    assert narrow.startswith("spoider 0.1.0") and narrow.endswith("3 cells")
    assert "/tmp" not in narrow


def test_top_bar_truncates_a_long_path_from_the_left():
    bar = compose_top_bar(40, "0.1.0", "/very/long/path/to/some/deep/map.json", 4).plain
    assert bar.endswith("4 cells")
    assert "…" in bar and "map.json" in bar


def test_no_header_and_no_command_palette():
    assert SpoiderApp.ENABLE_COMMAND_PALETTE is False
    assert SpoiderApp().theme == "textual-ansi"


async def test_top_bar_tracks_location_and_cell_count(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        bar = app.query_one(TopBar)
        assert "New Buffer" in bar.render().plain
        assert "1 cell" in bar.render().plain

        await pilot.press("ctrl+a")
        await pilot.press("x", "enter")
        await pilot.pause()
        assert "2 cells" in bar.render().plain

        await pilot.press("ctrl+s")
        await pilot.pause()
        rendered = bar.render().plain
        assert "map.json" in rendered  # long path keeps its tail
        assert "New Buffer" not in rendered
        assert "2 cells" in rendered


async def test_tab_adds_a_child_and_enter_adds_a_sibling(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        assert app.editing is True and len(app.mm.root.children) == 1

        await pilot.press("k", "i", "d", "enter")
        await pilot.pause()
        child = app.mm.root.children[0]
        assert child.text == "kid"

        await pilot.press("enter")
        await pilot.pause()
        assert app.editing is True
        await pilot.press("s", "i", "b", "enter")
        await pilot.pause()
        assert [c.text for c in app.mm.root.children] == ["kid", "sib"]


async def test_ctrl_aliases_still_add_nodes(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.select(branch.id)
        app.view.refresh_map()

        await pilot.press("ctrl+a")
        await pilot.pause()
        assert len(app.mm.find(branch.id).children) == 1
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("ctrl+j")
        await pilot.pause()
        assert len(app.mm.root.children) == 2


async def test_new_node_is_typed_into_directly(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        assert not isinstance(app.screen, TextPrompt)  # no dialog for a new node
        assert app.editing is True
        assert app.mm.root.children[0].text == ""
        assert "▊" in app.mm.root.children[0].preview

        await pilot.press("f", "i", "r", "s", "t")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "first▊"

        await pilot.press("enter")
        await pilot.pause()

        assert app.editing is False
        assert [child.text for child in app.mm.root.children] == ["first"]
        assert app.mm.root.children[0].preview is None
        assert app.dirty is True
        assert not path.exists()  # nothing is written until ^S/^O


async def test_escape_cancels_a_new_node(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("x")
        await pilot.press("escape")
        await pilot.pause()

        assert app.editing is False
        assert app.mm.root.children == []  # an abandoned node never happened
        assert app.selected == app.mm.root.id


async def test_ctrl_c_cancels_like_escape(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("x")
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.editing is False
        assert app.mm.root.children == []
        assert app.is_running is True  # ^C must not quit


async def test_editing_an_existing_node_types_in_place(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "old")
        app.select(node.id)
        app.view.refresh_map()

        await pilot.press("ctrl+e")
        await pilot.pause()
        assert not isinstance(app.screen, TextPrompt)
        assert app.mm.find(node.id).preview == "old▊"

        await pilot.press("!")
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.find(node.id).text == "old!"


async def test_cancelling_an_edit_keeps_the_old_text(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "keep me")
        app.select(node.id)
        app.view.refresh_map()

        await pilot.press("ctrl+e")
        await pilot.press("x")
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert app.mm.find(node.id).text == "keep me"
        assert app.mm.find(node.id).preview is None
        assert app.dirty is False


async def test_typing_swallows_shortcuts(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("a", "b", "c")
        await pilot.press("ctrl+d")  # would delete the branch outside edit mode
        await pilot.pause()
        assert len(app.mm.root.children) == 1

        await pilot.press("enter")
        await pilot.pause()
        assert app.mm.root.children[0].text == "abc"


async def test_backspace_and_caret_moves(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.pause()
        await pilot.press("a", "c")
        await pilot.press("left")
        await pilot.press("b")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "ab▊c"

        await pilot.press("backspace")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "a▊c"


async def test_add_sibling_on_ctrl_j(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("ctrl+j")
        await pilot.pause()
        await pilot.press("s", "e", "c", "o", "n", "d")
        await pilot.press("enter")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["first", "second"]


async def test_dialog_blocks_app_actions(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "branch")
        app.select(node.id)
        app.view.refresh_map()

        await pilot.press("ctrl+o")  # file dialog
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        await pilot.press("ctrl+d")  # must not delete anything
        await pilot.pause()
        assert app.mm.find(node.id) is not None

        await pilot.press("ctrl+c")  # and ^C closes it
        await pilot.pause()
        assert not issubclass(app.screen.__class__, TextPrompt)


async def test_save_writes_without_a_prompt(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "quick")
        app.select(node.id)
        app._mark_dirty()

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert not isinstance(app.screen, TextPrompt)
        assert path.exists()
        assert app.path == path
        assert app.dirty is False

    reopened = SpoiderApp(path)
    assert [child.text for child in reopened.mm.root.children] == ["quick"]


async def test_write_dialog_caret_is_visible(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()

        field = app.screen.query_one(Input)
        assert field.has_focus is True
        assert field.cursor_blink is False  # steady, not a half-second flash

        caret = field.get_component_rich_style("input--cursor")
        assert caret.reverse is True  # inverts the terminal's own colours…
        assert caret.color.is_default and caret.bgcolor.is_default  # …no black block


async def test_write_dialog_caret_follows_typing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()
        field = app.screen.query_one(Input)

        await pilot.press("home")
        await pilot.press("x")
        await pilot.pause()
        assert field.value.startswith("x")
        assert field.cursor_position == 1


async def test_write_out_asks_for_a_name(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "kept")
        app.select(node.id)
        app._mark_dirty()

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        field = app.screen.query_one(Input)
        assert field.value == str(path)

        other = tmp_path / "written.json"
        field.value = str(other)
        await pilot.press("enter")
        await pilot.pause()

        assert other.exists()
        assert app.path == other
        assert app.dirty is False
        assert not path.exists()

    reopened = SpoiderApp(other)
    assert [child.text for child in reopened.mm.root.children] == ["kept"]


async def test_mark_cycles_through_the_emoji_then_off(tmp_path: Path):
    from spoider.model import MARKS

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "thing")
        app.select(node.id)
        app.view.refresh_map()

        seen = []
        for _ in range(len(MARKS) + 1):
            await pilot.press("ctrl+g")
            await pilot.pause()
            seen.append(app.mm.find(node.id).mark)
        assert seen == [*MARKS, None]

        assert app.dirty is True
        await pilot.press("ctrl+z")
        await pilot.pause()
        assert app.mm.find(node.id).mark == MARKS[-1]


async def test_marks_survive_a_write(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "checked")
        app.select(node.id)
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert SpoiderApp(path).mm.find(node.id).mark == "✅"


async def test_spacing_keys_resize_the_canvas(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.mm.add_child(branch.id, "leaf")
        app.view.refresh_map()
        base = app.view.layout_.width

        await pilot.press("ctrl+plus")
        assert app.spacing == 1
        assert app.view.layout_.width > base

        await pilot.press("ctrl+minus")
        assert app.spacing == 0
        assert app.view.layout_.width == base

        await pilot.press("ctrl+underscore")  # the other spelling of ^-
        assert app.spacing == -1
        assert app.view.layout_.width < base


async def test_spacing_stops_at_the_limits(tmp_path: Path):
    from spoider.layout import MAX_SPACING, MIN_SPACING

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test():
        app._set_spacing(MAX_SPACING)
        app.action_spacing_more()
        assert app.spacing == MAX_SPACING

        app._set_spacing(MIN_SPACING)
        app.action_spacing_less()
        assert app.spacing == MIN_SPACING


async def test_navigation_moves_through_the_tree(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        # a right-hand branch with two leaves: in, out, and along the branch
        branch = app.mm.add_child(app.mm.root.id, "branch")
        one = app.mm.add_child(branch.id, "one")
        two = app.mm.add_child(branch.id, "two")
        app.view.refresh_map()
        app.select(branch.id)

        await pilot.press("ctrl+f")  # into the first child
        assert app.selected == one.id
        await pilot.press("ctrl+n")  # next sibling
        assert app.selected == two.id
        await pilot.press("ctrl+p")  # previous sibling
        assert app.selected == one.id
        await pilot.press("ctrl+b")  # back out to the parent
        assert app.selected == branch.id


async def test_navigation_flips_on_the_left_hand_branch(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        right = app.mm.add_child(app.mm.root.id, "right")  # index 0 -> drawn right
        left = app.mm.add_child(app.mm.root.id, "left")  # index 1 -> drawn left
        leaf = app.mm.add_child(left.id, "leaf")
        app.view.refresh_map()

        # right-hand branch keeps the original sense
        app.select(right.id)
        await pilot.press("left")
        assert app.selected == app.mm.root.id
        await pilot.press("right")
        assert app.selected == right.id

        # left-hand branch: towards the root is now RIGHT, deeper is LEFT
        app.select(left.id)
        await pilot.press("right")
        assert app.selected == app.mm.root.id

        app.select(left.id)
        await pilot.press("left")
        assert app.selected == leaf.id

        app.select(leaf.id)
        await pilot.press("right")
        assert app.selected == left.id


async def test_root_branches_both_ways(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        right = app.mm.add_child(app.mm.root.id, "right")  # index 0
        left = app.mm.add_child(app.mm.root.id, "left")  # index 1
        app.view.refresh_map()

        app.select(app.mm.root.id)
        await pilot.press("right")
        assert app.selected == right.id

        app.select(app.mm.root.id)
        await pilot.press("left")
        assert app.selected == left.id

        # ^B/^F keep the same meaning
        app.select(app.mm.root.id)
        await pilot.press("ctrl+b")
        assert app.selected == left.id
        app.select(app.mm.root.id)
        await pilot.press("ctrl+f")
        assert app.selected == right.id


async def test_root_left_is_inert_when_there_is_no_left_branch(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "only")  # index 0, so it hangs right
        app.view.refresh_map()

        app.select(app.mm.root.id)
        await pilot.press("left")
        assert app.selected == app.mm.root.id  # nothing on that side to enter

        await pilot.press("right")
        assert app.selected == app.mm.root.children[0].id


async def test_left_from_a_folded_root_unfolds_it(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "right")
        left = app.mm.add_child(app.mm.root.id, "left")
        app.mm.root.collapsed = True
        app.select(app.mm.root.id)
        app.view.refresh_map()

        await pilot.press("left")
        await pilot.pause()
        assert app.mm.root.collapsed is False
        assert app.selected == app.mm.root.id  # unfolding is not a move

        await pilot.press("left")
        assert app.selected == left.id


async def test_left_branch_flip_applies_to_the_ctrl_chords(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        left = app.mm.add_child(app.mm.root.id, "right-first")
        left = app.mm.add_child(app.mm.root.id, "left-second")
        leaf = app.mm.add_child(left.id, "leaf")
        app.view.refresh_map()

        app.select(left.id)
        await pilot.press("ctrl+f")  # forward = towards the root on this side
        assert app.selected == app.mm.root.id

        app.select(left.id)
        await pilot.press("ctrl+b")  # back = deeper on this side
        assert app.selected == leaf.id


async def test_arrow_keys_alias_the_ctrl_chords(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        app.mm.add_child(app.mm.root.id, "second")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("down")  # next sibling (drawn below)
        assert app.selected != first.id
        await pilot.press("right")  # back towards the root, this branch is left-hand
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


async def test_undo_marks_the_buffer_modified(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+a")
        await pilot.press("h", "i", "enter")
        await pilot.pause()
        assert app.dirty is True

        app._write(path)
        assert app.dirty is False

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert app.dirty is True


async def test_clean_quit_exits_without_a_dialog(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.is_running is False


async def test_dirty_quit_asks_before_discarding(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "doomed")
        app._mark_dirty()

        await pilot.press("ctrl+x")
        await pilot.pause()
        assert isinstance(app.screen, Confirm)

        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.is_running is True  # ^C cancels the dialog, does not quit
        assert app.dirty is True

        await pilot.press("ctrl+x")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.is_running is False
        assert not path.exists()


async def test_dirty_quit_saves_on_yes(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "rescued")
        app._mark_dirty()

        await pilot.press("ctrl+x")
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        await pilot.press("enter")
        await pilot.pause()
        assert app.is_running is False

    written = SpoiderApp(path)
    assert [child.text for child in written.mm.root.children] == ["rescued"]
