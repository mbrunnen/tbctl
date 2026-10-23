import tbctl.config as cfg
from tbctl import credentials


def test_save_uses_keyring(config_dir, memory_keyring):
    assert credentials.save("p", "v", "id1", 123) == "keyring"
    assert memory_keyring.store[("tbctl", "p")] == "v"
    assert cfg.load("p") == {"token_id": "id1", "token_expires": 123}
    assert credentials.get("p") == "v"
    assert credentials.source("p") == "keyring"
    assert credentials.expires("p") == 123


def test_save_falls_back_to_file(config_dir, no_keyring, capsys):
    cfg.save({"url": "u", "aliases": {"a": "b"}}, "p")
    assert credentials.save("p", "v", "id1", 123) == "file"
    assert cfg.load("p") == {
        "url": "u",
        "aliases": {"a": "b"},
        "token": "v",
        "token_id": "id1",
        "token_expires": 123,
    }
    assert credentials.source("p") == "file"
    assert credentials.get("p") == "v"
    assert "p.toml" in capsys.readouterr().err


def test_save_falls_back_with_broken_keyring(config_dir, broken_keyring):
    assert credentials.save("p", "v", "id1", 123) == "file"
    assert credentials.get("p") == "v"


def test_insecure_skips_keyring(config_dir, memory_keyring):
    assert credentials.save("p", "v", "id1", 123, insecure=True) == "file"
    assert memory_keyring.store == {}


def test_keyring_save_removes_file_token(config_dir):
    cfg.save({"token": "old", "token_id": "x", "token_expires": 1}, "p")
    credentials.save("p", "v", "id1", 123)
    assert "token" not in cfg.load("p")


def test_value_without_token_id_is_not_logged_in(config_dir, memory_keyring):
    memory_keyring.set_password("tbctl", "p", "legacy")
    cfg.save({"token": "legacy"}, "p")
    assert credentials.get("p") is None
    assert credentials.source("p") is None


def test_profiles_are_separate(config_dir):
    credentials.save("prod", "v", "id1", 123)
    assert credentials.get("default") is None


def test_env_wins(config_dir, monkeypatch):
    credentials.save("p", "v", "id1", 123)
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.get("p") == "env"
    assert credentials.source("p") == "TBCTL_TOKEN"


def test_env_without_login(config_dir, no_keyring, monkeypatch):
    monkeypatch.setenv("TBCTL_TOKEN", "env")
    assert credentials.get("p") == "env"


def test_empty_env_falls_back_to_keyring(config_dir, monkeypatch):
    credentials.save("p", "v", "id1", 123)
    monkeypatch.setenv("TBCTL_TOKEN", "")
    assert credentials.get("p") == "v"


def test_broken_keyring_reads_none(config_dir, broken_keyring):
    cfg.save({"token_id": "id1", "token_expires": 1}, "p")
    assert credentials.get("p") is None
    assert credentials.source("p") is None


def test_clear(config_dir, memory_keyring):
    cfg.save({"url": "u"}, "p")
    credentials.save("p", "v", "id1", 123)
    credentials.clear("p")
    assert memory_keyring.store == {}
    assert cfg.load("p") == {"url": "u"}


def test_clear_without_backend(config_dir, no_keyring):
    credentials.save("p", "v", "id1", 123)
    credentials.clear("p")
    assert credentials.get("p") is None


def test_token_id_without_expiry_is_not_logged_in(config_dir, memory_keyring):
    memory_keyring.set_password("tbctl", "p", "v")
    cfg.save({"token_id": "k1"}, "p")
    assert credentials.get("p") is None
    assert credentials.source("p") is None


def test_unreadable_keyring_names_the_reason_once(config_dir, broken_keyring, capsys):
    cfg.save({"token_id": "id1", "token_expires": 1}, "p")
    credentials.get("p")
    credentials.source("p")
    err = capsys.readouterr().err
    assert err.count("Cannot unlock the wallet") == 1


def test_clear_names_a_failing_keyring(config_dir, broken_keyring, capsys):
    cfg.save({"url": "u", "token_id": "id1", "token_expires": 1}, "p")
    credentials.clear("p")
    assert "Cannot unlock the wallet" in capsys.readouterr().err
    assert cfg.load("p") == {"url": "u"}


def test_clear_is_quiet_without_an_entry(config_dir, capsys):
    cfg.save({"url": "u", "token_id": "id1", "token_expires": 1, "token": "v"}, "p")
    credentials.clear("p")
    assert capsys.readouterr().err == ""


def test_clear_unknown_profile_creates_no_file(config_dir):
    credentials.clear("typo")
    assert not (config_dir / "typo.toml").exists()
