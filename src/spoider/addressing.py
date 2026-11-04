"""Reading `--position`: which cell the cursor starts on.

An address is a path of 1-based child numbers, `0` for the root itself: `9` is the ninth
child of the root, `7.4.9` the ninth child of the fourth grandchild of the seventh child.
`0` inside a path is not a cell, so it is rejected rather than silently guessed at.

The cut stack is addressed with a leading `s`, in the order the panel shows it (newest
first): `s2` is the second cut, `s2.1` its first child. A malformed or out-of-range address
falls back to the root, which is what an argument nobody typed should do.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import MindMap

STACK_PREFIX = "s"


@dataclass(frozen=True)
class Address:
    """A path to a cell, and which of the two documents it names."""

    stack: bool
    steps: tuple[int, ...]


def parse(text: str) -> Address | None:
    """The address `text` spells, or None when it spells nothing."""
    cleaned = text.strip().lower()
    if not cleaned:
        return None
    stack = cleaned.startswith(STACK_PREFIX)
    if stack:
        cleaned = cleaned[len(STACK_PREFIX) :]
    parts = cleaned.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return None
    numbers = tuple(int(part) for part in parts)
    if not stack and numbers == (0,):
        return Address(stack=False, steps=())
    if any(number < 1 for number in numbers):
        return None
    return Address(stack=stack, steps=numbers)


def resolve(mm: MindMap, address: Address) -> str | None:
    """The id the address points at, or None when the map has no such cell."""
    if address.stack:
        # newest first, which is the order the panel draws
        entries = list(reversed(mm.cut_stack))
        if not address.steps or address.steps[0] > len(entries):
            return None
        node = entries[address.steps[0] - 1]
        steps = address.steps[1:]
    else:
        node = mm.root
        steps = address.steps
    for step in steps:
        if step > len(node.children):
            return None
        node = node.children[step - 1]
    return node.id
