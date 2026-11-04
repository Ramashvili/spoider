import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Editor preferences live in XDG_CONFIG_HOME; keep tests off the real file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))


@pytest.fixture(autouse=True)
def no_first_run_question(request, tmp_path_factory, monkeypatch):
    """Keep the desktop question out of tests that are not about it.

    A test that *is* about it marks itself `desktop_question` and gets the real gate.
    """
    data_home = tmp_path_factory.mktemp("data-home")
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    if request.node.get_closest_marker("desktop_question"):
        return
    monkeypatch.setattr(
        "spoider.app.SpoiderApp._maybe_ask_desktop", lambda self: None
    )
