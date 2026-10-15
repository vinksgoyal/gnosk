"""Tests for the interactive TUI.

questionary prompts are monkeypatched, so pytest never touches a real
terminal. The scan itself runs against a tmp_path.
"""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from gnosk import interactive


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False)


class _Stub:
    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value


def _patch_questionary(
    monkeypatch,
    *,
    folder: str | None,
    mode: str | None = "quick",
    confirm: bool | None = True,
    outfile: str | None = "out.md",
):
    monkeypatch.setattr(interactive.questionary, "path", lambda *a, **k: _Stub(folder))
    monkeypatch.setattr(interactive.questionary, "select", lambda *a, **k: _Stub(mode))
    monkeypatch.setattr(
        interactive.questionary, "confirm", lambda *a, **k: _Stub(confirm)
    )
    monkeypatch.setattr(interactive.questionary, "text", lambda *a, **k: _Stub(outfile))


class TestCancelPaths:
    def test_cancel_at_folder_prompt(self, monkeypatch, console, tmp_path):
        _patch_questionary(monkeypatch, folder=None)
        assert interactive.run(console) == 130

    def test_cancel_at_mode_prompt(self, monkeypatch, console, tmp_path):
        _patch_questionary(monkeypatch, folder=str(tmp_path), mode=None)
        assert interactive.run(console) == 130

    def test_missing_path_returns_1(self, monkeypatch, console, tmp_path):
        _patch_questionary(monkeypatch, folder=str(tmp_path / "nope"))
        assert interactive.run(console) == 1


class TestHappyPath:
    def test_no_findings_skips_report_prompt(self, monkeypatch, console, tmp_path):
        (tmp_path / "clean.txt").write_text("no pii here")
        called = {"confirm": 0}
        original = interactive.questionary.confirm

        def spy(*a, **k):
            called["confirm"] += 1
            return original(*a, **k)

        _patch_questionary(monkeypatch, folder=str(tmp_path))
        monkeypatch.setattr(interactive.questionary, "confirm", spy)
        assert interactive.run(console) == 0
        assert called["confirm"] == 0

    def test_writes_report_when_confirmed(self, monkeypatch, console, tmp_path):
        (tmp_path / "x.txt").write_text("email: real@example.com")
        out = tmp_path / "inv.md"
        _patch_questionary(
            monkeypatch,
            folder=str(tmp_path),
            confirm=True,
            outfile=str(out),
        )
        assert interactive.run(console) == 0
        assert out.exists()
        assert "Gnosk Data Inventory" in out.read_text()
        assert (tmp_path / "inv.json").exists()

    def test_does_not_write_when_declined(self, monkeypatch, console, tmp_path):
        (tmp_path / "x.txt").write_text("email: real@example.com")
        out = tmp_path / "inv.md"
        _patch_questionary(
            monkeypatch, folder=str(tmp_path), confirm=False, outfile=str(out)
        )
        assert interactive.run(console) == 0
        assert not out.exists()
