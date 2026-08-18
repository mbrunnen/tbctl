import pytest


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    """Redirect the config directory so no test reads the real user config."""
    monkeypatch.setattr("tbctl.config.CONFIG_DIR", tmp_path)
    return tmp_path
