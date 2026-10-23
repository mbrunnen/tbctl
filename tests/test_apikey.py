import pytest
import typer

import tbctl.config as cfg
from tbctl import apikey, credentials
from tbctl.commands._client import build_client
from tests.conftest import jwt_with

DAY = 86_400_000
NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("tbctl.apikey._now_ms", lambda: NOW)


def _logged_in(expires, insecure=False):
    cfg.save({"url": "https://tb"}, "p")
    credentials.save("p", "secret1", "k1", expires, insecure=insecure)


def test_login_returns_jwt(fake_server):
    jwt = apikey.login("https://tb", "u", "pw")
    assert jwt == fake_server.login_reply["token"]
    method, path, auth, body = fake_server.calls[0]
    assert (method, path, auth) == ("POST", "/api/auth/login", None)
    assert body == {"username": "u", "password": "pw"}


def test_login_refuses_2fa_scope_claim(fake_server):
    fake_server.login_reply = {"token": jwt_with({"scopes": ["PRE_VERIFICATION_TOKEN"]})}
    with pytest.raises(apikey.TwoFactorRequired):
        apikey.login("https://tb", "u", "pw")


def test_login_refuses_2fa_scope_field(fake_server):
    fake_server.login_reply = {"token": jwt_with({}), "scope": "PRE_VERIFICATION_TOKEN"}
    with pytest.raises(apikey.TwoFactorRequired):
        apikey.login("https://tb", "u", "pw")


def test_create_sets_30_day_expiry(fake_server):
    key = apikey.create(build_client("https://tb", "jwt", prefix="Bearer"), "p", NOW)
    body = fake_server.calls[-1][3]
    assert body["expirationTime"] == NOW + 30 * DAY
    assert body["userId"] == {"id": "u1", "entityType": "USER"}
    assert body["enabled"] is True
    assert body["description"].startswith("tbctl ") and body["description"].endswith(" p")
    assert key == apikey.Key("secret2", "k2", NOW + 30 * DAY)
    assert {c[2] for c in fake_server.calls} == {"Bearer jwt"}


def test_rotate_outside_window_does_nothing(fake_server):
    _logged_in(NOW + 8 * DAY)
    assert apikey.rotate("p") is None
    assert fake_server.calls == []


def test_rotate_inside_window_replaces_key(fake_server):
    _logged_in(NOW + 6 * DAY)
    key = apikey.rotate("p")
    assert key.value == "secret2"
    assert credentials.get("p") == "secret2"
    assert cfg.load("p")["token_id"] == "k2"
    assert credentials.expires("p") == NOW + 30 * DAY
    assert fake_server.paths("DELETE") == []
    assert {c[2] for c in fake_server.calls} == {"ApiKey secret1"}


def test_rotate_force(fake_server):
    _logged_in(NOW + 20 * DAY)
    assert apikey.rotate("p", force=True).id == "k2"


def test_rotate_keeps_file_storage(fake_server):
    _logged_in(NOW + 6 * DAY, insecure=True)
    apikey.rotate("p")
    assert cfg.load("p")["token"] == "secret2"


def test_rotate_rechecks_under_lock(fake_server):
    _logged_in(NOW + 6 * DAY)
    apikey.rotate("p")
    apikey.rotate("p")
    assert fake_server.paths("POST").count("/api/apiKey") == 1


def test_ensure_fresh_returns_valid_key(fake_server):
    _logged_in(NOW + 20 * DAY)
    assert apikey.ensure_fresh("p") == "secret1"
    assert fake_server.calls == []


def test_ensure_fresh_rotates_in_window(fake_server):
    _logged_in(NOW + 1 * DAY)
    assert apikey.ensure_fresh("p") == "secret2"


def test_ensure_fresh_expired_exits(fake_server, capsys):
    _logged_in(NOW - 1)
    with pytest.raises(typer.Exit):
        apikey.ensure_fresh("p")
    assert "tbctl auth login" in capsys.readouterr().err


def test_ensure_fresh_warns_on_failure(fake_server, capsys):
    _logged_in(NOW + 1 * DAY)
    fake_server.fail["/api/apiKey"] = OSError("network down")
    assert apikey.ensure_fresh("p") == "secret1"
    assert "could not refresh the API key (network down)" in capsys.readouterr().err


def test_ensure_fresh_skips_env(fake_server, monkeypatch):
    _logged_in(NOW + 1 * DAY)
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert apikey.ensure_fresh("p") == "env"
    assert fake_server.calls == []


def test_ensure_fresh_not_logged_in(fake_server):
    assert apikey.ensure_fresh("p") is None


def test_delete(fake_server):
    apikey.delete(build_client("https://tb", "secret1"), "k1")
    assert fake_server.calls == [("DELETE", "/api/apiKey/k1", "ApiKey secret1", None)]


def test_rotate_waits_for_lock_and_rechecks(fake_server):
    import fcntl
    import threading

    _logged_in(NOW + 6 * DAY)
    with open(cfg.CONFIG_DIR / "p.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        worker = threading.Thread(target=apikey.rotate, args=("p",))
        worker.start()
        worker.join(0.2)
        assert worker.is_alive()
        credentials.save("p", "other", "k9", NOW + 30 * DAY)
    worker.join(2)
    assert fake_server.paths("POST") == []
    assert credentials.get("p") == "other"


def test_ensure_fresh_warning_is_one_line_for_api_errors(fake_server, capsys):
    from tb_client.exceptions import ApiException

    _logged_in(NOW + 1 * DAY)
    fake_server.fail["/api/apiKey"] = ApiException(
        status=403, reason="Forbidden", body='{"message": "No permission"}'
    )
    apikey.ensure_fresh("p")
    err = capsys.readouterr().err
    assert err == "Warning: could not refresh the API key (Error 403: No permission)\n"
