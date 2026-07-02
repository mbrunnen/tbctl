import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tbctl.cli import app
from tbctl.commands import telemetry

runner = CliRunner()

DEVICE = "11111111-2222-3333-4444-555555555555"


def _invoke(args, api):
    with (
        patch("tbctl.commands.telemetry.telemetry_api", return_value=api),
        patch("tbctl.commands.telemetry.resolve_device_id", return_value=DEVICE),
    ):
        return runner.invoke(app, args)


def test_keys():
    api = MagicMock()
    # endpoint returns a Python repr string, not JSON
    api.get_timeseries_keys.return_value = "['humidity', 'temperature']"

    result = _invoke(["telemetry", "keys", DEVICE], api)

    assert result.exit_code == 0
    assert result.output.splitlines() == ["humidity", "temperature"]
    api.get_timeseries_keys.assert_called_once_with("DEVICE", DEVICE)


def test_keys_empty():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "[]"

    result = _invoke(["telemetry", "keys", DEVICE], api)

    assert result.exit_code == 0
    assert "No time-series keys found" in result.output


def test_keys_json():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['temperature']"

    result = _invoke(["telemetry", "keys", DEVICE, "--json"], api)

    assert result.exit_code == 0
    assert json.loads(result.output) == ["temperature"]


def test_latest():
    api = MagicMock()
    api.get_latest_timeseries.return_value = (
        "{'temperature': [{'ts': 1700000000000, 'value': '21.5'}]}"
    )

    result = _invoke(["telemetry", "latest", DEVICE], api)

    assert result.exit_code == 0
    assert "temperature" in result.output
    assert "21.5" in result.output


def test_history():
    api = MagicMock()
    api.get_timeseries.return_value = (
        "{'temperature': ["
        "{'ts': 1700000000000, 'value': '21.5'}, "
        "{'ts': 1700000060000, 'value': '21.6'}]}"
    )

    result = _invoke(["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "1h"], api)

    assert result.exit_code == 0
    assert "21.5" in result.output
    assert "21.6" in result.output


def test_history_default_fetches_all_via_pagination():
    api = MagicMock()
    api.get_timeseries.return_value = "{'temperature': [{'ts': 1700000000000, 'value': '21.5'}]}"

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "30d"], api
    )

    assert result.exit_code == 0
    _, kwargs = api.get_timeseries.call_args
    # a page-sized request in ascending order, not the user-facing limit
    assert kwargs["limit"] == str(telemetry._PAGE_SIZE)
    assert kwargs["order_by"] == "ASC"


def test_history_paginates_until_short_page(monkeypatch):
    monkeypatch.setattr(telemetry, "_PAGE_SIZE", 2)
    api = MagicMock()
    api.get_timeseries.side_effect = [
        "{'log': [{'ts': 1000, 'value': 'aaa'}, {'ts': 2000, 'value': 'bbb'}]}",
        "{'log': [{'ts': 3000, 'value': 'ccc'}]}",
    ]

    result = _invoke(["telemetry", "history", DEVICE, "--keys", "log", "--last", "30d"], api)

    assert result.exit_code == 0
    assert api.get_timeseries.call_count == 2
    # the second page starts just after the last timestamp of the first page
    assert api.get_timeseries.call_args_list[1].args[2] == 2001
    for value in ("aaa", "bbb", "ccc"):
        assert value in result.output


def test_history_pagination_respects_desc_order(monkeypatch):
    monkeypatch.setattr(telemetry, "_PAGE_SIZE", 2)
    api = MagicMock()
    api.get_timeseries.side_effect = [
        "{'log': [{'ts': 1000, 'value': 'aaa'}, {'ts': 2000, 'value': 'bbb'}]}",
        "{'log': [{'ts': 3000, 'value': 'ccc'}]}",
    ]

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "log", "--last", "30d", "--order", "DESC"], api
    )

    assert result.exit_code == 0
    # pages are always fetched ascending, then reversed for display
    assert all(call.kwargs["order_by"] == "ASC" for call in api.get_timeseries.call_args_list)
    assert result.output.index("ccc") < result.output.index("aaa")


def test_history_explicit_limit_is_respected():
    api = MagicMock()
    api.get_timeseries.return_value = "{'temperature': [{'ts': 1700000000000, 'value': '21.5'}]}"

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "30d", "--limit", "50"],
        api,
    )

    assert result.exit_code == 0
    _, kwargs = api.get_timeseries.call_args
    assert kwargs["limit"] == "50"


def test_history_warns_when_limit_reached():
    api = MagicMock()
    api.get_timeseries.return_value = (
        "{'temperature': ["
        "{'ts': 1700000000000, 'value': '21.5'}, "
        "{'ts': 1700000060000, 'value': '21.6'}]}"
    )

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "30d", "--limit", "2"],
        api,
    )

    assert result.exit_code == 0
    assert "may be truncated" in result.output.lower()
    assert "2" in result.output


def test_history_no_warning_below_limit():
    api = MagicMock()
    api.get_timeseries.return_value = "{'temperature': [{'ts': 1700000000000, 'value': '21.5'}]}"

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "30d", "--limit", "50"],
        api,
    )

    assert result.exit_code == 0
    assert "may be truncated" not in result.output.lower()


def test_history_plot():
    api = MagicMock()
    api.get_timeseries.return_value = (
        "{'temperature': ["
        "{'ts': 1700000000000, 'value': '21.5'}, "
        "{'ts': 1700000060000, 'value': '21.6'}]}"
    )

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "1h", "--plot"],
        api,
    )

    assert result.exit_code == 0
    assert "temperature" in result.output


def test_history_plot_non_numeric():
    api = MagicMock()
    api.get_timeseries.return_value = "{'fw_version': [{'ts': 1700000000000, 'value': '0.12.0'}]}"

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "fw_version", "--last", "1h", "--plot"],
        api,
    )

    assert result.exit_code != 0
    assert "numeric" in result.output


def test_history_plot_and_json_conflict():
    api = MagicMock()

    result = _invoke(
        [
            "telemetry",
            "history",
            DEVICE,
            "--keys",
            "temperature",
            "--last",
            "1h",
            "--plot",
            "--json",
        ],
        api,
    )

    assert result.exit_code != 0
    assert "--plot and --json" in result.output
    api.get_timeseries.assert_not_called()


def test_history_requires_start_or_last():
    api = MagicMock()

    result = _invoke(["telemetry", "history", DEVICE, "--keys", "temperature"], api)

    assert result.exit_code != 0
    assert "Provide --start or --last" in result.output
    api.get_timeseries.assert_not_called()


def test_keys_api_exception():
    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_timeseries_keys.side_effect = ApiException(status=403, reason="Forbidden")

    result = _invoke(["telemetry", "keys", DEVICE], api)

    assert result.exit_code != 0
    assert "403" in result.output
