# pyright: reportAttributeAccessIssue=false
"""One area of SpoiderApp's keys: edit actions.

A mixin, so the methods keep using the app's own state and helpers. Nothing here is
bound directly; the bindings live in app.py.
"""

from __future__ import annotations

from textual import events

from .chrome import FAILURE, QUICK
from .editing import Buffer, reflow
from .model import MAX_CELL_CHARS
from .text import clean_text

#: Character keys that can arrive named and empty-handed, and what they type.
PUNCTUATION = {
    "period": ".",
    "full_stop": ".",
    "comma": ",",
    "colon": ":",
    "semicolon": ";",
    "exclamation_mark": "!",
    "question_mark": "?",
    "apostrophe": "'",
    "quotation_mark": '"',
    "hyphen": "-",
    "minus": "-",
    "plus": "+",
    "equals_sign": "=",
    "slash": "/",
    "backslash": "\\",
    "paren_left": "(",
    "paren_right": ")",
    "bracket_left": "[",
    "bracket_right": "]",
    "underscore": "_",
    "at": "@",
    "hash": "#",
    "percent": "%",
    "ampersand": "&",
    "asterisk": "*",
    "space": " ",
}


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
        self._buffer.PAGE_LINES = self.config.page_lines
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
        if key == "enter":
            self.finish_edit(commit=True)
            return True
        if key == "tab":
            # A cell is a text field, so Tab types a tab; making a child is what Tab
            # does on the map, where Return already covers the same ground
            buffer.insert("\t")
            self._sync_preview()
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
            "pageup": buffer.page_up,
            "pagedown": buffer.page_down,
            "ctrl+left": buffer.word_left,
            "ctrl+right": buffer.word_right,
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
            self._insert_and_warn(buffer, self._text_clip)
        elif self._action_for(key) == "justify":
            self.action_justify()
        elif self._action_for(key) == "undo":
            buffer.undo()
        elif self._action_for(key) == "redo":
            buffer.redo()
        elif character and character.isprintable():
            buffer.insert(character)
        elif key in PUNCTUATION:
            # Some terminals send a character key by name, with no character of its own.
            # A cell still has to be able to end a sentence.
            buffer.insert(PUNCTUATION[key])
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
        self.notify("copied cell text to the terminal clipboard", timeout=QUICK)
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
            self._insert_and_warn(self._buffer, event.text)
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
    def _insert_and_warn(self, buffer: Buffer, chunk: str) -> None:
        """Insert, and say so when the cell was full: pasted text is never silently cut.

        The chunk is cleaned first. A clipboard can carry a tab, a carriage return or an
        escape sequence, and the loader strips those from a saved map, so text that
        skipped them would come back different the next time the map was opened.
        """
        buffer.clipped = False
        buffer.insert(clean_text(chunk))
        if buffer.clipped:
            self.notify(
                f"a cell holds {MAX_CELL_CHARS} characters at most, so the end was dropped",
                severity="error",
                timeout=FAILURE,
            )

    def finish_edit(self, *, commit: bool) -> None:
        node_id = self._edit_id
        self._edit_id = None
        # The tree the keys are in: the map, or the panel's copy of the stack. Deleting
        # from `self.mm` while the panel has the keys missed the copy every time, so an
        # abandoned cell in the panel stayed, and the copy was then written back with it.
        doc = self.document
        node = doc.find(node_id) if node_id else None
        text = self._buffer.text.strip() if self._buffer is not None else ""
        fresh = self._edit_fresh
        if node is not None:
            node.preview = None
            node.caret = None
            node.overwrite = False
            node.sel = None
        self._buffer = None

        if node is None or not commit:
            # An abandoned new node was only ever a promise; take it away again. An empty
            # commit is not abandonment: an empty cell is a cell, and the screen draws it
            # as "(empty)" until something is typed into it.
            if fresh and node is not None:
                result = doc.delete(node.id)
                if self.stack_open:
                    self._commit_stack(doc)
                if result is not None:
                    self.selected = result[1]
                if self.stack_open:
                    self._stack_changed()
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

