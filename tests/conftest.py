import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Editor preferences live in XDG_CONFIG_HOME; keep tests off the real file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))
