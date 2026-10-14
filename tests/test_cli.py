"""CLI smoke tests via typer's CliRunner."""

from pathlib import Path

from typer.testing import CliRunner

from vaultscan.cli import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "vaultscan" in result.stdout


def test_scan_reports_findings(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("email: alice@example.com")
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "email" in result.stdout
    assert "Found" in result.stdout


def test_scan_missing_path_exits_nonzero() -> None:
    result = runner.invoke(app, ["scan", "/nonexistent/path/xyz"])
    assert result.exit_code == 1
