"""Tests for terminal presentation helpers."""

from __future__ import annotations

from pathlib import Path

from gnosk import ui


class TestIsInteractive:
    def test_false_when_no_color(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        assert ui.is_interactive() is False

    def test_false_when_gnosk_no_tty(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setenv("GNOSK_NO_TTY", "1")
        assert ui.is_interactive() is False

    def test_false_under_pytest(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("GNOSK_NO_TTY", raising=False)
        # pytest captures stdout, so isatty() is False.
        assert ui.is_interactive() is False


class TestConfigDir:
    def test_honors_env_override(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("GNOSK_CONFIG_DIR", str(tmp_path / "cfg"))
        assert ui.config_dir() == tmp_path / "cfg"

    def test_default_under_home(self, monkeypatch):
        monkeypatch.delenv("GNOSK_CONFIG_DIR", raising=False)
        assert ui.config_dir().name == "gnosk"
        assert ui.config_dir().parent.name == ".config"


class TestFirstRun:
    def test_is_first_run_true_when_marker_missing(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("GNOSK_CONFIG_DIR", str(tmp_path))
        assert ui.is_first_run() is True

    def test_mark_seen_flips_flag(self, monkeypatch, tmp_path: Path):
        monkeypatch.setenv("GNOSK_CONFIG_DIR", str(tmp_path))
        assert ui.is_first_run() is True
        ui.mark_seen()
        assert ui.is_first_run() is False

    def test_mark_seen_tolerates_io_error(self, monkeypatch, tmp_path: Path):
        # Point at a path where a file already exists, so mkdir fails.
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        monkeypatch.setenv("GNOSK_CONFIG_DIR", str(blocker))
        # Should not raise.
        ui.mark_seen()


class TestColors:
    def test_known_category_has_color(self):
        assert ui.color_for("aadhaar") == "cyan"
        assert ui.color_for("api_key") == "red"

    def test_unknown_category_falls_back(self):
        assert ui.color_for("something_new") == "white"


class TestBanner:
    def test_banner_skipped_when_not_interactive(self, monkeypatch):
        from io import StringIO

        from rich.console import Console

        monkeypatch.setenv("NO_COLOR", "1")
        buf = StringIO()
        console = Console(file=buf, force_terminal=False)
        ui.print_banner(console, "0.0.1")
        assert buf.getvalue() == ""
