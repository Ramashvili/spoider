"""The command line is one function with three jobs: a path, a flag, and no mouse.

Tested by standing a stub in for the app, so nothing waits for a terminal.
"""

from pathlib import Path

from spoider import app as module
from spoider.config import Config
from spoider.model import MindMap, Node


def _run(monkeypatch, argv: list[str]) -> dict:
    seen: dict = {}

    class Stub:
        def __init__(
            self,
            path: Path | None,
            demo: bool = False,
            position: str | None = None,
            cell_id: str | None = None,
        ) -> None:
            seen["path"] = path
            seen["demo"] = demo
            seen["position"] = position
            seen["cell_id"] = cell_id
            # an app whose config already holds the desktop answer, so no question
            self.config = Config(desktop_asked=True)
            self.load_error = None
            self.config_path = Path("/nonexistent/spoider.conf")

        def _key_entries(self) -> list[tuple[str, str, str]]:
            return []

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
    assert _run(monkeypatch, [])["position"] is None, "the file's own cursor, when nothing is asked"
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


def test_an_empty_position_is_refused(monkeypatch, capsys):
    """Quoting nothing must not silently throw away the cursor the file remembers."""
    try:
        module.main(["-p", ""])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("an empty address should be refused")
    assert "needs an address" in capsys.readouterr().err


def test_an_empty_id_is_refused(capsys):
    try:
        module.main(["--id", ""])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("an empty id should be refused")
    assert "--id needs a cell id" in capsys.readouterr().err


def test_position_and_id_together_are_refused(tmp_path, capsys):
    path = tmp_path / "map.spoider"
    MindMap(Node("root")).save(path)
    try:
        module.main(["-p", "0", "--id", "abc", str(path)])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("two ways to place the cursor should be refused")
    assert "not both" in capsys.readouterr().err


def test_an_id_that_is_not_in_the_map_is_refused(tmp_path, capsys):
    """A program launching a map wants a code it can test, not a map in the wrong place."""
    path = tmp_path / "map.spoider"
    MindMap(Node("root")).save(path)
    try:
        module.main(["--id", "nosuchcell", str(path)])
    except SystemExit as exit_code:
        assert exit_code.code == 2, "the refusal must be visible to a caller"
    else:
        raise AssertionError("an unknown id should be refused")
    assert "not a cell in this map" in capsys.readouterr().err


# -- the desktop question, before the screen exists ------------------------


class _FakeTTY:
    def isatty(self) -> bool:
        return True


class _FakePipe:
    def isatty(self) -> bool:
        return False


def _launch(monkeypatch, tmp_path: Path, answers: list[str], *, tty: bool = True) -> dict:
    """Run main() as far as the question, without starting the screen."""
    seen: dict = {"installed": 0, "printed": ""}
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(module.sys, "stdin", _FakeTTY() if tty else _FakePipe())
    monkeypatch.setattr(module.SpoiderApp, "run", lambda self, **kwargs: None)
    monkeypatch.setattr(
        module, "install_desktop", lambda: seen.__setitem__("installed", seen["installed"] + 1) or 0
    )
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies, ""))
    module.main([str(tmp_path / "map.spoider")])
    return seen


def _config(tmp_path: Path) -> Path:
    return tmp_path / "config" / "spoider" / "spoider.conf"


def test_the_desktop_question_runs_before_the_screen(monkeypatch, tmp_path: Path):
    seen = _launch(monkeypatch, tmp_path, ["n"])
    config = _config(tmp_path)
    assert config.exists(), "the answer needs a file to live in"
    text = config.read_text(encoding="utf-8")
    assert "desktop_asked = true" in text
    assert "editor settings" in text, "written as the template, not a single line"
    assert seen["installed"] == 0


def test_answering_yes_installs_the_desktop_files(monkeypatch, tmp_path: Path):
    seen = _launch(monkeypatch, tmp_path, ["y"])
    assert seen["installed"] == 1


def test_the_question_says_what_it_will_write(capsys, monkeypatch, tmp_path: Path):
    _launch(monkeypatch, tmp_path, ["n"])
    out = capsys.readouterr().out
    for line in (
        "x-spoider.xml",
        "spoider.desktop",
        "update-mime-database",
        "update-desktop-database",
        "xdg-mime",
    ):
        assert line in out, f"the question should name {line}"


def test_a_pipe_is_not_asked_and_nothing_is_recorded(monkeypatch, tmp_path: Path):
    """A program launching a map gets no question, and the question survives."""
    _launch(monkeypatch, tmp_path, [], tty=False)
    config = _config(tmp_path)
    assert not config.exists() or "desktop_asked = true" not in config.read_text()


def test_a_config_that_holds_the_answer_is_not_asked(monkeypatch, tmp_path: Path):
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    config.write_text("desktop_asked = true\n", encoding="utf-8")
    seen = _launch(monkeypatch, tmp_path, [])
    assert seen["installed"] == 0
    assert config.read_text(encoding="utf-8") == "desktop_asked = true\n"


def test_deleting_the_config_brings_the_question_back(monkeypatch, tmp_path: Path):
    entry = tmp_path / "data" / "applications"
    entry.mkdir(parents=True)
    (entry / "spoider.desktop").write_text("[Desktop Entry]\nName=spoider\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    config = _config(tmp_path)
    config.parent.mkdir(parents=True)
    config.write_text("# mine\ndesktop_asked = true\n", encoding="utf-8")

    _launch(monkeypatch, tmp_path, [])
    assert "desktop_asked = true" in config.read_text()

    config.unlink()
    seen = _launch(monkeypatch, tmp_path, ["y"])
    assert seen["installed"] == 1, "the record was deleted, so the question returns"


def test_a_file_that_is_not_a_map_leaves_a_code_behind(monkeypatch, tmp_path: Path):
    """A launcher gets a failure, not a map that quietly turned into an empty buffer."""
    bad = tmp_path / "notes.txt"
    bad.write_text("my notes\n", encoding="utf-8")
    monkeypatch.setattr(module.sys.stdin, "isatty", lambda: False)
    app_holder: dict = {}

    def fake_run(self, **kwargs) -> None:
        app_holder["message"] = self.load_error

    monkeypatch.setattr(module.SpoiderApp, "run", fake_run)
    try:
        module.main([str(bad)])
    except SystemExit as exit_code:
        assert exit_code.code == 2
    else:
        raise AssertionError("an unreadable file should end with a failure code")
    assert app_holder["message"] is not None, "and it had a reason to give"
