import fcntl
import json
import threading

import pytest
import typer

import tbctl.config as cfg
from tbctl import credentials, session
from tbctl.credentials import API_KEY, JWT
from tests.conftest import NOW_MS, jwt_with, make_pair

S = 1000


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("tbctl.session._now_ms", lambda: NOW_MS)


def _logged_in(pair, insecure=False):
    cfg.save({"url": "https://tb"}, "p")
    credentials.save(
        "p", JWT, json.dumps(pair), session.exp_ms(pair["refreshToken"]), insecure=insecure
    )


def _pair_ending(access_left_ms, refresh_left_ms=7 * 86400 * S):
    return {
        "token": jwt_with({"exp": (NOW_MS + access_left_ms) // S}),
        "refreshToken": jwt_with({"exp": (NOW_MS + refresh_left_ms) // S}),
    }


def test_login_returns_pair(fake_server):
    assert session.login("https://tb", "u", "pw") == fake_server.login_reply
    method, path, auth, body = fake_server.calls[0]
    assert (method, path, auth) == ("POST", "/api/auth/login", None)
    assert body == {"username": "u", "password": "pw"}


def test_login_refuses_2fa_scope_claim(fake_server):
    fake_server.login_reply = {"token": jwt_with({"scopes": ["PRE_VERIFICATION_TOKEN"]})}
    with pytest.raises(session.TwoFactorRequired):
        session.login("https://tb", "u", "pw")


def test_login_refuses_2fa_scope_field(fake_server):
    fake_server.login_reply = {"token": jwt_with({}), "scope": "PRE_VERIFICATION_TOKEN"}
    with pytest.raises(session.TwoFactorRequired):
        session.login("https://tb", "u", "pw")


def test_ensure_fresh_uses_valid_access_token(fake_server):
    pair = _pair_ending(120 * S)
    _logged_in(pair)
    assert session.ensure_fresh("p") == (pair["token"], "Bearer")
    assert fake_server.calls == []


def test_ensure_fresh_renews_in_window(fake_server):
    _logged_in(_pair_ending(30 * S))
    token, prefix = session.ensure_fresh("p")
    assert (token, prefix) == (make_pair(2)["token"], "Bearer")
    method, path, auth, body = fake_server.calls[0]
    assert (path, auth) == ("/api/auth/token", None)
    assert body == {"refreshToken": _pair_ending(30 * S)["refreshToken"]}
    assert json.loads(credentials.load("p").secret) == make_pair(2)
    assert cfg.load("p")["refresh_expires"] == NOW_MS + 7 * 86400 * S


def test_renew_keeps_file_storage(fake_server):
    _logged_in(_pair_ending(30 * S), insecure=True)
    session.ensure_fresh("p")
    assert json.loads(cfg.load("p")["token"]) == make_pair(2)


def test_renew_force(fake_server):
    _logged_in(_pair_ending(3600 * S))
    assert session.renew("p", force=True) == make_pair(2)


def test_renew_waits_for_lock_and_rechecks(fake_server):
    _logged_in(_pair_ending(30 * S))
    with open(cfg.CONFIG_DIR / "p.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        worker = threading.Thread(target=session.renew, args=("p",))
        worker.start()
        worker.join(0.2)
        assert worker.is_alive()
        other = _pair_ending(3600 * S)
        credentials.save("p", JWT, json.dumps(other), session.exp_ms(other["refreshToken"]))
    worker.join(2)
    assert fake_server.calls == []


def test_expired_refresh_token_exits(fake_server, capsys):
    _logged_in(_pair_ending(-S, refresh_left_ms=-S))
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "Session for profile 'p' expired. Run `tbctl auth login`." in capsys.readouterr().err
    assert fake_server.calls == []


def test_rejected_refresh_token_exits(fake_server, capsys):
    from tb_client.exceptions import ApiException

    _logged_in(_pair_ending(30 * S))
    fake_server.fail["/api/auth/token"] = ApiException(status=401, reason="Unauthorized")
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "Session for profile 'p' expired" in capsys.readouterr().err


def test_network_failure_with_valid_token_warns(fake_server, capsys):
    pair = _pair_ending(30 * S)
    _logged_in(pair)
    fake_server.fail["/api/auth/token"] = OSError("network down")
    assert session.ensure_fresh("p") == (pair["token"], "Bearer")
    assert "could not renew the session (network down)" in capsys.readouterr().err


def test_network_failure_with_expired_token_exits(fake_server, capsys):
    _logged_in(_pair_ending(-S))
    fake_server.fail["/api/auth/token"] = OSError("network down")
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "network down" in capsys.readouterr().err


def test_api_key_login_is_used_as_is(fake_server):
    cfg.save({"url": "https://tb"}, "p")
    credentials.save("p", API_KEY, "key")
    assert session.ensure_fresh("p") == ("key", "ApiKey")


def test_env_is_used_as_api_key(fake_server, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert session.ensure_fresh("p") == ("env", "ApiKey")


def test_not_logged_in(fake_server):
    assert session.ensure_fresh("p") is None


def test_logout_posts_with_bearer(fake_server):
    session.logout("https://tb", make_pair(1))
    assert fake_server.calls == [
        ("POST", "/api/auth/logout", f"Bearer {make_pair(1)['token']}", {})
    ]


def test_corrupt_jwt_secret_asks_for_login(fake_server, capsys):
    cfg.save({"url": "https://tb"}, "p")
    credentials.save("p", JWT, "not json", 1)
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "Run `tbctl auth login`" in capsys.readouterr().err


def test_empty_token_reply_is_named(fake_server, capsys, monkeypatch):
    _logged_in(_pair_ending(-S))
    monkeypatch.setattr(fake_server, "post", lambda api, path, body: None)
    monkeypatch.setattr("tbctl.commands._client.raw_post", lambda api, path, body: None)
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "unexpected reply from /api/auth/token" in capsys.readouterr().err


def test_empty_login_reply_is_named(fake_server, monkeypatch):
    monkeypatch.setattr("tbctl.commands._client.raw_post", lambda api, path, body: None)
    with pytest.raises(session.UnexpectedReply, match="/api/auth/login"):
        session.login("https://tb", "u", "pw")


def test_failed_renewal_then_unreadable_secret_is_clean(fake_server, capsys, monkeypatch):
    _logged_in(_pair_ending(30 * S))
    fake_server.fail["/api/auth/token"] = OSError("network down")
    real_load = credentials.load
    calls = []

    def load_then_vanish(profile):
        calls.append(profile)
        return real_load(profile) if len(calls) <= 2 else None

    monkeypatch.setattr("tbctl.credentials.load", load_then_vanish)
    with pytest.raises(typer.Exit):
        session.ensure_fresh("p")
    assert "cannot be read" in capsys.readouterr().err
