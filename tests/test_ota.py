from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tb.cli import app

runner = CliRunner()


def _mock_package(
    pkg_id="abc-123", title="Firmware 1.0", version="1.0", pkg_type="FIRMWARE", size=1024
):
    pkg = MagicMock()
    pkg.id.id = pkg_id
    pkg.title = title
    pkg.version = version
    pkg.type = pkg_type
    pkg.data_size = size
    return pkg


def test_list():
    mock_api = MagicMock()
    mock_api.get_ota_packages_v1.return_value.data = [_mock_package()]
    mock_api.get_ota_packages_v1.return_value.total_elements = 1

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "Firmware 1.0" in result.output


def test_list_empty():
    mock_api = MagicMock()
    mock_api.get_ota_packages_v1.return_value.data = []

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "list"])

    assert result.exit_code == 0
    assert "No OTA packages found" in result.output


def test_get():
    mock_api = MagicMock()
    mock_api.get_ota_package_info_by_id_v1.return_value.to_dict.return_value = {
        "title": "Firmware 1.0",
        "version": "1.0",
    }

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "get", "abc-123"])

    assert result.exit_code == 0
    mock_api.get_ota_package_info_by_id_v1.assert_called_once_with(ota_package_id="abc-123")


def test_delete():
    mock_api = MagicMock()

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123", "--yes"])

    assert result.exit_code == 0
    mock_api.delete_ota_package_v1.assert_called_once_with(ota_package_id="abc-123")
    assert "Deleted abc-123" in result.output


def test_delete_confirm():
    mock_api = MagicMock()

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123"], input="y\n")

    assert result.exit_code == 0
    mock_api.delete_ota_package_v1.assert_called_once_with(ota_package_id="abc-123")


def test_delete_abort():
    mock_api = MagicMock()

    with patch("tb.commands.ota._get_api", return_value=mock_api):
        result = runner.invoke(app, ["ota", "delete", "abc-123"], input="n\n")

    assert result.exit_code != 0
    mock_api.delete_ota_package_v1.assert_not_called()
