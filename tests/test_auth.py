import json

import pytest
from typer.testing import CliRunner

import tbctl.config as cfg
from tbctl import credentials, session
from tbctl.cli import app
from tbctl.credentials import API_KEY, JWT
from tests.conftest import NOW_MS, jwt_with, make_pair

runner = CliRunner()
REFRESH_EXPIRES = NOW_MS + 7 * 86_400_000


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("tbctl.session._now_ms", lambda: NOW_MS)


def _login(*args, input="https://tb\nme@example.com\npw\n"):
    return runner.invoke(app, ["auth", "login", *args], input=input)


def _logged_in(pair=None):
    pair = pair or make_pair(1)
    cfg.save({"url": "https://tb"}, "default")
    credentials.save("default", JWT, json.dumps(pair), session.exp_ms(pair["refreshToken"]))


def _api_key_login(key="key1"):
    cfg.save({"url": "https://tb"}, "default")
    credentials.save("default", API_KEY, key)


def test_login_stores_pair(fake_server, memory_keyring):
    result = _login()
    assert result.exit_code == 0, result.output
    assert json.loads(memory_keyring.store[("tbctl", "default")]) == make_pair(1)
    assert cfg.load("default") == {
        "url": "https://tb",
        "auth": "jwt",
        "refresh_expires": REFRESH_EXPIRES,
    }
    assert "pw" not in result.output.split("Password:")[-1]
    assert session.date(REFRESH_EXPIRES) in result.output


def test_login_takes_options(fake_server):
    result = _login("--url", "https://tb", "-u", "me@example.com", input="pw\n")
    assert result.exit_code == 0, result.output
    assert fake_server.calls[0][3] == {"username": "me@example.com", "password": "pw"}


def test_login_defaults_to_stored_url(fake_server):
    cfg.save({"url": "https://kept"}, "default")
    assert _login(input="\nu\npw\n").exit_code == 0
    assert cfg.load("default")["url"] == "https://kept"


def test_login_wrong_password_stores_nothing(fake_server, memory_keyring):
    from tb_client.exceptions import ApiException

    fake_server.fail["/api/auth/login"] = ApiException(
        status=401, reason="Unauthorized", body='{"message": "Invalid username or password"}'
    )
    result = _login()
    assert result.exit_code == 1
    assert result.stderr == "Error 401: Invalid username or password\n"
    assert cfg.load("default") == {}
    assert memory_keyring.store == {}


def test_login_unreachable_url_is_clean(fake_server):
    fake_server.fail["/api/auth/login"] = OSError("Name or service not known")
    result = _login()
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Could not reach https://tb: Name or service not known" in result.stderr


def test_login_refuses_under_env(fake_server, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    result = _login()
    assert result.exit_code == 1
    assert "TBCTL_TOKEN is set" in result.stderr
    assert fake_server.calls == []


def test_login_2fa_message(fake_server):
    fake_server.login_reply = {"token": jwt_with({"scopes": ["PRE_VERIFICATION_TOKEN"]})}
    result = _login()
    assert result.exit_code == 1
    assert "Two-factor authentication is not supported" in result.stderr
    assert cfg.load("default") == {}


def test_login_insecure_storage_writes_file(fake_server, memory_keyring, config_dir):
    result = _login("--insecure-storage")
    assert result.exit_code == 0
    assert memory_keyring.store == {}
    assert json.loads(cfg.load("default")["token"]) == make_pair(1)
    assert str(config_dir / "default.toml") in result.stderr


def test_login_to_new_host_never_pairs_old_secret_with_new_url(fake_server, monkeypatch):
    _api_key_login()
    seen = []
    real_save = cfg.save

    def spy(data, profile="default"):
        real_save(data, profile)
        cred = credentials.load(profile)
        seen.append((cfg.load(profile).get("url"), cred and cred.secret))

    monkeypatch.setattr("tbctl.config.save", spy)
    assert _login(input="https://new\nu\npw\n").exit_code == 0
    assert ("https://new", "key1") not in seen


def test_api_key_login_from_stdin(fake_server, memory_keyring):
    result = runner.invoke(
        app, ["auth", "login", "--api-key", "--url", "https://tb"], input="key9\n"
    )
    assert result.exit_code == 0, result.output
    assert memory_keyring.store[("tbctl", "default")] == "key9"
    assert cfg.load("default") == {"url": "https://tb", "auth": "api-key"}
    assert fake_server.calls == [("GET", "/api/auth/user", "ApiKey key9", None)]
    assert "key9" not in result.output


def test_api_key_login_prompts_when_interactive(fake_server, memory_keyring, monkeypatch):
    monkeypatch.setattr("tbctl.commands.auth._stdin_is_tty", lambda: True)
    result = runner.invoke(
        app, ["auth", "login", "--api-key", "--url", "https://tb"], input="key9\n"
    )
    assert result.exit_code == 0, result.output
    assert "API key:" in result.output
    assert "key9" not in result.output
    assert memory_keyring.store[("tbctl", "default")] == "key9"


def test_rejected_api_key_keeps_previous_login(fake_server):
    from tb_client.exceptions import ApiException

    _logged_in()
    fake_server.fail["/api/auth/user"] = ApiException(status=401, reason="Unauthorized")
    result = runner.invoke(
        app, ["auth", "login", "--api-key", "--url", "https://tb"], input="bad\n"
    )
    assert result.exit_code == 1
    assert "401" in result.stderr
    assert credentials.load("default").kind == JWT


def test_api_key_login_refuses_username(fake_server):
    result = runner.invoke(app, ["auth", "login", "--api-key", "-u", "me"], input="k\n")
    assert result.exit_code == 1
    assert "--api-key" in result.stderr


def test_refresh_renews_jwt(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 0, result.output
    assert json.loads(credentials.load("default").secret) == make_pair(2)
    assert session.date(REFRESH_EXPIRES) in result.output


def test_refresh_api_key_fails(fake_server):
    _api_key_login()
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "API keys are not refreshed" in result.stderr


def test_refresh_under_env_fails(fake_server, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "API keys are not refreshed" in result.stderr


def test_refresh_not_logged_in(fake_server):
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "tbctl auth login" in result.stderr


def test_refresh_expired_session(fake_server):
    _logged_in(make_pair(1, now_ms=NOW_MS - 8 * 86_400_000))
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "Session for profile 'default' expired" in result.stderr
    assert fake_server.calls == []


def test_status_jwt(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "status", "-j"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "url": "https://tb",
        "user": "me@example.com",
        "auth": "jwt",
        "source": "keyring",
        "expires": session.date(REFRESH_EXPIRES),
    }
    assert fake_server.calls[0][2] == f"Bearer {make_pair(1)['token']}"


def test_status_api_key_text(fake_server):
    _api_key_login()
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0
    assert "auth = api-key" in result.stdout
    assert "key1" not in result.stdout


def test_status_not_logged_in_exits_1(fake_server):
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 1
    assert "tbctl auth login" in result.stderr


def test_status_rejected_exits_1(fake_server):
    from tb_client.exceptions import ApiException

    _api_key_login()
    fake_server.fail["/api/auth/user"] = ApiException(status=401, reason="Unauthorized")
    assert runner.invoke(app, ["auth", "status"]).exit_code == 1


def test_logout_jwt(fake_server, memory_keyring):
    _logged_in()
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert fake_server.paths("POST") == ["/api/auth/logout"]
    assert memory_keyring.store == {}
    assert cfg.load("default") == {"url": "https://tb"}


def test_logout_warns_when_server_fails(fake_server, memory_keyring):
    _logged_in()
    fake_server.fail["/api/auth/logout"] = OSError("network down")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert "network down" in result.stderr
    assert memory_keyring.store == {}


def test_logout_api_key_sends_nothing(fake_server, memory_keyring):
    _api_key_login()
    assert runner.invoke(app, ["auth", "logout"]).exit_code == 0
    assert fake_server.calls == []
    assert memory_keyring.store == {}


def test_logout_under_env_says_so(fake_server, monkeypatch):
    _logged_in()
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert fake_server.calls == []
    assert "TBCTL_TOKEN is set" in result.stderr


def test_logout_not_logged_in(fake_server, config_dir):
    result = runner.invoke(app, ["-c", "typo", "auth", "logout"])
    assert result.exit_code == 1
    assert "Not logged in for profile 'typo'" in result.stderr
    assert not (config_dir / "typo.toml").exists()


def test_logout_removes_orphaned_keyring_secret(fake_server, memory_keyring):
    memory_keyring.set_password("tbctl", "default", "tb_oldkey")
    cfg.save({"url": "https://tb", "token_id": "k1"}, "default")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert memory_keyring.store == {}
    assert "Removed" in result.stdout


def test_status_without_refresh_expires_is_clean(fake_server):
    _logged_in()
    data = cfg.load("default")
    del data["refresh_expires"]
    cfg.save(data, "default")
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0, result.output
    assert "expires = unknown" in result.stdout


def test_refresh_without_url_is_clean(fake_server):
    _logged_in()
    fake_server.fail["/api/auth/token"] = OSError("network down")
    data = cfg.load("default")
    del data["url"]
    cfg.save(data, "default")
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


def test_login_as_customer_stores_customer_id(fake_server):
    from tests.conftest import CUSTOMER_UUID

    fake_server.as_customer()
    assert _login().exit_code == 0
    assert cfg.load("default")["customer_id"] == CUSTOMER_UUID
    assert ("GET", "/api/auth/user", f"Bearer {make_pair(1)['token']}", None) in fake_server.calls


def test_login_as_tenant_stores_no_customer_id(fake_server):
    cfg.save({"url": "https://tb", "customer_id": "old"}, "default")
    assert _login().exit_code == 0
    assert "customer_id" not in cfg.load("default")


def test_api_key_login_as_customer_stores_customer_id(fake_server):
    from tests.conftest import CUSTOMER_UUID

    fake_server.as_customer()
    result = runner.invoke(app, ["auth", "login", "--api-key", "--url", "https://tb"], input="k\n")
    assert result.exit_code == 0, result.output
    assert cfg.load("default")["customer_id"] == CUSTOMER_UUID


def test_logout_drops_customer_id(fake_server):
    fake_server.as_customer()
    _login()
    runner.invoke(app, ["auth", "logout"])
    assert "customer_id" not in cfg.load("default")
