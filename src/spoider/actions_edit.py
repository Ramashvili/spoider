# pyright: reportAttributeAccessIssue=false
"""One area of SpoiderApp's keys: edit actions.

A mixin, so the methods keep using the app's own state and helpers. Nothing here is
bound directly; the bindings live in app.py.
"""

from __future__ import annotations

from textual import events

from .chrome import FAILURE, NOTE, QUICK
from .editing import Buffer, reflow
from .layout import box_height, box_width
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
        self._edit_id = node_id
        self._edit_fresh = fresh
        # Nothing goes into the history yet: a cell opened and closed again changes nothing, and a
        # step that changes nothing also throws away the redo stack. The snapshot is taken at the
        # first keystroke that really changes the cell.
        self._edit_was = "" if fresh else (node.text or "")
        self._edit_pushed = fresh  # making the cell was already a step of its own
        # A cell that has been visited before brings its fine history back, so ^Z here walks the
        # steps of the earlier visits as well; the document's words are the ones it comes back to.
        filed = None if fresh else self._filed.get(node_id)
        buffer = filed if filed is not None else Buffer("" if fresh else (node.text or ""))
        buffer.text = node.text or ""
        buffer.caret = min(buffer.caret, len(buffer.text))
        buffer.anchor = None
        buffer.break_run()
        self._buffer = buffer
        self._buffer.PAGE_LINES = self.config.page_lines
        self._caret_moved()  # a cell that has just opened starts solid, and blinks after a pause
        self._edit_before = buffer.stacks()
        self._edit_delta = None
        if fresh:
            # making the cell was a step, so the typing inside it belongs to that step and an undo
            # of the step takes the typing with it
            self._edit_delta = self._attach_cell_steps(node_id, self._edit_before)
        # the picture is new to this cell, so the first synchronisation must rebuild it
        self._picture_key = None
        self._state_key = None
        self._sync_preview()
        self._sync_footer()
    def _sync_preview(self) -> None:
        node = self._live_node(self._edit_id) if self._edit_id else None
        if node is None:
            return
        if self._buffer is None:
            return
        self._caret_moved()
        if not self._edit_pushed and self._buffer.text != self._edit_was:
            self._push_undo()
            self._edit_pushed = True
            # the step this keystroke makes is the one that carries the visit's fine steps
            self._edit_delta = self._attach_cell_steps(self._edit_id or "", self._edit_before)
        node.preview = self._buffer.text
        node.caret = self._buffer.caret
        node.overwrite = self._buffer.overwrite
        node.sel = self._buffer.selection()
        # The picture depends on the text and the selection in it, not on where the caret
        # stands: moving the caret repaints one cell, and rebuilding the whole map for it was
        # most of what holding a key cost.
        # What the picture is made of, and everything the screen shows of this cell. A key
        # that moves nothing, a right at the last character, is neither: the caret cannot go
        # past the edge, and repainting the map for it was a wasted frame per press.
        picture = (node.preview, node.sel)
        state = (picture, node.caret, node.overwrite)
        if state == self._state_key:
            return
        self._state_key = state
        if picture == self._picture_key:
            # the caret moved, or the mode did: two rows of the screen, and nothing else
            self.view.refresh_caret()
            return
        self._picture_key = picture
        if self._kept_its_size(node):
            # the box says something else but is no bigger, so nothing around it moves
            self.view.refresh_picture()
        else:
            self.view.refresh_map()

    def _kept_its_size(self, node) -> bool:
        """Whether a cell's box is still the size the arrangement gave it.

        A wider box moves its children and its siblings, so the arrangement is redone; a box that
        stayed the same size moves nothing and only its own cells change.

        A cell in the panel is measured against the panel's arrangement, which is the one that holds
        it. The panel's arrangement is kept until the document changes, and a preview is not a
        document change, so a growing entry keeps the boxes it was drawn with and never widens: the
        memo is dropped here when the size moved, which is what makes the panel behave like the map.
        """
        if self.stack_open and self._stack_doc().find(node.id) is not None:
            panel = self.stack_layout()
            if panel is None:
                return False
            placed = panel.box(node.id)
            if placed is None:
                return False
            kept = placed.w == box_width(node, panel.walls) and placed.h == box_height(
                node, panel.walls
            )
            if not kept:
                self._stack_layout_key = None  # the arrangement is worked out again with the text
            return kept
        layout = self.view.layout_
        placed = layout.box(node.id)
        if placed is None:
            return False
        return placed.w == box_width(node, layout.walls) and placed.h == box_height(
            node, layout.walls
        )
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
        if key == "escape":
            # esc finishes the cell the way enter does: the text is what you typed, and ^Z is
            # the way back if it was not what you meant. A new cell nobody typed into is the one
            # exception: there is nothing to keep, so it goes as it always did.
            typed = (buffer.text or "").strip()
            self.finish_edit(commit=bool(typed) or not self._edit_fresh)
            return True
        if key == "ctrl+c":
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
        elif key in ("alt+d", "alt+delete"):
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
            if not self._text_clip:
                # a key that would do nothing says it did nothing: silence reads as a lost key
                self.notify("nothing to paste", severity="warning", timeout=NOTE)
            else:
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
        self.notify("cell text copied", timeout=QUICK)
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
            event.stop()
            if not clean_text(event.text):
                # a paste of nothing is still a key the reader pressed: say it landed nowhere
                self.notify("nothing to paste", severity="warning", timeout=NOTE)
                return
            self._insert_and_warn(self._buffer, event.text)
            self._sync_preview()
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
        if self._buffer is not None:
            if commit and node is not None and node_id is not None:
                # the visit is over: the steps it made are what the step of the document carries,
                # and the buffer files itself away for the next visit to that cell
                if self._edit_delta is not None:
                    undo, redo = self._buffer.stacks()
                    self._edit_delta.undo_after = undo
                    self._edit_delta.redo_after = redo
                    self._edit_delta.complete = True
                self._file_buffer(node_id, self._buffer)
            else:
                # nothing of the visit happened, so its steps go back with its words
                self._buffer.set_stacks(*self._edit_before)
                self._buffer.text = (node.text or "") if node is not None else ""
                self._buffer.caret = min(self._buffer.caret, len(self._buffer.text))
                self._forget_cell_steps(self._edit_delta)
        self._edit_delta = None
        self._buffer = None
        self.view.caret_visible = True  # the next cell to open starts solid
        self._edit_was, self._edit_pushed = None, False

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
                if self._undo:
                    # the cell is gone again, so making it is not a step either
                    self._undo.pop()
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

