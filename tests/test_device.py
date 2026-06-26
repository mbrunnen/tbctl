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
