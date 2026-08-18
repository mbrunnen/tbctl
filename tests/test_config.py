import tomllib

from typer.testing import CliRunner

import tbctl.config as cfg
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
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["token"] == "tb_abc123"


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
    assert "tb_abc123" in result.output


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
    assert data["url"] == "https://example.com"
    assert data["token"] == "secret-token"
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
    assert data["token"] == "old-token"


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
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["token"] == "bad-token"


def test_init_profile(config_dir, monkeypatch):
    _ok(monkeypatch)
    result = runner.invoke(
        app, ["-c", "staging", "config", "init"], input="https://staging.example.com\ntok\n"
    )
    assert result.exit_code == 0
    with open(config_dir / "staging.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://staging.example.com"


def test_show_flattens_the_alias_table(config_dir):
    import tbctl.aliases as aliases

    runner.invoke(app, ["config", "set-url", "https://example.com"])
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    aliases.add("default", "horst", "OX1-1T6570")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "aliases.ruedi = OX1-Y2HUZR" in result.output
    assert "aliases.horst = OX1-1T6570" in result.output
    assert "{" not in result.output


def test_show_flattens_nested_tables(config_dir):
    cfg.save({"url": "https://example.com", "a": {"b": {"c": "deep"}}}, "default")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "a.b.c = deep" in result.output
