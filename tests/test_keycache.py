import stat

import click
import pytest
import typer

import tbctl.aliases as aliases
from tbctl import config, keycache
from tbctl.cli import app

UUID = "11111111-2222-3333-4444-555555555555"


def _ctx(command, params, profile=None, group="telemetry"):
    """Build a Click context tree as shell completion sees it for ``<group> <command>``."""
    root = typer.main.get_command(app)
    root_ctx = click.Context(root)
    root_ctx.params = {"config": profile} if profile else {}
    group_ctx = click.Context(root.commands[group], parent=root_ctx)
    ctx = click.Context(group_ctx.command.commands[command], parent=group_ctx)
    ctx.params = params
    return ctx


def test_record_and_lookup_by_uuid_and_name():
    keycache.record("p", "dev1", UUID, keycache.TIMESERIES, ["b", "a"], full=True)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == ["a", "b"]
    assert keycache.lookup("p", "dev1", keycache.TIMESERIES) == ["a", "b"]


def test_partial_record_merges():
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a"], full=True)
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["b", "a"], full=False)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == ["a", "b"]


def test_full_record_replaces():
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a", "b"], full=True)
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["c"], full=True)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == ["c"]


def test_scopes_are_separate():
    keycache.record("p", UUID, UUID, "SHARED_SCOPE", ["x"], full=True)
    assert keycache.lookup("p", UUID, "SERVER_SCOPE") == []


def test_profiles_are_separate():
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup("q", UUID, keycache.TIMESERIES) == []


def test_file_is_private():
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a"], full=True)
    path = keycache.CACHE_DIR / "p" / "keys.json"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_corrupt_file_is_ignored():
    path = keycache.CACHE_DIR / "p" / "keys.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == []
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == ["a"]


def test_unknown_device_completes_nothing():
    ctx = _ctx("latest", {"device": "nobody"})
    assert keycache.complete_timeseries_keys(ctx, "") == []


def test_complete_without_device_completes_nothing():
    assert keycache.complete_timeseries_keys(_ctx("latest", {}), "") == []


def test_complete_timeseries_keys():
    keycache.record("default", "dev1", UUID, keycache.TIMESERIES, ["rsrp", "soc"], full=True)
    ctx = _ctx("latest", {"device": "dev1"})
    assert keycache.complete_timeseries_keys(ctx, "r") == ["rsrp"]


def test_complete_comma_list():
    keys = ["humidity", "temp", "temp_max"]
    keycache.record("default", "dev1", UUID, keycache.TIMESERIES, keys, full=True)
    ctx = _ctx("latest", {"device": "dev1"})
    assert keycache.complete_timeseries_keys(ctx, "temp,") == ["temp,humidity", "temp,temp_max"]
    assert keycache.complete_timeseries_keys(ctx, "temp,hu") == ["temp,humidity"]


def test_complete_attribute_keys_uses_scope():
    keycache.record("default", "dev1", UUID, "SERVER_SCOPE", ["srv"], full=True)
    keycache.record("default", "dev1", UUID, "SHARED_SCOPE", ["shr"], full=True)
    assert keycache.complete_attribute_keys(
        _ctx("latest", {"device": "dev1", "scope": "server"}), ""
    ) == ["srv"]
    assert keycache.complete_attribute_keys(_ctx("latest", {"device": "dev1"}), "") == ["shr"]
    assert (
        keycache.complete_attribute_keys(_ctx("latest", {"device": "dev1", "scope": "x"}), "") == []
    )


def test_completion_follows_the_profile_flag():
    keycache.record("prod", "dev1", UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    assert keycache.complete_timeseries_keys(_ctx("latest", {"device": "dev1"}, "prod"), "") == [
        "rsrp"
    ]
    assert keycache.complete_timeseries_keys(_ctx("latest", {"device": "dev1"}), "") == []


@pytest.mark.parametrize(
    "content", ['{"names": []}', '{"devices": []}', '{"devices": {"%s": []}}' % UUID]
)
def test_wrong_structure_is_ignored_and_repaired(content):
    path = keycache.CACHE_DIR / "p" / "keys.json"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == []
    keycache.record("p", "dev1", UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup("p", "dev1", keycache.TIMESERIES) == ["a"]


def test_unusable_cache_dir_is_ignored():
    keycache.CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    keycache.CACHE_DIR.write_text("not a directory")
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup("p", UUID, keycache.TIMESERIES) == []


def test_lookup_resolves_alias_locally():
    aliases.add("p", "ruedi", "OX1-Y2HUZR", UUID)
    keycache.record("p", UUID, UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    assert keycache.lookup("p", "ruedi", keycache.TIMESERIES) == ["rsrp"]
    assert keycache.lookup("p", "RUEDI", keycache.TIMESERIES) == ["rsrp"]


def test_alias_by_name_resolves_through_the_device_name():
    aliases.add("p", "ruedi", "OX1-Y2HUZR")
    keycache.record("p", "OX1-Y2HUZR", UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    assert keycache.lookup("p", "ruedi", keycache.TIMESERIES) == ["rsrp"]


def test_complete_writable_keys_drops_protected():
    config.save({"protected_attributes": ["iccid"]})
    keycache.record("default", "dev1", UUID, "SERVER_SCOPE", ["iccid", "mode"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "scope": "server", "keys": None}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == ["mode"]


def test_complete_writable_keys_skips_given():
    keycache.record("default", "dev1", UUID, "SHARED_SCOPE", ["a", "b"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "keys": ("a",)}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == ["b"]


@pytest.mark.parametrize("given", [[("a", 1)], ["a=1"]])
def test_complete_writable_pairs_adds_equals_and_skips_given(given):
    keycache.record("default", "dev1", UUID, "SHARED_SCOPE", ["a", "b"], full=True)
    ctx = _ctx("set", {"device": "dev1", "pairs": given}, group="attributes")
    assert keycache.complete_writable_pairs(ctx, "") == ["b="]


def test_complete_writable_keys_client_scope_is_empty():
    keycache.record("default", "dev1", UUID, "CLIENT_SCOPE", ["a"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "scope": "client"}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == []
