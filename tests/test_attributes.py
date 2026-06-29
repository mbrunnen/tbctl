import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

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


def test_get_all_scopes():
    api = MagicMock()
    api.get_attributes.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code == 0
    assert "fwVersion" in result.output
    assert "1.2.3" in result.output
    api.get_attributes.assert_called_once_with("DEVICE", DEVICE, {}, keys=None)


def test_get_by_scope():
    api = MagicMock()
    api.get_attributes_by_scope.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE, "--scope", "SERVER_SCOPE"], api)

    assert result.exit_code == 0
    api.get_attributes_by_scope.assert_called_once_with(
        "DEVICE", DEVICE, "SERVER_SCOPE", {}, keys=None
    )


def test_get_invalid_scope():
    api = MagicMock()

    result = _invoke(["attributes", "get", DEVICE, "--scope", "BOGUS"], api)

    assert result.exit_code != 0
    assert "--scope must be one of" in result.output
    api.get_attributes.assert_not_called()
    api.get_attributes_by_scope.assert_not_called()


def test_get_json():
    api = MagicMock()
    api.get_attributes.return_value = ATTRS

    result = _invoke(["attributes", "get", DEVICE, "--json"], api)

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["key"] == "active"


def test_get_empty():
    api = MagicMock()
    api.get_attributes.return_value = "[]"

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code == 0
    assert "No attributes found" in result.output


def test_get_api_exception():
    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_attributes.side_effect = ApiException(status=404, reason="Not Found")

    result = _invoke(["attributes", "get", DEVICE], api)

    assert result.exit_code != 0
    assert "404" in result.output
