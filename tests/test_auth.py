import json

import pytest
from typer.testing import CliRunner

import tbctl.config as cfg
from tbctl import credentials, session, state
from tbctl.cli import app
from tbctl.credentials import API_KEY, JWT
from tests.conftest import NOW_MS, URL, jwt_with, make_pair

runner = CliRunner()
REFRESH_EXPIRES = NOW_MS + 7 * 86_400_000
KEY = f"default@{URL}"


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("tbctl.session._now_ms", lambda: NOW_MS)


def _login(*args, input="pw\n"):
    return runner.invoke(app, ["auth", "login", *args], input=input)


def _logged_in(pair=None):
    pair = pair or make_pair(1)
    credentials.save(cfg.resolve(), JWT, json.dumps(pair), session.exp_ms(pair["refreshToken"]))


def _api_key_login(key="key1"):
    credentials.save(cfg.resolve(), API_KEY, key)


def test_login_stores_pair(fake_server, memory_keyring):
    result = _login()
    assert result.exit_code == 0, result.output
    assert json.loads(memory_keyring.store[("tbctl", KEY)]) == make_pair(1)
    assert state.load(KEY) == {"auth": "jwt", "refresh_expires": REFRESH_EXPIRES}
    assert "pw" not in result.output.split("Password:")[-1]
    assert session.date(REFRESH_EXPIRES) in result.output


def test_login_wrong_password_stores_nothing(fake_server, memory_keyring):
    from tb_client.exceptions import ApiException

    fake_server.fail["/api/auth/login"] = ApiException(
        status=401, reason="Unauthorized", body='{"message": "Invalid username or password"}'
    )
    result = _login()
    assert result.exit_code == 1
    assert result.stderr == "Error 401: Invalid username or password\n"
    assert state.load(KEY) == {}
    assert memory_keyring.store == {}


def test_login_unreachable_url_is_clean(fake_server):
    fake_server.fail["/api/auth/login"] = OSError("Name or service not known")
    result = _login()
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Could not reach https://tb.example.com: Name or service not known" in result.stderr


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
    assert state.load(KEY) == {}


def test_login_insecure_storage_writes_file(fake_server, memory_keyring, config_dir):
    result = _login("--insecure-storage")
    assert result.exit_code == 0
    assert memory_keyring.store == {}
    assert json.loads(state.load(KEY)["token"]) == make_pair(1)
    assert "state.toml" in result.stderr


def test_api_key_login_from_stdin(fake_server, memory_keyring):
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="key9\n")
    assert result.exit_code == 0, result.output
    assert memory_keyring.store[("tbctl", KEY)] == "key9"
    assert state.load(KEY) == {"auth": "api-key"}
    assert fake_server.calls == [("GET", "/api/auth/user", "ApiKey key9", None)]
    assert "key9" not in result.output


def test_api_key_login_prompts_when_interactive(fake_server, memory_keyring, monkeypatch):
    monkeypatch.setattr("tbctl.commands.auth._stdin_is_tty", lambda: True)
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="key9\n")
    assert result.exit_code == 0, result.output
    assert "API key:" in result.output
    assert "key9" not in result.output
    assert memory_keyring.store[("tbctl", KEY)] == "key9"


def test_rejected_api_key_keeps_previous_login(fake_server):
    from tb_client.exceptions import ApiException

    _logged_in()
    fake_server.fail["/api/auth/user"] = ApiException(status=401, reason="Unauthorized")
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="bad\n")
    assert result.exit_code == 1
    assert "401" in result.stderr
    assert credentials.load(cfg.resolve()).kind == JWT


def test_refresh_renews_jwt(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 0, result.output
    assert json.loads(credentials.load(cfg.resolve()).secret) == make_pair(2)
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
    assert "Session for context 'default' expired" in result.stderr
    assert fake_server.calls == []


def test_status_jwt(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "status", "-j"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
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
    assert state.load(KEY) == {}


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


def test_logout_not_logged_in(fake_server):
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 1
    assert "Not logged in for context 'default'" in result.stderr
    assert not (state.STATE_DIR / "state.toml").exists()


def test_logout_removes_orphaned_keyring_secret(fake_server, memory_keyring):
    memory_keyring.set_password("tbctl", KEY, "tb_oldkey")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert memory_keyring.store == {}
    assert "Removed" in result.stdout


def test_status_without_refresh_expires_is_clean(fake_server):
    _logged_in()
    data = state.load(KEY)
    del data["refresh_expires"]
    state.save(KEY, data)
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 0, result.output
    assert "expires = unknown" in result.stdout


def test_login_as_customer_stores_customer_id(fake_server):
    from tests.conftest import CUSTOMER_UUID

    fake_server.as_customer()
    assert _login().exit_code == 0
    assert state.load(KEY)["customer_id"] == CUSTOMER_UUID
    assert ("GET", "/api/auth/user", f"Bearer {make_pair(1)['token']}", None) in fake_server.calls


def test_login_as_tenant_stores_no_customer_id(fake_server):
    state.save(KEY, {"customer_id": "old"})
    assert _login().exit_code == 0
    assert "customer_id" not in state.load(KEY)


def test_api_key_login_as_customer_stores_customer_id(fake_server):
    from tests.conftest import CUSTOMER_UUID

    fake_server.as_customer()
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="k\n")
    assert result.exit_code == 0, result.output
    assert state.load(KEY)["customer_id"] == CUSTOMER_UUID


def test_logout_drops_customer_id(fake_server):
    fake_server.as_customer()
    _login()
    runner.invoke(app, ["auth", "logout"])
    assert "customer_id" not in state.load(KEY)


def test_status_shows_login_only(fake_server):
    _logged_in()
    data = json.loads(runner.invoke(app, ["auth", "status", "-j"]).stdout)
    assert set(data) == {"user", "auth", "source", "expires"}


def test_login_takes_the_user_from_the_context(fake_server):
    result = runner.invoke(app, ["auth", "login"], input="pw\n")
    assert result.exit_code == 0, result.output
    assert fake_server.calls[0][3] == {"username": "me@example.com", "password": "pw"}
    assert "Username" not in result.output


def test_username_option_is_gone(fake_server):
    assert runner.invoke(app, ["auth", "login", "-u", "x"], input="pw\n").exit_code == 2


def _no_user_config(config_dir):
    path = config_dir / "config.toml"
    path.write_text('# mine\n[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\n')
    return path


def test_login_without_user_asks_and_writes_it(config_dir, fake_server):
    path = _no_user_config(config_dir)
    result = runner.invoke(app, ["--context", "a", "auth", "login"], input="me@example.com\npw\n")
    assert result.exit_code == 0, result.output
    assert fake_server.calls[0][3] == {"username": "me@example.com", "password": "pw"}
    assert cfg.contexts(cfg.read(path))["a"]["user"] == "me@example.com"
    assert "user" not in cfg.contexts(cfg.read(path))["b"]
    assert path.read_text().startswith("# mine\n")


def test_failed_login_writes_no_user(config_dir, fake_server):
    from tb_client.exceptions import ApiException

    path = _no_user_config(config_dir)
    fake_server.fail["/api/auth/login"] = ApiException(status=401, reason="Unauthorized")
    result = runner.invoke(app, ["--context", "a", "auth", "login"], input="me@example.com\npw\n")
    assert result.exit_code == 1
    assert "user" not in cfg.contexts(cfg.read(path))["a"]


def test_api_key_login_needs_no_user(config_dir, fake_server):
    path = config_dir / "config.toml"
    path.write_text('[contexts.a]\nurl = "https://a"\n')
    path.chmod(0o600)
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="key\n")
    assert result.exit_code == 0, result.output


def test_login_stores_no_user_in_the_state(fake_server):
    assert _login().exit_code == 0
    assert "user" not in state.load(KEY)


def test_first_login_with_flags_asks_only_for_the_password(config_dir, fake_server):
    path = config_dir / "config.toml"
    path.unlink()
    result = runner.invoke(
        app, ["auth", "login", "--url", "https://a.example.com/", "--user", "me"], input="pw\n"
    )
    assert result.exit_code == 0, result.output
    assert "URL" not in result.output and "Username" not in result.output
    assert cfg.contexts(cfg.read(path)) == {
        "a.example.com": {"url": "https://a.example.com", "user": "me", "default": True}
    }


def test_url_flag_matching_the_file_is_accepted(context, fake_server):
    assert _login("--url", URL + "/").exit_code == 0
    assert list(cfg.contexts(cfg.read(context.file))) == ["default"]


def test_url_flag_disagreeing_with_the_file_fails(context, fake_server):
    result = runner.invoke(
        app, ["--context", "default", "auth", "login", "--url", "https://other"], input="pw\n"
    )
    assert result.exit_code == 1
    assert URL in result.output
    assert fake_server.calls == []


def test_url_without_context_adds_a_context_named_after_the_host(context, fake_server):
    result = _login("--url", "https://b.example.com", "--user", "me")
    assert result.exit_code == 0, result.output
    found = cfg.contexts(cfg.read(context.file))
    assert found["b.example.com"] == {"url": "https://b.example.com", "user": "me"}
    assert found["default"]["url"] == URL


def test_user_flag_fills_a_missing_user(config_dir, fake_server):
    path = _no_user_config(config_dir)
    result = runner.invoke(app, ["--context", "a", "auth", "login", "--user", "me"], input="pw\n")
    assert result.exit_code == 0, result.output
    assert "Username" not in result.output
    assert cfg.contexts(cfg.read(path))["a"]["user"] == "me"


def test_user_flag_disagreeing_with_the_file_fails(fake_server):
    result = _login("--user", "other")
    assert result.exit_code == 1
    assert "me@example.com" in result.output
    assert fake_server.calls == []


def test_user_flag_matching_the_file_is_accepted(fake_server):
    assert _login("--user", "me@example.com").exit_code == 0


def test_url_flag_on_a_broken_context_fails_cleanly(context, fake_server):
    context.file.write_text(context.file.read_text() + '[contexts."b.example.com"]\nuser = "me"\n')
    for url in ("https://b.example.com", "/"):
        result = _login("--url", url)
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit), result.exception
        assert fake_server.calls == []


def test_first_login_without_config_creates_the_context(config_dir, fake_server):
    path = config_dir / "config.toml"
    path.unlink()
    result = runner.invoke(
        app, ["auth", "login"], input="https://test.cloud.orgatex.com/\nme@example.com\npw\n"
    )
    assert result.exit_code == 0, result.output
    assert cfg.contexts(cfg.read(path)) == {
        "test.cloud.orgatex.com": {
            "url": "https://test.cloud.orgatex.com",
            "user": "me@example.com",
            "default": True,
        }
    }
    assert credentials.load(cfg.resolve()).kind == JWT


def test_login_to_a_missing_named_context_adds_it(context, fake_server):
    context.file.write_text("# mine\n" + context.file.read_text())
    result = runner.invoke(
        app, ["--context", "prod", "auth", "login"], input="https://prod\nme@example.com\npw\n"
    )
    assert result.exit_code == 0, result.output
    found = cfg.contexts(cfg.read(context.file))
    assert found["prod"] == {"url": "https://prod", "user": "me@example.com"}
    assert cfg.resolve().name == "default"
    assert context.file.read_text().startswith("# mine\n")


def test_failed_first_login_writes_no_config(config_dir, fake_server):
    from tb_client.exceptions import ApiException

    path = config_dir / "config.toml"
    path.unlink()
    fake_server.fail["/api/auth/login"] = ApiException(status=401, reason="Unauthorized")
    result = runner.invoke(app, ["auth", "login"], input="https://a.example.com\nme\npw\n")
    assert result.exit_code == 1
    assert not path.exists()


def test_first_api_key_login_creates_the_context(config_dir, fake_server):
    path = config_dir / "config.toml"
    path.unlink()
    result = runner.invoke(app, ["auth", "login", "--api-key"], input="https://a.example.com\nk\n")
    assert result.exit_code == 0, result.output
    assert cfg.contexts(cfg.read(path)) == {
        "a.example.com": {"url": "https://a.example.com", "default": True}
    }


def test_login_renews_a_valid_session_without_a_password(fake_server):
    _logged_in()
    result = _login(input="")
    assert result.exit_code == 0, result.output
    assert "Password" not in result.output
    assert fake_server.paths("POST") == ["/api/auth/token"]
    assert json.loads(credentials.load(cfg.resolve()).secret) == make_pair(2)
    assert session.date(REFRESH_EXPIRES) in result.output


def test_login_with_an_expired_session_asks_for_the_password(fake_server):
    _logged_in(make_pair(1, now_ms=NOW_MS - 8 * 86_400_000))
    result = _login()
    assert result.exit_code == 0, result.output
    assert fake_server.paths("POST") == ["/api/auth/login"]
    assert json.loads(credentials.load(cfg.resolve()).secret) == make_pair(1)


def test_login_with_a_rejected_session_asks_for_the_password(fake_server):
    from tb_client.exceptions import ApiException

    _logged_in()
    fake_server.fail["/api/auth/token"] = ApiException(status=401, reason="Unauthorized")
    result = _login()
    assert result.exit_code == 0, result.output
    assert fake_server.paths("POST") == ["/api/auth/token", "/api/auth/login"]
    assert json.loads(credentials.load(cfg.resolve()).secret) == make_pair(1)


def test_login_over_an_api_key_asks_for_the_password(fake_server):
    _api_key_login()
    result = _login()
    assert result.exit_code == 0, result.output
    assert fake_server.paths("POST") == ["/api/auth/login"]
    assert credentials.load(cfg.resolve()).kind == JWT
