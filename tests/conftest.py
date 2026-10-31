import os

import keyring
import keyring.backend
import keyring.backends.fail
import keyring.errors
import pytest

# Typer forces styled help output when one of these is set at import time, as on GitHub Actions.
for var in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(var, None)


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
    monkeypatch.setattr("tbctl.keycache.CACHE_DIR", tmp_path / "cache")
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


NOW_MS = 1_800_000_000_000
NULL_UUID = "13814000-1dd2-11b2-8080-808080808080"
CUSTOMER_UUID = "d6b77b60-714f-11f1-ba38-655c002e257c"
ACCESS_S = 9000
REFRESH_S = 7 * 86400


def make_pair(n: int, now_ms: int = NOW_MS) -> dict:
    now_s = now_ms // 1000
    return {
        "token": jwt_with({"n": n, "scopes": ["TENANT_ADMIN"], "exp": now_s + ACCESS_S}),
        "refreshToken": jwt_with({"n": n, "scopes": ["REFRESH_TOKEN"], "exp": now_s + REFRESH_S}),
    }


class FakeServer:
    """Answer the auth endpoints, recording each call with its auth header."""

    def __init__(self):
        self.calls = []
        self.login_reply = make_pair(1)
        self.fail = {}
        self.pairs = 1
        self.user = {
            "id": {"id": "u1", "entityType": "USER"},
            "email": "me@example.com",
            "authority": "TENANT_ADMIN",
            "customerId": {"id": NULL_UUID, "entityType": "CUSTOMER"},
        }

    def as_customer(self):
        self.user["authority"] = "CUSTOMER_USER"
        self.user["customerId"]["id"] = CUSTOMER_UUID

    def _record(self, method, api, path, body=None):
        conf = api.configuration
        self.calls.append((method, path, conf.get_api_key_with_prefix("API key form"), body))
        if path in self.fail:
            raise self.fail[path]

    def get(self, api, path, query=None):
        self._record("GET", api, path)
        if path == "/api/auth/user":
            return self.user
        raise AssertionError(path)

    def post(self, api, path, body):
        self._record("POST", api, path, body)
        if path == "/api/auth/login":
            return self.login_reply
        if path == "/api/auth/token":
            self.pairs += 1
            return make_pair(self.pairs)
        if path == "/api/auth/logout":
            return None
        raise AssertionError(path)

    def paths(self, method):
        return [c[1] for c in self.calls if c[0] == method]


@pytest.fixture
def fake_server(monkeypatch):
    server = FakeServer()
    monkeypatch.setattr("tbctl.commands._client.raw_get", server.get)
    monkeypatch.setattr("tbctl.commands._client.raw_post", server.post)
    return server
