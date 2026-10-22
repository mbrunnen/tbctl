import json
import tomllib

import pytest
from typer.testing import CliRunner

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl.cli import app, complete_profile

runner = CliRunner()


def test_list_profiles(config_dir):
    runner.invoke(app, ["-c", "PROD", "config", "set-url", "https://prod.example.com"])
    runner.invoke(app, ["-c", "dev", "config", "set-url", "https://dev.example.com"])
    assert cfg.list_profiles() == ["PROD", "dev"]


def test_list_profiles_empty(config_dir):
    assert cfg.list_profiles() == []


def test_complete_profile(config_dir):
    runner.invoke(app, ["-c", "PROD", "config", "set-url", "https://prod.example.com"])
    runner.invoke(app, ["-c", "dev", "config", "set-url", "https://dev.example.com"])
    assert complete_profile("") == ["PROD", "dev"]
    assert complete_profile("de") == ["dev"]


def test_set_url(config_dir):
    result = runner.invoke(app, ["config", "set-url", "https://example.com"])
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://example.com"


def test_set_url_profile(config_dir):
    result = runner.invoke(
        app, ["-c", "staging", "config", "set-url", "https://staging.example.com"]
    )
    assert result.exit_code == 0
    with open(config_dir / "staging.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://staging.example.com"


def test_set_token(config_dir):
    result = runner.invoke(app, ["config", "set-token", "tb_abc123"])
    assert result.exit_code == 0
    assert credentials.stored("default") == "tb_abc123"
    assert not (config_dir / "default.toml").exists()


def test_set_token_without_backend(config_dir, no_keyring):
    result = runner.invoke(app, ["config", "set-token", "tb_abc123"])
    assert result.exit_code == 1
    assert "TBCTL_TOKEN" in result.stderr


def test_show_empty(config_dir):
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "No configuration found" in result.output
    assert "default" in result.output


def test_show(config_dir):
    runner.invoke(app, ["config", "set-url", "https://example.com"])
    runner.invoke(app, ["config", "set-token", "tb_abc123"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "https://example.com" in result.output
    assert "token = keyring" in result.output
    assert "tb_abc123" not in result.output


def test_show_reports_env_source(config_dir, monkeypatch):
    runner.invoke(app, ["config", "set-url", "https://example.com"])
    monkeypatch.setenv("TBCTL_TOKEN", "x")
    result = runner.invoke(app, ["config", "show"])
    assert "token = TBCTL_TOKEN" in result.output


def test_show_profile_isolation(config_dir):
    runner.invoke(app, ["-c", "prod", "config", "set-url", "https://prod.example.com"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "prod.example.com" not in result.output


def _ok(monkeypatch, email="me@example.com"):
    monkeypatch.setattr(
        "tbctl.commands.config_cmd.check_connection", lambda url, token: (True, email)
    )


def test_init_writes_config(config_dir, monkeypatch):
    _ok(monkeypatch)
    result = runner.invoke(app, ["config", "init"], input="https://example.com\nsecret-token\n")
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        data = tomllib.load(f)
    assert data == {"url": "https://example.com"}
    assert credentials.stored("default") == "secret-token"
    assert "Connection OK" in result.output
    assert "me@example.com" in result.output


def test_init_hides_token(config_dir, monkeypatch):
    _ok(monkeypatch)
    result = runner.invoke(app, ["config", "init"], input="https://example.com\nsecret-token\n")
    assert result.exit_code == 0
    assert "secret-token" not in result.output


def test_init_keeps_existing_token_on_empty(config_dir, monkeypatch):
    _ok(monkeypatch)
    runner.invoke(app, ["config", "set-url", "https://old.example.com"])
    runner.invoke(app, ["config", "set-token", "old-token"])
    result = runner.invoke(app, ["config", "init"], input="https://new.example.com\n\n")
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        data = tomllib.load(f)
    assert data["url"] == "https://new.example.com"
    assert credentials.stored("default") == "old-token"


def test_init_url_default_prefill(config_dir, monkeypatch):
    _ok(monkeypatch)
    runner.invoke(app, ["config", "set-url", "https://kept.example.com"])
    runner.invoke(app, ["config", "set-token", "old-token"])
    result = runner.invoke(app, ["config", "init"], input="\n\n")
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://kept.example.com"


def test_init_saves_despite_validation_failure(config_dir, monkeypatch):
    monkeypatch.setattr(
        "tbctl.commands.config_cmd.check_connection",
        lambda url, token: (False, "401 Unauthorized"),
    )
    result = runner.invoke(app, ["config", "init"], input="https://example.com\nbad-token\n")
    assert result.exit_code == 0
    assert "Warning" in result.output
    assert credentials.stored("default") == "bad-token"
    assert cfg.load("default") == {"url": "https://example.com"}


def test_init_without_backend_writes_nothing(config_dir, monkeypatch, no_keyring):
    _ok(monkeypatch)
    result = runner.invoke(app, ["config", "init"], input="https://example.com\nsecret-token\n")
    assert result.exit_code == 1
    assert "TBCTL_TOKEN" in result.stderr
    assert not (config_dir / "default.toml").exists()


def test_init_profile(config_dir, monkeypatch):
    _ok(monkeypatch)
    result = runner.invoke(
        app, ["-c", "staging", "config", "init"], input="https://staging.example.com\ntok\n"
    )
    assert result.exit_code == 0
    with open(config_dir / "staging.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://staging.example.com"


def test_save_keeps_the_previous_file_when_writing_fails(config_dir, monkeypatch):
    cfg.save({"url": "https://example.com"}, "default")

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("tbctl.config.tomli_w.dump", boom)
    with pytest.raises(RuntimeError):
        cfg.save({"url": "https://broken.example"}, "default")

    assert cfg.load("default") == {"url": "https://example.com"}
    assert sorted(p.name for p in config_dir.iterdir()) == ["default.toml"]


def test_show_flattens_the_alias_table(config_dir):
    import tbctl.aliases as aliases

    runner.invoke(app, ["config", "set-url", "https://example.com"])
    aliases.add("default", "ruedi", "OX1-Y2HUZR", "b1f2c3d4-1111-2222-3333-444455556666")
    aliases.add("default", "horst", "OX1-1T6570")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "aliases.ruedi.name = OX1-Y2HUZR" in result.output
    assert "aliases.ruedi.id = b1f2c3d4-1111-2222-3333-444455556666" in result.output
    assert "aliases.horst.name = OX1-1T6570" in result.output
    assert "{" not in result.output


def test_show_hides_plaintext_token(config_dir):
    cfg.save({"url": "https://example.com", "token": "secret"}, "default")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "secret" not in result.stdout
    assert "token = not set" in result.stdout


def test_show_json(config_dir):
    runner.invoke(app, ["config", "set-url", "https://example.com"])
    runner.invoke(app, ["config", "set-token", "tb_abc123"])
    result = runner.invoke(app, ["config", "show", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"url": "https://example.com", "token": "keyring"}


def test_show_json_empty(config_dir):
    result = runner.invoke(app, ["config", "show", "-j"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_load_warns_about_unknown_key(config_dir, capsys):
    cfg.save({"url": "u", "token": "secret"}, "default")
    assert cfg.load("default")["url"] == "u"
    err = capsys.readouterr().err
    assert "unknown key 'token'" in err
    assert "secret" not in err


def test_load_warns_once_per_key(config_dir, capsys):
    cfg.save({"url": "u", "token": "x"}, "default")
    cfg.load("default")
    cfg.load("default")
    assert capsys.readouterr().err.count("unknown key 'token'") == 1


def test_load_is_silent_during_completion(config_dir, capsys, monkeypatch):
    monkeypatch.setenv("_TBCTL_COMPLETE", "complete_zsh")
    cfg.save({"url": "u", "token": "x"}, "default")
    cfg.load("default")
    assert capsys.readouterr().err == ""


def test_load_is_silent_for_known_keys(config_dir, capsys):
    cfg.save({"url": "u", "aliases": {}}, "default")
    cfg.load("default")
    assert capsys.readouterr().err == ""


def test_set_token_with_broken_backend_names_the_reason(config_dir, broken_keyring):
    result = runner.invoke(app, ["config", "set-token", "tb_abc123"])
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "Cannot unlock the wallet" in result.stderr
    assert "TBCTL_TOKEN" in result.stderr
