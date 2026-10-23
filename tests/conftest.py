import keyring
import keyring.backend
import keyring.backends.fail
import keyring.errors
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
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("not found")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    """Redirect the config directory so no test reads the real user config."""
    monkeypatch.setattr("tbctl.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("tbctl.config._warned", set(), raising=False)
    monkeypatch.setattr("tbctl.credentials._warned", set(), raising=False)
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

    def delete_password(self, service, username):
        raise Exception("Cannot unlock the wallet")


@pytest.fixture
def broken_keyring():
    keyring.set_keyring(BrokenKeyring())


def jwt_with(claims: dict) -> str:
    import base64
    import json

    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"eyJhbGciOiJIUzUxMiJ9.{payload}.sig"


class FakeServer:
    """Answer the auth and API key endpoints, recording each call with its auth header."""

    def __init__(self):
        self.calls = []
        self.login_reply = {"token": jwt_with({"scopes": ["TENANT_ADMIN"]}), "refreshToken": "r"}
        self.fail = {}
        self.key_counter = 1

    def _record(self, method, api, path, body=None):
        conf = api.configuration
        self.calls.append((method, path, conf.get_api_key_with_prefix("API key form"), body))
        if path in self.fail:
            raise self.fail[path]

    def get(self, api, path, query=None):
        self._record("GET", api, path)
        if path == "/api/auth/user":
            return {"id": {"id": "u1", "entityType": "USER"}, "email": "me@example.com"}
        raise AssertionError(path)

    def post(self, api, path, body):
        self._record("POST", api, path, body)
        if path == "/api/auth/login":
            return self.login_reply
        if path == "/api/apiKey":
            self.key_counter += 1
            return {
                "id": {"id": f"k{self.key_counter}", "entityType": "API_KEY"},
                "value": f"ApiKey secret{self.key_counter}",
                "expirationTime": body["expirationTime"],
            }
        raise AssertionError(path)

    def delete(self, api, path):
        self._record("DELETE", api, path)

    def paths(self, method):
        return [c[1] for c in self.calls if c[0] == method]


@pytest.fixture
def fake_server(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr("tbctl.commands._client.raw_get", server.get)
    monkeypatch.setattr("tbctl.commands._client.raw_post", server.post)
    monkeypatch.setattr("tbctl.commands._client.raw_delete", server.delete, raising=False)
    return server
