import time

import pytest

from tbctl.commands._format import clip, fmt_ts, fmt_value, ts_header


@pytest.fixture
def berlin(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_fmt_ts_utc():
    assert fmt_ts(1700000000000) == "2023-11-14 22:13:20"


def test_fmt_ts_none():
    assert fmt_ts(None) == "-"


def test_fmt_ts_local(berlin):
    assert fmt_ts(1700000000000, local=True) == "2023-11-14 23:13:20"


def test_ts_header_utc():
    assert ts_header("Timestamp", local=False) == "Timestamp (UTC)"


def test_ts_header_local(berlin, monkeypatch):
    monkeypatch.setattr("tbctl.commands._format.time.time", lambda: 1700000000.0)
    assert ts_header("Timestamp", local=True) == "Timestamp (+01:00)"


def test_fmt_value():
    assert fmt_value({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'
    assert fmt_value([1, 2]) == "[1,2]"
    assert fmt_value("21.5") == "21.5"
    assert fmt_value(True) == "True"
    assert fmt_value('{"x": 1}') == '{"x": 1}'


def test_clip():
    assert clip("a" * 40) == "a" * 40
    assert clip("a" * 41) == "a" * 39 + "…"
    assert len(clip("x" * 200)) == 40
