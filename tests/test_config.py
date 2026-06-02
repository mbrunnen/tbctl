import tomllib

from typer.testing import CliRunner

from tb.cli import app

runner = CliRunner()


def test_set_url(config_path):
    result = runner.invoke(app, ["config", "set-url", "https://example.com"])
    assert result.exit_code == 0
    with open(config_path, "rb") as f:
        assert tomllib.load(f)["url"] == "https://example.com"


def test_set_token(config_path):
    result = runner.invoke(app, ["config", "set-token", "tb_abc123"])
    assert result.exit_code == 0
    with open(config_path, "rb") as f:
        assert tomllib.load(f)["token"] == "tb_abc123"


def test_show_empty(config_path):
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "No configuration found" in result.output


def test_show(config_path):
    runner.invoke(app, ["config", "set-url", "https://example.com"])
    runner.invoke(app, ["config", "set-token", "tb_abc123"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "https://example.com" in result.output
    assert "tb_abc123" in result.output
