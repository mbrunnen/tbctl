import json

import pytest
import tomlkit
import typer
from typer.testing import CliRunner

import tbctl.aliases as aliases
import tbctl.config as cfg
import tbctl.credentials as credentials
from tbctl import state
from tbctl.cli import app

runner = CliRunner()


def _add(path, name, url):
    """Add a context the way a hand edit would, through the config writer."""
    doc = cfg.read(path)
    if "contexts" not in doc:
        doc["contexts"] = tomlkit.table(is_super_table=True)
    doc["contexts"][name] = {"url": url}
    cfg.write(path, doc)


def test_show(context):
    credentials.save(context, "api-key", "tb_abc123")
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "url = https://tb.example.com" in result.output
    assert "context = default" in result.output
    assert "tb_abc123" not in result.output


def test_show_context_isolation(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "https://a"\ndefault = true\n[contexts.b]\nurl = "https://b"\n',
    )
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "https://b" not in result.output


def test_write_keeps_the_previous_file_when_writing_fails(context, monkeypatch):
    before = context.file.read_text()

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr("tbctl.config.tomlkit.dumps", boom)
    with pytest.raises(RuntimeError):
        _add(context.file, "x", "https://x")

    assert context.file.read_text() == before
    assert not [p for p in context.file.parent.iterdir() if p.name.endswith(".tmp")]


def test_show_flattens_the_alias_table(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    aliases.add(context, "horst", "DEVICE-B")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "aliases.ruedi.name = DEVICE-A" in result.output
    assert "aliases.horst.name = DEVICE-B" in result.output
    assert "{" not in result.output


def test_show_json(context):
    credentials.save(context, "api-key", "tb_abc123")
    result = runner.invoke(app, ["config", "show", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "file": str(context.file),
        "file_source": "default",
        "context": "default",
        "context_source": "default",
        "url": "https://tb.example.com",
    }


def test_known_keys_are_silent(config_dir, capsys):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "u"\ndefault = true\nprotected_attributes = ["iccid"]\n'
        "[contexts.a.aliases]\n",
    )
    cfg.resolve()
    assert capsys.readouterr().err == ""


def test_unknown_key_warns_once(config_dir, capsys):
    write(config_dir / "config.toml", '[contexts.a]\nurl = "u"\ncolour = "secret"\n')
    cfg.resolve()
    cfg.resolve()
    err = capsys.readouterr().err
    assert err.count("unknown key 'colour'") == 1
    assert "secret" not in err


def test_unknown_key_is_silent_during_completion(config_dir, capsys, monkeypatch):
    monkeypatch.setenv("_TBCTL_COMPLETE", "complete_zsh")
    write(config_dir / "config.toml", '[contexts.a]\nurl = "u"\ncolour = "x"\n')
    cfg.resolve()
    assert capsys.readouterr().err == ""


def test_write_keeps_the_mode_of_a_file_elsewhere(tmp_path):
    path = tmp_path / "elsewhere" / "ci.toml"
    path.parent.mkdir()
    path.write_text("")
    path.chmod(0o644)
    _add(path, "a", "https://x")
    assert path.stat().st_mode & 0o777 == 0o644


def test_show_hides_file_token(context, no_keyring):
    credentials.save(context, "jwt", "secret", refresh_expires=1_800_000_000_000)
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "secret" not in result.stdout


def test_old_config_commands_are_gone(config_dir):
    for command in ("init", "set-token", "set-url"):
        assert runner.invoke(app, ["config", command]).exit_code == 2


def test_state_file_must_be_private(context, capsys):
    state.save(context.key, {"auth": "jwt"})
    (state.STATE_DIR / "state.toml").chmod(0o644)
    with pytest.raises(typer.Exit):
        state.load(context.key)


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o600)


def test_file_order(config_dir, tmp_path, monkeypatch):
    assert cfg.config_file(None) == (config_dir / "config.toml", "default")
    monkeypatch.setenv("TBCTL_CONFIG", str(tmp_path / "env.toml"))
    assert cfg.config_file(None) == (tmp_path / "env.toml", "env")
    assert cfg.config_file(str(tmp_path / "x.toml")) == (tmp_path / "x.toml", "flag")


def test_flag_that_looks_like_a_name_gets_a_hint():
    with pytest.raises(cfg.ConfigError, match="did you mean --context preprod"):
        cfg.config_file("preprod")


def test_context_order(config_dir, monkeypatch):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\ndefault = true\n',
    )
    assert (cfg.resolve().name, cfg.resolve().name_source) == ("b", "default")
    monkeypatch.setenv("TBCTL_CONTEXT", "a")
    assert (cfg.resolve().name, cfg.resolve().name_source) == ("a", "env")
    assert cfg.resolve(context_flag="b").name_source == "flag"


def test_only_context_is_chosen(config_dir):
    write(config_dir / "config.toml", '[contexts.a]\nurl = "https://a"\n')
    assert cfg.resolve().name_source == "only"


@pytest.mark.parametrize(
    "text,match",
    [
        ('[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\n', "--context"),
        (
            '[contexts.a]\nurl = "https://a"\ndefault = true\n'
            '[contexts.b]\nurl = "https://b"\ndefault = true\n',
            "default",
        ),
        ("[contexts.a]\ndefault = true\n", "url"),
        ("", "no context"),
    ],
)
def test_resolve_errors(config_dir, text, match):
    write(config_dir / "config.toml", text)
    with pytest.raises(cfg.ConfigError, match=match):
        cfg.resolve()


def test_unknown_context_is_an_error(config_dir):
    write(config_dir / "config.toml", '[contexts.a]\nurl = "https://a"\n')
    with pytest.raises(cfg.ConfigError, match="'z'"):
        cfg.resolve(context_flag="z")


def test_key_ignores_trailing_slash(config_dir):
    write(config_dir / "config.toml", '[contexts.a]\nurl = "https://a.example.com/"\n')
    ctx = cfg.resolve()
    assert ctx.url == "https://a.example.com"
    assert ctx.key == "a@https://a.example.com"
    assert "/" not in ctx.safe_key


def test_file_outside_config_dir_may_be_world_readable(tmp_path):
    path = tmp_path / "elsewhere" / "ci.toml"
    write(path, '[contexts.a]\nurl = "https://a"\n')
    path.chmod(0o644)
    assert cfg.resolve(config_flag=str(path)).file == path


def test_unknown_keys_warn(config_dir, capsys):
    write(config_dir / "config.toml", 'colour = 1\n[contexts.a]\nurl = "https://a"\ntoken = "x"\n')
    cfg.resolve()
    err = capsys.readouterr().err
    assert "unknown key 'colour'" in err
    assert "unknown key 'token'" in err


def test_dotted_context_names_round_trip(config_dir):
    path = config_dir / "config.toml"
    write(path, '[contexts."test.cloud.orgatex.com"]\nurl = "https://test.cloud.orgatex.com"\n')
    _add(path, "b", "https://b")
    assert list(cfg.contexts(cfg.read(path))) == ["test.cloud.orgatex.com", "b"]


def test_show_names_file_and_context_sources(context, monkeypatch):
    monkeypatch.setenv("TBCTL_CONFIG", str(context.file))
    data = json.loads(runner.invoke(app, ["config", "show", "-j"]).output)
    assert data["file"] == str(context.file)
    assert data["file_source"] == "env"
    assert data["context"] == "default"
    assert data["context_source"] == "default"
    assert data["url"] == "https://tb.example.com"


def test_show_lists_protected_attributes(context):
    with open(context.file, "a") as f:
        f.write('protected_attributes = ["iccid"]\n')
    data = json.loads(runner.invoke(app, ["config", "show", "-j"]).output)
    assert data["protected_attributes"] == ["iccid"]


def test_contexts_marks_default(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.dev]\nurl = "https://d"\n'
        '[contexts.preprod]\nurl = "https://p"\ndefault = true\n',
    )
    result = runner.invoke(app, ["config", "contexts"])
    assert result.exit_code == 0
    assert result.output == "dev\npreprod (default)\n"


def test_contexts_needs_no_selectable_context(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\n',
    )
    assert runner.invoke(app, ["config", "contexts"]).output == "a\nb\n"


def test_write_follows_a_symlink(tmp_path):
    real = tmp_path / "dotfiles" / "tbctl.toml"
    real.parent.mkdir()
    real.write_text('# mine\n[contexts.a]\nurl = "https://a"\n')
    link = tmp_path / "elsewhere" / "config.toml"
    link.parent.mkdir()
    link.symlink_to(real)
    _add(link, "b", "https://b")
    assert link.is_symlink()
    assert "b" in cfg.contexts(cfg.read(real))
    assert real.read_text().startswith("# mine\n")


def test_flag_naming_an_existing_file_is_read(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    (work / "tb.conf").write_text('[contexts.a]\nurl = "https://a"\n')
    assert cfg.resolve(config_flag="tb.conf").name == "a"


def test_user_is_a_known_key(context, capsys):
    cfg.resolve()
    assert "unknown key" not in capsys.readouterr().err


def test_open_config_file_and_dir_are_read(context, config_dir):
    context.file.chmod(0o664)
    config_dir.chmod(0o755)
    assert cfg.resolve().name == "default"
    config_dir.chmod(0o700)


def test_global_protected_attributes_is_a_known_key(config_dir, capsys):
    write(
        config_dir / "config.toml",
        'protected_attributes = ["iccid"]\n[contexts.a]\nurl = "https://a"\n',
    )
    cfg.resolve()
    assert "unknown key" not in capsys.readouterr().err
