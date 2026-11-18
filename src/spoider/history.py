"""One undoable step: the document, and what it did to the fine histories of cells.

A cell's own history is fine, one step per burst of typing, and it outlives the visit that made it.
A step of the document's history is coarse, one per edit. The two describe the same words, so a
step of one has to carry what happened to the other: undoing a coarse step takes the fine steps it
consumed with it, and redoing it puts them back.

The stacks are captured whole rather than as a delta. A buffer's stacks are lists of `(text, caret)`
tuples, so copying them is cheap and exact, and no bookkeeping has to run during the edit.
"""

from __future__ import annotations

from dataclasses import dataclass

#: One fine step of a cell: the text as it was, and where the caret stood.
Fine = tuple[str, int]


@dataclass
class CellSteps:
    """What one step of the document did to one cell's fine history.

    Made at the first keystroke, when the stacks before the change are known, and completed when the
    cell is left, when the stacks after it are. The same object is read backwards for an undo and
    forwards for a redo, so both directions come from one record.
    """

    cell: str
    undo_before: tuple[Fine, ...] = ()
    redo_before: tuple[Fine, ...] = ()
    undo_after: tuple[Fine, ...] = ()
    redo_after: tuple[Fine, ...] = ()
    complete: bool = False

    def backwards(self) -> tuple[tuple[Fine, ...], tuple[Fine, ...]]:
        """The cell's stacks as they stood before the step."""
        return self.undo_before, self.redo_before

    def forwards(self) -> tuple[tuple[Fine, ...], tuple[Fine, ...]]:
        """The cell's stacks as they stood after it."""
        return self.undo_after, self.redo_after


@dataclass(frozen=True)
class Step:
    """One step of the document's history: the map as packed JSON, and the cells it moved."""

    document: bytes
    cells: tuple[CellSteps, ...] = ()
