import json
from pathlib import Path

from textual.widgets import Input

from spoider.app import BINDINGS, SpoiderApp
from spoider.chrome import compose_footer, hint_chunks, pinned_bar
from spoider.layout import compute
from spoider.widgets import TopBar, compose_top_bar
from spoider.screens import HELP, Confirm, HelpScreen, SettingsScreen, TextPrompt, help_text, settings_text


def test_every_shortcut_uses_a_modifier():
    # Bare keys are only the terminal's own cursor keys, the two ergonomic
    # inserts, and the vim aliases for those cursor keys — nothing else.
    allowed_plain = {
        "tab",
        "enter",
        "escape",
        "space",
        "up",
        "down",
        "left",
        "right",
        "h",
        "j",
        "k",
        "l",
    }
    for binding in SpoiderApp.BINDINGS:
        for key in str(binding.key).split(","):
            assert key.startswith(("ctrl+", "alt+")) or key in allowed_plain, key


def test_footer_lists_the_visible_bindings_plus_the_pinned_cluster():
    line = compose_footer(160, hint_chunks(BINDINGS)).plain
    assert "⇥ child" in line and "^X quit" in line
    assert "^, settings" in line and "^/ help" in line
    assert "^Y" not in line  # redo stays out of the bar
    assert "^A" not in line and "^J" not in line  # aliases stay off the bar
    for nav in ("^P", "^N", "^B", "^F"):
        assert nav not in line, nav
    assert "equals_sign" not in line and "COMMA" not in line


def test_footer_caps_are_coloured_text_without_a_block():
    from spoider.chrome import CAP_STYLE, entry

    chunk = entry("ctrl+d", "del")
    cap = chunk.spans[0]
    assert str(cap.style) == CAP_STYLE
    assert "reverse" not in CAP_STYLE
    assert " on " not in CAP_STYLE  # no background at all
    assert CAP_STYLE.split()[-1] in {"cyan", "blue", "green", "yellow", "magenta", "red"}


def test_pinned_cluster_survives_any_width():
    for width in (40, 55, 70, 90, 120, 200):
        line = compose_footer(width, hint_chunks(BINDINGS))
        assert line.plain.rstrip().endswith("^/ help")
        assert "^, settings" in line.plain
        assert line.cell_len == width  # fills the row exactly, never overflows


def test_hints_are_dropped_before_the_pinned_cluster():
    wide = compose_footer(200, hint_chunks(BINDINGS)).plain
    narrow = compose_footer(60, hint_chunks(BINDINGS)).plain
    assert "^Z undo" in wide and "^Z undo" not in narrow
    assert "^/ help" in wide and "^/ help" in narrow
    # whole entries only: no half-drawn cap at the edge
    assert "loose" not in narrow.split("│")[0] or "looser" in narrow


def test_help_documents_every_binding():
    documented = {action for _, rows in HELP for actions, _, _ in rows for action in actions}
    bound = {binding.action for binding in BINDINGS}
    assert bound - documented == set(), f"undocumented: {sorted(bound - documented)}"
    assert documented - bound == set(), f"stale help entries: {sorted(documented - bound)}"


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


def test_top_bar_marks_an_unsaved_buffer():
    assert compose_top_bar(90, "0.1.0", "/tmp/map.json", 7).plain.count("*") == 0
    dirty = compose_top_bar(90, "0.1.0", "/tmp/map.json", 7, True).plain
    assert "map.json *" in dirty
    assert compose_top_bar(90, "0.1.0", "New Buffer", 1, True).plain.find("New Buffer *") > 0


async def test_top_bar_star_appears_and_clears_with_the_edit(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        bar = app.query_one(TopBar)
        assert "*" not in bar.render().plain

        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()
        assert "*" in bar.render().plain  # visible without a title bar

        await pilot.press("ctrl+s")
        await pilot.pause()
        assert "*" not in bar.render().plain


async def test_top_bar_never_shows_the_star_under_autosave(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "e.json")
    async with app.run_test() as pilot:
        app.set_autosave(True)
        await pilot.pause()
        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()

        assert "*" not in app.query_one(TopBar).render().plain


def test_top_bar_truncates_a_long_path_from_the_left():
    bar = compose_top_bar(40, "0.1.0", "/very/long/path/to/some/deep/map.json", 4).plain
    assert bar.endswith("4 cells")
    assert "…" in bar and "map.json" in bar


def test_spacing_chords_match_the_names_the_key_parser_produces():
    """The escape sequences below are what a terminal actually sends; the key
    NAMES they parse into are not guessable, so pin them against BINDINGS."""
    from textual._xterm_parser import XTermParser

    bound = {key for binding in SpoiderApp.BINDINGS for key in str(binding.key).split(",")}
    sequences = {
        "ctrl+shift+equals_sign": "\x1b[61;6u",  # ^+ under the kitty keyboard protocol
        "ctrl+equals_sign": "\x1b[61;5u",  # ctrl+= under it
        "ctrl+minus": "\x1b[45;5u",  # ^- under it
        "ctrl+underscore": "\x1f",  # ^- on a plain terminal (the ^_ control char)
    }
    for expected, sequence in sequences.items():
        parsed = [key.key for key in XTermParser().feed(sequence) if hasattr(key, "key")]
        assert parsed == [expected], f"{sequence!r} parses to {parsed}"
        assert expected in bound, f"{expected} is not bound"


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


async def test_vim_keys_alias_the_arrows(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")  # index 0 -> right
        one = app.mm.add_child(branch.id, "one")
        two = app.mm.add_child(branch.id, "two")
        app.view.refresh_map()
        app.select(branch.id)

        await pilot.press("j")  # down/next sibling from a node with no siblings
        assert app.selected == branch.id  # root has one child, so nothing to move to
        await pilot.press("l")  # right = into the first child
        assert app.selected == one.id
        await pilot.press("j")
        assert app.selected == two.id
        await pilot.press("k")
        assert app.selected == one.id
        await pilot.press("h")  # left = out to the parent
        assert app.selected == branch.id


async def test_vim_keys_flip_on_a_left_branch(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "right")
        left = app.mm.add_child(app.mm.root.id, "left")
        leaf = app.mm.add_child(left.id, "leaf")
        app.view.refresh_map()

        app.select(left.id)
        await pilot.press("h")  # drawn leftwards, so h goes deeper
        assert app.selected == leaf.id
        await pilot.press("l")
        assert app.selected == left.id


async def test_vim_letters_type_while_editing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("h", "j", "k", "l", "enter")
        await pilot.pause()

        assert app.mm.root.children[0].text == "hjkl"
        assert app.selected == app.mm.root.children[0].id


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

        # and the spelling a kitty-protocol terminal actually delivers
        await pilot.press("ctrl+shift+equals_sign")
        assert app.spacing == 0


def test_help_text_covers_keys_and_notes():
    body = help_text().plain
    for expected in ("Making cells", "Moving", "File", "⇥", "⏎", "^D", "^X", "⌥↑", "^/", "^,"):
        assert expected in body, expected
    assert "Mouse" in body and "Saving" in body


async def test_help_opens_with_ctrl_slash_and_closes(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_help_closes_on_ctrl_c(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)
        assert app.is_running is True


async def test_help_is_reachable_mid_typing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("a", "b")
        await pilot.pause()

        await pilot.press("ctrl+slash")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert app.editing is True  # the half-typed name survived
        assert app.mm.root.children[0].preview == "ab▊"


async def test_settings_shows_only_the_autosave_toggle(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

        body = settings_text(app).plain
        assert "autosave" in body and "off" in body
        # and nothing invented beyond the one setting
        for absent in ("colours", "version", "cells", "spacing"):
            assert absent not in body, absent

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)


async def test_toggling_autosave_persists_to_the_editor_config(tmp_path: Path):
    config_path = tmp_path / "editor.json"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        assert app.autosave is False
        await pilot.press("ctrl+comma")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.autosave is True
        assert isinstance(app.screen, SettingsScreen)  # stays open to show "on"

    assert json.loads(config_path.read_text())["autosave"] is True
    reopened = SpoiderApp(tmp_path / "map.json", config_path=config_path)
    assert reopened.autosave is True  # and it survives the editor restarting


async def test_toggling_autosave_repaints_the_footer_immediately(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        footer = app.query_one("#footer")
        repaints = []
        original = footer.refresh

        def spy(*args, **kwargs):
            repaints.append(1)
            return original(*args, **kwargs)

        footer.refresh = spy  # type: ignore[method-assign]
        app.set_autosave(True)
        await pilot.pause()
        assert repaints, "changing autosave must repaint the bar, not wait for a nudge"
        assert "^S save" not in footer.render().plain


async def test_autosave_writes_after_every_edit(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "editor.json")
    async with app.run_test() as pilot:
        app.set_autosave(True)
        await pilot.pause()

        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()
        assert path.exists()  # no ^S needed
        assert app.dirty is False
        assert json.loads(path.read_text())["root"]["children"][0]["text"] == "a"

        await pilot.press("ctrl+minus")  # a view/edit change, same rule
        await pilot.pause()
        assert json.loads(path.read_text())["spacing"] == -1

        await pilot.press("ctrl+d")
        await pilot.pause()
        assert json.loads(path.read_text())["root"]["children"] == []


async def test_autosave_quits_without_asking(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "editor.json")
    async with app.run_test() as pilot:
        app.set_autosave(True)
        await pilot.pause()
        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()

        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.is_running is False
        assert not isinstance(app.screen, Confirm)

    assert json.loads(path.read_text())["root"]["children"][0]["text"] == "a"


async def test_autosave_hides_manual_save_from_the_bar(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        from spoider.chrome import compose_footer, hint_chunks

        with_save = compose_footer(160, hint_chunks(BINDINGS)).plain
        assert "^S save" in with_save

        app.set_autosave(True)
        await pilot.pause()
        without = compose_footer(160, hint_chunks(BINDINGS, frozenset({"save"}))).plain
        assert "^S save" not in without
        # the bar the app actually renders agrees
        footer = app.query_one("#footer")
        assert "^S save" not in footer.render().plain


async def test_spacing_is_saved_with_the_map(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()
        await pilot.press("ctrl+minus")
        await pilot.pause()
        assert app.dirty is True  # document state, so it needs writing
        await pilot.press("ctrl+s")
        await pilot.pause()

    import json

    assert json.loads(path.read_text())["spacing"] == -1

    reopened = SpoiderApp(path)
    assert reopened.spacing == -1
    # and the reopened app actually draws with it: one column tighter
    assert compute(reopened.mm.root, reopened.spacing).width < compute(
        reopened.mm.root, 0
    ).width


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
