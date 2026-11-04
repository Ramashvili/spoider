# pyright: reportAttributeAccessIssue=false
"""One area of SpoiderApp's keys: edit actions.

A mixin, so the methods keep using the app's own state and helpers. Nothing here is
bound directly; the bindings live in app.py.
"""

from __future__ import annotations

from textual import events

from .editing import Buffer, reflow


class EditActions:
    def begin_edit(self, node_id: str, *, fresh: bool = False) -> None:
        node = self._live_node(node_id)
        if node is None:
            return
        if not fresh:
            self._push_undo()
        self._edit_id = node_id
        self._edit_fresh = fresh
        self._buffer = Buffer("" if fresh else (node.text or ""))
        self._sync_preview()
        self._sync_footer()
    def _sync_preview(self) -> None:
        node = self._live_node(self._edit_id) if self._edit_id else None
        if node is None:
            return
        if self._buffer is None:
            return
        node.preview = self._buffer.text
        node.caret = self._buffer.caret
        node.overwrite = self._buffer.overwrite
        node.sel = self._buffer.selection()
        self.view.refresh_map()
    def handle_edit_key(self, key: str, character: str | None) -> bool:
        """Every keystroke while typing into a cell. Returns True if consumed.

        The cell is a small text editor, so these are a text editor's keys: lines,
        a selection dragged out with shift, word deletes, an overwrite mode, cut
        and copy through the clipboard, and ^J to reflow the text. Enter keeps its
        meaning here, which is to finish the cell; a line break is its own key.
        """
        if not self.editing or self._buffer is None:
            return False
        buffer = self._buffer
        if key in ("ctrl+slash", "ctrl+comma"):
            return False  # help and settings stay reachable mid-typing

        if key == "enter":
            self.finish_edit(commit=True)
            return True
        if key in ("escape", "ctrl+c"):
            self.finish_edit(commit=False)
            return True

        base = key.removeprefix("shift+")
        extend = base != key
        moves = {
            "left": buffer.left,
            "right": buffer.right,
            "up": buffer.up,
            "down": buffer.down,
            "home": buffer.home,
            "end": buffer.end,
            "ctrl+e": buffer.end,
            "ctrl+home": buffer.document_home,
            "ctrl+end": buffer.document_end,
        }
        if base in moves:
            moves[base](extend=extend)
        elif key == "shift+enter":
            buffer.insert("\n")
        elif key == "backspace":
            buffer.backspace()
        elif key == "delete":
            buffer.delete()
        elif key in ("alt+backspace", "ctrl+w"):
            buffer.delete_word_before()
        elif key == "alt+d":
            buffer.delete_word_after()
        elif self._action_for(key) == "select_all":
            buffer.select_all()
        elif key == "insert":
            buffer.overwrite = not buffer.overwrite
        elif self._action_for(key) == "cut":
            self._cut_or_copy(cut=True)
        elif self._action_for(key) == "copy":
            self._cut_or_copy(cut=False)
        elif self._action_for(key) == "paste":
            buffer.insert(self._text_clip)
        elif self._action_for(key) == "justify":
            self.action_justify()
        elif self._action_for(key) == "undo":
            buffer.undo()
        elif self._action_for(key) == "redo":
            buffer.redo()
        elif character and character.isprintable():
            buffer.insert(character)
        self._sync_preview()
        return True
    def action_copy(self) -> None:
        """M-6 — copy text: the selection while typing, else the selected cell's."""
        if self.editing:
            self._cut_or_copy(cut=False)
            return
        node = self.document.find(self.focus)
        if node is None or not node.text.strip():
            return
        self._text_clip = node.text
        self.copy_to_clipboard(node.text)
        self.notify("Copied the cell's text", timeout=1)
    def _cut_or_copy(self, *, cut: bool) -> None:
        """^K cuts the selection out of a cell, M-6 copies it.

        With nothing selected the whole cell's text goes, which is what a box this
        size usually wants. The text also goes to the system clipboard (OSC 52), so
        it can leave spoider.
        """
        if self._buffer is None:
            return
        text = self._buffer.selected_text() or self._buffer.text
        if not text:
            return
        self._text_clip = text
        self.copy_to_clipboard(text)
        if cut:
            if self._buffer.selection() is None:
                self._buffer.select_all()
            self._buffer.insert("")
    def on_paste(self, event: events.Paste) -> None:
        """Text the terminal pasted (ctrl+shift+v) lands at the caret."""
        if self.editing and self._buffer is not None:
            self._buffer.insert(event.text)
            self._sync_preview()
            event.stop()
    def action_justify(self) -> None:
        """^J — reflow a cell's text to a width you give, the way nano justifies."""
        node_id = self._edit_id if self.editing else self.focus
        if node_id is None:
            return
        self._justify_id = node_id
        self._show_prompt(
            "justify",
            "Justify to width: ",
            str(self.mm.justify or self.config.justify_width_default),
            preselect=True,
            submit=self._justify_submitted,
            cancel=self._close_drawers,
        )
    def _justify_submitted(self, value: str) -> None:
        self._close_drawers()
        try:
            width = int(value.strip())
        except ValueError:
            width = self.mm.justify or self.config.justify_width_default
        width = max(10, min(width, 400))
        if width != self.mm.justify:
            # the width is part of the map, so a file opened elsewhere justifies
            # the same way; the config only holds the default to offer
            self.mm.justify = width
            self._mark_dirty()
        node_id, self._justify_id = self._justify_id, None
        if node_id is None:
            return
        if self.editing and self._buffer is not None and node_id == self._edit_id:
            self._buffer.text = reflow(self._buffer.text, width)
            self._buffer.caret = min(self._buffer.caret, len(self._buffer.text))
            self._buffer.anchor = None
            self._sync_preview()
            return
        node = self.document.find(node_id)
        if node is None:
            return
        wrapped = reflow(node.text, width)
        if wrapped == node.text:
            return
        self._push_undo()
        node.text = wrapped
        self._touched(node.id)
        self._mark_dirty()
    def finish_edit(self, *, commit: bool) -> None:
        node_id = self._edit_id
        self._edit_id = None
        node = self._live_node(node_id) if node_id else None
        text = self._buffer.text.strip() if self._buffer is not None else ""
        fresh = self._edit_fresh
        if node is not None:
            node.preview = None
            node.caret = None
            node.overwrite = False
            node.sel = None
        self._buffer = None

        if node is None or not commit or not text:
            # An abandoned new node was only ever a promise; take it away again.
            if fresh and node is not None:
                result = self.mm.delete(node.id)
                if result is not None:
                    self.selected = result[1]
            self._sync_footer()
            self.view.refresh_map()
            return

        if node.text != text:
            node.text = text
            self._touched(node.id)
            self._mark_dirty()
        else:
            self.view.refresh_map()
        self._sync_footer()

