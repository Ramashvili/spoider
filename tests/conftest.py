import pytest


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Editor preferences live in XDG_CONFIG_HOME; keep tests off the real file."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config-home"))


@pytest.fixture(autouse=True)
def registered_desktop(tmp_path_factory, monkeypatch):
    """Pretend `.spoider` is already registered, so the first-run question stays away.

    Every other test would otherwise open a drawer nobody asked it about. The tests of
    that question point XDG_DATA_HOME at an empty directory themselves.
    """
    data_home = tmp_path_factory.mktemp("data-home")
    entry = data_home / "applications" / "spoider.desktop"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("[Desktop Entry]\nName=spoider\n")
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
