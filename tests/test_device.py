import sys
from unittest.mock import MagicMock, patch

DEVICE_UUID = "11111111-1111-1111-1111-111111111111"
PROFILE_UUID = "22222222-2222-2222-2222-222222222222"


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
