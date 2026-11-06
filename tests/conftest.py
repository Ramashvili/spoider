import pytest

from spoider.text import DEFAULT_TAB_WIDTH, set_tab_width


@pytest.fixture(autouse=True)
def _default_tab_width():
    """The tab stop lives in spoider.text, so a test that changes it must not leak."""
    set_tab_width(DEFAULT_TAB_WIDTH)
    yield
    set_tab_width(DEFAULT_TAB_WIDTH)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Keep tests off the real config and data directories."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data-home"))
