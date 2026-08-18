import json

import pytest

from tbctl.commands._client import (
    check_connection,
    handle_api_error,
    make_api_client,
    parse_response,
    resolve_device_id,
)


def _device_response(payload, status=200):
    from unittest.mock import MagicMock

    response = MagicMock()
    response.status = status
    response.data = json.dumps(payload).encode()
    return response


def test_api_client_strips_uri_template():
    from tb_client.configuration import Configuration

    client = make_api_client(Configuration(host="https://tb.example"))
    _, url, *_ = client.param_serialize(
        method="GET",
        resource_path="/api/foo{?keys,startTs}",
        query_params=[("keys", "temp")],
    )
    assert url == "https://tb.example/api/foo?keys=temp"


def test_parse_response_json():
    assert parse_response('{"a": 1}') == {"a": 1}


def test_parse_response_python_repr():
    assert parse_response("[{'key': 'temp', 'value': True}]") == [{"key": "temp", "value": True}]


def test_parse_response_already_parsed():
    value = [{"key": "temp"}]
    assert parse_response(value) is value


def test_resolve_device_id_uuid_passthrough():
    uuid = "11111111-2222-3333-4444-555555555555"
    assert resolve_device_id("default", uuid) == uuid


def test_resolve_device_id_name_lookup(monkeypatch):
    from unittest.mock import MagicMock

    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(
        {"id": {"id": "resolved-uuid"}}
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    assert resolve_device_id("default", "OX1-UQEUBW") == "resolved-uuid"
    api.get_tenant_device_without_preload_content.assert_called_once_with(device_name="OX1-UQEUBW")


def test_resolve_device_id_name_lookup_tolerates_default_transport(monkeypatch):
    from unittest.mock import MagicMock

    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(
        {
            "id": {"id": "resolved-uuid"},
            "deviceData": {"transportConfiguration": {"type": "DEFAULT"}},
        }
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    assert resolve_device_id("default", "OX1-UQEUBW") == "resolved-uuid"


def test_resolve_device_id_not_found(monkeypatch):
    from unittest.mock import MagicMock

    import typer

    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(None)
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    with pytest.raises(typer.Exit):
        resolve_device_id("default", "missing")


def test_check_connection_success(monkeypatch):
    monkeypatch.setattr(
        "tbctl.commands._client.raw_get",
        lambda api, path: {"email": "me@example.com"},
    )
    ok, message = check_connection("https://tb.example", "tok")
    assert ok is True
    assert message == "me@example.com"


def test_check_connection_failure(monkeypatch):
    from tb_client.exceptions import ApiException

    def _raise(api, path):
        raise ApiException(status=401, reason="Unauthorized")

    monkeypatch.setattr("tbctl.commands._client.raw_get", _raise)
    ok, message = check_connection("https://tb.example", "bad")
    assert ok is False
    assert "401" in message


def test_handle_api_error_shows_server_message(capsys):
    import typer

    from tb_client.exceptions import ApiException

    body = '{"status":400,"message":"Device already exists!","errorCode":31}'
    with pytest.raises(typer.Exit):
        handle_api_error(ApiException(status=400, body=body))
    err = capsys.readouterr().err
    assert "Device already exists!" in err
    assert "errorCode" not in err
    assert "{" not in err


def test_handle_api_error_falls_back_to_reason(capsys):
    import typer

    from tb_client.exceptions import ApiException

    with pytest.raises(typer.Exit):
        handle_api_error(ApiException(status=401, reason="Unauthorized"))
    err = capsys.readouterr().err
    assert "401" in err
    assert "Unauthorized" in err


def test_resolve_device_id_403_hint(monkeypatch, capsys):
    from unittest.mock import MagicMock

    import typer

    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_tenant_device_without_preload_content.side_effect = ApiException(
        status=403, reason="Forbidden"
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    with pytest.raises(typer.Exit):
        resolve_device_id("default", "OX1-UQEUBW")
    assert "pass the device UUID instead" in capsys.readouterr().err


def test_resolve_device_id_maps_an_alias_to_the_device_name(monkeypatch, config_dir):
    from unittest.mock import MagicMock

    import tbctl.aliases as aliases

    aliases.add("default", "ruedi", "OX1-Y2HUZR")
    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(
        {"id": {"id": "resolved-uuid"}}
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    assert resolve_device_id("default", "ruedi") == "resolved-uuid"
    api.get_tenant_device_without_preload_content.assert_called_once_with(device_name="OX1-Y2HUZR")


def test_resolve_device_id_prefers_an_alias_over_a_device_of_the_same_name(monkeypatch, config_dir):
    from unittest.mock import MagicMock

    import tbctl.aliases as aliases

    aliases.add("default", "horst", "OX1-1T6570")
    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(
        {"id": {"id": "resolved-uuid"}}
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    resolve_device_id("default", "horst")
    api.get_tenant_device_without_preload_content.assert_called_once_with(device_name="OX1-1T6570")


def test_resolve_device_id_takes_an_alias_pointing_at_a_uuid(monkeypatch, config_dir):
    from unittest.mock import MagicMock

    import tbctl.aliases as aliases

    uuid = "11111111-2222-3333-4444-555555555555"
    aliases.add("default", "jacky", uuid)
    api = MagicMock()
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    assert resolve_device_id("default", "jacky") == uuid
    api.get_tenant_device_without_preload_content.assert_not_called()


def test_resolve_device_id_uses_the_alias_table_of_the_active_profile(monkeypatch, config_dir):
    from unittest.mock import MagicMock

    import tbctl.aliases as aliases

    aliases.add("prod", "ruedi", "OX1-Y2HUZR")
    api = MagicMock()
    api.get_tenant_device_without_preload_content.return_value = _device_response(
        {"id": {"id": "resolved-uuid"}}
    )
    monkeypatch.setattr("tbctl.commands._client.device_api", lambda profile: api)

    resolve_device_id("test", "ruedi")
    api.get_tenant_device_without_preload_content.assert_called_once_with(device_name="ruedi")
