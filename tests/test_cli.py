"""The command line is one function with three jobs: a path, a flag, and no mouse.

Tested by standing a stub in for the app, so nothing waits for a terminal.
"""

from pathlib import Path

from spoider import app as module


def _run(monkeypatch, argv: list[str]) -> dict:
    seen: dict = {}

    class Stub:
        def __init__(
            self, path: Path | None, demo: bool = False, position: str | None = None
        ) -> None:
            seen["path"] = path
            seen["demo"] = demo
            seen["position"] = position

        def run(self, **kwargs) -> None:
            seen["run"] = kwargs

    monkeypatch.setattr(module, "SpoiderApp", Stub)
    module.main(argv)
    return seen


def test_a_path_on_the_command_line_is_the_map_to_open(monkeypatch, tmp_path: Path):
    seen = _run(monkeypatch, [str(tmp_path / "map.json")])
    assert seen["path"] == tmp_path / "map.json"
    assert seen["demo"] is False
    assert seen["run"] == {"mouse": False}, "the terminal keeps its own mouse"


def test_no_argument_starts_a_new_buffer(monkeypatch):
    seen = _run(monkeypatch, [])
    assert seen["path"] is None
    assert seen["demo"] is False


def test_the_position_flag_is_handed_to_the_app(monkeypatch):
    assert _run(monkeypatch, [])["position"] == "0", "the root when nothing is asked for"
    assert _run(monkeypatch, ["-p", "7.4.9"])["position"] == "7.4.9"
    assert _run(monkeypatch, ["--position", "s2.1"])["position"] == "s2.1"
    assert _run(monkeypatch, ["-p7.4"])["position"] == "7.4"


def test_the_demo_flag_has_a_short_form(monkeypatch):
    assert _run(monkeypatch, ["-d"])["demo"] is True
    assert _run(monkeypatch, ["--demo"])["demo"] is True


def test_the_help_lists_the_options_and_says_how_to_start(monkeypatch, capsys):
    try:
        module.main(["--help"])
    except SystemExit:
        pass
    printed = capsys.readouterr().out
    for option in ("-d, --demo", "-p ADDRESS", "--install-desktop"):
        assert option in printed, option
    assert "tab makes a child" in printed, "and the first thing to know"


def test_the_demo_flag_is_what_asks_for_the_demo_map(monkeypatch):
    assert _run(monkeypatch, ["--demo"])["demo"] is True
    assert _run(monkeypatch, [])["demo"] is False, "and it is off unless asked for"


def test_a_tilde_in_the_path_is_the_home_directory(monkeypatch):
    seen = _run(monkeypatch, ["~/maps/one.json"])
    assert seen["path"] == Path.home() / "maps" / "one.json"
