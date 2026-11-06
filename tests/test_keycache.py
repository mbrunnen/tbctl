import stat

import click
import pytest
import typer

import tbctl.aliases as aliases
from tbctl import config, keycache
from tbctl.cli import app
from tests.conftest import context_for, second_context

USER = "me@example.com"
CACHE_KEY = "me%40example.com%40tb.example.com"


def _logged_in(context, user=USER):
    """Name the context's user in its config file, which keys the cache."""
    doc = config.read(context.file)
    doc["contexts"][context.name]["user"] = user
    config.write(context.file, doc)
    return context


UUID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def _context(config_dir):
    global C
    C = _logged_in(config.resolve())


def _ctx(command, params, context=None, group="telemetry"):
    """Build a Click context tree as shell completion sees it for ``<group> <command>``."""
    root = typer.main.get_command(app)
    root_ctx = click.Context(root)
    root_ctx.params = {"context": context} if context else {}
    group_ctx = click.Context(root.commands[group], parent=root_ctx)
    ctx = click.Context(group_ctx.command.commands[command], parent=group_ctx)
    ctx.params = params
    return ctx


def test_record_and_lookup_by_uuid_and_name():
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, ["b", "a"], full=True)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == ["a", "b"]
    assert keycache.lookup(C, "dev1", keycache.TIMESERIES) == ["a", "b"]


def test_partial_record_merges():
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    keycache.record(C, UUID, keycache.TIMESERIES, ["b", "a"], full=False)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == ["a", "b"]


def test_full_record_replaces():
    keycache.record(C, UUID, keycache.TIMESERIES, ["a", "b"], full=True)
    keycache.record(C, UUID, keycache.TIMESERIES, ["c"], full=True)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == ["c"]


def test_scopes_are_separate():
    keycache.record(C, UUID, "SHARED_SCOPE", ["x"], full=True)
    assert keycache.lookup(C, UUID, "SERVER_SCOPE") == []


def test_contexts_are_separate(config_dir):
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    other = _logged_in(second_context(config_dir))
    assert keycache.lookup(other, UUID, keycache.TIMESERIES) == []


def test_file_is_private():
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    path = keycache.CACHE_DIR / CACHE_KEY / "keys.json"
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_corrupt_file_is_ignored():
    path = keycache.CACHE_DIR / CACHE_KEY / "keys.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == []
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == ["a"]


def test_unknown_device_completes_nothing():
    ctx = _ctx("latest", {"device": "nobody"})
    assert keycache.complete_timeseries_keys(ctx, "") == []


def test_complete_without_device_completes_nothing():
    assert keycache.complete_timeseries_keys(_ctx("latest", {}), "") == []


def test_complete_timeseries_keys():
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, ["rsrp", "soc"], full=True)
    ctx = _ctx("latest", {"device": "dev1"})
    assert keycache.complete_timeseries_keys(ctx, "r") == ["rsrp"]


def test_complete_comma_list():
    keys = ["humidity", "temp", "temp_max"]
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, keys, full=True)
    ctx = _ctx("latest", {"device": "dev1"})
    assert keycache.complete_timeseries_keys(ctx, "temp,") == ["temp,humidity", "temp,temp_max"]
    assert keycache.complete_timeseries_keys(ctx, "temp,hu") == ["temp,humidity"]


def test_complete_attribute_keys_uses_scope():
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "SERVER_SCOPE", ["srv"], full=True)
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "SHARED_SCOPE", ["shr"], full=True)
    assert keycache.complete_attribute_keys(
        _ctx("latest", {"device": "dev1", "scope": "server"}), ""
    ) == ["srv"]
    assert keycache.complete_attribute_keys(_ctx("latest", {"device": "dev1"}), "") == ["shr"]
    assert (
        keycache.complete_attribute_keys(_ctx("latest", {"device": "dev1", "scope": "x"}), "") == []
    )


def test_completion_follows_the_context_flag(config_dir):
    prod = _logged_in(second_context(config_dir))
    keycache.remember(prod, {"dev1": UUID})
    keycache.record(prod, UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    prod_ctx = _ctx("latest", {"device": "dev1"}, "prod")
    assert keycache.complete_timeseries_keys(prod_ctx, "") == ["rsrp"]
    assert keycache.complete_timeseries_keys(_ctx("latest", {"device": "dev1"}), "") == []


@pytest.mark.parametrize(
    "content", ['{"names": []}', '{"devices": []}', '{"devices": {"%s": []}}' % UUID]
)
def test_wrong_structure_is_ignored_and_repaired(content):
    path = keycache.CACHE_DIR / CACHE_KEY / "keys.json"
    path.parent.mkdir(parents=True)
    path.write_text(content)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == []
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(C, "dev1", keycache.TIMESERIES) == ["a"]


def test_unusable_cache_dir_is_ignored():
    keycache.CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    keycache.CACHE_DIR.write_text("not a directory")
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == []


def test_lookup_resolves_alias_locally():
    aliases.add(C, "ruedi", "DEVICE-A")
    keycache.remember(C, {"DEVICE-A": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    assert keycache.lookup(C, "ruedi", keycache.TIMESERIES) == ["rsrp"]
    assert keycache.lookup(C, "RUEDI", keycache.TIMESERIES) == ["rsrp"]


def test_alias_by_name_resolves_through_the_device_name():
    aliases.add(C, "ruedi", "DEVICE-A")
    keycache.remember(C, {"DEVICE-A": UUID})
    keycache.record(C, UUID, keycache.TIMESERIES, ["rsrp"], full=True)
    assert keycache.lookup(C, "ruedi", keycache.TIMESERIES) == ["rsrp"]


def test_complete_writable_keys_drops_protected():
    with open(C.file, "a") as f:
        f.write('protected_attributes = ["iccid"]\n')
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "SERVER_SCOPE", ["iccid", "mode"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "scope": "server", "keys": None}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == ["mode"]


def test_complete_writable_keys_skips_given():
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "SHARED_SCOPE", ["a", "b"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "keys": ("a",)}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == ["b"]


@pytest.mark.parametrize("given", [[("a", 1)], ["a=1"]])
def test_complete_writable_pairs_adds_equals_and_skips_given(given):
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "SHARED_SCOPE", ["a", "b"], full=True)
    ctx = _ctx("set", {"device": "dev1", "pairs": given}, group="attributes")
    assert keycache.complete_writable_pairs(ctx, "") == ["b="]


def test_complete_writable_keys_client_scope_is_empty():
    keycache.remember(C, {"dev1": UUID})
    keycache.record(C, UUID, "CLIENT_SCOPE", ["a"], full=True)
    ctx = _ctx("delete", {"device": "dev1", "scope": "client"}, group="attributes")
    assert keycache.complete_writable_keys(ctx, "") == []


def test_cache_is_keyed_by_user_and_host():
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert (keycache.CACHE_DIR / CACHE_KEY / "keys.json").exists()


def test_same_login_shares_the_cache_across_contexts(tmp_path):
    other = _logged_in(context_for(tmp_path / "x" / "o.toml", "other", "https://tb.example.com"))
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(other, UUID, keycache.TIMESERIES) == ["a"]


def test_other_user_on_the_same_host_has_its_own_cache(tmp_path):
    other = context_for(tmp_path / "x" / "o.toml", "other", "https://tb.example.com")
    _logged_in(other, "admin@example.com")
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(other, UUID, keycache.TIMESERIES) == []


def test_no_known_user_keeps_no_cache():
    doc = config.read(C.file)
    del doc["contexts"][C.name]["user"]
    config.write(C.file, doc)
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.lookup(C, UUID, keycache.TIMESERIES) == []
    assert not keycache.CACHE_DIR.exists()


def test_cache_user_comes_from_the_config(tmp_path):
    other = context_for(tmp_path / "x" / "o.toml", "other", "https://tb.example.com")
    with open(other.file, "a") as f:
        f.write('user = "me@example.com"\n')
    keycache.record(other, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert (keycache.CACHE_DIR / CACHE_KEY / "keys.json").exists()


def test_remember_and_device_id():
    keycache.remember(C, {"dev1": UUID})
    assert keycache.device_id(C, "dev1") == UUID
    assert keycache.device_id(C, "other") is None


def test_forget_drops_every_name_of_the_device():
    other = "99999999-2222-3333-4444-555555555555"
    keycache.remember(C, {"dev1": UUID, "old": UUID, "dev2": other})
    keycache.forget(C, UUID)
    assert keycache.device_names(C) == ["dev2"]


def test_device_names_sorted():
    keycache.remember(C, {"b": UUID, "a": UUID})
    assert keycache.device_names(C) == ["a", "b"]


def test_record_writes_no_names():
    keycache.record(C, UUID, keycache.TIMESERIES, ["a"], full=True)
    assert keycache.device_names(C) == []


def test_nothing_cached_without_user(config_dir):
    other = second_context(config_dir)
    keycache.remember(other, {"dev1": UUID})
    assert keycache.device_id(other, "dev1") is None
