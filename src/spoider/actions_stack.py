# pyright: reportAttributeAccessIssue=false
"""One area of SpoiderApp's keys: stack actions.

A mixin, so the methods keep using the app's own state and helpers. Nothing here is
bound directly; the bindings live in app.py.
"""

from __future__ import annotations

from . import nav
from .keys import (
    action_chords,
)
from .layout import compute_stack
from .model import MindMap, Node
from .nav import _standing_after


class StackActions:
    def action_cut(self) -> None:
        """^K — take the selected cells out of the map and put them on the stack.

        They are not deleted: the stack is last in, first out, and any of the cuts
        on it can be pasted back under whatever cell is selected. The cursor stays
        on a sibling, where the eye already is.

        The cursor stays where the eye already is: on the cell that closes the gap
        the cut left, or on the one before it when the run ended the branch. Only
        an only child leaves you on the parent, because there is nothing else
        left to stand on.
        """
        ids = self.selected_ids
        if self.mm.root.id in ids:
            self.notify("The root node cannot be cut", severity="error", timeout=2)
            return
        parent = self.mm.parent(ids[0])
        if parent is None:
            return
        # the slot the run will leave behind, read before it is closed up
        end = [child.id for child in parent.children].index(ids[-1])
        self._push_undo()
        taken: list[Node] = []
        for node_id in ids:
            result = self.mm.delete(node_id)
            if result is not None:
                taken.append(result[0])
        if not taken:
            self._undo.pop()
            return
        self.mm.push_cut(taken)
        self.anchor = None
        self.selected = _standing_after(parent, end)
        self._mark_dirty()
        if len(taken) == 1:
            self.notify("Cut onto the stack", severity="warning", timeout=2)
        else:
            self.notify(f"{len(taken)} cells cut onto the stack", severity="warning", timeout=2)
    def action_paste(self) -> None:
        """^U — take the most recent cut off the stack and hang it here.

        Last in, first out: cutting three branches and pressing ^U three times
        puts them back in the order they were cut, and each press empties the
        stack by one. A paste the eye cannot see is worth nothing, so the
        selection stays on the target as its children arrive.
        """
        if not self.mm.cut_stack:
            self.notify("Nothing to paste", severity="error", timeout=2)
            return
        self._push_undo()  # the snapshot holds the stack, so undo puts it back
        cell = self.mm.pop_cut()
        if cell is None or self.mm.paste(self.selected, cell) is None:
            self._undo.pop()
            return
        self._mark_dirty()
        self.notify("Pasted from the stack", severity="warning", timeout=2)
    def action_toggle_stack(self) -> None:
        """`p` — the stack itself, as a panel of cells over the map.

        The stack is where every cut cell waits, last in first out, until it is
        pasted somewhere; the panel shows what is on it and lets you work on a
        cell — rename it, mark it, cut it again, drop it — without pasting it back
        into the map first.
        """
        if self.stack_open:
            self._stack_open = False
            if self._map_cursor is not None:
                selected, anchor = self._map_cursor
                if selected is not None and self.mm.find(selected) is not None:
                    self.selected, self.anchor = selected, anchor
                self._map_cursor = None
            self.view.refresh()
            self._sync_footer()
            self._refresh_chrome()
            return
        entries = self._stack_entries()
        if not entries:
            self.notify("Nothing cut yet", severity="error", timeout=2)
            return
        self._map_cursor = (self.selected, self.anchor)  # where the map left off
        self._stack_open = True
        self.selected, self.anchor = entries[0].id, None  # the newest cut
        self.view.refresh()
        self._sync_footer()
        self._refresh_chrome()
    def _stack_entries(self) -> list[Node]:
        """The stack as the panel reads it: newest first."""
        return list(reversed(self.mm.cut_stack))
    def stack_layout(self):
        """The picture of the stack, or None when the panel is shut."""
        if not self.stack_open:
            return None
        return compute_stack(self._stack_entries(), self.mm.spacing)
    def _stack_doc(self) -> MindMap:
        """The stack as a document, made of the same Node objects.

        Its root is a cell of its own that nothing draws: it is there so the
        ordinary navigation helpers have a parent to walk up to, and its children
        are the stack, newest first.
        """
        return MindMap(Node("", children=self._stack_entries()))
    def _commit_stack(self, doc: MindMap) -> None:
        """The panel's top level *is* the stack: structural changes go back to it."""
        self.mm.cut_stack = list(reversed(doc.root.children))
    def _stack_changed(self) -> None:
        """Write the panel's state back and let the document know."""
        self._mark_dirty()
        self.view.refresh()
    def _stack_after_history(self) -> None:
        """Undo and redo swap the whole document, so the panel's cursor has to be
        put somewhere that still exists — and the panel closed if the stack the
        restored document carries is empty."""
        entries = self._stack_entries()
        if not entries:
            self.stack_open_or_close_after_undo()
            return
        known = {node.id for entry in entries for node in entry.walk()}
        if self.selected not in known:
            self.selected, self.anchor = entries[0].id, None  # the top of the stack
        self.view.refresh()
    def _stack_select(self, doc: MindMap, node_id: str) -> None:
        if node_id != doc.root.id:  # the invisible root is not a cell you can be on
            self.select(node_id)
    def _action_for(self, key: str) -> str | None:
        """Which action a chord belongs to, according to the keymap in force.

        The stack panel reads keys through this instead of matching strings, so a
        chord the reader has rebound works there too.
        """
        for action, chords in action_chords(self.config.keys).items():
            if key in chords:
                return action
        return None
    def handle_stack_key(self, key: str, character: str | None) -> bool:
        """Every key while the stack panel is open.

        The actions are the map's own — navigation is the branch shape's, because
        that is how the panel is drawn (up and down walk the stack, right goes into
        a cell's children, left comes back out) — so every key means what it means
        on the map, and the bar can say so in the same words.
        """
        if not self.stack_open:
            return False
        action = None if key in ("escape", "ctrl+c") else self._action_for(key)
        doc = self._stack_doc()
        selected = self.selected or doc.root.id

        if action is None and key not in ("escape", "ctrl+c"):
            return False
        if action == "toggle_stack" or key in ("escape", "ctrl+c"):
            self.action_toggle_stack()
        elif action == "prev":
            self._stack_select(doc, nav.to_sibling(doc, selected, -1))
        elif action == "next":
            self._stack_select(doc, nav.to_sibling(doc, selected, 1))
        elif action == "go_right":
            self._stack_select(doc, nav.to_child(doc, selected))
        elif action == "go_left":
            self._stack_select(doc, nav.to_parent(doc, selected))
        elif action == "edit":
            if doc.find(selected) is not None:
                self.begin_edit(selected)
        elif action == "select_all":
            self.action_select_all()
        elif action in ("extend_prev", "extend_next"):
            # the panel is always the branch shape: up and down walk siblings, so
            # those are the arrows that grow a run there
            self._extend("prev" if action == "extend_prev" else "next")
        elif action in ("extend_left", "extend_right"):
            pass  # left and right go to the parent and into a cell, never sideways
        elif action == "mark":
            self._push_undo()
            mark = doc.next_mark(selected, self.marks)
            for node_id in self.selected_ids:
                node = doc.find(node_id)
                if node is not None:
                    node.mark = mark
            self._stack_changed()
        elif action == "fold":
            lead = doc.find(selected)
            if lead is not None and lead.children:
                self._push_undo()
                fold = not lead.collapsed
                for node_id in self.selected_ids:
                    node = doc.find(node_id)
                    if node is not None and node.children:
                        node.collapsed = fold
                self._stack_changed()
        elif action == "cut":
            self._stack_take(doc, self.selected_ids, discard=False)
        elif action == "paste":
            self._stack_paste()
        elif action == "justify":
            self.action_justify()
        elif action == "copy":
            self.action_copy()
        elif action == "delete":
            self._stack_take(doc, self.selected_ids, discard=True)
        elif action == "move_up":
            self._stack_reorder(doc, selected, -1)
        elif action == "move_down":
            self._stack_reorder(doc, selected, 1)
        elif action == "spacing_more":
            self._set_spacing(self.mm.spacing + 1)
        elif action == "spacing_less":
            self._set_spacing(self.mm.spacing - 1)
        elif action == "undo":
            self.action_undo()
            self._stack_after_history()
        elif action == "redo":
            self.action_redo()
            self._stack_after_history()
        else:
            return False
        return True
    def _stack_reorder(self, doc: MindMap, node_id: str, delta: int) -> None:
        """Move a cell among its siblings inside the panel. For an entry at the
        top level that is the stack's own order, so alt+↑ puts it nearer the top."""
        parent = doc.parent(node_id)
        if parent is None:
            return
        order = [child.id for child in parent.children]
        index = order.index(node_id)
        target = index + delta
        if not 0 <= target < len(order):
            return
        self._push_undo()
        node = parent.children.pop(index)
        parent.children.insert(target, node)
        self.mm.cut_stack = list(reversed(doc.root.children))
        self._stack_changed()
    def stack_open_or_close_after_undo(self) -> None:
        """Undo can empty the stack a panel is showing; the panel goes with it."""
        self._stack_open = False
        if self._map_cursor is not None:
            selected, anchor = self._map_cursor
            if selected is not None and self.mm.find(selected) is not None:
                self.selected, self.anchor = selected, anchor
            self._map_cursor = None
        self._sync_footer()
        self._refresh_chrome()
        self.view.refresh()
    def _stack_paste(self) -> None:
        """^U inside the panel: hang the newest cut under the selected cell.

        This rearranges the stack without touching the map — the top comes off the
        stack and becomes a child of whatever is selected in the panel. A cell
        cannot be pasted into itself or into one of its own children (that would
        be a cycle), so that case does nothing at all and leaves the stack as it
        was, rather than reporting a failure for a key that cannot work here.
        """
        if not self.mm.cut_stack:
            self.notify("Nothing to paste", severity="error", timeout=2)
            return
        top = self.mm.cut_stack[-1]
        target = self.selected
        if target is None or any(node.id == target for node in top.walk()):
            return  # into itself, or into something it already contains

        self._push_undo()  # the stack is document state, so undo covers this too
        cell = self.mm.pop_cut()
        doc = self._stack_doc()  # rebuilt without the cell that left the stack
        if cell is None or doc.find(target) is None:
            self.mm.cut_stack.append(cell) if cell is not None else None
            self._undo.pop()
            return
        doc.paste(target, cell)
        self.mm.cut_stack = list(reversed(doc.root.children))
        self._mark_dirty()
        self.view.refresh()
    def _stack_take(self, doc: MindMap, ids: list[str], *, discard: bool) -> None:
        """Take cells off the stack: throw them away, or cut them again.

        Cutting again is the whole point of a stack — the cells go back on top,
        which is where a cut always goes, and the panel shows them at the top.
        A run keeps its order, so the first of them ends up highest in the panel.
        """
        if not ids:
            return
        parent = doc.parent(ids[0])
        if parent is None:
            return
        self._push_undo()  # every stack change is one step, like a map change
        taken: list[Node] = []
        for node_id in ids:
            holder = doc.parent(node_id)
            if holder is None:
                continue
            for position, child in enumerate(holder.children):
                if child.id == node_id:
                    taken.append(holder.children.pop(position))
                    break
        node = taken[0] if taken else None
        if node is None:
            self._undo.pop()
            return
        index = 0
        if not discard:
            # the panel reads newest first, so the top of the stack is its index 0
            for cell in reversed(taken):
                doc.root.children.insert(0, cell)
        entries = list(reversed(doc.root.children))  # the file's order: oldest first
        self.mm.cut_stack = entries
        self._stack_changed()
        if not entries:  # nothing left to show
            self.stack_open_or_close_after_undo()
            return
        self.anchor = None
        self.selected = node.id if not discard else entries[min(index, len(entries) - 1)].id
        self.view.refresh()

