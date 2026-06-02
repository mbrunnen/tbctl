import pytest


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr("tb.config.CONFIG_PATH", path)
    return path
