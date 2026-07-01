import typer

from tbctl.cli import app
from tests.readme_check import (
    check_invocation,
    iter_command_lines,
    root_command,
)


def _synthetic_root():
    sub = typer.Typer()

    @sub.command("list")
    def _list(
        json_: bool = typer.Option(False, "--json"),
        search: str = typer.Option(None, "--search"),
    ):
        pass

    parent = typer.Typer()
    parent.add_typer(sub, name="ota")

    @parent.callback()
    def _cb(config: str = typer.Option("default", "-c", "--config")):
        pass

    return root_command(parent)


def test_valid_invocation_has_no_errors():
    root = _synthetic_root()
    assert check_invocation(root, "tbctl ota list --json --search fw") == []


def test_unknown_command_is_reported():
    root = _synthetic_root()
    errors = check_invocation(root, "tbctl ota bogus")
    assert errors
    assert any("bogus" in e for e in errors)


def test_unknown_flag_is_reported():
    root = _synthetic_root()
    errors = check_invocation(root, "tbctl ota list --nope")
    assert errors
    assert any("--nope" in e for e in errors)


def test_global_option_is_valid_on_subcommand():
    root = _synthetic_root()
    assert check_invocation(root, "tbctl ota list -c prod") == []


def test_global_option_value_is_not_a_command():
    root = _synthetic_root()
    assert check_invocation(root, "tbctl -c prod ota list") == []


def test_iter_command_lines_extracts_only_fenced_tbctl_lines():
    text = "\n".join(
        [
            "prose tbctl ota list should be ignored",
            "```sh",
            "tbctl ota list --json   # a comment",
            "uv run tbctl config show",
            "pipx install .",
            "```",
            "`tbctl ota get <uuid>` inline prose ignored",
        ]
    )
    assert iter_command_lines(text) == [
        "tbctl ota list --json",
        "tbctl config show",
    ]


def test_readme_has_no_command_drift():
    from pathlib import Path

    readme = Path(__file__).resolve().parent.parent / "README.md"
    lines = iter_command_lines(readme.read_text())
    assert len(lines) > 10, "extraction found too few commands; regex likely broke"

    root = root_command(app)
    errors = [e for line in lines for e in check_invocation(root, line)]
    assert not errors, "README documents commands/flags absent from the CLI:\n" + "\n".join(errors)
