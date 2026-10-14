"""CLI smoke tests via typer's CliRunner."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from gnosk.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate_config(tmp_path, monkeypatch):
    """Keep the first-run marker out of the user's real home dir."""
    monkeypatch.setenv("GNOSK_CONFIG_DIR", str(tmp_path / "gnosk-cfg"))


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "gnosk" in result.stdout


def test_scan_reports_findings(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("email: alice@example.com")
    result = runner.invoke(app, ["scan", str(tmp_path)])
    assert result.exit_code == 0
    assert "email" in result.stdout
    assert "Found" in result.stdout


def test_scan_missing_path_exits_nonzero() -> None:
    result = runner.invoke(app, ["scan", "/nonexistent/path/xyz"])
    assert result.exit_code == 1



def test_report_writes_markdown_and_json(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.py").write_text('EMAIL = "admin@client.com"\n')
    out_md = tmp_path / "inv.md"
    result = runner.invoke(
        app, ["report", str(tmp_path), "--output", str(out_md)]
    )
    assert result.exit_code == 0, result.stdout
    assert out_md.exists()
    content = out_md.read_text()
    assert "# Gnosk Data Inventory" in content
    assert "admin@client.com" not in content  # redacted

    out_json = out_md.with_suffix(".json")
    assert out_json.exists()
    payload = json.loads(out_json.read_text())
    assert payload["project_path"] == str(tmp_path)
    assert len(payload["files"]) == 1


def test_report_missing_path_exits_nonzero(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report", "/nonexistent/xyz"])
    assert result.exit_code == 1


def test_scan_classify_flag_is_off_by_default(tmp_path: Path) -> None:
    """Without --classify, no model call should be attempted."""
    from gnosk import classifier

    called = {"n": 0}
    original = classifier.classify_findings

    def spy(*a, **k):
        called["n"] += 1
        return original(*a, **k)

    classifier.classify_findings = spy
    try:
        (tmp_path / "x.txt").write_text("email: a@b.com")
        result = runner.invoke(app, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert called["n"] == 0
    finally:
        classifier.classify_findings = original
