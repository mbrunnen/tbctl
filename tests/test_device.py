import json
import sys
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

DEVICE_UUID = "11111111-1111-1111-1111-111111111111"
PROFILE_UUID = "22222222-2222-2222-2222-222222222222"

runner = CliRunner()


def test_device_profile_api_builds_controller():
    from tb.commands import _client

    mock_config = MagicMock()
    mock_controller_class = MagicMock()
    mock_instance = MagicMock()
    mock_controller_class.return_value = mock_instance

    mock_module = MagicMock()
    mock_module.DeviceProfileControllerApi = mock_controller_class

    with patch.dict(sys.modules, {"tb_client.api.device_profile_controller_api": mock_module}):
        with patch.object(_client, "_configuration", return_value=mock_config):
            api = _client.device_profile_api("default")

    assert api is mock_instance
    mock_controller_class.assert_called_once_with(mock_config)


def _mock_device(
    device_id=DEVICE_UUID, name="sensor-1", dev_type="default", label="Lobby", created=0
):
    dev = MagicMock()
    dev.id.id = device_id
    dev.name = name
    dev.type = dev_type
    dev.label = label
    dev.created_time = created
    return dev


def test_list():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_tenant_devices.return_value.data = [_mock_device()]
    mock_api.get_tenant_devices.return_value.total_elements = 1

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "sensor-1" in result.output
    mock_api.get_tenant_devices.assert_called_once_with(
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
    mock_api.get_tenant_devices.return_value.data = []

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list"])

    assert result.exit_code == 0
    assert "No devices found" in result.output


def test_list_json():
    from tb.cli import app

    dev = _mock_device()
    dev.model_dump.return_value = {"name": "sensor-1"}
    mock_api = MagicMock()
    mock_api.get_tenant_devices.return_value.data = [dev]
    mock_api.get_tenant_devices.return_value.total_elements = 1

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "list", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [{"name": "sensor-1"}]


def test_get():
    from tb.cli import app

    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value.to_dict.return_value = {"name": "sensor-1"}

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "get", DEVICE_UUID])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"name": "sensor-1"}
    mock_api.get_device_by_id.assert_called_once_with(device_id=DEVICE_UUID)


def _mock_profile_info(name="custom", profile_id=PROFILE_UUID):
    info = MagicMock()
    info.name = name
    info.id.id = profile_id
    return info


def test_create_default_profile():
    from tb.cli import app

    profile_api = MagicMock()
    profile_api.get_default_device_profile_info.return_value.id.id = PROFILE_UUID
    device_api_mock = MagicMock()
    device_api_mock.save_device.return_value.id.id = DEVICE_UUID

    mock_device_class = MagicMock()
    mock_profile_id_class = MagicMock()
    device_instance = MagicMock()
    profile_id_instance = MagicMock()
    profile_id_instance.id = PROFILE_UUID
    mock_profile_id_class.return_value = profile_id_instance
    device_instance.device_profile_id = profile_id_instance
    device_instance.id = None
    device_instance.name = "sensor-1"
    mock_device_class.return_value = device_instance

    mock_device_module = MagicMock()
    mock_device_module.Device = mock_device_class
    mock_profile_id_module = MagicMock()
    mock_profile_id_module.DeviceProfileId = mock_profile_id_class

    with (
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
        patch("tb.commands.device.device_api", return_value=device_api_mock),
        patch.dict(
            sys.modules,
            {
                "tb_client": MagicMock(),
                "tb_client.models": MagicMock(),
                "tb_client.models.device": mock_device_module,
                "tb_client.models.device_profile_id": mock_profile_id_module,
            },
        ),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1"])

    assert result.exit_code == 0
    assert DEVICE_UUID in result.output
    sent = device_api_mock.save_device.call_args.kwargs["device"]
    assert sent.name == "sensor-1"
    assert mock_device_class.call_args.kwargs.get("id") is None
    assert str(sent.device_profile_id.id) == PROFILE_UUID


def test_create_named_profile():
    from tb.cli import app

    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [_mock_profile_info(name="custom")]
    device_api_mock = MagicMock()
    device_api_mock.save_device.return_value.id.id = DEVICE_UUID

    mock_device_class = MagicMock()
    mock_profile_id_class = MagicMock()
    device_instance = MagicMock()
    profile_id_instance = MagicMock()
    profile_id_instance.id = PROFILE_UUID
    mock_profile_id_class.return_value = profile_id_instance
    device_instance.device_profile_id = profile_id_instance
    mock_device_class.return_value = device_instance

    mock_device_module = MagicMock()
    mock_device_module.Device = mock_device_class
    mock_profile_id_module = MagicMock()
    mock_profile_id_module.DeviceProfileId = mock_profile_id_class

    with (
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
        patch("tb.commands.device.device_api", return_value=device_api_mock),
        patch.dict(
            sys.modules,
            {
                "tb_client": MagicMock(),
                "tb_client.models": MagicMock(),
                "tb_client.models.device": mock_device_module,
                "tb_client.models.device_profile_id": mock_profile_id_module,
            },
        ),
    ):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "custom"])

    assert result.exit_code == 0
    sent = device_api_mock.save_device.call_args.kwargs["device"]
    assert str(sent.device_profile_id.id) == PROFILE_UUID
    profile_api.get_device_profile_infos.assert_called_once_with(
        page_size=100, page=0, text_search="custom"
    )


def test_create_profile_not_found():
    from tb.cli import app

    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = []

    with patch("tb.commands.device.device_profile_api", return_value=profile_api):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "ghost"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_create_profile_ambiguous():
    from tb.cli import app

    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [
        _mock_profile_info(name="dup", profile_id=PROFILE_UUID),
        _mock_profile_info(name="dup", profile_id=DEVICE_UUID),
    ]

    with patch("tb.commands.device.device_profile_api", return_value=profile_api):
        result = runner.invoke(app, ["device", "create", "sensor-1", "--profile", "dup"])

    assert result.exit_code == 1
    assert "ambiguous" in result.output


def test_update_label_only():
    from tb.cli import app

    existing = MagicMock()
    existing.name = "sensor-1"
    existing.label = "old"
    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value = existing

    with patch("tb.commands.device.device_api", return_value=mock_api):
        result = runner.invoke(app, ["device", "update", DEVICE_UUID, "--label", "new"])

    assert result.exit_code == 0
    sent = mock_api.save_device.call_args.kwargs["device"]
    assert sent.label == "new"
    assert sent.name == "sensor-1"


def test_update_profile_resolves():
    from tb.cli import app

    existing = MagicMock()
    mock_api = MagicMock()
    mock_api.get_device_by_id.return_value = existing
    profile_api = MagicMock()
    profile_api.get_device_profile_infos.return_value.data = [_mock_profile_info(name="custom")]

    with (
        patch("tb.commands.device.device_api", return_value=mock_api),
        patch("tb.commands.device.device_profile_api", return_value=profile_api),
    ):
        result = runner.invoke(app, ["device", "update", DEVICE_UUID, "--profile", "custom"])

    assert result.exit_code == 0
    sent = mock_api.save_device.call_args.kwargs["device"]
    assert str(sent.device_profile_id.id) == PROFILE_UUID


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
