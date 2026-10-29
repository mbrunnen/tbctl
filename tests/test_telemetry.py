import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from tbctl import keycache
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


NOW_MS = 1_700_000_000_000
DAY_MS = 86_400_000


def test_history_defaults_to_all_keys_last_24h(monkeypatch):
    monkeypatch.setattr(telemetry, "_now_ms", lambda: NOW_MS)
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['rsrp', 'soc']"
    api.get_timeseries.return_value = "{}"

    result = _invoke(["telemetry", "history", DEVICE], api)

    assert result.exit_code == 0
    assert [c.kwargs["keys"] for c in api.get_timeseries.call_args_list] == ["rsrp", "soc"]
    args, _ = api.get_timeseries.call_args
    assert args[2] == NOW_MS - DAY_MS
    assert args[3] == NOW_MS


def test_history_end_alone_spans_the_day_before():
    api = MagicMock()
    api.get_timeseries.return_value = "{}"

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--end", str(NOW_MS)], api
    )

    assert result.exit_code == 0
    args, _ = api.get_timeseries.call_args
    assert args[2] == NOW_MS - DAY_MS
    assert args[3] == NOW_MS


def test_history_device_without_keys():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "[]"

    result = _invoke(["telemetry", "history", DEVICE], api)

    assert result.exit_code == 0
    assert "No telemetry found in the given range." in result.output
    api.get_timeseries.assert_not_called()


def test_history_last_count_without_keys_uses_all_keys():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['rsrp', 'soc']"
    api.get_timeseries.return_value = "{}"

    result = _invoke(["telemetry", "history", DEVICE, "--last", "20"], api)

    assert result.exit_code == 0
    api.get_timeseries.assert_called_once()
    assert api.get_timeseries.call_args.kwargs["keys"] == "rsrp,soc"


def test_keys_fills_cache():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['humidity', 'temperature']"

    _invoke(["telemetry", "keys", DEVICE], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == ["humidity", "temperature"]


def test_keys_cache_is_indexed_by_the_typed_name():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['rsrp']"

    _invoke(["telemetry", "keys", "OX1DEV-FOGMAZ"], api)

    assert keycache.lookup("default", "OX1DEV-FOGMAZ", keycache.TIMESERIES) == ["rsrp"]


def test_history_without_keys_replaces_cache():
    keycache.record("default", DEVICE, DEVICE, keycache.TIMESERIES, ["gone"], full=True)
    api = MagicMock()
    api.get_timeseries_keys.return_value = "['rsrp']"
    api.get_timeseries.return_value = "{}"

    _invoke(["telemetry", "history", DEVICE], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == ["rsrp"]


def test_history_with_keys_adds_to_cache():
    keycache.record("default", DEVICE, DEVICE, keycache.TIMESERIES, ["a"], full=True)
    api = MagicMock()
    api.get_timeseries.return_value = "{'temperature': [{'ts': 1700000000000, 'value': '21.5'}]}"

    _invoke(["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "1h"], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == ["a", "temperature"]


def test_latest_without_keys_replaces_cache():
    keycache.record("default", DEVICE, DEVICE, keycache.TIMESERIES, ["gone"], full=True)
    api = MagicMock()
    api.get_latest_timeseries.return_value = "{'soc': [{'ts': 1700000000000, 'value': '18'}]}"

    _invoke(["telemetry", "latest", DEVICE], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == ["soc"]


def test_latest_with_keys_adds_to_cache():
    keycache.record("default", DEVICE, DEVICE, keycache.TIMESERIES, ["a"], full=True)
    api = MagicMock()
    api.get_latest_timeseries.return_value = "{'soc': [{'ts': 1700000000000, 'value': '18'}]}"

    _invoke(["telemetry", "latest", DEVICE, "--keys", "soc"], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == ["a", "soc"]


def test_failed_call_writes_no_cache():
    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_timeseries_keys.side_effect = ApiException(status=403, reason="Forbidden")

    _invoke(["telemetry", "keys", DEVICE], api)

    assert keycache.lookup("default", DEVICE, keycache.TIMESERIES) == []


_TWO_POINTS_DESC = (
    "{'temperature': ["
    "{'ts': 1700000060000, 'value': '21.6'}, "
    "{'ts': 1700000000000, 'value': '21.5'}]}"
)


def test_history_last_without_unit_fetches_the_newest_points():
    api = MagicMock()
    api.get_timeseries.return_value = _TWO_POINTS_DESC

    result = _invoke(["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "20"], api)

    assert result.exit_code == 0
    args, kwargs = api.get_timeseries.call_args
    # the whole series is in scope; the count alone bounds the result
    assert args[2] == 0
    assert kwargs["limit"] == "20"
    assert kwargs["order_by"] == "DESC"
    assert "may be truncated" not in result.output.lower()
    # fetched newest-first, displayed oldest-first like every other window
    assert result.output.index("21.5") < result.output.index("21.6")


def test_history_last_without_unit_respects_desc_order():
    api = MagicMock()
    api.get_timeseries.return_value = _TWO_POINTS_DESC

    result = _invoke(
        [
            "telemetry",
            "history",
            DEVICE,
            "--keys",
            "temperature",
            "--last",
            "20",
            "--order",
            "DESC",
        ],
        api,
    )

    assert result.exit_code == 0
    assert result.output.index("21.6") < result.output.index("21.5")


def test_history_last_count_rejects_limit():
    api = MagicMock()

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "20", "--limit", "5"],
        api,
    )

    assert result.exit_code != 0
    assert "cannot be combined" in result.output
    api.get_timeseries.assert_not_called()


def test_history_last_count_rejects_agg():
    api = MagicMock()

    result = _invoke(
        ["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "20", "--agg", "AVG"],
        api,
    )

    assert result.exit_code != 0
    assert "cannot be combined" in result.output
    api.get_timeseries.assert_not_called()


def test_history_last_count_rejects_zero():
    api = MagicMock()

    result = _invoke(["telemetry", "history", DEVICE, "--keys", "temperature", "--last", "0"], api)

    assert result.exit_code != 0
    assert "positive count" in result.output
    api.get_timeseries.assert_not_called()


def test_keys_api_exception():
    from tb_client.exceptions import ApiException

    api = MagicMock()
    api.get_timeseries_keys.side_effect = ApiException(status=403, reason="Forbidden")

    result = _invoke(["telemetry", "keys", DEVICE], api)

    assert result.exit_code != 0
    assert "403" in result.output


def test_history_json_device_without_keys():
    api = MagicMock()
    api.get_timeseries_keys.return_value = "[]"

    result = _invoke(["telemetry", "history", DEVICE, "--json"], api)

    assert result.exit_code == 0
    assert json.loads(result.output) == {}
