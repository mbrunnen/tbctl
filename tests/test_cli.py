import json
import subprocess
import sys

from typer.testing import CliRunner

import tbctl.aliases as aliases
from tbctl.cli import app, complete_context
from tests.conftest import fake_click_ctx


def test_cli_imports_without_click():
    """Typer vendors Click since 0.26, so an install has no click package to import."""
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.modules['click'] = None; import tbctl.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_completion_prints_script_for_named_shell():
    result = CliRunner().invoke(app, ["completion", "fish"])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("complete --command tbctl")
    assert "_TBCTL_COMPLETE=complete_fish" in result.output


def test_completion_rejects_unknown_shell():
    result = CliRunner().invoke(app, ["completion", "tcsh"])
    assert result.exit_code == 2


def write(path, text):
    path.write_text(text)
    path.chmod(0o600)


def test_context_flag_picks_the_context(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\n',
    )
    result = CliRunner().invoke(app, ["--context", "b", "config", "show", "-j"])
    assert json.loads(result.output)["url"] == "https://b"


def test_config_flag_reads_any_file(tmp_path):
    path = tmp_path / "elsewhere" / "ci.toml"
    path.parent.mkdir()
    path.write_text('[contexts.ci]\nurl = "https://ci"\n')
    result = CliRunner().invoke(app, ["-c", str(path), "config", "show", "-j"])
    assert json.loads(result.output)["url"] == "https://ci"


def test_unresolvable_context_is_one_line_error(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.a]\nurl = "https://a"\n[contexts.b]\nurl = "https://b"\n',
    )
    result = CliRunner().invoke(app, ["device", "list"])
    assert result.exit_code == 1
    assert "--context" in result.output


def test_completion_is_silent_without_config(config_dir, monkeypatch, capsys):
    (config_dir / "config.toml").unlink()
    monkeypatch.setenv("_TBCTL_COMPLETE", "complete_zsh")
    assert aliases.complete_device(fake_click_ctx({}), "") == []
    assert capsys.readouterr().err == ""


def test_completion_is_silent_with_open_config(config_dir, monkeypatch, capsys):
    (config_dir / "config.toml").chmod(0o644)
    monkeypatch.setenv("_TBCTL_COMPLETE", "complete_zsh")
    assert aliases.complete_device(fake_click_ctx({}), "") == []
    assert capsys.readouterr().err == ""


def test_context_completion_lists_names(config_dir):
    write(
        config_dir / "config.toml",
        '[contexts.dev]\nurl = "https://a"\n[contexts.PROD]\nurl = "https://b"\n',
    )
    assert complete_context(fake_click_ctx({}), "d") == ["dev"]


def test_old_spellings_are_gone(config_dir):
    for args in (
        ["alias", "rm", "x"],
        ["telemetry", "history", "dev", "--order", "ASC"],
        ["ota", "upload", "--url", "https://x/fw.bin"],
    ):
        assert CliRunner().invoke(app, args).exit_code == 2, args
