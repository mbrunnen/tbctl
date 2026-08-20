import json

import click
import pytest
import typer
from typer.testing import CliRunner

import tbctl.aliases as aliases
import tbctl.config as cfg
from tbctl.cli import app
from tests.test_ota import _strip_ansi

runner = CliRunner()

UUID_A = "b1f2c3d4-1111-2222-3333-444455556666"
UUID_B = "c0ffee00-1111-2222-3333-444455556666"


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
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR")}


def test_add_keeps_url_and_token(config_dir):
    cfg.save({"url": "https://tb.example", "token": "secret"}, "prod")
    aliases.add("prod", "horst", "OX1-1T6570")
    data = cfg.load("prod")
    assert data["url"] == "https://tb.example"
    assert data["token"] == "secret"
    assert data["aliases"] == {"horst": {"name": "OX1-1T6570"}}


def test_add_overwrites_and_returns_previous_target(config_dir):
    aliases.add("default", "jacky", "OX1-DQRX5Z")
    previous = aliases.add("default", "jacky", "OX1-ZZ0001")
    assert previous == aliases.Alias("OX1-DQRX5Z")
    assert aliases.load("default")["jacky"] == aliases.Alias("OX1-ZZ0001")


def test_add_returns_none_for_a_new_alias(config_dir):
    assert aliases.add("default", "ruedi", "OX1-Y2HUZR") is None


def test_aliases_are_per_profile(config_dir):
    aliases.add("prod", "ruedi", "OX1-Y2HUZR")
    assert aliases.load("test") == {}


def test_resolve_returns_the_device_name(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve("default", "ruedi") == aliases.Alias("OX1-Y2HUZR")


def test_resolve_ignores_case(config_dir):
    aliases.add("default", "Jacky", "OX1-DQRX5Z")
    assert aliases.resolve("default", "jacky") == aliases.Alias("OX1-DQRX5Z")
    assert aliases.resolve("default", "JACKY") == aliases.Alias("OX1-DQRX5Z")


def test_resolve_is_none_for_an_unknown_alias(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    assert aliases.resolve("default", "horst") is None


def test_umlauts_survive_the_round_trip(config_dir):
    aliases.add("default", "rüdiger", "OX1-Y2HUZR")
    assert aliases.load("default") == {"rüdiger": aliases.Alias("OX1-Y2HUZR")}
    assert aliases.resolve("default", "RÜDIGER") == aliases.Alias("OX1-Y2HUZR")


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
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR")}
    assert "ruedi" in result.output
    assert "OX1-Y2HUZR" in result.output


def test_add_command_stores_the_uuid(config_dir):
    result = runner.invoke(app, ["alias", "add", "ruedi", "OX1-Y2HUZR", "--id", UUID_A])
    assert result.exit_code == 0
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR", UUID_A)}
    assert UUID_A in _strip_ansi(result.output)


def test_add_command_rejects_an_invalid_uuid(config_dir):
    result = runner.invoke(app, ["alias", "add", "ruedi", "OX1-Y2HUZR", "--id", "nope"])
    assert result.exit_code == 1
    assert "nope" in _strip_ansi(result.output)
    assert aliases.load("default") == {}


def test_add_command_reports_the_replaced_target(config_dir):
    runner.invoke(app, ["alias", "add", "jacky", "OX1-DQRX5Z"])
    result = runner.invoke(app, ["alias", "add", "jacky", "OX1-ZZ0001"])
    assert result.exit_code == 0
    assert "OX1-DQRX5Z" in result.output
    assert aliases.load("default")["jacky"] == aliases.Alias("OX1-ZZ0001")


def test_add_command_uses_the_active_profile(config_dir):
    runner.invoke(app, ["-c", "prod", "alias", "add", "horst", "OX1-1T6570"])
    assert aliases.load("prod") == {"horst": aliases.Alias("OX1-1T6570")}
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


def test_list_command_shows_the_uuid(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR", UUID_A)
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    output = _strip_ansi(result.output)
    assert "UUID" in output
    assert UUID_A in output


def test_list_command_omits_the_uuid_column_when_no_alias_has_one(config_dir):
    aliases.add("default", "horst", "OX1-1T6570")
    result = runner.invoke(app, ["alias", "list"])
    assert result.exit_code == 0
    assert "UUID" not in _strip_ansi(result.output)


def test_list_command_json(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ruedi": {"name": "OX1-Y2HUZR", "id": None}}


def test_list_command_json_includes_the_uuid(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR", UUID_A)
    result = runner.invoke(app, ["alias", "list", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"ruedi": {"name": "OX1-Y2HUZR", "id": UUID_A}}


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


def test_add_stores_a_name_and_a_uuid(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR", UUID_A)
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR", UUID_A)}


def test_add_without_a_uuid_omits_the_id_key(config_dir):
    aliases.add("default", "horst", "OX1-1T6570")
    assert aliases.load("default") == {"horst": aliases.Alias("OX1-1T6570")}
    assert cfg.load("default")["aliases"]["horst"] == {"name": "OX1-1T6570"}


def test_add_replaces_the_whole_entry(config_dir):
    aliases.add("default", "jacky", "OX1-DQRX5Z", UUID_A)
    aliases.add("default", "jacky", "OX1-ZZ0001")
    assert aliases.load("default")["jacky"] == aliases.Alias("OX1-ZZ0001")


def test_add_returns_the_replaced_entry(config_dir):
    aliases.add("default", "jacky", "OX1-DQRX5Z", UUID_A)
    previous = aliases.add("default", "jacky", "OX1-ZZ0001", UUID_B)
    assert previous == aliases.Alias("OX1-DQRX5Z", UUID_A)


def test_add_rejects_an_invalid_uuid(config_dir):
    with pytest.raises(ValueError):
        aliases.add("default", "ruedi", "OX1-Y2HUZR", "not-a-uuid")
    assert aliases.load("default") == {}


def test_resolve_returns_the_entry(config_dir):
    aliases.add("default", "ruedi", "OX1-Y2HUZR", UUID_A)
    assert aliases.resolve("default", "ruedi") == aliases.Alias("OX1-Y2HUZR", UUID_A)


def test_load_migrates_a_legacy_string_entry(config_dir):
    cfg.save({"aliases": {"ruedi": "OX1-Y2HUZR"}}, "default")
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR")}
    assert cfg.load("default")["aliases"] == {"ruedi": {"name": "OX1-Y2HUZR"}}


def test_load_migrates_a_legacy_uuid_target_into_the_name(config_dir):
    cfg.save({"aliases": {"ruedi": UUID_A}}, "default")
    assert aliases.load("default") == {"ruedi": aliases.Alias(UUID_A)}


def test_migration_keeps_url_and_token(config_dir):
    cfg.save(
        {"url": "https://tb.example", "token": "secret", "aliases": {"ruedi": "OX1-Y2HUZR"}},
        "prod",
    )
    aliases.load("prod")
    data = cfg.load("prod")
    assert data["url"] == "https://tb.example"
    assert data["token"] == "secret"
    assert data["aliases"] == {"ruedi": {"name": "OX1-Y2HUZR"}}


def test_load_does_not_rewrite_an_already_migrated_file(config_dir, monkeypatch):
    aliases.add("default", "ruedi", "OX1-Y2HUZR", UUID_A)

    def refuse(*args, **kwargs):
        raise AssertionError("load must not write an already migrated file")

    monkeypatch.setattr(cfg, "save", refuse)
    assert aliases.load("default") == {"ruedi": aliases.Alias("OX1-Y2HUZR", UUID_A)}
