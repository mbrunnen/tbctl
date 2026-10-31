import subprocess
import sys

from typer.testing import CliRunner

from tbctl.cli import app


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
