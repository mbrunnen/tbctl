import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

DEVICE_UUID = "11111111-1111-1111-1111-111111111111"
PROFILE_UUID = "22222222-2222-2222-2222-222222222222"

runner = CliRunner()


def _device_dict(device_id=DEVICE_UUID, name="sensor-1", dev_type="default", label="Lobby"):
    return {
        "id": {"id": device_id, "entityType": "DEVICE"},
        "name": name,
        "type": dev_type,
        "label": label,
        "createdTime": 0,
    }


def _raw_response(payload, status=200):
    resp = MagicMock()
    resp.status = status
    resp.data = json.dumps(payload).encode()
    return resp


def test_list():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices_without_preload_content.return_value = _raw_response(
        {"data": [_device_dict()], "totalElements": 1}
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "sensor-1" in result.output
    mock_api.get_tenant_devices_without_preload_content.assert_called_once_with(
        page_size=20,
        page=0,
        type=None,
        text_search=None,
        sort_property=None,
        sort_order=None,
    )


def test_list_empty():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices_without_preload_content.return_value = _raw_response(
        {"data": [], "totalElements": 0}
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "No devices found" in result.output


def test_list_json():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices_without_preload_content.return_value = _raw_response(
        {"data": [_device_dict()], "totalElements": 1}
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [_device_dict()]


def test_list_customer():
    from tb.cli import app

    customer = "d6b77b60-714f-11f1-ba38-655c002e257c"
    mock_api = MagicMock()
    mock_api.get_customer_devices_without_preload_content.return_value = _raw_response(
        {"data": [_device_dict()], "totalElements": 1}
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list", "--customer", customer])

    assert result.exit_code == 0
    assert "sensor-1" in result.output
    mock_api.get_customer_devices_without_preload_content.assert_called_once_with(
        customer_id=customer, page_size=20, page=0, type=None, text_search=None
    )


def test_list_with_token():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices_without_preload_content.return_value = _raw_response(
        {"data": [_device_dict()], "totalElements": 1}
    )
    mock_api.get_device_credentials_by_device_id.return_value.credentials_id = "TOK123"

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list", "--token", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output)[0]["accessToken"] == "TOK123"
    mock_api.get_device_credentials_by_device_id.assert_called_once_with(device_id=DEVICE_UUID)


def test_list_api_error():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices_without_preload_content.return_value = _raw_response(
        {"message": "forbidden"}, status=403
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 1
    assert "403" in result.output


def test_get():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_device_by_id_without_preload_content.return_value = _raw_response(
        {"name": "sensor-1"}
    )

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "get", DEVICE_UUID])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"name": "sensor-1"}
    mock_api.get_device_by_id_without_preload_content.assert_called_once_with(device_id=DEVICE_UUID)


def test_create_default_profile():
    from tb.cli import app

    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device.resolve_profile_id", return_value=PROFILE_UUID),
        patch(
            "tb.commands.device._save_device_raw", return_value={"id": {"id": DEVICE_UUID}}
        ) as save_raw,
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1"])

    assert result.exit_code == 0
    assert DEVICE_UUID in result.output
    body = save_raw.call_args.args[1]
    assert body["name"] == "sensor-1"
    assert "id" not in body
    assert body["deviceProfileId"]["id"] == PROFILE_UUID


def test_create_resolves_named_profile():
    from tb.cli import app

    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device.resolve_profile_id", return_value=PROFILE_UUID) as resolve,
        patch("tb.commands.device._save_device_raw", return_value={"id": {"id": DEVICE_UUID}}),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "custom"])

    assert result.exit_code == 0
    resolve.assert_called_once_with("default", "custom")


def test_resolve_profile_default():
    from tb.commands.device import resolve_profile_id

    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device._raw_get", return_value={"id": {"id": PROFILE_UUID}}),
    ):
        assert resolve_profile_id("test", "default") == PROFILE_UUID


def test_resolve_profile_named_exact_match():
    from tb.commands.device import resolve_profile_id

    page = {"data": [{"id": {"id": PROFILE_UUID}, "name": "custom"}]}
    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device._raw_get", return_value=page),
    ):
        assert resolve_profile_id("test", "custom") == PROFILE_UUID


def test_create_profile_not_found():
    from tb.cli import app

    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device._raw_get", return_value={"data": []}),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "ghost"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_create_profile_ambiguous():
    from tb.cli import app

    page = {
        "data": [
            {"id": {"id": PROFILE_UUID}, "name": "dup"},
            {"id": {"id": DEVICE_UUID}, "name": "dup"},
        ]
    }
    with (
        patch("tb.commands.device.device_api", return_value=MagicMock()),
        patch("tb.commands.device._raw_get", return_value=page),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "dup"])

    assert result.exit_code == 1
    assert "ambiguous" in result.output


def test_update_label_only():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_device_by_id_without_preload_content.return_value = _raw_response(
        {"id": {"id": DEVICE_UUID}, "name": "sensor-1", "label": "old"}
    )

    with (
        patch("tb.commands.device.device_api", return_value=mock_api),
        patch("tb.commands.device._save_device_raw") as save_raw,
    ):
        result = runner.invoke(app, ["device", "update", DEVICE_UUID, "--label", "new"])

    assert result.exit_code == 0
    sent = save_raw.call_args.args[1]
    assert sent["label"] == "new"
    assert sent["name"] == "sensor-1"


def test_update_profile_resolves():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_device_by_id_without_preload_content.return_value = _raw_response(
        {"id": {"id": DEVICE_UUID}, "name": "sensor-1"}
    )

    with (
        patch("tb.commands.device.device_api", return_value=mock_api),
        patch("tb.commands.device.resolve_profile_id", return_value=PROFILE_UUID),
        patch("tb.commands.device._save_device_raw") as save_raw,
    ):
        result = runner.invoke(app, ["device", "update", DEVICE_UUID, "--profile", "custom"])

    assert result.exit_code == 0
    sent = save_raw.call_args.args[1]
    assert sent["deviceProfileId"]["id"] == PROFILE_UUID


def test_delete_with_yes():
    from tb.cli import app

    mock_api = MagicMock()

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "delete", DEVICE_UUID, "--yes"])

    assert result.exit_code == 0
    mock_api.delete_device.assert_called_once_with(device_id=DEVICE_UUID)


def test_delete_confirm_aborts():
    from tb.cli import app

    mock_api = MagicMock()

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "delete", DEVICE_UUID], input="n\n")

    assert result.exit_code != 0
    mock_api.delete_device.assert_not_called()


def test_assign_to_customer():
    from tb.cli import app

    mock_api = MagicMock()
    customer = "d6b77b60-714f-11f1-ba38-655c002e257c"

    with patch("tb.commands.device.owner_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "assign", DEVICE_UUID, "--customer", customer])

    assert result.exit_code == 0
    assert customer in result.output
    mock_api.change_owner_to_customer.assert_called_once_with(
        owner_id=customer, entity_type="DEVICE", entity_id=DEVICE_UUID
    )


def test_assign_requires_customer():
    from tb.cli import app

    result = runner.invoke(app, ["device", "assign", DEVICE_UUID])

    assert result.exit_code != 0
