import json
from pathlib import Path

from textual.widgets import Input

from spoider.app import BINDINGS, SpoiderApp
from spoider.chrome import FooterBar, SearchBar, compose_footer, hint_chunks
from spoider.config import load_config
from spoider.layout import compute
from spoider.screens import (
    HELP,
    Confirm,
    HelpScreen,
    SettingsScreen,
    TextPrompt,
    help_text,
    keys_for,
    settings_text,
)
from spoider.widgets import TopBar, compose_top_bar


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
    for nav in ("^P", "^N", "^B"):
        assert nav not in line, nav
    # ^F is the search now, so it has earned its place in the bar
    assert "^F search" in line
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
    documented = {action for _, rows in HELP for actions, _ in rows for action in actions}
    bound = {binding.action for binding in BINDINGS}
    assert bound - documented == set(), f"undocumented: {sorted(bound - documented)}"
    assert documented - bound == set(), f"stale help entries: {sorted(documented - bound)}"


def test_top_bar_layout():
    bar = compose_top_bar(80, "0.1.0", "/tmp/map.json", "7 cells", "bush").plain
    assert bar.startswith("spoider 0.1.0")
    assert bar.endswith("7 cells  bush")
    assert "/tmp/map.json" in bar
    assert len(bar) == 80

    assert compose_top_bar(70, "0.1.0", "New Buffer", "1 cell", "spider").plain.endswith("1 cell  spider")
    # too narrow for three fields: the location is the one that goes
    narrow = compose_top_bar(24, "0.1.0", "/tmp/map.json", "3 cells").plain
    # and the shape is the first thing to go when even that does not fit
    assert narrow.startswith("spoider 0.1.0") and narrow.endswith("3 cells")
    assert "/tmp" not in narrow


def test_top_bar_marks_an_unsaved_buffer():
    assert compose_top_bar(90, "0.1.0", "/tmp/map.json", "7 cells").plain.count("*") == 0
    dirty = compose_top_bar(90, "0.1.0", "/tmp/map.json", "7 cells", "", True).plain
    assert "map.json *" in dirty
    assert compose_top_bar(90, "0.1.0", "New Buffer", "1 cell", "", True).plain.find("New Buffer *") > 0


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
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        app.set_autosave(True)
        await pilot.pause()
        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()

        assert "*" not in app.query_one(TopBar).render().plain


def test_top_bar_truncates_a_long_path_from_the_left():
    bar = compose_top_bar(40, "0.1.0", "/very/long/path/to/some/deep/map.json", "4 cells").plain
    assert bar.endswith("4 cells")
    assert "…" in bar and "map.json" in bar


def test_spacing_chords_match_the_names_the_key_parser_produces():
    """The escape sequences below are what a terminal actually sends; the key
    NAMES they parse into are not guessable, so pin them against BINDINGS."""
    from textual._xterm_parser import XTermParser

    bound = {key for binding in SpoiderApp.BINDINGS for key in str(binding.key).split(",")}
    sequences = {
        "ctrl+equals_sign": "\x1b[61;5u",  # ^= under the kitty keyboard protocol
        "ctrl+minus": "\x1b[45;5u",  # ^- under it
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

        await pilot.press("ctrl+equals_sign")
        assert app.spacing == 1
        assert app.view.layout_.width > base

        await pilot.press("ctrl+minus")
        assert app.spacing == 0
        assert app.view.layout_.width == base

        await pilot.press("ctrl+minus")  # and past the default, into tighter
        assert app.spacing == -1
        assert app.view.layout_.width < base


def test_help_text_covers_keys(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    body = help_text(app).plain
    # chords come from the keymap, so they read as they are actually bound
    for expected in ("Making cells", "Moving", "File", "⇥", "⏎", "^D", "^X", "⌥↑", "^/", "^,"):
        assert expected in body, expected
    # no lectures: the panel is the keys, nothing else
    for absent in ("Mouse", "Saving", "Colours", "Also", "esc closes"):
        assert absent not in body, absent


def test_help_follows_a_rebound_chord(tmp_path: Path):
    config = tmp_path / "config.conf"
    config.write_text("mark = ctrl+m\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    body = help_text(app).plain
    assert "^M" in body
    assert "^G" not in body  # the old chord is gone everywhere, help included


async def test_help_opens_with_ctrl_slash_and_closes(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)

        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)


async def test_help_closes_on_any_key(tmp_path: Path):
    for key in ("x", "space", "f5", "tab"):
        app = SpoiderApp(tmp_path / "map.json", demo=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+slash")
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)

            await pilot.press(key)
            await pilot.pause()
            assert not isinstance(app.screen, HelpScreen), key


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


async def test_settings_closes_on_ctrl_x(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)

        await pilot.press("ctrl+x")
        await pilot.pause()
        assert not isinstance(app.screen, SettingsScreen)
        assert app.is_running is True  # it closed the dialog, it did not quit


async def test_toggling_autosave_persists_to_the_editor_config(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        assert app.autosave is False
        await pilot.press("ctrl+comma")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert app.autosave is True
        assert isinstance(app.screen, SettingsScreen)  # stays open to show "on"

    assert load_config(config_path).autosave is True
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


def test_marks_are_an_editor_preference(tmp_path: Path):
    from spoider.config import MAX_MARKS, Config, write_config

    path = tmp_path / "config.conf"
    assert load_config(path).marks  # defaults when the file is missing
    write_config(Config(marks=("🔴", "🟢")), path)
    assert load_config(path).marks == ("🔴", "🟢")

    # a blank value falls back rather than breaking ^G
    path.write_text("marks =\n")
    assert len(load_config(path).marks) > 0
    # and a runaway list is capped
    write_config(Config(marks=tuple(str(i) for i in range(MAX_MARKS + 5))), path)
    assert len(load_config(path).marks) == MAX_MARKS


def test_config_is_a_flat_rc_file_with_every_key_prefilled(tmp_path: Path):
    path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    app._save_config()
    text = path.read_text()

    assert "{" not in text and "}" not in text and "[" not in text  # no JSON, no sections
    assert "autosave = false" in text
    assert "marks = ✅ ❌ ❓ ❗ 🕐" in text  # space separated, no quotes
    assert "# add_child = tab" in text  # prefilled, but switched off

    config = load_config(path)
    assert config.autosave is False
    assert config.keys == {}  # everything commented out means defaults apply

    # uncommenting one line is all it takes to rebind
    path.write_text(text.replace("# save = ctrl+s", "save = ctrl+w"))
    assert load_config(path).keys["save"] == "ctrl+w"
    assert SpoiderApp(tmp_path / "map.json", config_path=path).keymap["save"] == "ctrl+w"


async def test_a_stale_config_file_is_regenerated_on_start(tmp_path: Path):
    path = tmp_path / "config.conf"
    # what an older build wrote: six spellings apiece and a chord that is gone
    path.write_text(
        "autosave = true\n"
        "marks = 🔴 🟢\n"
        "\n"
        "# spacing_more = ctrl+shift+equals_sign,ctrl+equals_sign,ctrl+plus\n"
        "# gone_action = ctrl+y\n"
    )

    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    async with app.run_test() as pilot:
        await pilot.pause()

    text = path.read_text()
    assert "# spacing_more = ctrl+equals_sign\n" in text
    assert "ctrl+plus" not in text and "gone_action" not in text
    # and nothing of the user's was lost
    assert "autosave = true" in text
    assert "marks = 🔴 🟢" in text


async def test_a_current_config_file_is_left_alone(tmp_path: Path):
    path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    async with app.run_test() as pilot:
        await pilot.pause()
    app._save_config()
    # a note of the user's own
    note = "# my own note\n"
    path.write_text(path.read_text() + note)

    async with SpoiderApp(tmp_path / "map.json", demo=False, config_path=path).run_test():
        pass
    assert "# my own note" in path.read_text()  # untouched, comment included


def test_comments_and_loose_spacing_are_tolerated(tmp_path: Path):
    from spoider.config import parse

    config = parse(
        "# a comment\n"
        "autosave   =   yes     # trailing comment\n"
        "marks = ✅   ❌\n"
        "\n"
        "save = ctrl+w\n"
        "a line with no equals sign\n"
    )
    assert config.autosave is True
    assert config.marks == ("✅", "❌")
    assert config.keys == {"save": "ctrl+w"}


def test_an_old_json_config_is_still_read(tmp_path: Path):
    legacy = tmp_path / "config.json"
    legacy.write_text(json.dumps({"autosave": True, "keys": {"save": "ctrl+w"}}))

    config = SpoiderApp(tmp_path / "map.json", config_path=tmp_path / "config.conf").config
    assert config.autosave is True
    assert config.keys["save"] == "ctrl+w"


def test_an_old_toml_config_is_still_read(tmp_path: Path):
    legacy = tmp_path / "config.toml"
    legacy.write_text('autosave = true\nmarks = ["🔴"]\n[keys]\nsave = "ctrl+w"\n')

    config = SpoiderApp(tmp_path / "map.json", config_path=tmp_path / "config.conf").config
    assert config.autosave is True
    assert config.marks == ("🔴",)
    assert config.keys["save"] == "ctrl+w"


async def test_editing_the_marks_from_settings(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        screen = app.screen

        await pilot.press("down")  # onto the marks row
        await pilot.pause()
        assert screen.row == 1

        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)
        field = app.screen.query_one(Input)
        assert field.value == " ".join(app.marks)  # pre-filled with the current set

        field.value = "🔴 🟢"
        await pilot.press("enter")
        await pilot.pause()

        assert app.marks == ("🔴", "🟢")
        assert load_config(config_path).marks == ("🔴", "🟢")
        assert isinstance(app.screen, SettingsScreen)  # back on the rows
        assert "🔴 🟢" in settings_text(app, 1).plain

    # and the next editor start reads them back
    assert SpoiderApp(tmp_path / "map.json", config_path=config_path).marks == ("🔴", "🟢")


async def test_ctrl_g_cycles_the_configured_marks(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        app.set_marks(["🔴", "🟢"])
        node = app.mm.add_child(app.mm.root.id, "x")
        app.select(node.id)
        app.view.refresh_map()

        seen = []
        for _ in range(4):
            await pilot.press("ctrl+g")
            await pilot.pause()
            seen.append(app.mm.find(node.id).mark)
        assert seen == ["🔴", "🟢", None, "🔴"]


async def test_prompt_supports_undo_and_redo(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        await pilot.press("down")  # marks row
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, TextPrompt)

        await pilot.press("home")
        await pilot.press("a", "b", "c")
        await pilot.pause()
        field = app.screen.query_one(Input)
        assert field.value.startswith("abc")

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert field.value.startswith("ab")

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert field.value.startswith("a")

        await pilot.press("ctrl+z")  # and back to the value it opened with
        await pilot.pause()
        assert field.value == " ".join(app.marks)

        await pilot.press("ctrl+y")
        await pilot.pause()
        assert field.value.startswith("a")


def test_config_can_rebind_every_chord(tmp_path: Path):
    from spoider.app import build_keymap, default_keymap

    defaults = default_keymap()
    assert len(defaults) == len({b.id for b in BINDINGS if b.id})  # every binding has an id
    assert all(binding.id for binding in BINDINGS), "every binding needs an id to be rebindable"

    merged = build_keymap({"save": "ctrl+w", "quit": "  ", "nonsense": "ctrl+k"})
    assert merged["save"] == "ctrl+w"
    assert merged["quit"] == defaults["quit"]  # blank is ignored
    assert "nonsense" not in merged  # unknown ids are ignored
    assert merged["edit"] == defaults["edit"]


async def test_a_rebound_chord_takes_effect(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    config_path.write_text("save = ctrl+w\ndelete = ctrl+k\n")

    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        assert app.keymap["save"] == "ctrl+w"

        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()

        await pilot.press("ctrl+w")  # the new save chord
        await pilot.pause()
        assert path.exists()
        assert app.dirty is False

        await pilot.press("ctrl+k")  # the new delete chord
        await pilot.pause()
        assert app.mm.root.children == []


def test_spacing_keys_are_one_chord_each():
    spacing = {b.id: b.key for b in BINDINGS if b.action.startswith("spacing")}
    assert spacing == {"spacing_more": "ctrl+equals_sign", "spacing_less": "ctrl+minus"}


def test_the_bar_shows_the_chords_in_force(tmp_path: Path):
    from spoider.chrome import hint_chunks

    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "e.conf")
    app.config.keys["save"] = "ctrl+w"
    bar = compose_footer(160, hint_chunks(BINDINGS, frozenset(), app.keymap)).plain
    assert "^W save" in bar and "^S save" not in bar


async def test_settings_opens_the_config_in_an_editor(tmp_path: Path, monkeypatch):
    import contextlib

    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)

    opened = []

    def fake_editor(path):
        opened.append(path)
        path.write_text("autosave = true\nsave = ctrl+w\n")

    monkeypatch.setattr("spoider.app.edit_in_editor", fake_editor)
    monkeypatch.setattr(SpoiderApp, "suspend", lambda self: contextlib.nullcontext())

    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        await pilot.press("down")
        await pilot.press("down")  # config row
        await pilot.pause()
        assert app.screen.row == 2

        await pilot.press("enter")
        await pilot.pause()

    assert opened and opened[0] == config_path
    assert config_path.exists()
    # what came back from the editor is reloaded and applied
    assert app.autosave is True
    assert app.keymap["save"] == "ctrl+w"


def test_the_saved_config_mentions_every_rebindable_chord(tmp_path: Path):
    from spoider.app import default_keymap

    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    app._save_config()
    text = config_path.read_text()
    for ident, chord in default_keymap().items():
        assert f"# {ident} = {chord}" in text, ident


async def test_autosave_writes_after_every_edit(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "config.conf")
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
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "config.conf")
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

        await pilot.press("right")  # into the first child
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
        await pilot.press("right")
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
        await pilot.press("right")  # forward = towards the root on this side
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


# -- a file that cannot be read must not take the editor down --------------


async def test_a_corrupt_file_starts_empty_and_keeps_the_file_untouched(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{not json")

    app = SpoiderApp(path, demo=False)
    assert app.load_error is not None
    assert app.has_file is False
    async with app.run_test():
        assert app.mm.count() == 1
        assert path.read_text() == "{not json"  # never overwritten on the way in


async def test_the_top_bar_says_new_buffer_when_the_file_could_not_be_opened(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("{oops")
    app = SpoiderApp(path, demo=False)
    async with app.run_test():
        assert "New Buffer" in app.query_one(TopBar).render().plain


async def test_the_path_survives_the_file_disappearing(tmp_path: Path):
    path = tmp_path / "map.json"
    path.write_text('{"root": {"text": "x"}}')
    app = SpoiderApp(path, demo=False)
    async with app.run_test():
        assert "map.json" in app.query_one(TopBar).render().plain
        path.unlink()
        # the bar reads state, not stat(): no mid-session flip to "New Buffer"
        assert "map.json" in app.query_one(TopBar).render().plain


async def test_quit_stays_put_when_autosave_cannot_write(tmp_path: Path, monkeypatch):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.set_autosave(True)
        app.mm.add_child(app.selected, "work that must not vanish")
        app.dirty = True

        def refuse(path):
            raise OSError(28, "No space left on device")

        monkeypatch.setattr(app.mm, "save", refuse)
        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.is_running  # the buffer is still here
        assert app.dirty


def test_the_terminal_title_cannot_carry_an_escape_sequence(tmp_path: Path):
    app = SpoiderApp(tmp_path / "plain.json", demo=False)
    app.path = tmp_path / "map\x1b]52;c;SGVsbG8=\x07.json"
    written: list[str] = []

    class Driver:
        def write(self, data: str) -> None:
            written.append(data)

    app._driver = Driver()
    app._set_terminal_title()
    assert written == ["\x1b]2;spoider — map]52;c;SGVsbG8=.json\x07"]


async def test_a_saved_map_reaches_the_disk_without_a_temp_file(tmp_path: Path):
    target = tmp_path / "out.json"
    app = SpoiderApp(tmp_path / "fresh.json", demo=False)
    async with app.run_test():
        app.mm.add_child(app.selected, "hello")
        app._write(target)
    assert json.loads(target.read_text())["root"]["children"][0]["text"] == "hello"
    assert [e.name for e in tmp_path.iterdir() if e.name != "config-home"] == ["out.json"]


# -- the shape of the map -------------------------------------------------


async def test_ctrl_l_cycles_the_shapes_and_marks_the_buffer_dirty(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        assert app.mm.layout == "spider"
        seen: list[str] = []
        for _ in range(4):
            await pilot.press("ctrl+l")
            await pilot.pause()
            seen.append(app.mm.layout)
        assert seen == ["pyramid", "bush", "branch", "spider"]
        assert app.dirty


async def test_the_shape_is_written_into_the_map_file(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+l")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
    assert json.loads(path.read_text())["layout"] == "pyramid"


async def test_a_saved_shape_is_what_opens_next_time(tmp_path: Path):
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"version": 1, "layout": "bush", "root": {"text": "x"}}))
    app = SpoiderApp(path, demo=False)
    async with app.run_test():
        assert app.mm.layout == "bush"
        assert app.view.layout_.boxes, "and it is what gets drawn"


async def test_arrows_follow_a_pyramid(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.layout = "pyramid"
        app.view.refresh_map()
        first = app.mm.add_child(app.selected, "one")
        second = app.mm.add_child(app.selected, "two")

        app.select(app.mm.root.id)
        await pilot.press("down")  # down goes into the children
        await pilot.pause()
        assert app.selected == first.id

        await pilot.press("up")  # up goes back to the parent
        await pilot.pause()
        assert app.selected == app.mm.root.id

        app.select(first.id)
        await pilot.press("right")  # siblings are side by side
        await pilot.pause()
        assert app.selected == second.id

        await pilot.press("left")
        await pilot.pause()
        assert app.selected == first.id


async def test_the_layout_key_is_in_the_bar_and_the_help(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test():
        assert keys_for(app, ("layout",)) == "^L"
        assert "cycle the shape" in help_text(app).plain


async def test_arrows_follow_a_bush(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.layout = "bush"
        app.view.refresh_map()
        child = app.mm.add_child(app.selected, "child")

        app.select(app.mm.root.id)
        await pilot.press("up")  # the branches grow upwards, so up goes deeper
        await pilot.pause()
        assert app.selected == child.id

        await pilot.press("down")  # and down comes back towards the root
        await pilot.pause()
        assert app.selected == app.mm.root.id


def test_up_and_down_mean_what_is_drawn():
    from spoider.app import DOWN_MEANING, UP_MEANING
    from spoider.model import LAYOUTS

    assert set(UP_MEANING) == set(LAYOUTS) == set(DOWN_MEANING)
    # a pyramid hangs its children below the parent, a bush above it
    assert (UP_MEANING["pyramid"], DOWN_MEANING["pyramid"]) == ("parent", "child")
    assert (UP_MEANING["bush"], DOWN_MEANING["bush"]) == ("child", "parent")
    # sideways shapes keep the siblings on the up/down arrows
    for name in ("spider", "branch"):
        assert (UP_MEANING[name], DOWN_MEANING[name]) == ("prev", "next")


# -- searching ------------------------------------------------------------


def _poem(app) -> dict[str, object]:
    """A tiny map with two cells that say 'one' and one that says 'two'."""
    alpha = app.mm.add_child(app.selected, "alpha one")
    beta = app.mm.add_child(app.selected, "beta one")
    gamma = app.mm.add_child(app.selected, "gamma two")
    app.view.refresh_map()
    app._refresh_chrome()
    return {"alpha": alpha, "beta": beta, "gamma": gamma}


async def test_ctrl_f_opens_a_prompt_and_counts_matches(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        assert "4 cells" in app.query_one(TopBar).render().plain

        await pilot.press("ctrl+f")
        await pilot.pause()
        prompt = app.query_one(SearchBar)
        assert prompt.display, "the prompt takes the line above the bar"
        footer = app.query_one(FooterBar)
        assert footer.display, "the bar stays: it is the way out"
        assert footer.mode == "search", "and it says what the prompt accepts"
        assert "⏎ search" in footer.render().plain

        await pilot.press("o", "n", "e")
        await pilot.pause()
        assert app.search_query == "one"
        assert len(app.matches) == 2
        # the top bar reports the matches in place of the cell count
        assert app.stat_text() == "2 matches"
        assert "2 matches" in app.query_one(TopBar).render().plain


async def test_enter_jumps_to_the_first_match_and_a_repeat_moves_on(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        nodes = _poem(app)
        await pilot.press("ctrl+f")
        await pilot.press("o", "n", "e", "enter")
        await pilot.pause()

        assert app.selected == app.matches[0]
        assert app.query_one(SearchBar).display is False
        assert app.query_one(FooterBar).mode == "keys"

        await pilot.press("ctrl+f", "enter")  # the prompt offers the last search
        await pilot.pause()
        assert app.selected == app.matches[1]
        assert app.selected != nodes["gamma"].id


async def test_searching_wraps_around_the_map(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        await pilot.press("ctrl+f", "o", "n", "e", "enter")
        await pilot.pause()
        first = str(app.selected)
        await pilot.press("ctrl+f", "enter")  # second match
        await pilot.pause()
        await pilot.press("ctrl+f", "enter")  # and round again
        await pilot.pause()
        assert app.selected == first


async def test_up_arrow_recalls_an_earlier_search(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        await pilot.press("ctrl+f", "t", "w", "o", "enter")
        await pilot.pause()
        await pilot.press("ctrl+f", "o", "n", "e", "enter")
        await pilot.pause()
        assert app.search_query == "one"

        await pilot.press("ctrl+f")  # offers the last search again
        await pilot.pause()
        assert app.query_one(SearchBar).value == "one"

        await pilot.press("up")
        await pilot.pause()
        assert app.query_one(SearchBar).value == "two"
        assert app.search_query == "two", "the count follows the recalled word"


async def test_escape_puts_the_cell_count_back(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        await pilot.press("ctrl+f", "o", "n", "e")
        await pilot.pause()
        assert app.stat_text() == "2 matches"

        await pilot.press("escape")
        await pilot.pause()
        assert app.search_query == ""
        assert app.matches == []
        assert app.stat_text() == "4 cells"
        assert app.query_one(FooterBar).display is True


async def test_typing_in_the_prompt_does_not_touch_the_map(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        before = app.mm.count()
        await pilot.press("ctrl+f")
        await pilot.press("d", "e", "ctrl+d", "ctrl+t")
        await pilot.pause()
        assert app.mm.count() == before, "a chord must not delete a cell behind the prompt"
        assert app.search_query == "de"


async def test_a_match_hidden_in_a_folded_branch_is_revealed(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.selected, "branch")
        needle = app.mm.add_child(branch.id, "the needle")
        branch.collapsed = True
        app.view.refresh_map()

        await pilot.press("ctrl+f", "n", "e", "e", "d", "l", "e", "enter")
        await pilot.pause()
        assert branch.collapsed is False, "a match you cannot see is no use"
        assert app.selected == needle.id


def test_the_bar_ranks_its_hints_from_leaving_down_to_the_air():
    line = compose_footer(400, hint_chunks(BINDINGS)).plain
    expected = [
        "^X quit",
        "^S save",
        "^O write",
        "^Z undo",
        "^F search",
        "^E edit",
        "^D del",
        "^T fold",
        "^G mark",
        "⇥ child",
        "⏎ sib",
        "^L layout",
        "^= looser",
        "^- tighter",
    ]
    positions = [line.index(item) for item in expected]
    assert positions == sorted(positions), "the bar should read most to least important"
    # and a narrow bar therefore keeps quitting and drops the spacing keys
    narrow = compose_footer(40, hint_chunks(BINDINGS)).plain
    assert "^X quit" in narrow
    assert "tighter" not in narrow


def test_every_visible_binding_has_a_place_in_the_ranking():
    from textual.binding import Binding

    from spoider.chrome import BAR_ORDER

    visible = {binding.id for binding in BINDINGS if isinstance(binding, Binding) and binding.show}
    assert visible <= set(BAR_ORDER), f"unranked: {sorted(visible - set(BAR_ORDER))}"
    assert len(BAR_ORDER) == len(set(BAR_ORDER))


async def test_the_match_count_lets_go_after_a_moment(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(SpoiderApp, "MATCH_COUNT_SECONDS", 0.5)
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _poem(app)
        await pilot.press("ctrl+f", "o", "n", "e", "enter")
        await pilot.pause()
        assert app.stat_text() == "2 matches"
        assert "2 matches" in app.query_one(TopBar).render().plain

        await pilot.pause(0.8)
        assert app.stat_text() == "4 cells", "the count gives the bar back"
        assert app.search_query == "one", "but the search and its marks stay"
        assert len(app.matches) == 2
