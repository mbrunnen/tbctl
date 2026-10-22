import keyring.errors
import pytest

from tbctl import credentials


def test_store_then_get():
    credentials.store("prod", "t1")
    assert credentials.get("prod") == "t1"


def test_profiles_are_separate():
    credentials.store("prod", "t1")
    assert credentials.get("default") is None


def test_env_overrides_keyring(monkeypatch):
    credentials.store("prod", "t1")
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.get("prod") == "env"


def test_empty_env_falls_back_to_keyring(monkeypatch):
    credentials.store("prod", "t1")
    monkeypatch.setenv("TBCTL_TOKEN", "")
    assert credentials.get("prod") == "t1"


def test_get_without_backend_returns_none(no_keyring):
    assert credentials.get("prod") is None


def test_get_without_backend_uses_env(no_keyring, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.get("prod") == "env"


def test_store_without_backend_raises(no_keyring):
    with pytest.raises(keyring.errors.KeyringError):
        credentials.store("prod", "t1")


def test_get_with_broken_backend_returns_none(broken_keyring):
    assert credentials.get("prod") is None
