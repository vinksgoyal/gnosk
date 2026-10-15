"""Tests for `gnosk update`.

All git and pip calls are stubbed — the tests never touch the network
or the real repository.
"""

from __future__ import annotations

import subprocess
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from gnosk import update


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


def _proc(stdout: str = "", stderr: str = "", rc: int = 0):
    return subprocess.CompletedProcess(
        args=["git"], returncode=rc, stdout=stdout, stderr=stderr
    )


# ---------- find_repo_root ----------

class TestFindRepoRoot:
    def test_finds_git_dir(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        pkg = tmp_path / "gnosk"
        pkg.mkdir()
        assert update.find_repo_root(pkg) == tmp_path

    def test_returns_none_when_no_git(self, tmp_path: Path):
        pkg = tmp_path / "gnosk"
        pkg.mkdir()
        assert update.find_repo_root(pkg) is None


# ---------- inspect_repo ----------

class TestInspectRepo:
    def test_reads_branch_and_status(self, monkeypatch, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        calls = {"n": 0}

        def fake_run(cmd, cwd):
            calls["n"] += 1
            if "rev-parse" in cmd and "--abbrev-ref" in cmd and "@{upstream}" in cmd[2]:
                return _proc("origin/main")
            if "rev-parse" in cmd:
                return _proc("main")
            if "status" in cmd:
                return _proc("")
            return _proc()

        monkeypatch.setattr(update, "_run", fake_run)
        state = update.inspect_repo(tmp_path)
        assert state.branch == "main"
        assert state.has_local_changes is False
        assert state.has_upstream is True

    def test_detects_local_changes(self, monkeypatch, tmp_path: Path):
        def fake_run(cmd, cwd):
            if "status" in cmd:
                return _proc("M gnosk/cli.py\n")
            if "@{upstream}" in " ".join(cmd):
                return _proc("origin/main")
            if "rev-parse" in cmd:
                return _proc("main")
            return _proc()

        monkeypatch.setattr(update, "_run", fake_run)
        state = update.inspect_repo(tmp_path)
        assert state.has_local_changes is True

    def test_raises_on_bad_repo(self, monkeypatch, tmp_path: Path):
        monkeypatch.setattr(
            update, "_run", lambda cmd, cwd: _proc("", "not a repo", 128)
        )
        with pytest.raises(update.UpdateError):
            update.inspect_repo(tmp_path)


# ---------- run() ----------

class TestRunNotAGitCheckout:
    def test_non_git_install_returns_1(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: None)
        assert update.run(console) == 1
        assert "PyPI" in console.file.getvalue()


class TestRunDirtyTree:
    def test_refuses_with_local_changes(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(
                root=tmp_path,
                branch="main",
                has_local_changes=True,
                has_upstream=True,
            ),
        )
        assert update.run(console) == 1
        out = console.file.getvalue()
        assert "uncommitted changes" in out
        assert "git stash" in out


class TestRunNoUpstream:
    def test_refuses_without_upstream(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(
                root=tmp_path,
                branch="main",
                has_local_changes=False,
                has_upstream=False,
            ),
        )
        assert update.run(console) == 1
        assert "no upstream" in console.file.getvalue()


class TestRunUpToDate:
    def test_no_updates_returns_0(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(tmp_path, "main", False, True),
        )
        monkeypatch.setattr(update, "fetch", lambda _: None)
        monkeypatch.setattr(update, "commits_behind", lambda *_: 0)
        assert update.run(console) == 0
        assert "Already up to date" in console.file.getvalue()


class TestRunUpdate:
    def test_pulls_and_reinstalls(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(tmp_path, "main", False, True),
        )
        monkeypatch.setattr(update, "fetch", lambda _: None)
        monkeypatch.setattr(update, "commits_behind", lambda *_: 3)
        monkeypatch.setattr(update, "pull", lambda _: None)
        monkeypatch.setattr(update, "reinstall", lambda _: None)
        monkeypatch.setattr(update, "_current_version", lambda: "0.0.1")
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: _proc("0.0.2"),
        )
        assert update.run(console) == 0
        out = console.file.getvalue()
        assert "Updated 0.0.1 → 0.0.2" in out

    def test_fetch_error_reported(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(tmp_path, "main", False, True),
        )

        def bad_fetch(_):
            raise update.UpdateError("Could not reach the remote.")

        monkeypatch.setattr(update, "fetch", bad_fetch)
        assert update.run(console) == 1
        assert "Could not reach the remote" in console.file.getvalue()

    def test_reinstall_failure_reported(self, monkeypatch, console, tmp_path: Path):
        monkeypatch.setattr(update, "find_repo_root", lambda _: tmp_path)
        monkeypatch.setattr(
            update,
            "inspect_repo",
            lambda _: update.RepoState(tmp_path, "main", False, True),
        )
        monkeypatch.setattr(update, "fetch", lambda _: None)
        monkeypatch.setattr(update, "commits_behind", lambda *_: 1)
        monkeypatch.setattr(update, "pull", lambda _: None)

        def bad_reinstall(_):
            raise update.UpdateError("Reinstall failed.")

        monkeypatch.setattr(update, "reinstall", bad_reinstall)
        assert update.run(console) == 1
        assert "Reinstall failed" in console.file.getvalue()
