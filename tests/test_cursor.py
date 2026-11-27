"""One cursor, two documents: wherever a change leaves it, a pane has to draw it.

These are the paths that used to lose it: undo from inside the panel, the panel closing on a stack
whose cells went back to the map, and a plain key sequence nobody thought about. The last test is
the general one: any sequence of the keys that move cells leaves the cursor somewhere the pane in
front of the reader holds.
"""

import random
from pathlib import Path

import pytest

from spoider.app import SpoiderApp
from spoider.model import MindMap, Node


def a_map(tmp_path: Path, names: tuple[str, ...] = ("one", "two", "three")) -> tuple[object, Path]:
    mm = MindMap(Node("root"))
    for name in names:
        mm.add_child(mm.root.id, name)
    mm.cursor = mm.root.id
    path = tmp_path / "map.spoider"
    mm.save(path)
    return mm, path


def cursor_trouble(app) -> str | None:
    """None when the cursor is somewhere the pane in front draws it, else what is wrong."""
    if app.stack_open:
        if not app.mm.cut_stack:
            return "the panel is open on an empty stack"
        held = {node.id for entry in app.mm.cut_stack for node in entry.walk()}
        if app.selected not in held:
            return "the panel is open and the cursor is not on the stack"
        return None
    if app.mm.find(app.selected) is None:
        return "the panel is shut and the cursor is not a cell of the map"
    return None


async def test_undoing_in_the_panel_twice_leaves_the_cursor_in_the_map(tmp_path: Path):
    mm, path = a_map(tmp_path)
    _one, two, three = mm.root.children
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "c.conf")
    async with app.run_test(size=(110, 26)) as pilot:
        await pilot.pause()
        app.select(two.id)
        await pilot.press("ctrl+k")
        await pilot.pause()
        app.select(three.id)
        await pilot.press("ctrl+k")
        await pilot.pause()

        await pilot.press("p")
        await pilot.pause()
        await pilot.press("ctrl+z")
        await pilot.pause()
        await pilot.press("ctrl+z")
        await pilot.pause()
        await pilot.press("p")          # closing (or opening) again, whichever the state is
        await pilot.pause()

        assert cursor_trouble(app) is None, cursor_trouble(app)
        assert [child.text for child in app.mm.root.children] == ["one", "two", "three"]


async def test_a_parked_cell_this_document_does_not_hold_still_lands_home(tmp_path: Path):
    """The panel remembers a cell to come back to; an undo can take that cell out from under it."""
    _mm, path = a_map(tmp_path)
    app = SpoiderApp(path, demo=False, config_path=tmp_path / "c.conf")
    async with app.run_test(size=(110, 26)) as pilot:
        await pilot.pause()
        await pilot.press("p")          # nothing on the stack, so nothing opens
        await pilot.pause()
        # the state an undo can leave behind: a panel open, a park that names no cell, a cursor
        # on a cell that no longer exists
        app.mm.cut_stack.append(Node("parked"))
        app._stack_open = True
        app._map_cursor = ("000000000000", None)
        app.selected = "111111111111"

        app._close_stack()

        assert not app.stack_open
        assert app.selected == app.mm.root.id, "the root is the one cell a map always draws"


MAP_KEYS = ("p", "ctrl+k", "ctrl+u", "ctrl+z", "ctrl+r", "tab", "enter", "down", "up", "escape", "x")
PANEL_KEYS = ("p", "ctrl+k", "ctrl+u", "ctrl+z", "ctrl+r", "tab", "enter", "down", "up", "escape", "x")


@pytest.mark.parametrize("mode", ("map", "panel"))
@pytest.mark.parametrize("seed", range(6))
async def test_no_key_sequence_leaves_the_cursor_nowhere(tmp_path: Path, seed: int, mode: str):
    """The guarantee, rather than a list of paths: whatever the keys do, a pane holds the cursor."""
    rng = random.Random(seed)
    mm = MindMap(Node("root"))
    branch = mm.add_child(mm.root.id, "branch")
    for index in range(3):
        mm.add_child(branch.id, f"leaf {index}")
    mm.add_child(mm.root.id, "lonely")
    path = tmp_path / f"fuzz-{mode}-{seed}.spoider"
    mm.save(path)

    app = SpoiderApp(path, demo=False, config_path=tmp_path / "c.conf")
    async with app.run_test(size=(110, 28)) as pilot:
        await pilot.pause()
        if mode == "panel":
            app.select(mm.root.children[0].id)
            await pilot.press("ctrl+k")   # something on the stack for the panel to show
            await pilot.pause()
            await pilot.press("p")
            await pilot.pause()
        used: list[str] = []
        for _ in range(40):
            key = rng.choice(MAP_KEYS if mode == "map" else PANEL_KEYS)
            used.append(key)
            await pilot.press(key)
            await pilot.pause()
            trouble = cursor_trouble(app)
            assert trouble is None, f"{trouble}, after: {' '.join(used)}"
