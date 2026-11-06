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
    aliases.add(context, "ruedi", "DEVICE-A")
    assert aliases.load(context) == {"ruedi": "DEVICE-A"}


def test_add_keeps_the_rest_of_the_context(context):
    aliases.add(context, "horst", "DEVICE-B")
    assert cfg.table(context) == {
        "url": "https://tb.example.com",
        "user": "me@example.com",
        "default": True,
        "aliases": {"horst": {"name": "DEVICE-B"}},
    }


def test_add_overwrites_and_returns_previous_target(context):
    aliases.add(context, "jacky", "DEVICE-C")
    previous = aliases.add(context, "jacky", "DEVICE-D")
    assert previous == "DEVICE-C"
    assert aliases.load(context)["jacky"] == "DEVICE-D"


def test_add_returns_none_for_a_new_alias(context):
    assert aliases.add(context, "ruedi", "DEVICE-A") is None


def test_aliases_are_per_context(context, config_dir):
    aliases.add(second_context(config_dir), "ruedi", "DEVICE-A")
    assert aliases.load(context) == {}


def test_resolve_returns_the_device_name(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    assert aliases.resolve(context, "ruedi") == "DEVICE-A"


def test_resolve_ignores_case(context):
    aliases.add(context, "Jacky", "DEVICE-C")
    assert aliases.resolve(context, "jacky") == "DEVICE-C"
    assert aliases.resolve(context, "JACKY") == "DEVICE-C"


def test_resolve_is_none_for_an_unknown_alias(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    assert aliases.resolve(context, "horst") is None


def test_umlauts_survive_the_round_trip(context):
    aliases.add(context, "rüdiger", "DEVICE-A")
    assert aliases.load(context) == {"rüdiger": "DEVICE-A"}
    assert aliases.resolve(context, "RÜDIGER") == "DEVICE-A"


def test_remove_deletes_the_alias(context):
    aliases.add(context, "horst", "DEVICE-B")
    assert aliases.remove(context, "horst") is True
    assert aliases.load(context) == {}


def test_remove_ignores_case(context):
    aliases.add(context, "Horst", "DEVICE-B")
    assert aliases.remove(context, "horst") is True
    assert aliases.load(context) == {}


def test_remove_reports_an_unknown_alias(context):
    assert aliases.remove(context, "nobody") is False


def test_add_command_stores_the_alias(context):
    result = runner.invoke(app, ["alias", "add", "ruedi", "DEVICE-A"])
    assert result.exit_code == 0
    assert aliases.load(context) == {"ruedi": "DEVICE-A"}
    assert "ruedi" in result.output
    assert "DEVICE-A" in result.output


def test_add_command_reports_the_replaced_target(context):
    runner.invoke(app, ["alias", "add", "jacky", "DEVICE-C"])
    result = runner.invoke(app, ["alias", "add", "jacky", "DEVICE-D"])
    assert result.exit_code == 0
    assert "DEVICE-C" in result.output
    assert aliases.load(context)["jacky"] == "DEVICE-D"


def test_add_command_uses_the_active_context(context, config_dir):
    prod = second_context(config_dir)
    runner.invoke(app, ["--context", "prod", "alias", "add", "horst", "DEVICE-B"])
    assert aliases.load(prod) == {"horst": "DEVICE-B"}
    assert aliases.load(context) == {}


def test_list_command_shows_every_alias(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    aliases.add(context, "jacky", "DEVICE-C")
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "ruedi" in output
    assert "DEVICE-A" in output
    assert "jacky" in output
    assert "DEVICE-C" in output


def test_list_command_without_aliases(config_dir):
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    assert "No aliases" in result.output


def test_list_command_json(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ruedi": "DEVICE-A"}


def test_list_command_json_without_aliases(config_dir):
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {}


def test_delete_command_removes_the_alias(context):
    aliases.add(context, "horst", "DEVICE-B")
    result = runner.invoke(app, ["alias", "delete", "horst"])
    assert result.exit_code == 0
    assert aliases.load(context) == {}


def test_delete_command_reports_an_unknown_alias(config_dir):
    result = runner.invoke(app, ["alias", "delete", "nobody"])
    assert result.exit_code == 1
    assert "nobody" in result.output


def test_complete_device_suggests_aliases_of_the_active_context(config_dir):
    prod = second_context(config_dir)
    aliases.add(prod, "ruedi", "DEVICE-A")
    aliases.add(prod, "horst", "DEVICE-B")
    ctx = _completion_context("prod")
    assert aliases.complete_device(ctx, "") == ["horst", "ruedi"]
    assert aliases.complete_device(ctx, "r") == ["ruedi"]


def test_complete_device_falls_back_to_the_default_context(context):
    aliases.add(context, "jacky", "DEVICE-C")
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
    aliases.add(context, "ruedi", "DEVICE-A")
    root = typer.main.get_command(app)
    found = list(_device_params(root))
    assert len(found) >= 10
    for path, param in found:
        completions = param.shell_complete(click.Context(root), "r")
        assert [c.value for c in completions] == ["ruedi"], " ".join(path)


def test_add_stores_only_the_name(context):
    aliases.add(context, "horst", "DEVICE-B")
    assert cfg.table(context)["aliases"]["horst"] == {"name": "DEVICE-B"}


def _with_stored_id(context):
    with open(context.file, "a") as f:
        f.write(f'[contexts.default.aliases]\nruedi = {{ name = "DEVICE-A", id = "{UUID_A}" }}\n')


def test_stored_id_is_ignored(context):
    _with_stored_id(context)
    assert aliases.resolve(context, "ruedi") == "DEVICE-A"


def test_add_drops_a_stored_id(context):
    _with_stored_id(context)
    aliases.add(context, "ruedi", "DEVICE-A")
    assert cfg.table(context)["aliases"]["ruedi"] == {"name": "DEVICE-A"}


def test_alias_add_has_no_id_option(context):
    result = runner.invoke(app, ["alias", "add", "ruedi", "DEVICE-A", "--id", UUID_A])
    assert result.exit_code != 0
    assert aliases.load(context) == {}


def test_add_returns_the_replaced_name(context):
    aliases.add(context, "jacky", "DEVICE-C")
    assert aliases.add(context, "jacky", "DEVICE-D") == "DEVICE-C"


def test_load_does_not_write(context, monkeypatch):
    aliases.add(context, "ruedi", "DEVICE-A")
    monkeypatch.setattr(cfg, "write", lambda *a, **k: pytest.fail("load must not write"))
    assert aliases.load(context) == {"ruedi": "DEVICE-A"}


def test_alias_add_keeps_comments(context):
    context.file.write_text("# servers\n" + context.file.read_text())
    aliases.add(context, "lab", "LAB-1")
    assert context.file.read_text().startswith("# servers\n")
    assert aliases.resolve(context, "LAB") == "LAB-1"


def test_complete_device_offers_aliases_and_cached_names(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    keycache.remember(context, {"DEVICE-A": UUID_A, "DEVICE-F": UUID_B})
    ctx = _completion_context(None)
    assert aliases.complete_device(ctx, "") == ["DEVICE-A", "DEVICE-F", "ruedi"]
    assert aliases.complete_device(ctx, "DEVICE-F") == ["DEVICE-F"]


def test_complete_alias_offers_aliases_only(context):
    aliases.add(context, "ruedi", "DEVICE-A")
    keycache.remember(context, {"DEVICE-F": UUID_B})
    assert aliases.complete_alias(_completion_context(None), "") == ["ruedi"]
