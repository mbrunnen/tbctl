import keyring
import keyring.backend
import keyring.backends.fail
import pytest


class MemoryKeyring(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self):
        self.store = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    """Redirect the config directory so no test reads the real user config."""
    monkeypatch.setattr("tbctl.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("tbctl.config._warned", set(), raising=False)
    return tmp_path


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    """Keep every test away from the real Secret Service and the caller's environment."""
    monkeypatch.delenv("TBCTL_TOKEN", raising=False)
    monkeypatch.delenv("_TBCTL_COMPLETE", raising=False)
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    return backend


@pytest.fixture
def no_keyring():
    """Simulate a container, where no Secret Service is reachable."""
    keyring.set_keyring(keyring.backends.fail.Keyring())


class BrokenKeyring(MemoryKeyring):
    """Raise what secretstorage and jeepney raise past keyring's own error types."""

    def get_password(self, service, username):
        raise Exception("Cannot unlock the wallet")

    def set_password(self, service, username, password):
        raise Exception("Cannot unlock the wallet")


@pytest.fixture
def broken_keyring():
    keyring.set_keyring(BrokenKeyring())
