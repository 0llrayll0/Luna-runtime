from typer.testing import CliRunner

from luna.cli.main import app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_cli_doctor():
    runner = CliRunner()
    result = runner.invoke(app, ["doctor"])
    # may fail due config but should not crash unhandled
    assert result.exit_code in (0, 1)


def test_cli_config():
    runner = CliRunner()
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0


def test_cli_agent_list():
    runner = CliRunner()
    result = runner.invoke(app, ["agent", "list"])
    assert result.exit_code == 0


def test_cli_provider_add_invalid():
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "add", "x", "not-a-url"])
    assert result.exit_code != 0


def test_cli_provider_add_valid():
    runner = CliRunner()
    result = runner.invoke(app, ["provider", "add", "local", "http://localhost:11434"])
    assert result.exit_code == 0
