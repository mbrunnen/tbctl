import json

import click
import typer
from typer.testing import CliRunner

import tbctl.aliases as aliases
import tbctl.config as cfg
from tbctl.cli import app
from tests.test_ota import _strip_ansi

runner = CliRunner()


def _completion_context(profile):
    """Build a real Click context tree as the shell completion sees it."""
    root = typer.main.get_command(app)
    root_ctx = click.Context(root)
    root_ctx.params = {"config": profile} if profile else {}
    group_ctx = click.Context(root.commands["telemetry"], parent=root_ctx)
    return click.Context(group_ctx.command.commands["latest"], parent=group_ctx)


def test_load_is_empty_for_unknown_profile(config_dir):
    assert aliases.load("default") == {}


def test_add_is_readable_back(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    assert aliases.load("default") == {"ruedi": "OX1-Y2HUZR"}


def test_add_keeps_url_and_token(config_dir):
    cfg.save({"url": "https://tb.example", "token": "secret"}, "prod")
    aliases.add("prod", "horst", "OX1-1T6570")
    data = cfg.load("prod")
    assert data["url"] == "https://tb.example"
    assert data["token"] == "secret"
    assert data["aliases"] == {"horst": "OX1-1T6570"}


def test_add_overwrites_and_returns_previous_target(config_dir):
    aliases.add("default", "jacky", "OX1-DQRX5Z")
    previous = aliases.add("default", "jacky", "OX1-ZZ0001")
    assert previous == "OX1-DQRX5Z"
    assert aliases.load("default")["jacky"] == "OX1-ZZ0001"


def test_add_returns_none_for_a_new_alias(config_dir):
    assert aliases.add("default", "ruedi", "OX1-Y2HUZR") is None


def test_aliases_are_per_profile(config_dir):
    aliases.add("prod", "ruedi", "OX1-Y2HUZR")
    assert aliases.load("test") == {}


def test_resolve_returns_the_device_name(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve("default", "ruedi") == "OX1-Y2HUZR"


def test_resolve_ignores_case(config_dir):
    aliases.add("default", "Jacky", "OX1-DQRX5Z")
    assert aliases.resolve("default", "jacky") == "OX1-DQRX5Z"
    assert aliases.resolve("default", "JACKY") == "OX1-DQRX5Z"


def test_resolve_is_none_for_an_unknown_alias(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve("default", "horst") is None


def test_umlauts_survive_the_round_trip(config_dir):
    aliases.add("default", "rüdiger", "OX1-Y2HUZR")
    assert aliases.load("default") == {"rüdiger": "OX1-Y2HUZR"}
    assert aliases.resolve("default", "RÜDIGER") == "OX1-Y2HUZR"


def test_remove_deletes_the_alias(config_dir):
    aliases.add("default", "horst", "OX1-1T6570")
    assert aliases.remove("default", "horst") is True
    assert aliases.load("default") == {}


def test_remove_ignores_case(config_dir):
    aliases.add("default", "Horst", "OX1-1T6570")
    assert aliases.remove("default", "horst") is True
    assert aliases.load("default") == {}


def test_remove_reports_an_unknown_alias(config_dir):
    assert aliases.remove("default", "nobody") is False


def test_add_command_stores_the_alias(config_dir):
    result = runner.invoke(app, ["alias", "add", "ruedi", "OX1-Y2HUZR"])
    assert result.exit_code == 0
    assert aliases.load("default") == {"ruedi": "OX1-Y2HUZR"}
    assert "ruedi" in result.output
    assert "OX1-Y2HUZR" in result.output


def test_add_command_reports_the_replaced_target(config_dir):
    runner.invoke(app, ["alias", "add", "jacky", "OX1-DQRX5Z"])
    result = runner.invoke(app, ["alias", "add", "jacky", "OX1-ZZ0001"])
    assert result.exit_code == 0
    assert "OX1-DQRX5Z" in result.output
    assert aliases.load("default")["jacky"] == "OX1-ZZ0001"


def test_add_command_uses_the_active_profile(config_dir):
    runner.invoke(app, ["-c", "prod", "alias", "add", "horst", "OX1-1T6570"])
    assert aliases.load("prod") == {"horst": "OX1-1T6570"}
    assert aliases.load("default") == {}


def test_list_command_shows_every_alias(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    aliases.add("default", "jacky", "OX1-DQRX5Z")
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "ruedi" in output
    assert "OX1-Y2HUZR" in output
    assert "jacky" in output
    assert "OX1-DQRX5Z" in output


def test_list_command_without_aliases(config_dir):
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    assert "No aliases" in result.output


def test_list_command_json(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ruedi": "OX1-Y2HUZR"}


def test_list_command_json_without_aliases(config_dir):
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_rm_command_removes_the_alias(config_dir):
    aliases.add("default", "horst", "OX1-1T6570")
    result = runner.invoke(app, ["alias", "rm", "horst"])
    assert result.exit_code == 0
    assert aliases.load("default") == {}


def test_rm_command_reports_an_unknown_alias(config_dir):
    result = runner.invoke(app, ["alias", "rm", "nobody"])
    assert result.exit_code == 1
    assert "nobody" in result.output


def test_complete_device_suggests_aliases_of_the_active_profile(config_dir):
    aliases.add("prod", "ruedi", "OX1-Y2HUZR")
    aliases.add("prod", "horst", "OX1-1T6570")
    ctx = _completion_context("prod")
    assert aliases.complete_device(ctx, "") == ["horst", "ruedi"]
    assert aliases.complete_device(ctx, "r") == ["ruedi"]


def test_complete_device_falls_back_to_the_default_profile(config_dir):
    aliases.add("default", "jacky", "OX1-DQRX5Z")
    ctx = _completion_context(None)
    assert aliases.complete_device(ctx, "") == ["jacky"]


def _device_params(command, path=()):
    """Yield ``(path, param)`` for every parameter named ``device`` in the tree."""
    if hasattr(command, "commands"):
        for name, sub in command.commands.items():
            yield from _device_params(sub, (*path, name))
        return
    for param in command.params:
        if param.name == "device":
            yield path, param


def test_every_device_parameter_completes_aliases(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    root = typer.main.get_command(app)
    found = list(_device_params(root))
    assert len(found) >= 10
    for path, param in found:
        completions = param.shell_complete(click.Context(root), "r")
        assert [c.value for c in completions] == ["ruedi"], " ".join(path)
