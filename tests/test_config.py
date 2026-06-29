import tomllib

from typer.testing import CliRunner

from tbctl.cli import app

runner = CliRunner()


def test_set_url(config_dir):
    result = runner.invoke(app, ["config", "set-url", "https://example.com"])
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://example.com"


def test_set_url_profile(config_dir):
    result = runner.invoke(
        app, ["-c", "staging", "config", "set-url", "https://staging.example.com"]
    )
    assert result.exit_code == 0
    with open(config_dir / "staging.toml", "rb") as f:
        assert tomllib.load(f)["url"] == "https://staging.example.com"


def test_set_token(config_dir):
    result = runner.invoke(app, ["config", "set-token", "tb_abc123"])
    assert result.exit_code == 0
    with open(config_dir / "default.toml", "rb") as f:
        assert tomllib.load(f)["token"] == "tb_abc123"


def test_show_empty(config_dir):
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "No configuration found" in result.output
    assert "default" in result.output


def test_show(config_dir):
    runner.invoke(app, ["config", "set-url", "https://example.com"])
    runner.invoke(app, ["config", "set-token", "tb_abc123"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "https://example.com" in result.output
    assert "tb_abc123" in result.output


def test_show_profile_isolation(config_dir):
    runner.invoke(app, ["-c", "prod", "config", "set-url", "https://prod.example.com"])
    result = runner.invoke(app, ["config", "show"])
    assert result.exit_code == 0
    assert "prod.example.com" not in result.output
