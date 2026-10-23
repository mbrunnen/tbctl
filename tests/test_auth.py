import json

import pytest
from typer.testing import CliRunner

import tbctl.config as cfg
from tbctl import credentials
from tbctl.cli import app
from tests.conftest import jwt_with

runner = CliRunner()
DAY = 86_400_000
NOW = 1_800_000_000_000


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr("tbctl.apikey._now_ms", lambda: NOW)


def _login(*args, input="https://tb\nme@example.com\npw\n"):
    return runner.invoke(app, ["auth", "login", *args], input=input)


def _logged_in(expires=NOW + 20 * DAY):
    cfg.save({"url": "https://tb"}, "default")
    credentials.save("default", "secret1", "k1", expires)


def test_login_stores_key_and_url(fake_server, memory_keyring):
    result = _login()
    assert result.exit_code == 0, result.output
    assert memory_keyring.store[("tbctl", "default")] == "secret2"
    assert cfg.load("default") == {
        "url": "https://tb",
        "token_id": "k2",
        "token_expires": NOW + 30 * DAY,
    }
    assert "pw" not in result.output.replace("\n", " ").split("Password:")[-1]
    assert "2027-02-14" in result.output


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

    fake_server.fail["/api/auth/login"] = ApiException(status=401, reason="Unauthorized")
    result = _login()
    assert result.exit_code == 1
    assert "Error 401" in result.stderr
    assert cfg.load("default") == {}
    assert memory_keyring.store == {}


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


def test_login_insecure_storage_writes_file(fake_server, memory_keyring):
    assert _login("--insecure-storage").exit_code == 0
    assert memory_keyring.store == {}
    assert cfg.load("default")["token"] == "secret2"


def test_login_replaces_previous_key_without_deleting(fake_server):
    _logged_in()
    assert _login().exit_code == 0
    assert credentials.get("default") == "secret2"
    assert fake_server.paths("DELETE") == []


def test_refresh_rotates_with_force(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 0, result.output
    assert credentials.get("default") == "secret2"
    assert "2027-02-14" in result.output


def test_refresh_under_env_fails(fake_server, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "TBCTL_TOKEN" in result.stderr


def test_refresh_not_logged_in(fake_server):
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "tbctl auth login" in result.stderr


def test_refresh_expired(fake_server):
    _logged_in(NOW - 1)
    result = runner.invoke(app, ["auth", "refresh"])
    assert result.exit_code == 1
    assert "tbctl auth login" in result.stderr
    assert fake_server.calls == []


def test_status_reports_source_and_expiry(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "status", "-j"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "url": "https://tb",
        "user": "me@example.com",
        "token": "keyring",
        "expires": "2027-02-04",
    }


def test_status_text(fake_server):
    _logged_in()
    result = runner.invoke(app, ["auth", "status"])
    assert "user = me@example.com" in result.stdout
    assert "secret1" not in result.stdout


def test_status_not_logged_in_exits_1(fake_server):
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 1
    assert "tbctl auth login" in result.stderr


def test_status_rejected_key_exits_1(fake_server):
    from tb_client.exceptions import ApiException

    _logged_in()
    fake_server.fail["/api/auth/user"] = ApiException(status=401, reason="Unauthorized")
    result = runner.invoke(app, ["auth", "status"])
    assert result.exit_code == 1


def test_logout_deletes_and_clears(fake_server, memory_keyring):
    _logged_in()
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert fake_server.calls == [("DELETE", "/api/apiKey/k1", "ApiKey secret1", None)]
    assert memory_keyring.store == {}
    assert cfg.load("default") == {"url": "https://tb"}


def test_logout_clears_even_if_server_fails(fake_server, memory_keyring):
    _logged_in()
    fake_server.fail["/api/apiKey/k1"] = OSError("network down")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert "network down" in result.stderr
    assert memory_keyring.store == {}


def test_logout_not_logged_in(fake_server, config_dir):
    result = runner.invoke(app, ["-c", "typo", "auth", "logout"])
    assert result.exit_code == 1
    assert "Not logged in for profile 'typo'" in result.stderr
    assert fake_server.calls == []
    assert not (config_dir / "typo.toml").exists()


def test_login_insecure_storage_warns(fake_server, config_dir):
    result = _login("--insecure-storage")
    assert str(config_dir / "default.toml") in result.stderr


def test_login_to_new_host_never_pairs_old_key_with_new_url(fake_server, monkeypatch):
    _logged_in()
    seen = []
    real_save = cfg.save

    def spy(data, profile="default"):
        real_save(data, profile)
        seen.append((cfg.load(profile).get("url"), credentials.get(profile)))

    monkeypatch.setattr("tbctl.config.save", spy)
    assert _login(input="https://new\nu\npw\n").exit_code == 0
    assert ("https://new", "secret1") not in seen
    assert seen[-1] == ("https://new", "secret2")


def test_login_unreachable_url_is_clean(fake_server):
    fake_server.fail["/api/auth/login"] = OSError("Name or service not known")
    result = _login()
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Could not reach https://tb" in result.stderr
    assert "Name or service not known" in result.stderr


def test_login_wrong_password_has_no_login_hint(fake_server):
    from tb_client.exceptions import ApiException

    fake_server.fail["/api/auth/login"] = ApiException(
        status=401, reason="Unauthorized", body='{"message": "Invalid username or password"}'
    )
    result = _login()
    assert result.stderr == "Error 401: Invalid username or password\n"


def test_logout_under_env_says_server_key_stays(fake_server, monkeypatch):
    _logged_in()
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    result = runner.invoke(app, ["auth", "logout"])
    assert result.exit_code == 0
    assert fake_server.calls == []
    assert "not deleted on the server" in result.stderr
