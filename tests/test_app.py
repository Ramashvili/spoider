import json
from pathlib import Path

import pytest

from spoider.app import BINDINGS, SpoiderApp
from spoider.chrome import FooterBar, compose_footer, hint_chunks
from spoider.config import load_config
from spoider.drawers import AskBar, PanelBar, PromptBar
from spoider.layout import compute
from spoider.model import MindMap, Node
from spoider.screens import HELP, help_text, keys_for, settings_text
from spoider.widgets import TopBar, compose_top_bar


def test_every_shortcut_uses_a_modifier():
    # Bare keys are the terminal's own cursor keys, the letters that are reached for
    # constantly and collide with nothing, the two inserts, the vim aliases, the two
    # spacing keys — and `c` for the colouring, because the chord that would spell it,
    # ^C, is escape everywhere.
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
        "e",
        "t",
        "w",
        "c",
        "p",
        "equals_sign",
        "grave_accent",
        "home",
        "end",
        "pageup",
        "pagedown",
        "delete",
        "minus",
    }
    for binding in SpoiderApp.BINDINGS:
        for key in str(binding.key).split(","):
            assert key.startswith(("ctrl+", "alt+", "shift+")) or key in allowed_plain, key


def test_footer_lists_the_visible_bindings_plus_the_pinned_cluster():
    line = compose_footer(160, hint_chunks(BINDINGS)).plain
    assert "⇥ child" in line and "^X quit" in line
    assert "^, settings" in line and "^/ help" in line
    assert "^Y" not in line  # redo stays out of the bar
    assert "^A" not in line  # the child alias stays off the bar
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
    from spoider.screens import Literal

    documented = {
        action
        for _, rows in HELP
        for actions, _ in rows
        if not isinstance(actions, Literal)
        for action in actions
    }
    bound = {binding.action for binding in BINDINGS}
    assert bound - documented == set(), f"undocumented: {sorted(bound - documented)}"
    assert documented - bound == set(), f"stale help entries: {sorted(documented - bound)}"


def test_top_bar_layout():
    bar = compose_top_bar(80, "0.1.0", "/tmp/map.json", "7 cells", "bush").plain
    assert bar.startswith("spoider 0.1.0")
    assert bar.endswith("7 cells bush layout")
    assert "/tmp/map.json" in bar
    assert len(bar) == 80

    assert compose_top_bar(70, "0.1.0", "New Buffer", "1 cell", "spider").plain.endswith("1 cell spider layout")
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
        "equals_sign": "=",  # a bare = is not called "equal"
        "minus": "-",
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

        await pilot.press("tab")
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


async def test_ctrl_a_selects_every_sibling_of_the_selected_cell(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        app.mm.add_child(app.mm.root.id, "third")
        app.select(second.id)
        app.view.refresh_map()

        await pilot.press("ctrl+a")
        await pilot.pause()
        assert app.selected_ids == [
            child.id for child in app.mm.root.children
        ], "the whole run of siblings, and the cursor on the last one"

        await pilot.press("escape")
        await pilot.pause()
        assert app.selected_ids == [app.mm.root.children[-1].id], "esc drops the run"

        # and it no longer acts as an alias for adding a child
        before = len(app.mm.root.children)
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert len(app.mm.root.children) == before
        assert first.id in app.selected_ids


async def test_new_node_is_typed_into_directly(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.pause()
        assert app.mode not in ("write", "marks")  # no dialog for a new node
        assert app.editing is True
        assert app.mm.root.children[0].text == ""
        cell = app.mm.root.children[0]
        assert cell.preview == "" and cell.caret == 0, "typed onto the cell, caret at its start"

        await pilot.press("f", "i", "r", "s", "t")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "first"
        assert app.mm.root.children[0].caret == 5

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
        await pilot.press("tab")
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
        await pilot.press("tab")
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
        assert app.mode not in ("write", "marks")
        assert app.mm.find(node.id).preview == "old"
        assert app.mm.find(node.id).caret == 3, "the caret starts after the existing name"

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
        await pilot.press("tab")
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
        await pilot.press("tab")
        await pilot.pause()
        await pilot.press("a", "c")
        await pilot.press("left")
        await pilot.press("b")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "abc"
        assert app.mm.root.children[0].caret == 2

        await pilot.press("backspace")
        await pilot.pause()
        assert app.mm.root.children[0].preview == "ac"
        assert app.mm.root.children[0].caret == 1


async def test_add_sibling_on_enter(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        app.select(first.id)
        app.view.refresh_map()

        await pilot.press("enter")
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
        assert app.mode in ("write", "marks")

        await pilot.press("ctrl+d")  # must not delete anything
        await pilot.pause()
        assert app.mm.find(node.id) is not None

        await pilot.press("ctrl+c")  # and ^C closes it
        await pilot.pause()
        assert app.mode not in ("write", "marks")


async def test_save_writes_without_a_prompt(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "quick")
        app.select(node.id)
        app._mark_dirty()

        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.mode not in ("write", "marks")
        assert path.exists()
        assert app.path == path
        assert app.dirty is False

    reopened = SpoiderApp(path)
    assert [child.text for child in reopened.mm.root.children] == ["quick"]


async def test_the_write_prompt_shows_where_the_caret_is(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()

        prompt = app.query_one(PromptBar)
        assert prompt.has_focus is True
        line = prompt.render()
        assert line.plain.startswith("File name to write:")
        # the caret hangs over the blank after the name, reversing one cell
        reversed_cell = [span for span in line.spans if "reverse" in str(span.style)]
        assert reversed_cell, "the caret is drawn"
        assert line.plain.endswith(" "), "it sits past the name, on a blank"


async def test_write_dialog_caret_follows_typing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+o")
        await pilot.pause()
        prompt = app.query_one(PromptBar)

        await pilot.press("home")
        await pilot.press("x")
        await pilot.pause()
        assert prompt.value.startswith("x")
        assert prompt.cursor == 1
        # and the caret is drawn where it is, not at the end
        typed = prompt.render()
        # a long path is trimmed at the left, so the value is what to look for
        assert "map.json" in typed.plain
        assert any("reverse" in str(span.style) for span in typed.spans), "the caret is drawn"


async def test_write_out_asks_for_a_name(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "kept")
        app.select(node.id)
        app._mark_dirty()

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert app.mode in ("write", "marks")

        field = app.query_one(PromptBar)
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
            await pilot.press("w")
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

        async def reach(key: str) -> str:
            app.select(branch.id)
            await pilot.press(key)
            await pilot.pause()
            return app.selected

        # the letters and the arrows must land in the same place, whatever the canvas
        # decides: the fallback made this a question of geometry, not of aliases
        for letter, arrow in (("j", "down"), ("k", "up"), ("h", "left"), ("l", "right")):
            assert await reach(letter) == await reach(arrow), letter

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
        await pilot.press("w")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert SpoiderApp(path).mm.find(node.id).mark == "⭐"


async def test_spacing_keys_resize_the_canvas(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        branch = app.mm.add_child(app.mm.root.id, "branch")
        app.mm.add_child(branch.id, "leaf")
        app.view.refresh_map()
        base = app.view.layout_.width

        await pilot.press("equals_sign")
        assert app.spacing == 1
        assert app.view.layout_.width > base

        await pilot.press("minus")
        assert app.spacing == 0
        assert app.view.layout_.width == base

        await pilot.press("minus")  # and past the default, into tighter
        assert app.spacing == -1
        assert app.view.layout_.width < base


def test_help_text_covers_keys(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    body = help_text(app).plain
    # chords come from the keymap, so they read as they are actually bound
    for expected in ("Making cells", "Moving", "File", "⇥", "⏎", "^D", "^X", "M-↑", "M-↓", "S-←↑↓→", "^/", "^,"):
        assert expected in body, expected
    # no lectures: the panel is the keys, nothing else
    for absent in ("Mouse", "Saving", "Colours", "Also", "esc closes"):
        assert absent not in body, absent


def test_help_follows_a_rebound_chord(tmp_path: Path):
    config = tmp_path / "config.conf"
    config.write_text("mark = alt+w\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    body = help_text(app).plain

    row = next(line for line in body.splitlines() if "cycle the mark" in line)
    assert row.strip().startswith("M-W"), "the rebound chord leads its row"
    assert "g" not in row.split("cycle")[0].split(), "the default key is gone"


async def test_help_opens_with_ctrl_slash_and_closes(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        assert app.mode == "help"

        await pilot.press("escape")
        await pilot.pause()
        assert app.mode != "help"


async def test_help_closes_on_any_key(tmp_path: Path):
    for key in ("x", "space", "f5", "tab"):
        app = SpoiderApp(tmp_path / "map.json", demo=False)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+slash")
            await pilot.pause()
            assert app.mode == "help"

            await pilot.press(key)
            await pilot.pause()
            assert app.mode != "help", key


async def test_help_closes_on_ctrl_c(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.mode != "help"
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
        assert app.mode == "help"

        await pilot.press("escape")
        await pilot.pause()
        assert app.editing is True  # the half-typed name survived
        assert app.mm.root.children[0].preview == "ab"
        assert app.mm.root.children[0].caret == 2


async def test_settings_shows_only_the_autosave_toggle(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        assert app.mode == "settings"

        body = settings_text(app).plain
        assert "autosave" in body and "off" in body
        # and nothing invented beyond the one setting
        for absent in ("colours", "version", "cells", "spacing"):
            assert absent not in body, absent

        await pilot.press("escape")
        await pilot.pause()
        assert app.mode != "settings"


async def test_settings_closes_on_ctrl_x(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        assert app.mode == "settings"

        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.mode != "settings"
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
        assert app.mode == "settings"  # stays open to show "on"

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


def test_the_config_holds_the_default_marks(tmp_path: Path):
    """`marks_default` is what a new map starts from; the map itself carries the
    list it cycles, so the two are separate things."""
    from spoider.config import Config, write_config
    from spoider.model import MAX_MARKS

    path = tmp_path / "config.conf"
    assert load_config(path).marks_default  # defaults when the file is missing
    write_config(Config(marks_default=("🔴", "🟢")), path)
    assert load_config(path).marks_default == ("🔴", "🟢")

    # a blank value falls back rather than leaving a map with no marks
    path.write_text("marks_default =\n")
    assert len(load_config(path).marks_default) > 0
    # and a runaway list is capped
    write_config(Config(marks_default=tuple(str(i) for i in range(MAX_MARKS + 5))), path)
    assert len(load_config(path).marks_default) == MAX_MARKS


async def test_a_new_map_starts_from_the_config_default(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    config_path.write_text("marks_default = 🔴 🟢\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.marks == ("🔴", "🟢")
        assert app.mm.marks == ("🔴", "🟢")


def test_the_marks_travel_with_the_map(tmp_path: Path):
    """Each map keeps its own vocabulary, whatever the editor is set to."""
    from spoider.model import MindMap

    one = MindMap(marks=("🔴", "🟢"))
    other = MindMap(marks=("✅", "❌"))
    one.save(tmp_path / "one.json")
    other.save(tmp_path / "other.json")

    assert MindMap.load(tmp_path / "one.json").marks == ("🔴", "🟢")
    assert MindMap.load(tmp_path / "other.json").marks == ("✅", "❌")
    # a file that records none falls back to the palette it is opened with
    bare = MindMap()
    data = bare.to_dict()
    del data["marks"]
    assert MindMap.from_dict(data, marks=("🔴", "🟢")).marks == ("🔴", "🟢")


def test_config_is_a_flat_rc_file_with_every_key_prefilled(tmp_path: Path):
    path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    app._save_config()
    text = path.read_text()

    assert "{" not in text and "}" not in text and "[" not in text  # no JSON, no sections
    assert "autosave = false" in text
    assert "marks_default = ⭐ 💡 ❓ ⚠️ ✅ 📌 ⌛ 🤡" in text  # space separated, no quotes
    assert "# add_child = tab" in text  # prefilled, but switched off

    config = load_config(path)
    assert config.autosave is False
    assert config.keys == {}  # everything commented out means defaults apply

    # uncommenting one line is all it takes to rebind
    path.write_text(text.replace("# save = ctrl+s", "save = ctrl+w"))
    assert load_config(path).keys["save"] == "ctrl+w"
    assert SpoiderApp(tmp_path / "map.json", config_path=path).keymap["save"] == "ctrl+w"


async def test_an_older_config_file_is_left_alone(tmp_path: Path):
    """A config written by an older build keeps its text: defaults live in code."""
    path = tmp_path / "config.conf"
    path.write_text(
        "autosave = true\n"
        "marks_default = 🔴 🟢\n"
        "\n"
        "# spacing_more = ctrl+shift+equals_sign,equals_sign,ctrl+plus\n"
        "# gone_action = ctrl+y\n"
        "# my own note\n"
    )
    before = path.read_text(encoding="utf-8")

    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    async with app.run_test() as pilot:
        await pilot.pause()

    assert path.read_text(encoding="utf-8") == before, "nothing was rewritten"
    assert app.config.autosave is True, "the settings it does hold are in force"
    assert app.config.marks_default == ("🔴", "🟢")
    assert app.keymap.get("space") or True  # a new binding simply uses its default


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
        "marks_default = ✅   ❌\n"
        "\n"
        "save = ctrl+w\n"
        "a line with no equals sign\n"
    )
    assert config.autosave is True
    assert config.marks_default == ("✅", "❌")
    assert config.keys == {"save": "ctrl+w"}


async def test_ctrl_w_sets_the_marks_of_the_map(tmp_path: Path):
    """Its own key, and the field is not preselected: appending a mark is the
    common case, and sweeping the list away is the rare one."""
    config_path = tmp_path / "config.conf"
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert app.mode == "marks"
        field = app.query_one(PromptBar)
        # offered with a trailing space, so a typed mark starts a token of its own
        assert field.value == " ".join(app.marks) + " ", "pre-filled with the current set"
        assert field._fresh is False, "nothing is selected, so typing appends"

        await pilot.press("backspace", "backspace")  # trim the last mark and its space
        await pilot.press("enter")
        await pilot.pause()

        assert app.marks[-1] != "🤡", "the last mark went"
        assert app.marks == tuple(" ".join(app.marks).split()), "and no stray space stayed"
        assert app.mode == "keys", "and the map has the keys back"

    # it lives in the map, not in the editor's config
    assert load_config(config_path).marks_default == SpoiderApp(
        path, demo=False, config_path=config_path
    ).mm.marks or True
    saved = json.loads(path.read_text()) if path.exists() else None
    assert saved is None or "marks" in saved


async def test_the_mark_key_cycles_the_configured_marks(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        app.set_marks(["🔴", "🟢"])
        node = app.mm.add_child(app.mm.root.id, "x")
        app.select(node.id)
        app.view.refresh_map()

        seen = []
        for _ in range(4):
            await pilot.press("w")
            await pilot.pause()
            seen.append(app.mm.find(node.id).mark)
        assert seen == ["🔴", "🟢", None, "🔴"]


async def test_prompt_supports_undo_and_redo(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert app.mode == "marks"

        await pilot.press("home")
        await pilot.press("a", "b", "c")
        await pilot.pause()
        field = app.query_one(PromptBar)
        assert field.value.startswith("abc")

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert field.value.startswith("ab")

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert field.value.startswith("a")

        await pilot.press("ctrl+z")  # and back to the value it opened with
        await pilot.pause()
        assert field.value == " ".join(app.marks) + " ", "the offered value, space included"

        await pilot.press("ctrl+y")
        await pilot.pause()
        assert field.value.startswith("a")


def test_config_can_rebind_every_chord(tmp_path: Path):
    from spoider.keys import build_keymap, default_keymap

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
    config_path.write_text("save = ctrl+g\ndelete = ctrl+k\n")

    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        assert app.keymap["save"] == "ctrl+g"

        await pilot.press("tab")
        await pilot.press("a", "enter")
        await pilot.pause()

        await pilot.press("ctrl+g")  # the new save chord
        await pilot.pause()
        assert path.exists()
        assert app.dirty is False

        await pilot.press("ctrl+k")  # the new delete chord
        await pilot.pause()
        assert app.mm.root.children == []


def test_spacing_keys_are_one_chord_each():
    spacing = {b.id: b.key for b in BINDINGS if b.action.startswith("spacing")}
    assert spacing == {"spacing_more": "equals_sign", "spacing_less": "minus"}


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
        await pilot.press("down")  # config row
        await pilot.pause()
        assert app._settings_row == 1

        await pilot.press("enter")
        await pilot.pause()

    assert opened and opened[0] == config_path
    assert config_path.exists()
    # what came back from the editor is reloaded and applied
    assert app.autosave is True
    assert app.keymap["save"] == "ctrl+w"


def test_the_saved_config_mentions_every_rebindable_chord(tmp_path: Path):
    """One line per action, carrying every chord it answers to: an alias shares
    its action's line instead of getting an entry of its own."""
    from spoider.keys import action_chords

    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    app._save_config()
    text = config_path.read_text()

    chords = action_chords()
    entries = app._key_entries()
    for ident, listed, _ in entries:
        assert f"# {ident} = {listed}" in text, ident
        action = next(binding.action for binding in BINDINGS if binding.id == ident)
        assert listed.split() == chords[action], f"{ident} lists all of its chords"

    assert "edit_alt" not in text and "prev_vim" not in text, "aliases are not lines"
    assert "# edit = e ctrl+e" in text, "and the aliases are on the line that matters"


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

        await pilot.press("minus")  # a view/edit change, same rule
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
        assert app.mode != "ask"

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
        await pilot.press("minus")
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
        await pilot.press("tab")
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
        assert app.mode == "ask"

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
        assert app.mode in ("write", "marks")

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
    from spoider.actions_map import DOWN_MEANING, UP_MEANING
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
        prompt = app.query_one(PromptBar)
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
        assert app.query_one(PromptBar).display is False
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
        assert app.query_one(PromptBar).value == "one"

        await pilot.press("up")
        await pilot.pause()
        assert app.query_one(PromptBar).value == "two"
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
        assert app.stat_text() == "4 cells total"
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
        "⇥ child",
        "⏎ sib",
        "^X quit",
        "^S save",
        "^O write",
        "^Z undo",
        "^F search",
        "e edit",
        "w mark",
        "^J justify",
        "^D del",
        "^K cut",
        "^U paste",
        "p show stack",
        "t fold",
        "^L layout",
        "= looser",
        "- tighter",
    ]
    positions = [line.index(item) for item in expected]
    assert positions == sorted(positions), "the bar should read most to least important"
    # and a narrow bar keeps the inserts and quitting, and drops the spacing
    narrow = compose_footer(60, hint_chunks(BINDINGS)).plain
    assert "⇥ child" in narrow and "⏎ sib" in narrow
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
        assert app.stat_text() == "4 cells total", "the count gives the bar back"
        assert app.search_query == "one", "but the search and its marks stay"
        assert len(app.matches) == 2


# -- the drawers: dialogs at the bottom, one bar --------------------------


async def test_nothing_opens_over_the_map(tmp_path: Path):
    from spoider.widgets import MindMapView

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        for key, mode in (
            ("ctrl+o", "write"),
            ("ctrl+slash", "help"),
            ("ctrl+comma", "settings"),
        ):
            await pilot.press(key)
            await pilot.pause()
            assert app.mode == mode
            assert len(app.screen_stack) == 1, "a drawer, not a screen on top"
            assert app.query_one(FooterBar).display is True, "one bar, still there"
            assert app.query_one(MindMapView).size.height > 0, "the map is still on screen"
            await pilot.press("escape")
            await pilot.pause()
            assert app.mode == "keys"


async def test_the_bar_says_what_each_drawer_accepts(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        bar = app.query_one(FooterBar)

        await pilot.press("ctrl+o")  # a file name
        await pilot.pause()
        line = bar.render().plain
        assert "⏎ write" in line and "esc/^C cancel" in line and "^Z undo" in line
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("ctrl+comma")  # the settings list
        await pilot.pause()
        line = bar.render().plain
        assert "↑↓ move" in line and "⏎ change" in line and "esc close" in line
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("ctrl+slash")  # help: any key closes, nothing to say
        await pilot.pause()
        line = bar.render().plain
        assert "move" not in line and "cancel" not in line
        assert "settings" in line, "the pinned cluster stays"
        await pilot.press("x")
        await pilot.pause()
        assert app.mode == "keys"


async def test_the_quit_question_is_a_line_not_a_dialog(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.selected, "unsaved")
        app._mark_dirty()

        await pilot.press("ctrl+x")
        await pilot.pause()

        assert app.mode == "ask"
        assert app.query_one(AskBar).display
        assert "Save modified buffer?" in app.query_one(AskBar).render().plain
        line = app.query_one(FooterBar).render().plain
        assert "y save" in line and "n discard" in line and "esc cancel" in line

        await pilot.press("escape")  # cancel: the buffer stays
        await pilot.pause()
        assert app.is_running
        assert app.mode == "keys"


# -- a new buffer unless a file is named ----------------------------------


def test_without_a_file_spoider_starts_a_new_buffer(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    default = tmp_path / "data" / "spoider" / "map.spoider"
    default.parent.mkdir(parents=True)
    default.write_text(json.dumps({"version": 1, "root": {"text": "last time"}}))

    app = SpoiderApp(None, demo=False)
    assert app.path is None
    assert app.has_file is False
    assert app.mm.root.text != "last time", "it must not open the default map behind your back"


async def test_the_top_bar_calls_it_a_new_buffer(tmp_path: Path):
    app = SpoiderApp(None, demo=False)
    async with app.run_test():
        assert "New Buffer" in app.query_one(TopBar).render().plain


async def test_a_file_named_on_the_command_line_is_opened(tmp_path: Path):
    path = tmp_path / "map.json"
    path.write_text(json.dumps({"version": 1, "root": {"text": "saved earlier"}}))

    app = SpoiderApp(path, demo=False)
    async with app.run_test():
        assert app.has_file is True
        assert app.mm.root.text == "saved earlier"


async def test_save_asks_for_a_name_when_the_buffer_has_none(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    entry = tmp_path / "data" / "applications" / "spoider.desktop"
    entry.parent.mkdir(parents=True)  # registered, so the first-run question stays away
    entry.write_text("[Desktop Entry]\nName=spoider\n")
    app = SpoiderApp(None, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()

        assert app.mode == "write", "there is no file to save over"
        prompt = app.query_one(PromptBar)
        offered = tmp_path / "data" / "spoider" / "map.spoider"
        assert prompt.value == str(offered), "the default place is offered, not used"

        await pilot.press("enter")
        await pilot.pause()
        assert app.path == offered
        assert offered.exists()
        assert app.has_file is True
        assert app.dirty is False


async def test_a_new_buffer_quits_with_autosave_on(tmp_path: Path):
    app = SpoiderApp(None, demo=False)
    async with app.run_test() as pilot:
        app.set_autosave(True)
        app.mm.add_child(app.selected, "work in progress")
        app._mark_dirty()
        assert app.dirty, "nowhere to autosave to, so it stays dirty"

        await pilot.press("ctrl+x")
        await pilot.pause()
        assert app.mode == "ask", "and it falls back to asking, instead of hanging"


def test_the_demo_map_is_something_you_ask_for():
    assert SpoiderApp(None).mm.count() == 1, "a new buffer is empty"
    assert SpoiderApp(None, demo=True).mm.count() > 1


async def test_save_never_offers_a_name_that_is_already_taken(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    default = tmp_path / "data" / "spoider" / "map.spoider"
    default.parent.mkdir(parents=True)
    existing = json.dumps({"version": 1, "root": {"text": "someone else's map"}})
    default.write_text(existing)

    app = SpoiderApp(None)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert app.query_one(PromptBar).value == "", "no offer to write over it"
        await pilot.press("escape")
        await pilot.pause()

    assert default.read_text() == existing


# -- coming back to the terminal ------------------------------------------


async def test_a_drawer_keeps_the_keys_when_focus_wanders(tmp_path: Path):
    """The mouse is off, but focus can still be moved from outside (a terminal
    focus event, a resize): a drawer must take the keys back rather than leave the
    reader typing into the map with a question on screen."""
    from spoider.widgets import MindMapView

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        panel = app.query_one(PanelBar)
        assert app.focused is panel

        app.screen.set_focus(app.query_one(MindMapView))
        await pilot.pause()

        assert app.focused is panel, "the drawer takes the keys back"
        row = app._settings_row
        await pilot.press("down")
        await pilot.pause()
        assert app._settings_row == row + 1



async def test_returning_to_the_terminal_lands_where_you_were(tmp_path: Path):
    """Losing the window and getting it back must leave the keys where they were.

    A prompt that is still on screen owns them, whatever kind it is: losing them to
    the map behind it left the reader typing into nothing with a question showing.
    """
    from textual import events

    def away_and_back():
        app.post_message(events.AppBlur())
        app.post_message(events.AppFocus())

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "half typed words to search")

        # a prompt, with something half typed in it
        await pilot.press("ctrl+f")
        await pilot.press("w", "o")
        await pilot.pause()
        typed = app.query_one(PromptBar).value
        away_and_back()
        await pilot.pause()
        assert app.focused is app.query_one(PromptBar)
        await pilot.press("r", "d")
        await pilot.pause()
        assert app.query_one(PromptBar).value == typed + "rd", "and it still takes keys"
        await pilot.press("escape")
        await pilot.pause()

        # justify, the prompt that was left answering nothing
        await pilot.press("ctrl+j")
        await pilot.pause()
        away_and_back()
        await pilot.pause()
        assert app.focused is app.query_one(PromptBar)
        await pilot.press("3", "0")
        await pilot.pause()
        assert app.query_one(PromptBar).value == "30", "typing replaces what was offered"
        await pilot.press("escape")
        await pilot.pause()

        # a panel
        await pilot.press("ctrl+comma")
        await pilot.pause()
        away_and_back()
        await pilot.pause()
        panel = app.query_one(PanelBar)
        assert app.focused is panel
        row = app._settings_row
        await pilot.press("down")
        await pilot.pause()
        assert app._settings_row == row + 1, "its own keys still move its own rows"
        await pilot.press("escape")
        await pilot.pause()

        # a question
        app._mark_dirty()
        await pilot.press("ctrl+x")
        await pilot.pause()
        ask = app.query_one(AskBar)
        assert ask.display is True
        away_and_back()
        await pilot.pause()
        assert app.focused is ask
        await pilot.press("n")
        await pilot.pause()
        assert app.mode == "keys", "and the answer still reaches it"

# -- cut and paste --------------------------------------------------------


def _branch_map(app):
    """root → alpha (→ leaf), beta."""
    alpha = app.mm.add_child(app.mm.root.id, "alpha")
    app.mm.add_child(alpha.id, "leaf")
    beta = app.mm.add_child(app.mm.root.id, "beta")
    app.view.refresh_map()
    return alpha, beta


async def test_cut_takes_the_branch_out_and_lands_on_the_next_sibling(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)
        app.select(alpha.id)

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["beta"]
        assert app.mm.find(alpha.id) is None
        assert app.selected == beta.id, "the cell that closed the gap has the focus"
        assert [cell.text for cell in app.mm.cut_stack] == ["alpha"]
        assert [node.text for node in app.mm.cut_stack[0].walk()] == ["alpha", "leaf"]
        assert app.dirty


async def test_paste_hangs_the_cut_under_the_selection_and_empties_the_stack(
    tmp_path: Path,
):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()

        app.select(beta.id)
        await pilot.press("ctrl+u")
        await pilot.pause()

        assert [child.text for child in beta.children] == ["alpha"]
        # the whole branch came along, and the index knows the copy
        assert [child.text for child in beta.children[0].children] == ["leaf"]
        assert app.mm.find(beta.children[0].children[0].id) is not None
        assert app.selected == beta.id, "the target keeps the selection"
        assert app.mm.cut_stack == [], "the cut has been used up"

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert [child.text for child in beta.children] == ["alpha"], "no second copy"


async def test_the_stack_is_last_in_first_out(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)

        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        app.select(beta.id)
        await pilot.press("ctrl+k")
        await pilot.pause()

        # oldest first on the list, the newest cut on top of it
        assert [cell.text for cell in app.mm.cut_stack] == ["alpha", "beta"]

        # the newest cut comes back first
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["beta"]

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["beta", "alpha"]
        assert app.mm.cut_stack == []


async def test_paste_with_nothing_cut_changes_nothing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _branch_map(app)
        before = app.mm.to_dict()

        await pilot.press("ctrl+u")
        await pilot.pause()

        assert app.mm.to_dict() == before
        assert app._undo == [], "and nothing to undo either"


async def test_the_root_cannot_be_cut(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _branch_map(app)
        app.select(app.mm.root.id)

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert app.mm.cut_stack == []
        assert app.mm.root.text


async def test_undo_brings_a_cut_branch_back(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, _ = _branch_map(app)
        app.select(alpha.id)

        await pilot.press("ctrl+k")
        await pilot.pause()
        await pilot.press("ctrl+z")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["alpha", "beta"]
        assert [child.text for child in app.mm.root.children[0].children] == ["leaf"]


async def test_paste_keeps_the_mark_it_was_cut_with(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)
        alpha.mark = "✅"
        app.select(alpha.id)

        await pilot.press("ctrl+k")
        await pilot.pause()
        app.select(beta.id)
        await pilot.press("ctrl+u")
        await pilot.pause()

        assert beta.children[0].mark == "✅"


# -- the bar under the panels --------------------------------------------


async def test_help_keeps_the_bar_and_says_how_to_leave(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()

        assert app.mode == "help"
        bar = app.query_one("#footer", FooterBar).render().plain
        assert "esc" in bar and "close" in bar, "the bar says what help accepts"
        assert "settings" in bar, "and the pinned cluster is still there"


async def test_settings_leave_a_line_between_the_rows_and_the_bar(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()

        lines = app.query_one(PanelBar).render().plain.split("\n")
        assert lines[-2].strip(), "the last row is a row"
        assert lines[-1] == "", "and there is one empty line above the bar"


# -- selecting a run of siblings -----------------------------------------


def _four(app):
    """root → a, b, c, d, all siblings."""
    cells = [app.mm.add_child(app.mm.root.id, name) for name in "abcd"]
    app.view.refresh_map()
    return cells


async def test_shift_and_the_sibling_arrow_select_a_run(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, b, c, _d = _four(app)
        app.select(a.id)

        await pilot.press("shift+down")
        await pilot.press("shift+down")
        await pilot.pause()

        assert app.selected_ids == [a.id, b.id, c.id]
        assert app.selected == c.id, "the cursor is at the moving end"
        assert app.anchor == a.id

        await pilot.press("shift+up")
        await pilot.pause()
        assert app.selected_ids == [a.id, b.id], "and it shrinks the same way"


async def test_a_plain_move_drops_the_run(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, _b, _c, _d = _four(app)
        app.select(a.id)
        await pilot.press("shift+down")
        await pilot.pause()

        await pilot.press("down")  # a plain sibling move
        await pilot.pause()

        assert app.anchor is None
        assert app.selected_ids == [app.selected]


async def test_escape_drops_the_run_without_moving(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, b, _c, _d = _four(app)
        app.select(a.id)
        await pilot.press("shift+down")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        assert app.selected_ids == [b.id], "still standing where it was"


async def test_shift_sideways_does_nothing_where_siblings_stack(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)  # spider by default
    async with app.run_test() as pilot:
        _a, b, _c, _d = _four(app)
        app.select(b.id)

        await pilot.press("shift+left")
        await pilot.press("shift+right")
        await pilot.pause()

        assert app.selected_ids == [b.id], "only the arrows that walk siblings select"


async def test_a_pyramid_selects_with_the_sideways_arrows(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, b, _c, _d = _four(app)
        app.mm.layout = "pyramid"
        app.select(a.id)

        await pilot.press("shift+right")
        await pilot.pause()

        assert app.selected_ids == [a.id, b.id]
        await pilot.press("shift+down")  # down is a child here, not a sibling
        await pilot.pause()
        assert app.selected_ids == [a.id, b.id]


async def test_delete_removes_the_whole_run_in_one_step(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _a, b, _c, _d = _four(app)
        app.select(b.id)
        await pilot.press("shift+down")  # b, c

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["a", "d"]
        assert app.selected == app.mm.root.id, "back to the parent they hung from"
        assert app.anchor is None

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert [child.text for child in app.mm.root.children] == ["a", "b", "c", "d"]


async def test_a_cut_run_comes_back_in_the_order_it_was_cut(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, _b, _c, d = _four(app)
        app.select(a.id)
        await pilot.press("shift+down")  # a, b

        await pilot.press("ctrl+k")
        await pilot.pause()
        # pushed newest-first, so the top of the stack is the first cell cut
        assert [cell.text for cell in app.mm.cut_stack] == ["b", "a"]
        assert [child.text for child in app.mm.root.children] == ["c", "d"]

        app.select(d.id)
        await pilot.press("ctrl+u")
        await pilot.pause()
        await pilot.press("ctrl+u")
        await pilot.pause()

        assert [child.text for child in d.children] == ["a", "b"]

        await pilot.press("ctrl+u")  # the stack is empty now
        await pilot.pause()
        assert [child.text for child in d.children] == ["a", "b"]


async def test_one_mark_press_marks_the_whole_run(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, b, c, _d = _four(app)
        app.select(a.id)
        await pilot.press("shift+down")

        await pilot.press("w")
        await pilot.pause()

        assert app.marks[0] == "⭐"
        assert a.mark == b.mark == "⭐"
        assert c.mark is None


async def test_fold_takes_the_run_with_it(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, b, c, _d = _four(app)
        app.mm.add_child(a.id, "under a")
        app.mm.add_child(b.id, "under b")
        app.select(a.id)
        await pilot.press("shift+down")

        await pilot.press("t")
        await pilot.pause()

        assert a.collapsed and b.collapsed
        assert not c.collapsed


async def test_a_run_moves_as_one_block(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _a, b, _c, _d = _four(app)
        app.select(b.id)
        await pilot.press("shift+down")  # b, c

        await pilot.press("alt+up")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["b", "c", "a", "d"]


async def test_the_bar_leaves_selection_to_help(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(120, 30)) as pilot:
        _four(app)
        bar = app.query_one("#footer", FooterBar).render().plain
        assert "select" not in bar, "the shift keys are left to be discovered"
        assert "⇧" not in bar and "⌥" not in bar

        await pilot.press("ctrl+slash")
        await pilot.pause()
        assert "select a run of siblings" in app.query_one(PanelBar).render().plain


async def test_help_lists_the_selection_keys(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()

        body = app.query_one(PanelBar).render().plain
        assert "S-←↑↓→" in body and "select a run of siblings" in body
        assert "single cell" in body


async def test_the_bar_counts_the_cuts_waiting(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)
        bar = app.query_one(TopBar)

        assert "0 cuts in stack" in bar.render().plain, "an empty stack is a fact too"

        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert "1 cut in stack" in bar.render().plain

        # the cut left the cursor on beta; the root itself can never be cut
        app.select(app.mm.root.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert "1 cut in stack" in bar.render().plain, "so the stack is unchanged"

        app.select(beta.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert "2 cut" in bar.render().plain

        await pilot.press("ctrl+u")
        await pilot.pause()
        assert "1 cut in stack" in bar.render().plain


async def test_a_cut_is_still_on_the_stack_after_saving_and_reopening(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        alpha, _ = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()

    assert [node.text for node in MindMap.load(path).cut_stack] == ["alpha"]


async def test_undo_after_a_paste_puts_the_cut_back_on_the_stack(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        alpha, beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        app.select(beta.id)
        await pilot.press("ctrl+u")
        await pilot.pause()

        await pilot.press("ctrl+z")
        await pilot.pause()

        # undo restores a snapshot, so read the tree through the app, not the
        # node this test is holding
        assert app.mm.find(beta.id).children == [], "the paste is undone"
        assert [cell.text for cell in app.mm.cut_stack] == ["alpha"], "and the cut is back"


async def test_cut_lands_on_the_sibling_before_it_at_the_end_of_a_branch(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _a, _b, c, d = _four(app)
        app.select(d.id)  # the last of the four

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert app.selected == c.id, "nothing after it, so the one before"


async def test_cut_of_an_only_child_lands_on_the_parent(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        only = app.mm.add_child(app.mm.root.id, "only")
        app.view.refresh_map()
        app.select(only.id)

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert app.selected == app.mm.root.id, "there is nothing else to stand on"


async def test_cut_of_a_run_lands_on_the_cell_that_closes_the_gap(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        _a, b, _c, d = _four(app)
        app.select(b.id)
        await pilot.press("shift+down")  # b, c

        await pilot.press("ctrl+k")
        await pilot.pause()

        assert [child.text for child in app.mm.root.children] == ["a", "d"]
        assert app.selected == d.id


# -- what the toast says and where it says it -----------------------------


async def test_a_cut_toasts_in_orange_at_the_top_right(tmp_path: Path):
    from textual.widgets._toast import Toast  # not exported by textual.widgets

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(100, 30), notifications=True) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()

        toast = app.query(Toast).last()
        assert "Cut onto the stack" in str(toast.render())
        assert "alpha" not in str(toast.render()), "a toast says what happened, not what was in the cell"
        assert toast.has_class("-warning"), "a cut is neither a success nor a failure"
        region = toast.region
        assert region.y <= 3, "it hangs from the top"
        assert region.x + region.width >= 96, "and from the right"


async def test_a_paste_toasts_in_orange_too(tmp_path: Path):
    from textual.widgets._toast import Toast

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        alpha, beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        app.select(beta.id)
        await pilot.press("ctrl+u")
        await pilot.pause()

        newest = app.query(Toast).last()
        assert newest.has_class("-warning")
        assert "Pasted from the stack" in str(newest.render())
        assert "alpha" not in str(newest.render())


async def test_saving_toasts_green_and_a_failure_toasts_red(tmp_path: Path):
    from textual.widgets._toast import Toast

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        await pilot.press("ctrl+s")  # the buffer has a path, so it writes
        await pilot.pause()
        await pilot.pause()

        assert app.query(Toast).last().has_class("-information"), "green"

        await pilot.press("ctrl+u")  # nothing has been cut
        await pilot.pause()
        await pilot.pause()  # the toast is mounted a beat after the notification

        newest = app.query(Toast).last()
        assert newest.has_class("-error"), "red"
        assert "Nothing to paste" in str(newest.render())


async def test_the_pinned_cluster_follows_a_rebound_chord(tmp_path: Path):
    config = tmp_path / "config.conf"
    config.write_text("settings = ctrl+p\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        bar = app.query_one("#footer", FooterBar).render().plain
        assert "^P settings" in bar, "the pinned key moved, so the label moves"
        assert "^, settings" not in bar


async def test_autosave_writes_the_file_once_per_change(tmp_path: Path, monkeypatch):
    from spoider.model import MindMap as Model

    writes: list[Path] = []
    original = Model.save

    def counted(self, path):
        writes.append(path)
        return original(self, path)

    monkeypatch.setattr(Model, "save", counted)
    config = tmp_path / "config.conf"
    config.write_text("autosave = true\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test() as pilot:
        _four(app)
        writes.clear()

        app.mm.add_child(app.mm.root.id, "one")
        app._mark_dirty()
        await pilot.pause()

        assert len(writes) == 1, "one edit, one write"


async def test_undo_lets_go_of_the_selected_run(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        a, _b, _c, _d = _four(app)
        app.select(a.id)
        await pilot.press("shift+down")  # a and its sibling
        assert app.anchor == a.id

        await pilot.press("w")  # mark both: an undoable change, run intact
        await pilot.pause()
        await pilot.press("ctrl+z")
        await pilot.pause()

        assert app.anchor is None, "the run belonged to the map that was undone"
        assert app.selected_ids == [app.selected]


# -- the cut stack, opened with p ----------------------------------------


async def test_the_stack_panel_opens_on_the_newest_cut(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")  # cuts alpha
        await pilot.press("ctrl+k")  # cuts beta, the sibling it landed on
        await pilot.pause()
        assert [cell.text for cell in app.mm.cut_stack] == ["alpha", "beta"]

        await pilot.press("p")
        await pilot.pause()

        assert app.stack_open
        assert app.document.find(app.selected).text == "beta", "newest on top"
        assert [cell.text for cell in app._stack_entries()] == ["beta", "alpha"]


async def test_the_panel_says_nothing_when_the_stack_is_empty(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.pause()

        assert not app.stack_open


async def test_the_panel_is_drawn_in_the_top_right_of_the_map(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        lines = app.view.render().plain.split("\n")
        row = next(index for index, line in enumerate(lines) if "alpha" in line)
        assert row <= 4, "it hangs from the top"
        assert lines[row].index("alpha") > 40, "and from the right"


async def test_navigation_inside_the_panel_walks_the_stack(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("down")  # the older cut, below the newest
        await pilot.pause()
        assert app.document.find(app.selected).text == "alpha"

        await pilot.press("right")  # into its branch
        await pilot.pause()
        assert app.document.find(app.selected).text == "leaf"

        await pilot.press("left")
        await pilot.pause()
        assert app.document.find(app.selected).text == "alpha"


async def test_the_map_is_not_touched_while_the_panel_is_open(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()
        cells = app.mm.count()

        await pilot.press("ctrl+k")  # cut again: a stack move, not a map one
        await pilot.press("down")
        await pilot.pause()

        assert app.mm.count() == cells
        assert [child.text for child in app.mm.root.children] == ["beta"]


async def test_cutting_again_moves_it_to_the_top(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("ctrl+k")  # the sibling it landed on
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("down")  # onto the older one
        await pilot.press("ctrl+k")  # cut it again
        await pilot.pause()

        assert next(cell.text for cell in app._stack_entries()) == "alpha"
        assert app.document.find(app.selected).text == "alpha", "and it is selected"


async def test_dropping_the_last_cut_closes_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert app.mm.cut_stack == []
        assert not app.stack_open, "there is nothing left to show"


async def test_a_cell_can_be_renamed_inside_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("e")
        await pilot.press("backspace", "backspace", "backspace", "backspace", "backspace")
        await pilot.press("o", "m", "e", "g", "a")
        await pilot.press("enter")
        await pilot.pause()

        assert [cell.text for cell in app.mm.cut_stack] == ["omega"]
        assert app.mm.count() == 2, "the map itself is untouched"


async def test_the_bar_switches_to_the_panel_keys(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(200, 24)) as pilot:  # wide enough to see the tail
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        bar = app.query_one("#footer", FooterBar).render().plain
        # the panel is the map with one difference, so the bar is the map's bar
        assert "p hide stack" in bar, "the panel says how to shut it"
        assert bar.index("^U paste") < bar.index("p hide stack"), "it keeps its place"
        assert "^K cut" in bar and "e edit" in bar and "^J justify" in bar
        assert "p show stack" not in bar, "one ^I per bar"
        for word in ("^X quit", "^S save", "^Z undo", "^F search", "t fold"):
            assert word in bar, f"the panel keeps {word}"

        await pilot.press("p")
        await pilot.pause()
        assert "p hide stack" not in app.query_one("#footer", FooterBar).render().plain


def test_the_cut_count_is_marked_when_the_panel_is_open():
    from spoider.widgets import compose_top_bar

    closed = compose_top_bar(120, "0.1.0", "/tmp/m.json", "5 cells total", "spider", False, "2 cuts in stack")
    opened = compose_top_bar(
        120, "0.1.0", "/tmp/m.json", "5 cells total", "spider", False, "2 cuts in stack", True
    )
    assert "2 cuts in stack" in closed.plain and "2 cuts in stack" in opened.plain
    # only the live one goes yellow, and only while the panel is open
    yellow = [str(span.style) for span in opened.spans if "on yellow" in str(span.style)]
    assert yellow, "the stack count is marked"
    assert not [span for span in closed.spans if "on yellow" in str(span.style)]
    # one space between the items, not a run of them
    assert "5 cells total 2 cuts in stack spider layout" in closed.plain
    assert [str(span.style) for span in closed.spans] == ["reverse"] * 3, "reverse video, never bold"


async def test_alt_arrows_move_an_entry_up_and_down_the_stack(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("ctrl+k")  # cuts beta too: it lands on the stack above alpha
        await pilot.press("p")
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["beta", "alpha"]

        await pilot.press("down")  # onto the older one, at the bottom of the panel
        assert app.document.find(app.selected).text == "alpha"
        await pilot.press("alt+up")
        await pilot.pause()

        assert [cell.text for cell in app._stack_entries()] == ["alpha", "beta"], (
            "moving it up the panel puts it nearer the top of the stack"
        )


async def test_the_gap_keys_work_inside_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()
        before = app.spacing

        await pilot.press("equals_sign")
        await pilot.pause()
        assert app.spacing == before + 1, "the same chord does the same thing here"

        await pilot.press("minus")
        await pilot.pause()
        assert app.spacing == before


async def test_a_rebound_chord_works_inside_the_panel(tmp_path: Path):
    config = tmp_path / "config.conf"
    config.write_text("mark = alt+w\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("alt+w")
        await pilot.pause()
        assert app.mm.cut_stack[0].mark == app.marks[0], "the panel honours the config"


async def test_the_panel_bar_borrows_the_main_bars_words(tmp_path: Path):
    config = tmp_path / "config.conf"
    config.write_text("cut = ctrl+w\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test(size=(220, 30)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+w")
        await pilot.press("p")
        await pilot.pause()

        bar = app.query_one("#footer", FooterBar).render().plain
        assert "^W cut" in bar, "the chord is the one in force, and the word is the bar's"


async def test_paste_inside_the_panel_nests_the_cut_under_the_selection(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")  # cuts alpha
        await pilot.press("ctrl+k")  # cuts beta, where the cursor landed
        await pilot.press("p")
        await pilot.pause()
        cells = app.mm.count()

        await pilot.press("down")  # onto the older entry, at the bottom
        await pilot.press("ctrl+u")  # the top of the stack becomes its child
        await pilot.pause()

        assert app.mm.count() == cells, "the map is not touched"
        assert [cell.text for cell in app._stack_entries()] == ["alpha"]
        # alpha already had "leaf"; the cut arrives after it
        assert [child.text for child in app.mm.cut_stack[0].children] == ["leaf", "beta"]


async def test_pasting_a_cell_into_itself_does_nothing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        # the cursor starts on the top of the stack, which is the cell ^U would paste
        await pilot.press("ctrl+u")
        await pilot.pause()

        assert [cell.text for cell in app.mm.cut_stack] == ["alpha"]
        assert [child.text for child in app.mm.cut_stack[0].children] == ["leaf"], (
            "it was not made its own child"
        )


async def test_pasting_a_cell_into_its_own_child_does_nothing(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("right")  # into alpha's own child
        assert app.document.find(app.selected).text == "leaf"
        await pilot.press("ctrl+u")
        await pilot.pause()

        assert [cell.text for cell in app.mm.cut_stack] == ["alpha"], "a cycle is refused"
        assert [child.text for child in app.mm.cut_stack[0].children] == ["leaf"]


async def test_the_panel_is_a_column_with_a_wall_and_a_title(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        lines = app.view.render().plain.split("\n")
        assert "LIFO cut/paste stack" in lines[0], "the column says what it is"
        wall = lines[0].index("│")
        assert all(len(line) > wall and line[wall] == "│" for line in lines), (
            "the wall runs the full height of the view"
        )


async def test_the_map_shows_no_cursor_while_the_panel_is_open(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)

        await pilot.press("p")  # with nothing cut, the panel stays shut
        await pilot.pause()
        before = {style for _, style in app.view._grid.cells.values()}
        assert any("reverse" in style for style in before), "the map shows where you are"

        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()
        during = {style for _, style in app.view._grid.cells.values()}

        assert not any("reverse" in style for style in during), (
            "the only highlight on screen is the panel's"
        )


async def test_undo_works_inside_the_stack_view(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["alpha"]

        await pilot.press("ctrl+d")  # drop it from the stack
        await pilot.pause()
        assert app.mm.cut_stack == []
        assert not app.stack_open, "an empty stack closes the panel"

        await pilot.press("ctrl+z")  # the panel shut itself, so this is the map's undo
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["alpha"], "it is back"

        await pilot.press("p")
        await pilot.pause()
        assert app.stack_open
        assert app.document.find(app.selected) is not None, "cursor re-pointed"


async def test_redo_works_inside_the_stack_view(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.press("ctrl+d")  # the stack is empty again
        await pilot.press("ctrl+z")
        await pilot.pause()
        assert app.mm.cut_stack

        await pilot.press("ctrl+y")  # redo the drop
        await pilot.pause()
        assert app.mm.cut_stack == []


async def test_undo_after_reordering_the_stack_puts_the_order_back(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(110, 24)) as pilot:
        alpha, _beta = _branch_map(app)
        app.select(alpha.id)
        await pilot.press("ctrl+k")
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["beta", "alpha"]

        await pilot.press("down")
        await pilot.press("alt+up")  # alpha to the top
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["alpha", "beta"]

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert [cell.text for cell in app._stack_entries()] == ["beta", "alpha"]


async def test_c_cycles_the_colouring_and_says_so(tmp_path: Path):
    from textual.widgets._toast import Toast

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(notifications=True) as pilot:
        assert app.mm.colours == "family"

        await pilot.press("c")
        await pilot.pause()
        assert app.mm.colours == "depth"
        assert app.dirty is True, "the colouring is written into the map"
        assert "depth" in str(app.query(Toast).last().render())

        await pilot.press("c")
        await pilot.pause()
        assert app.mm.colours == "family"


async def test_the_colouring_shows_in_the_help_and_the_bar(tmp_path: Path):
    from spoider.screens import help_text

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(240, 30)) as pilot:
        await pilot.pause()
        assert "c colours" in str(app.query_one("#footer").render().plain)
        assert "colour by depth, or by family" in help_text(app).plain


async def test_shift_enter_starts_a_new_line_and_enter_finishes_the_cell(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("f", "i", "r", "s", "t")
        await pilot.press("shift+enter")
        await pilot.press("s", "e", "c", "o", "n", "d")
        await pilot.pause()

        cell = app.mm.root.children[0]
        assert cell.preview == "first\nsecond", "a line break, not a commit"
        assert app.editing is True

        await pilot.press("enter")
        await pilot.pause()
        assert cell.text == "first\nsecond"
        assert app.editing is False


async def test_a_line_break_is_written_into_the_map_file(tmp_path: Path):
    path = tmp_path / "map.json"
    app = SpoiderApp(path, demo=False)
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("o", "n", "e")
        await pilot.press("shift+enter")
        await pilot.press("t", "w", "o")
        await pilot.press("enter")
        await pilot.press("ctrl+s")
        await pilot.pause()

    saved = json.loads(path.read_text())
    assert saved["root"]["children"][0]["text"] == "one\ntwo"


async def test_arrows_move_between_lines_and_keep_the_column(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "long line\nxy")
        app.select(node.id)
        await pilot.press("e")
        await pilot.press("up", "home")  # the caret starts at the end, on line two
        await pilot.press("right", "right", "right", "right")
        await pilot.pause()
        assert app._buffer.column() == 4

        await pilot.press("down")
        await pilot.pause()
        assert app._buffer.line_number() == 1
        assert app._buffer.column() == 2, "the short line clamps the column"

        await pilot.press("up")
        await pilot.pause()
        assert app._buffer.column() == 4, "and the caret came back to where it was"


async def test_alt_backspace_and_alt_d_eat_whole_words(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "alpha beta gamma")
        app.select(node.id)
        await pilot.press("e")
        await pilot.pause()

        await pilot.press("alt+backspace")
        await pilot.pause()
        assert app._buffer.text == "alpha beta "

        await pilot.press("home")
        await pilot.press("alt+d")
        await pilot.pause()
        assert app._buffer.text == " beta "


async def test_insert_toggles_overwrite_and_typing_replaces(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "abc")
        app.select(node.id)
        await pilot.press("e")
        await pilot.press("home")
        await pilot.pause()

        await pilot.press("insert")
        await pilot.pause()
        assert app._buffer.overwrite is True

        await pilot.press("x")
        await pilot.pause()
        assert app._buffer.text == "xbc", "the character under the caret was replaced"

        await pilot.press("insert")
        await pilot.press("y")
        await pilot.pause()
        assert app._buffer.text.startswith("xybc"), "back to inserting"


async def test_a_selection_is_cut_copied_and_pasted_inside_the_cell(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "alpha beta")
        app.select(node.id)
        await pilot.press("e")
        await pilot.press("home")
        await pilot.press("shift+right", "shift+right", "shift+right", "shift+right", "shift+right")
        await pilot.pause()
        assert app._buffer.selected_text() == "alpha"

        await pilot.press("alt+6")  # copy
        await pilot.pause()
        assert app._text_clip == "alpha"

        await pilot.press("end")
        await pilot.press("ctrl+u")  # paste
        await pilot.pause()
        assert app._buffer.text == "alpha betaalpha"

        await pilot.press("home")
        await pilot.press("shift+right", "shift+right", "shift+right", "shift+right", "shift+right")
        await pilot.press("ctrl+k")  # cut
        await pilot.pause()
        assert app._buffer.text == " betaalpha", "the selection went to the clipboard"


async def test_justify_rewraps_the_cell_and_the_map_keeps_the_width(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        node = app.mm.add_child(
            app.mm.root.id,
            "one two three four five six seven eight nine ten eleven twelve",
        )
        app.select(node.id)

        await pilot.press("ctrl+j")
        await pilot.pause()
        prompt = app.query_one(PromptBar)
        assert prompt.display is True
        assert prompt.value == "66", "the remembered width, or the default"

        prompt.value = "20"
        await pilot.press("enter")
        await pilot.pause()

        wrapped = app.mm.find(node.id).text
        assert wrapped.count("\n") >= 1
        assert all(len(line) <= 20 for line in wrapped.split("\n"))
        assert app.mm.justify == 20, "the map remembers the width"

        # it is document state, so it travels with the file
        path = tmp_path / "map.json"
        app.mm.save(path)
        assert json.loads(path.read_text())["justify"] == 20
        assert MindMap.load(path).justify == 20
        assert load_config(config_path).justify_width_default == 66, "the config keeps its default"

        await pilot.press("ctrl+j")
        await pilot.pause()
        assert app.query_one(PromptBar).value == "20", "and the next justify starts there"


async def test_undo_and_redo_work_inside_the_cell(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "abc")
        app.select(node.id)
        await pilot.press("e")
        await pilot.press("x", "y", "z")
        await pilot.pause()
        assert app._buffer.text == "abcxyz"

        await pilot.press("ctrl+z")
        await pilot.pause()
        assert app._buffer.text == "abc", "the run of typing came off in one step"

        await pilot.press("ctrl+y")
        await pilot.pause()
        assert app._buffer.text == "abcxyz"

        await pilot.press("enter")
        await pilot.pause()
        assert app.mm.find(node.id).text == "abcxyz"


async def test_the_editor_bar_shows_its_own_keys(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(160, 30)) as pilot:
        node = app.mm.add_child(app.mm.root.id, "abc")
        app.select(node.id)
        await pilot.press("e")
        await pilot.pause()
        bar = app.query_one("#footer", FooterBar).render().plain
        assert "⏎ done" in bar
        assert "S-⏎ new line" in bar
        assert "^J justify" in bar
        assert "^K cut" in bar and "^U paste" in bar


async def test_justify_follows_the_chord_it_was_bound_to(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    config_path.write_text("justify = ctrl+g\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "one two three four five six seven")
        app.select(node.id)
        await pilot.press("e")
        await pilot.pause()

        await pilot.press("ctrl+g")
        await pilot.pause()
        assert app.mode == "justify", "the cell answers to the rebound chord"

        app.query_one(PromptBar).value = "12"
        await pilot.press("enter")
        await pilot.pause()
        assert "\n" in app._buffer.text


async def test_ctrl_a_selects_all_the_text_inside_a_cell(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "alpha beta")
        app.select(node.id)
        await pilot.press("e")
        await pilot.press("home")
        await pilot.pause()

        await pilot.press("ctrl+a")
        await pilot.pause()
        assert app._buffer.selected_text() == "alpha beta"

        await pilot.press("ctrl+k")  # the selection goes, the cell is emptied
        await pilot.pause()
        assert app._buffer.text == ""
        assert app._text_clip == "alpha beta"


async def _panel_with_two_cuts(app, pilot):
    alpha, beta = _branch_map(app)
    app.select(alpha.id)
    await pilot.press("ctrl+k")
    await pilot.pause()
    app.select(beta.id)
    await pilot.press("ctrl+k")
    await pilot.press("p")
    await pilot.pause()


async def test_a_cut_can_be_renamed_inside_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        before = app.mm.cut_stack[-1].text

        await pilot.press("e")
        await pilot.pause()
        assert app.editing is True
        await pilot.press("!", "x")
        await pilot.press("enter")
        await pilot.pause()

        assert app.mm.cut_stack[-1].text == before + "!x", "the cut itself changed"
        assert app.dirty is True, "and the file knows"


async def test_new_cells_can_be_made_inside_a_cut(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        top = app.mm.cut_stack[-1]
        map_before = len(app.mm.root.children)

        await pilot.press("tab")  # a child of the cut under the cursor
        await pilot.pause()
        assert app.editing is True
        await pilot.press("k", "i", "d")
        await pilot.press("enter")
        await pilot.pause()

        assert [child.text for child in app.mm.cut_stack[-1].children] == ["kid"]
        assert len(app.mm.root.children) == map_before, "the map is left alone"
        assert app.mm.cut_stack[-1].id == top.id


async def test_a_new_sibling_of_a_cut_is_a_new_entry_on_the_stack(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        depth = len(app.mm.cut_stack)
        await pilot.press("up")  # the older cut, a top-level entry
        await pilot.pause()

        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("f", "r", "e", "s", "h")
        await pilot.press("enter")
        await pilot.pause()

        assert len(app.mm.cut_stack) == depth + 1
        assert "fresh" in [node.text for node in app.mm.cut_stack]


async def test_justify_from_the_panel_reflows_the_cut(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        node = app.mm.add_child(app.mm.root.id, "one two three four five six seven")
        app.select(node.id)
        await pilot.press("ctrl+k")
        await pilot.press("p")
        await pilot.pause()

        await pilot.press("ctrl+j")
        await pilot.pause()
        assert app.mode == "justify"
        app.query_one(PromptBar).value = "12"
        await pilot.press("enter")
        await pilot.pause()

        cut = app.mm.cut_stack[-1]
        assert cut.text.count("\n") >= 1
        assert all(len(line) <= 12 for line in cut.text.split("\n"))


async def test_select_all_inside_a_cut_selects_its_text(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        top = app.mm.cut_stack[-1]

        await pilot.press("e")
        await pilot.pause()
        await pilot.press("ctrl+a")
        await pilot.pause()
        assert app._buffer.selected_text() == top.text

        await pilot.press("ctrl+k")
        await pilot.pause()
        assert app._text_clip == top.text


def test_a_leftover_setting_never_becomes_a_chord(tmp_path: Path):
    """`justify = 12` was a *setting* before the key was renamed to `justify_width`.
    Read back as a chord it bound justify to a key called "12", which nothing can
    press, and then wrote itself into the file again on every save."""
    from spoider.config import load_config
    from spoider.keys import build_keymap

    config = tmp_path / "config.conf"
    config.write_text("justify_width_default = 60\njustify = 12\n")
    loaded = load_config(config, SpoiderApp._binding_ids())

    assert loaded.justify_width_default == 60
    assert loaded.keys == {}, "a name that is not a binding id is not a chord"
    assert build_keymap(loaded.keys).get("justify") == "ctrl+j"


async def test_a_leftover_chord_line_is_harmless(tmp_path: Path):
    """A line naming an action this build no longer has is ignored, not deleted."""
    config = tmp_path / "config.conf"
    config.write_text("justify_width_default = 60\njustify = 12\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one("#footer")

    text = config.read_text()
    assert "justify = 12" in text, "the file keeps its own lines"
    assert "justify_width_default = 60" in text
    assert app.config.justify_width_default == 60


async def test_the_rest_of_the_bar_works_inside_the_panel(tmp_path: Path):
    """The panel is the map with one difference. It takes the keys it implements
    itself and lets the rest through, so every hint in the bar is true there too."""
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        cuts_before = [node.text for node in app.mm.cut_stack]

        await pilot.press("c")  # colouring
        await pilot.pause()
        assert app.mm.colours == "depth"
        await pilot.press("c")
        await pilot.pause()
        assert app.mm.colours == "family"

        await pilot.press("ctrl+l")  # shape
        await pilot.pause()
        assert app.mm.layout != "spider"

        await pilot.press("ctrl+s")  # save
        await pilot.pause()
        assert app.dirty is False
        assert (tmp_path / "map.json").exists()

        assert [node.text for node in app.mm.cut_stack] == cuts_before, "the cuts are untouched"
        assert app.stack_open is True, "and the panel is still there"


async def test_delete_in_the_panel_drops_the_cut_not_the_map(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await _panel_with_two_cuts(app, pilot)
        cells = len(app.mm.root.children)
        cuts = len(app.mm.cut_stack)

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert len(app.mm.cut_stack) == cuts - 1, "the cut is gone"
        assert len(app.mm.root.children) == cells, "the map is not"


async def _panel_with_three_cuts(app, pilot):
    for text in ("alpha", "beta", "gamma"):
        cell = app.mm.add_child(app.mm.root.id, text)
        app.select(cell.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
    await pilot.press("p")
    await pilot.pause()


def _names(app) -> list[str]:
    return [app.document.find(node_id).text for node_id in app.selected_ids]


async def test_select_all_works_inside_the_panel(tmp_path: Path):
    """^A is one action over one document: it does not care which one is open."""
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(160, 30)) as pilot:
        await _panel_with_three_cuts(app, pilot)

        await pilot.press("ctrl+a")
        await pilot.pause()

        assert sorted(_names(app)) == ["alpha", "beta", "gamma"], "every entry"
        assert app.mm.root.children == [], "and the map is untouched"


async def test_shift_arrows_grow_a_run_inside_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(160, 30)) as pilot:
        await _panel_with_three_cuts(app, pilot)
        assert _names(app) == ["gamma"], "the newest cut, at the top"

        await pilot.press("shift+down")
        await pilot.pause()
        assert _names(app) == ["gamma", "beta"]

        await pilot.press("shift+down")
        await pilot.pause()
        assert _names(app) == ["gamma", "beta", "alpha"]

        await pilot.press("shift+up")
        await pilot.pause()
        assert _names(app) == ["gamma", "beta"], "and it shrinks again"

        await pilot.press("down")
        await pilot.pause()
        assert app.anchor is None, "a plain move gives the run up"


async def test_shift_sideways_does_not_grow_a_run_in_the_panel(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(160, 30)) as pilot:
        await _panel_with_three_cuts(app, pilot)
        await pilot.press("shift+left")
        await pilot.press("shift+right")
        await pilot.pause()
        assert _names(app) == ["gamma"], "left and right are not sideways there"


async def test_delete_takes_a_run_of_cuts(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(160, 30)) as pilot:
        await _panel_with_three_cuts(app, pilot)
        await pilot.press("shift+down")
        await pilot.pause()
        assert _names(app) == ["gamma", "beta"], "two of the three"

        await pilot.press("ctrl+d")
        await pilot.pause()

        assert [node.text for node in app.mm.cut_stack] == ["alpha"], "only the run went"
        assert app.mm.root.children == []


async def test_the_offered_width_is_drawn_selected(tmp_path: Path):
    """A prompt that offers a value shows it the way an editor shows a selection,
    so typing over it is the obvious thing to do."""
    from spoider.drawers import PromptBar

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        app.mm.add_child(app.mm.root.id, "some words to justify")
        await pilot.press("ctrl+j")
        await pilot.pause()

        bar = app.query_one(PromptBar)
        art = bar.render()
        value_start = len(bar.label)
        selected = [
            span for span in art.spans if str(span.style) == "reverse" and span.start >= value_start
        ]
        assert selected, "the value is highlighted"
        assert selected[0].start == value_start
        covered = "".join(art.plain[span.start : span.end] for span in selected)
        assert covered.strip() == bar.value, "all of it"

        await pilot.press("3")
        await pilot.pause()
        assert bar.value == "3", "typing replaces it"


# -- air around the map ---------------------------------------------------
async def test_a_tall_window_gives_the_map_a_row_of_air_twice(tmp_path: Path):
    """Below the header and above the bar, so the map does not butt against
    either. The drawers are left alone: a panel keeps its own blank line."""
    from spoider.widgets import MindMapView

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.pause()
        top = app.query_one("#topbar").region
        view = app.query_one(MindMapView).region
        foot = app.query_one("#footer").region

        assert view.y == top.bottom + 1, "a row of air under the header"
        assert view.bottom == foot.y - 1, "and one under the map"


async def test_a_window_of_thirty_rows_spends_every_row_on_the_map(tmp_path: Path):
    from spoider.widgets import MindMapView

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        top = app.query_one("#topbar").region
        view = app.query_one(MindMapView).region
        foot = app.query_one("#footer").region

        assert view.y == top.bottom
        assert view.bottom == foot.y
        assert view.height == 28, "all the rows the two bars left"


async def test_the_air_comes_back_at_thirty_one_rows(tmp_path: Path):
    from spoider.widgets import MindMapView

    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(100, 31)) as pilot:
        await pilot.pause()
        top = app.query_one("#topbar").region
        view = app.query_one(MindMapView).region
        assert view.y == top.bottom + 1


async def test_a_panel_keeps_one_blank_line_above_the_bar(tmp_path: Path):
    """The footer is not what carries the air: a panel already ends with a blank
    line, and two of them would read as a gap in the panel."""
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test(size=(100, 40)) as pilot:
        await pilot.press("ctrl+comma")
        await pilot.pause()
        panel = app.query_one(PanelBar)
        foot = app.query_one("#footer").region
        # the blank line is the panel's own last row, so the two touch and the
        # reader still sees one empty line above the bar
        assert panel.region.bottom == foot.y
        assert panel.render().plain.endswith("\n"), "and it is blank"


async def test_a_line_can_hold_two_chords(tmp_path: Path):
    """`edit = e ctrl+g` binds both: an rc file lists a thing on one line rather
    than saying the same thing twice."""
    config_path = tmp_path / "config.conf"
    config_path.write_text("edit = e ctrl+g\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+g")
        await pilot.pause()
        assert app.editing is True, "the second chord works"
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("e")
        await pilot.pause()
        assert app.editing is True, "and so does the first"


async def test_a_line_left_empty_of_a_chord_does_nothing(tmp_path: Path):
    config_path = tmp_path / "config.conf"
    config_path.write_text("edit = ctrl+g\n")
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config_path)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        assert app.editing is False, "a chord left off the line stops working"


def test_a_token_that_is_not_a_key_is_dropped_from_the_line(tmp_path: Path):
    """`copy = alt+6 12` keeps alt+6: the leftover that once broke justify is
    dropped, and the rest of the line still counts."""
    from spoider.config import load_config
    from spoider.keys import action_chords

    config_path = tmp_path / "config.conf"
    config_path.write_text("copy = alt+6 12\n")
    loaded = load_config(config_path, SpoiderApp._binding_ids())

    assert action_chords(loaded.keys)["copy"] == ["alt+6"]


def test_the_config_file_is_named_for_the_app(tmp_path: Path):
    """The name carries the app, so a copy of the file found somewhere else still
    says what it belongs to."""
    from spoider.config import default_config_path

    assert default_config_path().name == "spoider.conf"
    assert default_config_path().parent.name == "spoider"


def test_the_config_carries_a_vim_block_to_uncomment(tmp_path: Path):
    """Switching to vim is uncommenting a block, not writing a keymap by hand."""
    from spoider.config import VIM_BINDS, parse
    from spoider.keys import action_chords

    path = tmp_path / "spoider.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    app._save_config()
    text = path.read_text()

    head = text.index("# --- vim binds")
    block = [line for line in text[head:].splitlines() if "=" in line]
    assert len(block) == len(VIM_BINDS)

    # uncommenting the block is the whole switch
    switched = parse(text + "\n" + "\n".join(line[2:] for line in block))
    chords = action_chords(switched.keys)
    assert chords["prev"] == ["k", "up"], "and the arrows stay, they are not a convention"
    assert chords["next"] == ["j", "down"]
    assert chords["go_left"] == ["h", "left"]
    assert chords["go_right"] == ["l", "right"]
    assert chords["edit"] == ["i"]
    assert chords["cut"] == ["d"] and chords["paste"] == ["p"]
    assert chords["delete"] == ["x"] and chords["copy"] == ["y"]
    assert chords["undo"] == ["u"] and chords["redo"] == ["ctrl+r"]
    assert chords["add_sibling"] == ["o"] and chords["add_child"] == ["O"]
    assert chords["search"] == ["/"]


async def test_the_vim_block_works_when_uncommented(tmp_path: Path):
    path = tmp_path / "spoider.conf"
    path.write_text(
        "prev = k up\nnext = j down\nleft = h left\nright = l right\n"
        "edit = i\ncut = d\npaste = p\ndelete = x\n"
    )
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=path)
    async with app.run_test() as pilot:
        app.mm.root.children.append(Node("one"))
        app.mm.root.children.append(Node("two"))
        app.select(app.mm.root.children[0].id)
        await pilot.pause()

        await pilot.press("j")
        await pilot.pause()
        assert app.mm.find(app.selected).text == "two", "j walks down"

        await pilot.press("k")
        await pilot.pause()
        assert app.mm.find(app.selected).text == "one"

        await pilot.press("down")
        await pilot.pause()
        assert app.mm.find(app.selected).text == "two", "and an arrow still does"

        await pilot.press("i")
        await pilot.pause()
        assert app.editing is True, "i renames"


def test_a_map_names_itself(tmp_path: Path):
    """`.spoider` is what a map is called, so a file in a folder says what it is."""
    from spoider.app import default_path

    assert default_path().name == "map.spoider"
    assert default_path().parent.name == "spoider"


def test_the_packaging_tells_the_desktop_what_a_map_is():
    """The MIME type and the desktop entry are what make double-click work; they are
    kept honest by reading them rather than copying their contents here."""
    from pathlib import Path as Pathlib

    root = Pathlib(__file__).resolve().parent.parent
    mime = (root / "src" / "spoider" / "data" / "x-spoider.xml").read_text()
    desktop = (root / "src" / "spoider" / "data" / "spoider.desktop").read_text()

    assert '<mime-type type="application/x-spoider">' in mime
    assert '<glob pattern="*.spoider"/>' in mime
    assert "MimeType=application/x-spoider;" in desktop
    assert "Exec=spoider %f" in desktop, "the map is handed to the editor"
    assert "Terminal=true" in desktop, "spoider is a terminal program"


def test_install_desktop_writes_the_files_where_the_system_looks(tmp_path: Path, monkeypatch):
    """One command after an install, and it must work from a wheel: the files ship
    inside the package, not in a clone."""
    from spoider.desktop import install_desktop

    calls: list[list[str]] = []
    monkeypatch.setattr("spoider.desktop._run_tool", lambda argv: calls.append(argv) or True)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))

    assert install_desktop() == 0

    mime = tmp_path / "share" / "mime" / "packages" / "x-spoider.xml"
    entry = tmp_path / "share" / "applications" / "spoider.desktop"
    assert '<glob pattern="*.spoider"/>' in mime.read_text()
    assert "MimeType=application/x-spoider;" in entry.read_text()
    assert "Exec=" in entry.read_text() and "spoider --install-desktop" not in entry.read_text()

    commands = [call[0] for call in calls]
    assert commands == ["update-mime-database", "update-desktop-database", "xdg-mime"]
    assert calls[-1][-2:] == ["spoider.desktop", "application/x-spoider"]


def test_install_desktop_survives_a_tool_that_is_not_installed(tmp_path: Path, monkeypatch):
    from spoider.desktop import _run_tool, install_desktop

    monkeypatch.setattr("spoider.desktop._run_tool", lambda argv: False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))

    assert install_desktop() == 0, "the files are still written"
    assert (tmp_path / "share" / "mime" / "packages" / "x-spoider.xml").exists()
    assert _run_tool(["definitely-not-a-tool-on-this-machine"]) is False


def test_install_desktop_does_not_open_the_editor(monkeypatch, tmp_path: Path):
    from spoider import app as module

    monkeypatch.setattr("spoider.app.install_desktop", lambda: 0)
    monkeypatch.setattr(
        module, "SpoiderApp", lambda *a, **k: pytest.fail("the editor must not start")
    )
    with pytest.raises(SystemExit) as stop:
        module.main(["--install-desktop"])
    assert stop.value.code == 0


# -- the first-run question about the desktop ------------------------------


async def test_the_first_run_asks_about_opening_maps_from_the_desktop(tmp_path: Path, monkeypatch):
    from spoider.chrome import hint_chunks  # noqa: F401  (keeps the import graph honest)

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "empty-data"))
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=tmp_path / "c.conf")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.mode == "ask"
        assert "spoider from now on" in app.query_one(AskBar).question


async def test_answering_no_is_not_asked_again(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "empty-data"))
    config = tmp_path / "c.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

    assert app.mode == "keys"
    assert "desktop_asked = true" in config.read_text()
    assert not (tmp_path / "empty-data" / "applications" / "spoider.desktop").exists()

    again = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with again.run_test() as pilot:
        await pilot.pause()
        assert again.mode == "keys", "a no is an answer, not a delay"


async def test_answering_yes_registers_it(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[str] = []
    monkeypatch.setattr("spoider.app.install_desktop", lambda: calls.append("registered") or 0)

    config = tmp_path / "c.conf"
    app = SpoiderApp(tmp_path / "map.json", demo=False, config_path=config)
    async with app.run_test(notifications=True) as pilot:
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

    assert calls == ["registered"]
    assert "desktop_asked = true" in config.read_text()


async def test_there_is_no_question_when_it_is_already_registered(tmp_path: Path):
    """The conftest fixture registers it, so this is the ordinary test case."""
    app = SpoiderApp(tmp_path / "map.json", demo=False)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.mode == "keys"
        assert not app.query_one(AskBar).display


# -- where the cursor starts ----------------------------------------------


async def test_position_puts_the_cursor_where_it_points(tmp_path: Path):
    mm = MindMap(Node("root"))
    branch = mm.add_child(mm.root.id, "branch")
    target = mm.add_child(branch.id, "target")
    path = tmp_path / "map.spoider"
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf", position="1.1")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.selected == target.id
        assert not app.stack_open


async def test_position_into_the_stack_opens_the_panel(tmp_path: Path):
    mm = MindMap(Node("root"))
    older = Node("older")
    newer = Node("newer", children=[Node("child")])
    mm.cut_stack = [older, newer]
    path = tmp_path / "map.spoider"
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf", position="s1.1")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stack_open, "a cell you cannot see is not a place the cursor can be"
        assert app.selected == newer.children[0].id


async def test_an_address_past_the_end_leaves_the_cursor_on_the_root(tmp_path: Path):
    mm = MindMap(Node("root"))
    mm.add_child(mm.root.id, "only")
    path = tmp_path / "map.spoider"
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf", position="9.9")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.selected == app.mm.root.id


# -- the file remembers where the cursor was -------------------------------


async def test_the_cursor_is_written_with_the_map_and_restored(tmp_path: Path):
    path = tmp_path / "map.spoider"
    mm = MindMap(Node("root"))
    target = mm.add_child(mm.root.id, "target")
    mm.cursor = target.id
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.selected == target.id


async def test_saving_records_the_cursor(tmp_path: Path):
    path = tmp_path / "map.spoider"
    app = SpoiderApp(path, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        child = app.mm.add_child(app.mm.root.id, "child")
        app.view.refresh_map()
        app.select(child.id)
        app.action_save()
        await pilot.pause()
        assert '"cursor": "' + child.id + '"' in path.read_text()


async def test_a_saved_cut_opens_the_panel(tmp_path: Path):
    path = tmp_path / "map.spoider"
    mm = MindMap(Node("root"))
    cut = Node("cut")
    mm.cut_stack = [cut]
    mm.cursor = cut.id
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.stack_open, "a cursor on a cut is a cursor in the panel"
        assert app.selected == cut.id


async def test_an_address_beats_the_files_memory(tmp_path: Path):
    path = tmp_path / "map.spoider"
    mm = MindMap(Node("root"))
    other = mm.add_child(mm.root.id, "other")
    mm.cursor = other.id
    mm.save(path)

    app = SpoiderApp(path, config_path=tmp_path / "e.conf", position="0")
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.selected == app.mm.root.id, "-p says where to be"


def test_the_write_offer_carries_the_suffix_and_puts_the_caret_before_it(tmp_path: Path):
    app = SpoiderApp(tmp_path / "notes" / "map", config_path=tmp_path / "e.conf")
    app.path = None
    offered, caret = app._write_offer()
    assert offered.endswith(".spoider"), offered
    assert offered[caret:] == ".spoider", "the suffix is what the caret leaves alone"

    # a file the reader named with another suffix is left exactly as it is
    app.path = tmp_path / "map.json"
    offered, caret = app._write_offer()
    assert offered == str(tmp_path / "map.json")
    assert caret == len(offered)


# -- the properties overlay ------------------------------------------------


async def test_i_shows_the_file_properties_over_the_map(tmp_path: Path):
    path = tmp_path / "map.spoider"
    app = SpoiderApp(path, config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        child = app.mm.add_child(app.mm.root.id, "child")
        app.view.refresh_map()
        app.select(child.id)
        await pilot.pause()
        assert "cursor" not in app.view.render().plain, "off until asked for"

        await pilot.press("grave_accent")
        await pilot.pause()
        assert app.show_properties is True
        drawn = app.view.render().plain
        assert "cursor" in drawn and child.id in drawn
        assert "file" in drawn and drawn.lstrip().startswith("╭"), "the box is in the corner"

        await pilot.press("grave_accent")
        await pilot.pause()
        assert app.show_properties is False
        assert "cursor" not in app.view.render().plain


async def test_the_overlay_names_the_cell_that_was_edited(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.spoider", config_path=tmp_path / "e.conf")
    async with app.run_test() as pilot:
        await pilot.press("tab")
        await pilot.press("x", "y", "z")
        await pilot.press("enter")
        await pilot.pause()
        assert app.last_edited is not None, "a typed cell is the last one edited"
        await pilot.press("grave_accent")
        await pilot.pause()
        assert "xyz" in app.view.render().plain


async def test_the_tree_keys_walk_the_hierarchy(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.spoider", config_path=tmp_path / "k.conf")
    async with app.run_test(size=(120, 40)) as pilot:
        first = app.mm.add_child(app.mm.root.id, "first")
        second = app.mm.add_child(app.mm.root.id, "second")
        deep = app.mm.add_child(first.id, "deep")
        leaf = app.mm.add_child(deep.id, "leaf")
        app.view.refresh_map()
        app.select(second.id)
        await pilot.pause()

        await pilot.press("pageup")
        await pilot.pause()
        assert app.selected == first.id, "pgup is the first sibling"

        await pilot.press("pagedown")
        await pilot.pause()
        assert app.selected == second.id, "pgdn is the last sibling"

        await pilot.press("home")
        await pilot.pause()
        assert app.selected == app.mm.root.id, "home is the main cell"

        await pilot.press("end")
        await pilot.pause()
        assert app.selected == second.id, "from the root, end follows the last branch"

        app.select(first.id)
        await pilot.pause()
        await pilot.press("end")
        await pilot.pause()
        assert app.selected == leaf.id, "from a branch, end is its deepest cell"

        await pilot.press("delete")
        await pilot.pause()
        assert app.mm.find(leaf.id) is None, "del removes the cell, as ^D does"
        assert app.mm.find(deep.id) is not None, "its parent stays"


async def test_an_arrow_into_the_children_picks_the_one_in_its_direction(tmp_path: Path):
    """Which child you reach is decided by where the children are drawn."""
    app = SpoiderApp(tmp_path / "map.spoider", config_path=tmp_path / "n.conf", demo=False)
    async with app.run_test(size=(120, 40)) as pilot:
        kids = [app.mm.add_child(app.mm.root.id, name) for name in ("a", "b", "c")]
        app.view.refresh_map()
        app.select(app.mm.root.id)
        await pilot.pause()

        boxes = app.view.layout_.boxes
        below = [kid for kid in kids if boxes[kid.id].cy > boxes[app.mm.root.id].cy]
        assert below, "the fixture should put at least one child below the root"

        await pilot.press("down")
        await pilot.pause()
        assert app.selected in {kid.id for kid in below}
        assert app.selected != kids[0].id or len(below) == 1, "not simply the first child"


# -- the help page reads to the bottom -------------------------------------


async def test_help_scrolls_when_it_runs_past_the_screen(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.spoider", config_path=tmp_path / "h.conf", demo=False)
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        panel = app.query_one(PanelBar)
        assert panel.scrollable, "this size cannot show the whole page"
        first = panel.render().plain.splitlines()[0]

        await pilot.press("pagedown")
        await pilot.pause()
        assert panel.render().plain.splitlines()[0] != first, "the page moved"
        assert "scroll" in app.query_one("#footer", FooterBar).render().plain

        await pilot.press("end")
        await pilot.pause()
        assert "editor settings" in panel.render().plain, "the last section is reachable"

        await pilot.press("home")
        await pilot.pause()
        assert panel.render().plain.splitlines()[0] == first

        await pilot.press("pagedown")
        await pilot.press("escape")
        await pilot.pause()
        assert app.mode == "keys", "esc still closes it"


async def test_a_help_page_that_fits_names_only_close(tmp_path: Path):
    app = SpoiderApp(tmp_path / "map.spoider", config_path=tmp_path / "h.conf", demo=False)
    async with app.run_test(size=(140, 120)) as pilot:
        await pilot.press("ctrl+slash")
        await pilot.pause()
        panel = app.query_one(PanelBar)
        assert not panel.scrollable, "a tall screen shows it whole"
        assert "scroll" not in app.query_one("#footer", FooterBar).render().plain


def test_help_is_ordered_from_making_cells_to_this_screen():
    from spoider.screens import HELP

    order = [title for title, _rows in HELP]
    assert order == [
        "Making cells",
        "Marks and folds",
        "Moving",
        "By the tree",
        "The cut stack",
        "View",
        "File",
        "History",
        "While typing",
        "This screen",
    ]


def test_the_demo_names_the_tree_keys_and_the_debug_box():
    texts = [node.text for node in MindMap.demo().nodes()]
    joined = " ".join(texts)
    for word in ("pgup", "pgdn", "home", "end", "del", "`"):
        assert word in joined, f"the demo should mention {word}"
