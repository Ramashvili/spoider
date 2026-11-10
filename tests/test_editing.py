"""The text inside a cell, without a terminal, a key or a screen.

Driving these through the app costs a mounted screen per case and hides which rule
broke; here one line says what changed.
"""

from spoider.editing import Buffer, reflow


def at(text: str, caret: int | None = None) -> Buffer:
    buffer = Buffer(text)
    buffer.caret = len(text) if caret is None else caret
    return buffer


# -- words -------------------------------------------------------------------


def test_alt_backspace_eats_the_word_before_the_caret():
    buffer = at("one two three")  # the caret starts at the end
    buffer.delete_word_before()
    assert buffer.text == "one two "
    assert buffer.caret == 8


def test_alt_backspace_takes_the_punctuation_with_the_word():
    buffer = at("one two, three.")
    buffer.delete_word_before()
    assert buffer.text == "one two, "


def test_alt_backspace_at_the_start_of_the_text_does_nothing():
    buffer = at("word", 0)
    buffer.delete_word_before()
    assert buffer.text == "word"
    assert buffer.caret == 0


def test_a_word_ends_at_every_kind_of_punctuation():
    """A jump and a deletion answer to the same rule: anything that is not a space, a mark of
    punctuation or a sign a line of code leans on is part of the word."""
    buffer = at("see foo.bar(baz)#qux")
    stops = []
    while buffer.caret:
        buffer.word_left()
        stops.append(buffer.caret)
    assert stops == [17, 12, 8, 4, 0], "qux, baz, bar, foo, see"

    buffer = at("see foo.bar(baz)#qux")
    buffer.delete_word_before()
    assert buffer.text == "see foo.bar(baz)#", "the word alone goes"
    buffer.delete_word_before()
    assert buffer.text == "see foo.bar(", "and the sign and bracket after it"
    buffer.delete_word_before()
    assert buffer.text == "see foo.", "a bracket before a word is not the word's"


def test_alt_d_eats_the_word_after_the_caret():
    buffer = at("one two three", 4)  # on the "t" of "two"
    buffer.delete_word_after()
    assert buffer.text == "one  three", "the space before the caret stays"
    assert buffer.caret == 4


def test_alt_d_at_the_end_of_the_text_does_nothing():
    buffer = at("word", 4)
    buffer.delete_word_after()
    assert buffer.text == "word"


def test_a_word_delete_replaces_a_selection_instead():
    buffer = at("one two three", 0)
    buffer.select_all()
    buffer.delete_word_after()
    assert buffer.text == ""


# -- the edges of the text ---------------------------------------------------


def test_backspace_at_the_start_does_nothing():
    buffer = at("word", 0)
    buffer.backspace()
    assert buffer.text == "word"


def test_delete_at_the_end_does_nothing():
    buffer = at("word", 4)
    buffer.delete()
    assert buffer.text == "word"


def test_backspace_and_delete_join_lines():
    buffer = at("one\ntwo", 4)  # just after the newline
    buffer.backspace()
    assert buffer.text == "onetwo", "the newline is one character like any other"
    assert buffer.caret == 3

    buffer = at("one\ntwo", 3)  # just before it
    buffer.delete()
    assert buffer.text == "onetwo"


# -- overwrite ---------------------------------------------------------------


def test_overwrite_replaces_a_character_but_never_a_line_break():
    buffer = at("abc", 0)
    buffer.overwrite = True
    buffer.insert("X")
    assert buffer.text == "Xbc"

    buffer = at("a\nb", 1)  # on the break
    buffer.overwrite = True
    buffer.insert("X")
    assert buffer.text == "aX\nb", "typing at the end of a line pushes, it does not eat the break"


def test_typing_over_a_selection_replaces_it_even_in_overwrite_mode():
    buffer = at("abc def", 0)
    buffer.overwrite = True
    buffer.anchor = 2
    buffer.caret = 5  # the selection "c d"
    buffer.insert("X")
    assert buffer.text == "abXef"


# -- selections --------------------------------------------------------------


def test_a_plain_move_collapses_a_selection_to_the_end_it_moves_towards():
    buffer = at("abc def", 0)
    buffer.anchor = 2
    buffer.caret = 5

    buffer.left()
    assert buffer.caret == 2 and buffer.selection() is None

    buffer.anchor = 2
    buffer.caret = 5
    buffer.right()
    assert buffer.caret == 5 and buffer.selection() is None


def test_shift_and_a_key_extends_from_the_anchor():
    buffer = at("abc def", 0)
    buffer.right(extend=True)
    buffer.right(extend=True)
    assert buffer.selected_text() == "ab"


def test_home_and_end_hold_the_line_not_the_text():
    buffer = at("one\ntwo", 6)
    buffer.home()
    assert buffer.caret == 4
    buffer.end()
    assert buffer.caret == 7
    buffer.document_home()
    assert buffer.caret == 0
    buffer.document_end()
    assert buffer.caret == 7


# -- undo --------------------------------------------------------------------


def test_a_run_of_typing_is_one_undo_step():
    buffer = at("")
    for character in "hello":
        buffer.insert(character)
    buffer.undo()
    assert buffer.text == "", "the whole run, not one character"


def test_a_run_of_backspaces_is_one_undo_step():
    buffer = at("one two three")
    for _ in range(5):
        buffer.backspace()
    assert buffer.text == "one two "
    assert buffer.undo()
    assert buffer.text == "one two three", "the whole run comes back at once, not letter by letter"


def test_a_move_ends_the_run():
    buffer = at("abcdef")
    buffer.backspace()
    buffer.backspace()
    assert buffer.text == "abcd"
    buffer.left()  # a move closes the run
    buffer.backspace()
    assert buffer.text == "abd"
    buffer.undo()
    assert buffer.text == "abcd", "the step after the move comes back on its own"
    buffer.undo()
    assert buffer.text == "abcdef", "and the run before it is the next step"


def test_typing_and_deleting_are_separate_steps():
    buffer = at("")
    for character in "abc":
        buffer.insert(character)
    buffer.backspace()
    assert buffer.text == "ab", "a deletion after typing is not part of that run"
    buffer.undo()
    assert buffer.text == "abc"
    buffer.undo()
    assert buffer.text == ""


def test_a_word_delete_is_its_own_step():
    buffer = at("one two")
    for character in "!":
        buffer.insert(character)
    buffer.delete_word_before()
    buffer.undo()
    assert buffer.text == "one two!", "the word came back, not the typing"
    buffer.undo()
    assert buffer.text == "one two"


# -- justify -----------------------------------------------------------------


def test_reflow_fills_a_paragraph_greedily():
    assert reflow("one two three four", 8) == "one two\nthree\nfour"


def test_reflow_keeps_paragraphs_apart():
    assert reflow("one two\n\nthree four", 40) == "one two\n\nthree four"


def test_a_word_longer_than_the_width_keeps_its_line():
    assert reflow("supercalifragilistic and more", 6) == "supercalifragilistic\nand\nmore"


def test_reflow_collapses_the_whitespace_it_is_given():
    assert reflow("one    two\n  three", 40) == "one two three"


def test_reflow_keeps_one_blank_line_between_paragraphs():
    assert reflow("one\n\n\n\ntwo", 40) == "one\n\ntwo", "four breaks read as one break"
    assert reflow("one\n\n\n\n\n\ntwo", 40) == "one\n\ntwo"


def test_reflow_collapses_the_tabs_it_is_given():
    # a tab is a break between two words, not an indent the wrap has to carry
    assert reflow("one\n\t\tthree four", 40) == "one three four"
    assert reflow("\t\tone two", 40) == "one two"


def test_reflow_of_an_empty_line_is_an_empty_line():
    assert reflow("", 20) == ""
