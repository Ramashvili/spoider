# pyright: reportAttributeAccessIssue=false
"""One area of SpoiderApp's keys: map actions.

A mixin, so the methods keep using the app's own state and helpers. Nothing here is
bound directly; the bindings live in app.py.
"""

from __future__ import annotations

from . import nav
from .chrome import NOTE, QUICK, key_cap
from .layout import MAX_SPACING, MIN_SPACING
from .model import LAYOUTS, MindMap, Node, layout_name

UP_MEANING: dict[str, str] = {
    "spider": "go_up",
    "branch": "go_up",
    "branch-left": "go_up",
    "pyramid": "parent",
    "bush": "child",
}
DOWN_MEANING: dict[str, str] = {
    "spider": "go_down",
    "branch": "go_down",
    "branch-left": "go_down",
    "pyramid": "child",
    "bush": "parent",
}


class MapActions:
    def action_add_child(self) -> None:
        """^Tab — a new cell under the selection, in the map or in a cut."""
        doc = self.document
        self._push_undo()
        node = doc.add_child(self.focus)
        if node is None:
            self._undo.pop()
            return
        self._inserted(node, doc)
    def action_add_sibling(self) -> None:
        """⏎ — a new cell beside the selection; a sibling of a top-level cut is a
        new entry on the stack, because at that level the stack is the top level."""
        doc = self.document
        if doc.parent(self.focus) is None:
            self.action_add_child()
            return
        self._push_undo()
        node = doc.add_sibling(self.focus)
        if node is None:
            self._undo.pop()
            return
        self._inserted(node, doc)
    def _inserted(self, node: Node, doc: MindMap) -> None:
        """Stand on a cell that has just been made, and type its name."""
        if self.stack_open:
            self._commit_stack(doc)  # the document the cell was made in
            self.selected, self.anchor = node.id, None
            self._stack_changed()
        else:
            self.anchor = None
            self.selected = node.id
            self.view.refresh_map()
        self.begin_edit(node.id, fresh=True)
    def action_edit(self) -> None:
        """Renaming a run of cells at once would give them all one name, so this
        is the one action that stays with the cell the cursor is on."""
        if self.node is not None:
            self.anchor = None
            self.begin_edit(self.selected)
    def action_delete(self) -> None:
        """^D — delete everything selected, as one undoable step."""
        ids = self.selected_ids
        if self.mm.root.id in ids:
            self.notify("The root node cannot be deleted", severity="error", timeout=NOTE)
            return
        self._push_undo()
        if len(ids) == 1:
            result = self.mm.delete(ids[0])
            if result is None:
                self._undo.pop()
                return
            _, successor = result
            self.selected = successor
        else:
            # a run leaves you on the parent it hung from
            parent = self.mm.parent(ids[0])
            for node_id in ids:
                self.mm.delete(node_id)
            self.selected = parent.id if parent is not None else self.mm.root.id
        self.anchor = None
        self._mark_dirty()
    def action_set_marks(self) -> None:
        """^M — the marks this map cycles through, in the order m walks them.

        A line of its own rather than something buried in the settings: the
        vocabulary is part of the map, and it is edited while the map is in front
        of you. The list is not preselected — appending to it is the common case.
        """
        self._show_prompt(
            "marks",
            f"Marks, in the order {key_cap(self.keymap.get('mark', 'w'))} cycles: ",
            # a trailing space so a typed mark starts a token of its own rather
            # than growing the last one; it is stripped before anything is saved
            " ".join(self.marks) + " ",
            submit=self._marks_submitted,
            cancel=self._close_drawers,
        )
    def _marks_submitted(self, value: str) -> None:
        self.set_marks(value.split())
        self._close_drawers()
        self.view.focus()
    def action_mark(self) -> None:
        """m — cycle the mark: none, ⭐, 💡, ❓, ⚠️, ✅, 📌, ⌛, 🤡, none.

        A run of cells all take the mark the first one was about to show, so one
        press gives them one meaning instead of a spectrum.
        """
        ids = self.selected_ids
        if not ids:
            return
        self._push_undo()
        mark = self.mm.next_mark(ids[0], self.marks)
        for node_id in ids:
            node = self.mm.find(node_id)
            if node is not None:
                node.mark = mark
        self._touched(ids[0])
        self._mark_dirty()
    def action_fold(self) -> None:
        """t — fold or unfold, following the lead cell's state across the run."""
        ids = self.selected_ids
        lead = self.mm.find(ids[0])
        if lead is None:
            return
        fold = not lead.collapsed
        targets = [node for node in map(self.mm.find, ids) if node is not None and node.children]
        if not targets:
            return
        self._push_undo()
        for node in targets:
            node.collapsed = fold
        self._mark_dirty()
    def _to_parent(self) -> None:
        self.select(nav.to_parent(self.mm, self.selected))
    def _expand_if_collapsed(self) -> bool:
        node = self.node
        if node is not None and node.children and node.collapsed:
            self._push_undo()
            node.collapsed = False
            self._mark_dirty()
            return True
        return False
    def _into_child(self) -> None:
        if self._expand_if_collapsed():
            return
        self.select(nav.to_child(self.mm, self.selected))
    def _from_root(self, want: int) -> None:
        """The root branches both ways, so ← and → each pick their own side."""
        if self._expand_if_collapsed():
            return
        self.select(nav.to_child_on_side(self.mm, self.selected, want))
    @property
    def _at_root(self) -> bool:
        return self.selected == self.mm.root.id
    def action_go_left(self) -> None:
        """^B / ← — the cell to the left on the canvas, or the parent on that side.

        The shape's own rules still answer first when they name a parent, a child or a
        sibling; the canvas decides when they would do nothing, or would climb out to
        something that is not a relative at all.
        """
        self._go(-1, 0)

    def action_go_right(self) -> None:
        """^F / → — mirrors action_go_left."""
        self._go(+1, 0)

    @property
    def siblings_are_sideways(self) -> bool:
        """True when the levels are stacked, so ← / → walk the row of siblings
        and ↑ / ↓ are left to cross a level."""
        return self.mm.layout in ("pyramid", "bush")

    def action_go_up(self) -> None:
        """^P / ↑ — whatever is above the selection in this shape."""
        self._go(0, -1)

    def action_go_down(self) -> None:
        """^N / ↓ — whatever is below the selection in this shape."""
        self._go(0, +1)

    def _go(self, dx: int, dy: int) -> None:
        target = self._hierarchy_target(dx, dy)
        node = self.node
        into_a_child = node is not None and any(child.id == target for child in node.children)
        if into_a_child and self._expand_if_collapsed():
            return
        self._travel_to(target, dx, dy)

    def _hierarchy_target(self, dx: int, dy: int) -> str:
        """What the shape's own rules say, before the canvas gets a say."""
        here = self.selected
        if dy:
            kind = UP_MEANING[self.mm.layout] if dy < 0 else DOWN_MEANING[self.mm.layout]
            if kind in ("go_up", "go_down"):
                return nav.to_sibling(self.mm, here, -1 if kind == "go_up" else +1)
            if kind == "parent":
                return nav.to_parent(self.mm, here)
            return self._child_target(
                dx, dy, nav.to_child(self.document, here)
            )
        if self.siblings_are_sideways:
            return nav.to_sibling(self.mm, here, dx)
        if self._at_root:
            return self._child_target(
                dx, dy, nav.to_child_on_side(self.document, here, dx)
            )
        if nav.side(self.mm, here, self.mm.layout) < 0:
            # a left-hand branch: left goes deeper, right comes back towards the root
            if dx < 0:
                return self._child_target(dx, dy, nav.to_child(self.document, here))
            return nav.to_parent(self.mm, here)
        if dx < 0:
            return nav.to_parent(self.mm, here)
        return self._child_target(dx, dy, nav.to_child(self.document, here))

    def _child_target(self, dx: int, dy: int, fallback: str) -> str:
        """Going to a child: the one the canvas puts under the arrow, else the first."""
        reached = nav.child_towards(self.document, self._nav_layout(), self.selected, dx, dy)
        return reached or fallback

    def _nav_layout(self):
        """The layout the keys are moving in: the panel's if it is open, else the map's."""
        panel = self.stack_layout()
        return panel if panel is not None else self.view.layout_

    def _travel_to(self, target: str, dx: int, dy: int) -> None:
        """Take the hierarchy's answer when it is a relative; otherwise ask the canvas."""
        if target != self.selected and nav.is_direct_relative(self.document, self.selected, target):
            self.select(target)
            return
        reached = nav.towards(self.document, self._nav_layout(), self.selected, dx, dy)
        self.select(reached or target)

    def action_extend_prev(self) -> None:
        """Shift + the arrow that walks back between siblings."""
        self._extend(UP_MEANING[self.mm.layout])
    def action_extend_next(self) -> None:
        self._extend(DOWN_MEANING[self.mm.layout])
    def action_extend_left(self) -> None:
        self._extend("go_up" if self.siblings_are_sideways else None)
    def action_extend_right(self) -> None:
        self._extend("go_down" if self.siblings_are_sideways else None)
    def _extend(self, kind: str | None) -> None:
        """Grow or shrink the run by one sibling. Arrows that do not walk between
        siblings in this shape do nothing rather than jump somewhere else."""
        if kind not in ("go_up", "go_down"):
            return
        parent = self.document.parent(self.selected)
        if parent is None:
            return
        order = [child.id for child in parent.children]
        target = order.index(self.selected) + (-1 if kind == "go_up" else +1)
        if not 0 <= target < len(order):
            return
        if self.anchor is None:
            self.anchor = self.selected
        self.selected = order[target]
        self.view.refresh()
    def action_select_all(self) -> None:
        """^A — the whole text while a cell is being typed into, every sibling on
        the map (which is what a run is: siblings, never cousins)."""
        if self.editing:
            if self._buffer is not None:
                self._buffer.select_all()
                self._sync_preview()
            return
        parent = self.document.parent(self.selected)
        if parent is None or len(parent.children) < 2:
            return
        order = [child.id for child in parent.children]
        self.anchor = order[0]
        self.selected = order[-1]
        self.view.refresh()
    def action_clear_selection(self) -> None:
        """esc — back to one cell without moving it."""
        if self.anchor is None:
            return
        self.anchor = None
        self.view.refresh()
    def action_move_up(self) -> None:
        self._reorder(-1)
    def action_move_down(self) -> None:
        self._reorder(+1)
    def action_spacing_more(self) -> None:
        """^= — breathe: one more column between boxes and one more row between
        subtrees."""
        self._set_spacing(self.spacing + 1)
    def action_spacing_less(self) -> None:
        """^- — tighten. Stops before boxes would touch or overlap."""
        self._set_spacing(self.spacing - 1)
    def _set_spacing(self, value: int) -> None:
        value = max(MIN_SPACING, min(MAX_SPACING, value))
        if value == self.mm.spacing:
            return
        self.mm.spacing = value
        # Document state, so it makes the buffer dirty — but it stays out of the
        # undo stack: nudging the air in three steps should not bury the edit you
        # actually want to undo.
        self._mark_dirty()
    def action_colours(self) -> None:
        """c — cycle the colouring: by depth, or by family.

        `depth` gives every level one colour, `family` gives every branch under the
        root one colour for its whole subtree. Like the shape and the spacing it is
        document state, and like them it is not an edit worth undoing.
        """
        self.mm.colours = "family" if self.mm.colours == "depth" else "depth"
        self._mark_dirty()
        self.notify(f"Colours by {self.mm.colours}", timeout=QUICK)
    def action_layout(self) -> None:
        """^L — cycle the shape: spider, branch right, branch left, pyramid, bush."""
        order = LAYOUTS
        self.mm.layout = order[(order.index(self.mm.layout) + 1) % len(order)]
        # like spacing, the shape is document state but not an edit worth undoing
        self._mark_dirty()
        self.notify(f"Layout: {layout_name(self.mm.layout)}", timeout=QUICK)
    def _reorder(self, delta: int) -> None:
        """alt+↑ / alt+↓ — move the run as one block, keeping its order."""
        ids = self.selected_ids
        parent = self.mm.parent(ids[0])
        if parent is None:
            return
        order = [child.id for child in parent.children]
        if (delta < 0 and order.index(ids[0]) == 0) or (
            delta > 0 and order.index(ids[-1]) == len(order) - 1
        ):
            return  # the block is against the edge
        self._push_undo()
        for node_id in ids if delta < 0 else list(reversed(ids)):
            self.mm.move_sibling(node_id, delta)
        self._mark_dirty()

