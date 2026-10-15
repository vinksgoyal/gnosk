"""Tests for the interactive REPL.

The Console is redirected to a StringIO, and `console.input` is
monkeypatched to feed commands from a scripted list.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from gnosk import interactive


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


def _feed(monkeypatch, console, lines: list[str]):
    """Replace console.input with a scripted reader."""
    it = iter(lines)

    def fake_input(prompt=""):
        try:
            nxt = next(it)
        except StopIteration as exc:
            raise EOFError from exc
        console.file.write(prompt + nxt + "\n")
        return nxt

    monkeypatch.setattr(console, "input", fake_input)


class TestQuitPaths:
    def test_quit_returns_zero(self, monkeypatch, console):
        _feed(monkeypatch, console, ["quit"])
        assert interactive.run(console) == 0

    def test_exit_alias(self, monkeypatch, console):
        _feed(monkeypatch, console, ["exit"])
        assert interactive.run(console) == 0

    def test_eof_exits_cleanly(self, monkeypatch, console):
        _feed(monkeypatch, console, [])
        assert interactive.run(console) == 0


class TestCommands:
    def test_help_does_not_exit(self, monkeypatch, console):
        _feed(monkeypatch, console, ["help", "quit"])
        assert interactive.run(console) == 0
        assert "scan <path>" in console.file.getvalue()

    def test_unknown_command_keeps_session(self, monkeypatch, console):
        _feed(monkeypatch, console, ["frobnicate", "quit"])
        assert interactive.run(console) == 0
        assert "unknown command" in console.file.getvalue()

    def test_blank_line_ignored(self, monkeypatch, console):
        _feed(monkeypatch, console, ["", "quit"])
        assert interactive.run(console) == 0

    def test_scan_missing_path(self, monkeypatch, console):
        _feed(monkeypatch, console, ["scan /nonexistent/xyz", "quit"])
        assert interactive.run(console) == 0
        assert "Path not found" in console.file.getvalue()

    def test_scan_clean_folder(self, monkeypatch, console, tmp_path):
        (tmp_path / "clean.txt").write_text("nothing here")
        _feed(monkeypatch, console, [f"scan {tmp_path}", "quit"])
        assert interactive.run(console) == 0
        assert "0 finding" in console.file.getvalue()

    def test_scan_finds_email(self, monkeypatch, console, tmp_path):
        (tmp_path / "x.txt").write_text("contact real@example.com")
        _feed(monkeypatch, console, [f"scan {tmp_path}", "quit"])
        assert interactive.run(console) == 0
        out = console.file.getvalue()
        assert "email" in out
        assert "real@example.com" not in out  # redacted

    def test_report_writes_files(self, monkeypatch, console, tmp_path):
        (tmp_path / "x.txt").write_text("contact real@example.com")
        out = tmp_path / "inv.md"
        _feed(monkeypatch, console, [f"report {tmp_path} {out}", "quit"])
        assert interactive.run(console) == 0
        assert out.exists()
        assert out.with_suffix(".json").exists()

    def test_report_on_clean_folder_writes_nothing(self, monkeypatch, console, tmp_path):
        (tmp_path / "clean.txt").write_text("nothing")
        out = tmp_path / "inv.md"
        _feed(monkeypatch, console, [f"report {tmp_path} {out}", "quit"])
        assert interactive.run(console) == 0
        assert not out.exists()

    def test_scan_without_args_prints_usage(self, monkeypatch, console):
        _feed(monkeypatch, console, ["scan", "quit"])
        assert interactive.run(console) == 0
        assert "usage" in console.file.getvalue().lower()


class TestCliWiring:
    def test_gnosk_wizard_subcommand_exists(self):
        from typer.testing import CliRunner

        from gnosk.cli import app

        # Just invoking --help for the subcommand path proves it's registered.
        result = CliRunner().invoke(app, ["wizard", "--help"])
        assert result.exit_code == 0


def test_naked_path_runs_scan(monkeypatch, console, tmp_path):
    (tmp_path / "x.txt").write_text("email: real@example.com")
    _feed(monkeypatch, console, [str(tmp_path), "quit"])
    assert interactive.run(console) == 0
    out = console.file.getvalue()
    assert "email" in out
