import json

import pytest
import typer
from typer.testing import CliRunner

import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl.cli import app, complete_profile

runner = CliRunner()


def test_list_profiles(config_dir):
    cfg.save({"url": "https://prod.example.com"}, "PROD")
    cfg.save({"url": "https://dev.example.com"}, "dev")
    assert cfg.list_profiles() == ["PROD", "dev"]


def test_list_profiles_empty(config_dir):
    assert cfg.list_profiles() == []


def test_complete_profile(config_dir):
    cfg.save({"url": "https://prod.example.com"}, "PROD")
    cfg.save({"url": "https://dev.example.com"}, "dev")
    assert complete_profile("") == ["PROD", "dev"]
    assert complete_profile("de") == ["dev"]


def test_show_empty(config_dir):
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "No configuration found" in result.output
    assert "default" in result.output


def test_show(config_dir):
    cfg.save({"url": "https://example.com"}, "default")
    credentials.save("default", "api-key", "tb_abc123")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "https://example.com" in result.output
    assert "source = keyring" in result.output
    assert "tb_abc123" not in result.output


def test_show_reports_env_source(config_dir, monkeypatch):
    cfg.save({"url": "https://example.com"}, "default")
    monkeypatch.setenv("TBCTL_TOKEN", "x")
    result = runner.invoke(app, ["config", "show"])
    assert "source = TBCTL_TOKEN" in result.output


def test_show_profile_isolation(config_dir):
    cfg.save({"url": "https://prod.example.com"}, "prod")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "prod.example.com" not in result.output


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

    cfg.save({"url": "https://example.com"}, "default")
    aliases.add("default", "ruedi", "OX1-Y2HUZR", "b1f2c3d4-1111-2222-3333-444455556666")
    aliases.add("default", "horst", "OX1-1T6570")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "aliases.ruedi.name = OX1-Y2HUZR" in result.output
    assert "aliases.ruedi.id = b1f2c3d4-1111-2222-3333-444455556666" in result.output
    assert "aliases.horst.name = OX1-1T6570" in result.output
    assert "{" not in result.output


def test_show_ignores_token_without_login(config_dir):
    cfg.save({"url": "https://example.com", "token": "secret"}, "default")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "secret" not in result.stdout
    assert "auth = not set" in result.stdout


def test_show_json(config_dir):
    cfg.save({"url": "https://example.com"}, "default")
    credentials.save("default", "api-key", "tb_abc123")
    result = runner.invoke(app, ["config", "show", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "url": "https://example.com",
        "auth": "api-key",
        "source": "keyring",
    }


def test_show_json_empty(config_dir):
    result = runner.invoke(app, ["config", "show", "-j"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_load_warns_about_unknown_key(config_dir, capsys):
    cfg.save({"url": "u", "colour": "secret"}, "default")
    assert cfg.load("default")["url"] == "u"
    err = capsys.readouterr().err
    assert "unknown key 'colour'" in err
    assert "secret" not in err


def test_protected_attributes_is_a_known_key(config_dir, capsys):
    cfg.save({"protected_attributes": ["iccid"]}, "default")
    assert cfg.load("default")["protected_attributes"] == ["iccid"]
    assert "unknown key" not in capsys.readouterr().err


def test_load_warns_once_per_key(config_dir, capsys):
    cfg.save({"url": "u", "colour": "x"}, "default")
    cfg.load("default")
    cfg.load("default")
    assert capsys.readouterr().err.count("unknown key 'colour'") == 1


def test_load_is_silent_during_completion(config_dir, capsys, monkeypatch):
    monkeypatch.setenv("_TBCTL_COMPLETE", "complete_zsh")
    cfg.save({"url": "u", "colour": "x"}, "default")
    cfg.load("default")
    assert capsys.readouterr().err == ""


def test_load_is_silent_for_known_keys(config_dir, capsys):
    cfg.save({"url": "u", "aliases": {}}, "default")
    cfg.load("default")
    assert capsys.readouterr().err == ""


def test_save_is_private(config_dir):
    cfg.save({"url": "https://x"}, "p")
    assert (config_dir / "p.toml").stat().st_mode & 0o777 == 0o600


def test_save_creates_private_dir(tmp_path, monkeypatch):
    d = tmp_path / "new"
    monkeypatch.setattr("tbctl.config.CONFIG_DIR", d)
    cfg.save({"url": "https://x"}, "p")
    assert d.stat().st_mode & 0o777 == 0o700


def test_auth_keys_are_known(config_dir, capsys):
    cfg.save({"url": "u", "token": "t", "auth": "jwt", "refresh_expires": 1}, "p")
    cfg.load("p")
    assert capsys.readouterr().err == ""


def test_show_hides_file_token(config_dir, no_keyring):
    cfg.save({"url": "https://example.com"}, "default")
    credentials.save("default", "jwt", "secret", refresh_expires=1_800_000_000_000)
    result = runner.invoke(app, ["config", "show"])
    assert "auth = jwt" in result.stdout
    assert "source = file" in result.stdout
    assert "refresh_expires = 2027-01-15 " in result.stdout
    assert "secret" not in result.stdout


def test_old_config_commands_are_gone(config_dir):
    for command in ("init", "set-token", "set-url"):
        assert runner.invoke(app, ["config", command]).exit_code == 2


def test_load_warns_about_token_without_auth(config_dir, capsys):
    cfg.save({"url": "u", "token": "old", "refresh_expires": 1}, "default")
    cfg.load("default")
    cfg.load("default")
    err = capsys.readouterr().err
    assert err.count("ignoring 'token' without 'auth'") == 1
    assert "'refresh_expires' without 'auth'" in err
    assert "tbctl auth login" in err
    assert "old" not in err


def test_load_names_old_api_key_metadata_unknown(config_dir, capsys):
    cfg.save({"url": "u", "token_id": "k1", "token_expires": 1}, "default")
    cfg.load("default")
    err = capsys.readouterr().err
    assert "unknown key 'token_id'" in err
    assert "unknown key 'token_expires'" in err


def test_load_refuses_open_file(config_dir, capsys):
    cfg.save({"url": "https://x"}, "p")
    path = config_dir / "p.toml"
    path.chmod(0o664)
    with pytest.raises(typer.Exit):
        cfg.load("p")
    err = capsys.readouterr().err
    assert f"Permissions 664 for {path} are too open" in err
    assert f"chmod 600 {path}" in err
    assert path.stat().st_mode & 0o777 == 0o664


def test_load_refuses_open_dir(config_dir, capsys):
    cfg.save({"url": "https://x"}, "p")
    config_dir.chmod(0o755)
    with pytest.raises(typer.Exit):
        cfg.load("p")
    assert f"chmod 700 {config_dir}" in capsys.readouterr().err
    assert config_dir.stat().st_mode & 0o777 == 0o755


def test_load_accepts_private_profile(config_dir):
    cfg.save({"url": "https://x"}, "p")
    assert cfg.load("p") == {"url": "https://x"}
