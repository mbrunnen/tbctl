import pytest

from tbctl import credentials, state
from tbctl.credentials import API_KEY, JWT, Credential
from tests.conftest import context_for

KEY = "default@https://tb.example.com"


@pytest.fixture
def p(context):
    return context


def test_save_jwt_uses_keyring(p, memory_keyring):
    assert credentials.save(p, JWT, "pair", refresh_expires=123) == "keyring"
    assert memory_keyring.store[("tbctl", KEY)] == "pair"
    assert state.load(KEY) == {"auth": "jwt", "refresh_expires": 123}
    assert credentials.load(p) == Credential(JWT, "pair", "keyring")


def test_save_api_key_has_no_expiry(p):
    credentials.save(p, JWT, "pair", refresh_expires=123)
    credentials.save(p, API_KEY, "key")
    assert state.load(KEY) == {"auth": "api-key"}
    assert credentials.load(p) == Credential(API_KEY, "key", "keyring")


def test_save_falls_back_to_state_file(p, no_keyring, capsys):
    assert credentials.save(p, API_KEY, "key") == "file"
    assert state.load(KEY) == {"token": "key", "auth": "api-key"}
    assert credentials.load(p) == Credential(API_KEY, "key", "file")
    assert "state.toml" in capsys.readouterr().err


def test_save_falls_back_with_broken_keyring(p, broken_keyring):
    assert credentials.save(p, API_KEY, "key") == "file"


def test_insecure_skips_keyring(p, memory_keyring, capsys):
    assert credentials.save(p, API_KEY, "key", insecure=True) == "file"
    assert memory_keyring.store == {}
    assert "--insecure-storage" in capsys.readouterr().err


def test_keyring_save_removes_file_token(p):
    state.save(KEY, {"token": "old", "auth": "api-key"})
    credentials.save(p, API_KEY, "key")
    assert "token" not in state.load(KEY)


def test_secret_without_auth_is_not_logged_in(p, memory_keyring):
    memory_keyring.set_password("tbctl", KEY, "legacy")
    state.save(KEY, {"token": "legacy"})
    assert credentials.load(p) is None


def test_contexts_are_separate(p, tmp_path):
    other = context_for(tmp_path / "x" / "o.toml", "prod", "https://tb.example.com")
    credentials.save(other, API_KEY, "key")
    assert credentials.load(p) is None


def test_env_wins_as_api_key(p, monkeypatch):
    credentials.save(p, JWT, "pair", refresh_expires=1)
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.load(p) == Credential(API_KEY, "env", "TBCTL_TOKEN")


def test_empty_env_falls_back(p, monkeypatch):
    credentials.save(p, API_KEY, "key")
    monkeypatch.setenv("TBCTL_TOKEN", "")
    assert credentials.load(p).secret == "key"


def test_unreadable_keyring_names_the_reason_once(p, broken_keyring, capsys):
    state.save(KEY, {"auth": "api-key"})
    assert credentials.load(p) is None
    credentials.load(p)
    assert capsys.readouterr().err.count("Cannot unlock the wallet") == 1


def test_clear(p, memory_keyring):
    credentials.save(p, JWT, "pair", refresh_expires=1)
    state.save(KEY, {**state.load(KEY), "customer_id": "c"})
    credentials.clear(p)
    assert memory_keyring.store == {}
    assert state.load(KEY) == {}


def test_clear_names_a_failing_keyring(p, broken_keyring, capsys):
    state.save(KEY, {"auth": "api-key"})
    credentials.clear(p)
    assert "Cannot unlock the wallet" in capsys.readouterr().err
    assert state.load(KEY) == {}


def test_clear_is_quiet_without_an_entry(p, capsys):
    state.save(KEY, {"auth": "api-key", "token": "v"})
    credentials.clear(p)
    assert capsys.readouterr().err == ""


def test_clear_without_login_creates_no_state_file(p):
    credentials.clear(p)
    assert not (state.STATE_DIR / "state.toml").exists()


def test_keyring_secret_without_auth_is_named(p, memory_keyring, capsys):
    memory_keyring.set_password("tbctl", KEY, "tb_oldkey")
    assert credentials.load(p) is None
    credentials.load(p)
    err = capsys.readouterr().err
    assert err.count("ignoring the credential in the Secret Service") == 1
    assert "tbctl auth login" in err
    assert "tb_oldkey" not in err


def test_auth_without_keyring_entry_is_named(p, memory_keyring, capsys):
    state.save(KEY, {"auth": "jwt"})
    assert credentials.load(p) is None
    assert "no credential in the Secret Service for context 'default'" in capsys.readouterr().err


def test_clear_reports_removed_orphan(p, memory_keyring):
    memory_keyring.set_password("tbctl", KEY, "tb_oldkey")
    assert credentials.clear(p) is True
    assert memory_keyring.store == {}


def test_clear_reports_nothing_removed(p):
    assert credentials.clear(p) is False


def test_same_name_other_url_is_another_login(tmp_path, memory_keyring):
    a = context_for(tmp_path / "x" / "1.toml", "PROD", "https://one")
    b = context_for(tmp_path / "x" / "2.toml", "PROD", "https://two")
    credentials.save(a, credentials.API_KEY, "k1")
    assert credentials.load(b) is None
    assert ("tbctl", "PROD@https://one") in memory_keyring.store


def test_secret_never_lands_in_config_file(context, no_keyring):
    credentials.save(context, credentials.API_KEY, "secret")
    assert "secret" not in context.file.read_text()
    assert state.load(context.key)["token"] == "secret"


def test_env_token_needs_no_state(context, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "k")
    assert credentials.load(context) == credentials.Credential("api-key", "k", "TBCTL_TOKEN")
