import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tbctl import config, keycache
from tbctl.cli import app

runner = CliRunner()

DEVICE = "11111111-2222-3333-4444-555555555555"

ATTRS = (
    "[{'lastUpdateTs': 1700000000000, 'key': 'active', 'value': True}, "
    "{'lastUpdateTs': 1700000001000, 'key': 'fwVersion', 'value': '1.2.3'}]"
)


def _invoke(args, api):
    with (
        patch("tbctl.commands.attributes.telemetry_api", return_value=api),
        patch("tbctl.commands.attributes.resolve_device_id", return_value=DEVICE),
    ):
        return runner.invoke(app, args)


def test_get_defaults_to_shared_scope():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code == 0
    assert "fwVersion" in result.output
    assert "1.2.3" in result.output
    assert "shared" in result.output
    api.get_attributes_by_scope.assert_called_once_with(
        "DEVICE", DEVICE, "SHARED_SCOPE", {}, keys=None
    )
    api.get_attributes.assert_not_called()


@pytest.mark.parametrize("scope", ["server", "Server", "server_scope", "SERVER_SCOPE"])
def test_get_short_scope_any_case(scope):
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE, "--scope", scope], api)

    assert result.exit_code == 0
    api.get_attributes_by_scope.assert_called_once_with(
        "DEVICE", DEVICE, "SERVER_SCOPE", {}, keys=None
    )


def test_get_invalid_scope():
    api = MagicMock()

    result = _invoke(["attributes", "get", DEVICE, "--scope", "BOGUS"], api)

    assert result.exit_code != 0
    assert "--scope must be one of client, server, shared" in result.output
    api.get_attributes.assert_not_called()
    api.get_attributes_by_scope.assert_not_called()


def test_get_json():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE, "--json"], api)

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["key"] == "active"


def test_get_empty():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = "[]"

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code == 0
    assert "No attributes found" in result.output


def test_get_api_exception():
    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_attributes_by_scope.side_effect = ApiException(status=404, reason="Not Found")

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code != 0
    assert "404" in result.output


def test_get_fills_cache_per_scope():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    _invoke(["attributes", "get", DEVICE, "--scope", "server"], api)

    assert keycache.lookup("default", DEVICE, "SERVER_SCOPE") == ["active", "fwVersion"]
    assert keycache.lookup("default", DEVICE, "SHARED_SCOPE") == []


def test_get_with_keys_adds_to_cache():
    keycache.record("default", DEVICE, DEVICE, "SHARED_SCOPE", ["other"], full=True)
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    _invoke(["attributes", "get", DEVICE, "--keys", "active,fwVersion"], api)

    assert keycache.lookup("default", DEVICE, "SHARED_SCOPE") == ["active", "fwVersion", "other"]


def test_get_dict_value_is_compact_json():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = [
        {"lastUpdateTs": 1700000000000, "key": "cfg", "value": {"a": 1}}
    ]

    result = _invoke(["attributes", "get", DEVICE], api)

    assert '{"a":1}' in result.output


def test_get_local_header(monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    monkeypatch.setattr("tbctl.commands._format.time.time", lambda: 1700000000.0)
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS
    try:
        result = _invoke(["attributes", "get", DEVICE, "--local"], api)
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()

    assert result.exit_code == 0
    assert "Last update (+01:00)" in result.output
    assert "2023-11-14 23:13:20" in result.output


def test_complete_scope():
    from tbctl.commands.attributes import complete_scope

    assert complete_scope("s") == ["server", "shared"]
    assert complete_scope("") == ["client", "server", "shared"]


def test_normalise_scope():
    from tbctl.commands.attributes import normalise_scope

    for value in ("server", "Server", "server_scope", "SERVER_SCOPE"):
        assert normalise_scope(value) == "SERVER_SCOPE"
    assert normalise_scope("shared") == "SHARED_SCOPE"
    assert normalise_scope("client") == "CLIENT_SCOPE"
    assert normalise_scope("bogus") is None


def test_keys_defaults_to_shared_and_fills_cache():
    api = MagicMock()
    api.get_attribute_keys_by_scope.return_value = "['b', 'a']"

    result = _invoke(["attributes", "keys", DEVICE], api)

    assert result.exit_code == 0
    assert result.output == "a\nb\n"
    api.get_attribute_keys_by_scope.assert_called_once_with("DEVICE", DEVICE, "SHARED_SCOPE")
    assert keycache.lookup("default", DEVICE, "SHARED_SCOPE") == ["a", "b"]


def test_keys_server_scope_json():
    api = MagicMock()
    api.get_attribute_keys_by_scope.return_value = "['iccid']"

    result = _invoke(["attributes", "keys", DEVICE, "--scope", "server", "--json"], api)

    assert json.loads(result.output) == ["iccid"]
    api.get_attribute_keys_by_scope.assert_called_once_with("DEVICE", DEVICE, "SERVER_SCOPE")


def test_keys_empty():
    api = MagicMock()
    api.get_attribute_keys_by_scope.return_value = "[]"

    result = _invoke(["attributes", "keys", DEVICE], api)

    assert "No shared attribute keys found." in result.output


def _profile(protected):
    config.save({"protected_attributes": protected})


def test_set_parses_json_values_into_one_call():
    api = MagicMock()
    pairs = ["n=21", "b=true", 'o={"a":1}', 's="21"', "t=hello", "e=a=b", "z="]

    result = _invoke(["attributes", "set", DEVICE, *pairs], api)

    assert result.exit_code == 0
    api.save_device_attributes.assert_called_once()
    device_id, scope, body = api.save_device_attributes.call_args.args
    assert (device_id, scope) == (DEVICE, "SHARED_SCOPE")
    assert json.loads(body) == {
        "n": 21,
        "b": True,
        "o": {"a": 1},
        "s": "21",
        "t": "hello",
        "e": "a=b",
        "z": "",
    }
    assert "shared" in result.output


def test_set_json_prints_written_dict():
    result = _invoke(["attributes", "set", DEVICE, "a=1", "a=2", "--json"], MagicMock())

    assert json.loads(result.output) == {"a": 2}


@pytest.mark.parametrize("pair", ["novalue", "=1"])
def test_set_rejects_bad_pair(pair):
    api = MagicMock()

    result = _invoke(["attributes", "set", DEVICE, pair], api)

    assert result.exit_code == 2
    assert "is not key=value" in result.output
    api.save_device_attributes.assert_not_called()


def test_set_refuses_client_scope():
    api = MagicMock()

    result = _invoke(["attributes", "set", DEVICE, "a=1", "--scope", "client"], api)

    assert result.exit_code == 1
    assert "use --scope server or shared" in result.output
    api.save_device_attributes.assert_not_called()


def test_set_refuses_protected_key_and_writes_nothing():
    _profile(["iccid", "imei"])
    api = MagicMock()

    result = _invoke(["attributes", "set", DEVICE, "a=1", "imei=2", "--scope", "server"], api)

    assert result.exit_code == 1
    assert "imei" in result.output
    api.save_device_attributes.assert_not_called()


def test_protected_attributes_as_string_is_one_key():
    _profile("iccid")
    api = MagicMock()

    assert _invoke(["attributes", "set", DEVICE, "i=1"], api).exit_code == 0
    assert _invoke(["attributes", "set", DEVICE, "iccid=1"], api).exit_code == 1
