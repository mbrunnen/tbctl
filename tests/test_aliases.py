import json

import click
import pytest
import typer
from typer.testing import CliRunner

import tbctl.aliases as aliases
import tbctl.config as cfg
from tbctl import keycache
from tbctl.cli import app
from tests.conftest import second_context
from tests.test_ota import _strip_ansi

runner = CliRunner()

UUID_A = "b1f2c3d4-1111-2222-3333-444455556666"
UUID_B = "c0ffee00-1111-2222-3333-444455556666"


def _completion_context(name):
    """Build a real Click context tree as the shell completion sees it."""
    root = typer.main.get_command(app)
    root_ctx = click.Context(root)
    root_ctx.params = {"context": name} if name else {}
    group_ctx = click.Context(root.commands["telemetry"], parent=root_ctx)
    return click.Context(group_ctx.command.commands["latest"], parent=group_ctx)


def test_load_is_empty_without_aliases(context):
    assert aliases.load(context) == {}


def test_add_is_readable_back(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    assert aliases.load(context) == {"ruedi": "OX1-Y2HUZR"}


def test_add_keeps_the_rest_of_the_context(context):
    aliases.add(context, "horst", "OX1-1T6570")
    assert cfg.table(context) == {
        "url": "https://tb.example.com",
        "user": "me@example.com",
        "default": True,
        "aliases": {"horst": {"name": "OX1-1T6570"}},
    }


def test_add_overwrites_and_returns_previous_target(context):
    aliases.add(context, "jacky", "OX1-DQRX5Z")
    previous = aliases.add(context, "jacky", "OX1-ZZ0001")
    assert previous == "OX1-DQRX5Z"
    assert aliases.load(context)["jacky"] == "OX1-ZZ0001"


def test_add_returns_none_for_a_new_alias(context):
    assert aliases.add(context, "ruedi", "OX1-Y2HUZR") is None


def test_aliases_are_per_context(context, config_dir):
    aliases.add(second_context(config_dir), "ruedi", "OX1-Y2HUZR")
    assert aliases.load(context) == {}


def test_resolve_returns_the_device_name(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve(context, "ruedi") == "OX1-Y2HUZR"


def test_resolve_ignores_case(context):
    aliases.add(context, "Jacky", "OX1-DQRX5Z")
    assert aliases.resolve(context, "jacky") == "OX1-DQRX5Z"
    assert aliases.resolve(context, "JACKY") == "OX1-DQRX5Z"


def test_resolve_is_none_for_an_unknown_alias(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve(context, "horst") is None


def test_umlauts_survive_the_round_trip(context):
    aliases.add(context, "rüdiger", "OX1-Y2HUZR")
    assert aliases.load(context) == {"rüdiger": "OX1-Y2HUZR"}
    assert aliases.resolve(context, "RÜDIGER") == "OX1-Y2HUZR"


def test_remove_deletes_the_alias(context):
    aliases.add(context, "horst", "OX1-1T6570")
    assert aliases.remove(context, "horst") is True
    assert aliases.load(context) == {}


def test_remove_ignores_case(context):
    aliases.add(context, "Horst", "OX1-1T6570")
    assert aliases.remove(context, "horst") is True
    assert aliases.load(context) == {}


def test_remove_reports_an_unknown_alias(context):
    assert aliases.remove(context, "nobody") is False


def test_add_command_stores_the_alias(context):
    result = runner.invoke(app, ["alias", "add", "ruedi", "OX1-Y2HUZR"])
    assert result.exit_code == 0
    assert aliases.load(context) == {"ruedi": "OX1-Y2HUZR"}
    assert "ruedi" in result.output
    assert "OX1-Y2HUZR" in result.output


def test_add_command_reports_the_replaced_target(context):
    runner.invoke(app, ["alias", "add", "jacky", "OX1-DQRX5Z"])
    result = runner.invoke(app, ["alias", "add", "jacky", "OX1-ZZ0001"])
    assert result.exit_code == 0
    assert "OX1-DQRX5Z" in result.output
    assert aliases.load(context)["jacky"] == "OX1-ZZ0001"


def test_add_command_uses_the_active_context(context, config_dir):
    prod = second_context(config_dir)
    runner.invoke(app, ["--context", "prod", "alias", "add", "horst", "OX1-1T6570"])
    assert aliases.load(prod) == {"horst": "OX1-1T6570"}
    assert aliases.load(context) == {}


def test_list_command_shows_every_alias(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    aliases.add(context, "jacky", "OX1-DQRX5Z")
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


def test_list_command_json(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ruedi": "OX1-Y2HUZR"}


def test_list_command_json_without_aliases(config_dir):
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_delete_command_removes_the_alias(context):
    aliases.add(context, "horst", "OX1-1T6570")
    result = runner.invoke(app, ["alias", "delete", "horst"])
    assert result.exit_code == 0
    assert aliases.load(context) == {}


def test_delete_command_reports_an_unknown_alias(config_dir):
    result = runner.invoke(app, ["alias", "delete", "nobody"])
    assert result.exit_code == 1
    assert "nobody" in result.output


def test_complete_device_suggests_aliases_of_the_active_context(config_dir):
    prod = second_context(config_dir)
    aliases.add(prod, "ruedi", "OX1-Y2HUZR")
    aliases.add(prod, "horst", "OX1-1T6570")
    ctx = _completion_context("prod")
    assert aliases.complete_device(ctx, "") == ["horst", "ruedi"]
    assert aliases.complete_device(ctx, "r") == ["ruedi"]


def test_complete_device_falls_back_to_the_default_context(context):
    aliases.add(context, "jacky", "OX1-DQRX5Z")
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


def test_every_device_parameter_completes_aliases(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    root = typer.main.get_command(app)
    found = list(_device_params(root))
    assert len(found) >= 10
    for path, param in found:
        completions = param.shell_complete(click.Context(root), "r")
        assert [c.value for c in completions] == ["ruedi"], " ".join(path)


def test_add_stores_only_the_name(context):
    aliases.add(context, "horst", "OX1-1T6570")
    assert cfg.table(context)["aliases"]["horst"] == {"name": "OX1-1T6570"}


def _with_stored_id(context):
    with open(context.file, "a") as f:
        f.write(f'[contexts.default.aliases]\nruedi = {{ name = "OX1-Y2HUZR", id = "{UUID_A}" }}\n')


def test_stored_id_is_ignored(context):
    _with_stored_id(context)
    assert aliases.resolve(context, "ruedi") == "OX1-Y2HUZR"


def test_add_drops_a_stored_id(context):
    _with_stored_id(context)
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    assert cfg.table(context)["aliases"]["ruedi"] == {"name": "OX1-Y2HUZR"}


def test_alias_add_has_no_id_option(context):
    result = runner.invoke(app, ["alias", "add", "ruedi", "OX1-Y2HUZR", "--id", UUID_A])
    assert result.exit_code != 0
    assert aliases.load(context) == {}


def test_add_returns_the_replaced_name(context):
    aliases.add(context, "jacky", "OX1-DQRX5Z")
    assert aliases.add(context, "jacky", "OX1-ZZ0001") == "OX1-DQRX5Z"


def test_load_does_not_write(context, monkeypatch):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    monkeypatch.setattr(cfg, "write", lambda *a, **k: pytest.fail("load must not write"))
    assert aliases.load(context) == {"ruedi": "OX1-Y2HUZR"}


def test_alias_add_keeps_comments(context):
    context.file.write_text("# servers\n" + context.file.read_text())
    aliases.add(context, "lab", "OXLC-1")
    assert context.file.read_text().startswith("# servers\n")
    assert aliases.resolve(context, "LAB") == "OXLC-1"


def test_complete_device_offers_aliases_and_cached_names(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    keycache.remember(context, {"OX1-Y2HUZR": UUID_A, "OX1-AAAAAA": UUID_B})
    ctx = _completion_context(None)
    assert aliases.complete_device(ctx, "") == ["OX1-AAAAAA", "OX1-Y2HUZR", "ruedi"]
    assert aliases.complete_device(ctx, "OX1-A") == ["OX1-AAAAAA"]


def test_complete_alias_offers_aliases_only(context):
    aliases.add(context, "ruedi", "OX1-Y2HUZR")
    keycache.remember(context, {"OX1-AAAAAA": UUID_B})
    assert aliases.complete_alias(_completion_context(None), "") == ["ruedi"]
