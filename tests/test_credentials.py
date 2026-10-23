import tbctl.config as cfg
from tbctl import credentials
from tbctl.credentials import API_KEY, JWT, Credential


def test_save_jwt_uses_keyring(config_dir, memory_keyring):
    assert credentials.save("p", JWT, "pair", refresh_expires=123) == "keyring"
    assert memory_keyring.store[("tbctl", "p")] == "pair"
    assert cfg.load("p") == {"auth": "jwt", "refresh_expires": 123}
    assert credentials.load("p") == Credential(JWT, "pair", "keyring")


def test_save_api_key_has_no_expiry(config_dir):
    credentials.save("p", JWT, "pair", refresh_expires=123)
    credentials.save("p", API_KEY, "key")
    assert cfg.load("p") == {"auth": "api-key"}
    assert credentials.load("p") == Credential(API_KEY, "key", "keyring")


def test_save_falls_back_to_file(config_dir, no_keyring, capsys):
    cfg.save({"url": "u", "aliases": {"a": "b"}}, "p")
    assert credentials.save("p", API_KEY, "key") == "file"
    assert cfg.load("p") == {"url": "u", "aliases": {"a": "b"}, "token": "key", "auth": "api-key"}
    assert credentials.load("p") == Credential(API_KEY, "key", "file")
    assert "p.toml" in capsys.readouterr().err


def test_save_falls_back_with_broken_keyring(config_dir, broken_keyring):
    assert credentials.save("p", API_KEY, "key") == "file"


def test_insecure_skips_keyring(config_dir, memory_keyring, capsys):
    assert credentials.save("p", API_KEY, "key", insecure=True) == "file"
    assert memory_keyring.store == {}
    assert "--insecure-storage" in capsys.readouterr().err


def test_keyring_save_removes_file_token(config_dir):
    cfg.save({"token": "old", "auth": "api-key"}, "p")
    credentials.save("p", API_KEY, "key")
    assert "token" not in cfg.load("p")


def test_secret_without_auth_is_not_logged_in(config_dir, memory_keyring):
    memory_keyring.set_password("tbctl", "p", "legacy")
    cfg.save({"token": "legacy"}, "p")
    assert credentials.load("p") is None


def test_profiles_are_separate(config_dir):
    credentials.save("prod", API_KEY, "key")
    assert credentials.load("default") is None


def test_env_wins_as_api_key(config_dir, monkeypatch):
    credentials.save("p", JWT, "pair", refresh_expires=1)
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.load("p") == Credential(API_KEY, "env", "TBCTL_TOKEN")


def test_env_without_login(config_dir, no_keyring, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.load("p").secret == "env"


def test_empty_env_falls_back(config_dir, monkeypatch):
    credentials.save("p", API_KEY, "key")
    monkeypatch.setenv("TBCTL_TOKEN", "")
    assert credentials.load("p").secret == "key"


def test_unreadable_keyring_names_the_reason_once(config_dir, broken_keyring, capsys):
    cfg.save({"auth": "api-key"}, "p")
    assert credentials.load("p") is None
    credentials.load("p")
    assert capsys.readouterr().err.count("Cannot unlock the wallet") == 1


def test_clear(config_dir, memory_keyring):
    cfg.save({"url": "u"}, "p")
    credentials.save("p", JWT, "pair", refresh_expires=1)
    credentials.clear("p")
    assert memory_keyring.store == {}
    assert cfg.load("p") == {"url": "u"}


def test_clear_names_a_failing_keyring(config_dir, broken_keyring, capsys):
    cfg.save({"url": "u", "auth": "api-key"}, "p")
    credentials.clear("p")
    assert "Cannot unlock the wallet" in capsys.readouterr().err
    assert cfg.load("p") == {"url": "u"}


def test_clear_is_quiet_without_an_entry(config_dir, capsys):
    cfg.save({"url": "u", "auth": "api-key", "token": "v"}, "p")
    credentials.clear("p")
    assert capsys.readouterr().err == ""


def test_clear_unknown_profile_creates_no_file(config_dir):
    credentials.clear("typo")
    assert not (config_dir / "typo.toml").exists()


def test_keyring_secret_without_auth_is_named(config_dir, memory_keyring, capsys):
    memory_keyring.set_password("tbctl", "p", "tb_oldkey")
    cfg.save({"url": "u"}, "p")
    assert credentials.load("p") is None
    credentials.load("p")
    err = capsys.readouterr().err
    assert err.count("ignoring the credential in the Secret Service") == 1
    assert "tbctl auth login" in err
    assert "tb_oldkey" not in err


def test_auth_without_keyring_entry_is_named(config_dir, memory_keyring, capsys):
    cfg.save({"url": "u", "auth": "jwt"}, "p")
    assert credentials.load("p") is None
    assert "no credential in the Secret Service for profile 'p'" in capsys.readouterr().err


def test_clear_reports_removed_orphan(config_dir, memory_keyring):
    memory_keyring.set_password("tbctl", "p", "tb_oldkey")
    cfg.save({"url": "u"}, "p")
    assert credentials.clear("p") is True
    assert memory_keyring.store == {}


def test_clear_reports_nothing_removed(config_dir):
    cfg.save({"url": "u"}, "p")
    assert credentials.clear("p") is False
