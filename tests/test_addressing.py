"""`--position`: reading an address and finding the cell it names."""

from __future__ import annotations

import pytest

from spoider.addressing import Address, parse, resolve
from spoider.model import MindMap, Node


def map_with_path() -> tuple[MindMap, dict[str, Node]]:
    mm = MindMap(Node("root"))
    one = mm.add_child(mm.root.id, "one")
    two = mm.add_child(mm.root.id, "two")
    one_one = mm.add_child(one.id, "one-one")
    one_two = mm.add_child(one.id, "one-two")
    two_one = mm.add_child(two.id, "two-one")
    return mm, {
        "one": one,
        "two": two,
        "one-one": one_one,
        "one-two": one_two,
        "two-one": two_one,
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0", Address(stack=False, steps=())),
        ("2", Address(stack=False, steps=(2,))),
        ("1.2", Address(stack=False, steps=(1, 2))),
        ("1.1.1", Address(stack=False, steps=(1, 1, 1))),
        ("s1", Address(stack=True, steps=(1,))),
        ("S2.1", Address(stack=True, steps=(2, 1))),
        (" 7.4.9 ", Address(stack=False, steps=(7, 4, 9))),
    ],
)
def test_an_address_is_a_path_of_one_based_children(text: str, expected: Address):
    assert parse(text) == expected


@pytest.mark.parametrize("text", ["", " ", "x", "1..2", "1.a", "0.1", "1.0", "s", "-2", "s-2"])
def test_words_that_name_no_cell_are_rejected(text: str):
    assert parse(text) is None


def test_the_root_is_zero_and_the_nth_child_is_n():
    mm, nodes = map_with_path()
    assert resolve(mm, Address(stack=False, steps=())) == mm.root.id
    assert resolve(mm, Address(stack=False, steps=(2,))) == nodes["two"].id
    assert resolve(mm, Address(stack=False, steps=(1, 2))) == nodes["one-two"].id


def test_an_address_past_the_end_names_nothing():
    mm, _ = map_with_path()
    assert resolve(mm, Address(stack=False, steps=(3,))) is None
    assert resolve(mm, Address(stack=False, steps=(1, 3))) is None


def test_the_stack_is_addressed_newest_first():
    mm, _ = map_with_path()
    older = Node("older")
    newer = Node("newer", children=[Node("child")])
    mm.cut_stack = [older, newer]  # newest last, as a cut is appended
    assert resolve(mm, Address(stack=True, steps=(1,))) == newer.id
    assert resolve(mm, Address(stack=True, steps=(2,))) == older.id
    assert resolve(mm, Address(stack=True, steps=(1, 1))) == newer.children[0].id
    assert resolve(mm, Address(stack=True, steps=(3,))) is None
