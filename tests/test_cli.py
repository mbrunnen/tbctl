import subprocess
import sys


def test_cli_imports_without_click():
    """Typer vendors Click since 0.26, so an install has no click package to import."""
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.modules['click'] = None; import tbctl.cli"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
