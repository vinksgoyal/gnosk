"""Implementation of `gnosk update`.

Only handles the "installed from a git clone with `install.sh`" case,
which is how Gnosk is meant to be installed during the hackathon and
immediately after. If Gnosk later ships to PyPI, this module should
detect a non-editable install and redirect to `pip install --upgrade`.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console


@dataclass(slots=True)
class RepoState:
    root: Path
    branch: str
    has_local_changes: bool
    has_upstream: bool


class UpdateError(RuntimeError):
    """Raised for expected failures with a user-actionable message."""


def find_repo_root(package_path: Path) -> Path | None:
    """Walk up from `package_path` looking for a .git directory.

    Returns None if this isn't a git checkout — e.g. a wheel install.
    """
    for candidate in [package_path, *package_path.parents]:
        if (candidate / ".git").is_dir():
            return candidate
    return None


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def inspect_repo(root: Path) -> RepoState:
    branch_result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    if branch_result.returncode != 0:
        raise UpdateError(
            f"Could not read the git branch in {root}. "
            f"Is it a valid repository?\n{branch_result.stderr.strip()}"
        )
    branch = branch_result.stdout.strip()

    status_result = _run(["git", "status", "--porcelain"], root)
    if status_result.returncode != 0:
        raise UpdateError(f"git status failed: {status_result.stderr.strip()}")
    has_local_changes = bool(status_result.stdout.strip())

    upstream_result = _run(
        ["git", "rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], root
    )
    has_upstream = upstream_result.returncode == 0

    return RepoState(
        root=root,
        branch=branch,
        has_local_changes=has_local_changes,
        has_upstream=has_upstream,
    )


def fetch(root: Path) -> None:
    result = _run(["git", "fetch", "--quiet"], root)
    if result.returncode != 0:
        raise UpdateError(
            "Could not reach the remote. Check your network, then try again.\n"
            f"{result.stderr.strip()}"
        )


def commits_behind(root: Path, branch: str) -> int:
    result = _run(
        ["git", "rev-list", "--count", f"{branch}..{branch}@{{upstream}}"], root
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.strip())
    except ValueError:
        return 0


def pull(root: Path) -> None:
    result = _run(["git", "pull", "--ff-only"], root)
    if result.returncode != 0:
        raise UpdateError(
            "git pull failed. The branch may have diverged. "
            "Run `git pull` manually in the repo to resolve.\n"
            f"{result.stderr.strip()}"
        )


def reinstall(root: Path) -> None:
    # Use the venv's pip that is running this process, so we don't
    # accidentally reinstall into a different Python environment.
    venv_python = Path(sys.executable)
    venv_pip = venv_python.parent / "pip"
    if not venv_pip.exists():
        # Fall back to `python -m pip` if the direct script isn't there.
        cmd = [str(venv_python), "-m", "pip", "install", "-e", str(root)]
    else:
        cmd = [str(venv_pip), "install", "-e", str(root)]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise UpdateError(
            "Reinstall failed. Nothing was changed on disk — the repo is "
            "on the new commit but the installed package is old. Re-run "
            "`pip install -e .` manually in the repo.\n"
            f"{result.stderr.strip()[-500:]}"
        )


def _current_version() -> str:
    from gnosk import __version__

    return __version__


def run(console: Console) -> int:
    """Return a shell exit code (0 for success)."""
    import gnosk

    pkg_path = Path(gnosk.__file__).resolve().parent
    root = find_repo_root(pkg_path)
    if root is None:
        console.print(
            "[yellow]![/yellow] Gnosk was not installed from a git checkout."
        )
        console.print(
            "  If you installed from PyPI, update with:\n"
            "    [bold]pip install --upgrade gnosk[/bold]"
        )
        return 1

    try:
        state = inspect_repo(root)
    except UpdateError as exc:
        console.print(f"[red]✗[/red] {exc}")
        return 1

    if state.has_local_changes:
        console.print(
            "[yellow]![/yellow] You have uncommitted changes in "
            f"[bold]{root}[/bold]."
        )
        console.print(
            "  Commit or stash them first:\n"
            "    [bold]git stash[/bold]   # or: git commit -am 'wip'\n"
            "  Then re-run [bold]gnosk update[/bold]."
        )
        return 1

    if not state.has_upstream:
        console.print(
            f"[yellow]![/yellow] Branch [bold]{state.branch}[/bold] has no "
            "upstream configured."
        )
        console.print(
            "  Set one with:\n"
            "    [bold]git branch --set-upstream-to=origin/main main[/bold]"
        )
        return 1

    console.print(f"[dim]Checking for updates on {state.branch}…[/dim]")
    try:
        fetch(state.root)
    except UpdateError as exc:
        console.print(f"[red]✗[/red] {exc}")
        return 1

    behind = commits_behind(state.root, state.branch)
    before = _current_version()

    if behind == 0:
        console.print(
            f"[green]✓[/green] Already up to date (v{before}, "
            f"branch {state.branch})."
        )
        return 0

    noun = "commit" if behind == 1 else "commits"
    console.print(f"  [dim]Pulling {behind} new {noun}…[/dim]")
    try:
        pull(state.root)
    except UpdateError as exc:
        console.print(f"[red]✗[/red] {exc}")
        return 1

    console.print("  [dim]Reinstalling…[/dim]")
    try:
        reinstall(state.root)
    except UpdateError as exc:
        console.print(f"[red]✗[/red] {exc}")
        return 1

    # Re-import in a subprocess so the version reflects the new code.
    result = subprocess.run(
        [sys.executable, "-c", "import gnosk; print(gnosk.__version__)"],
        capture_output=True,
        text=True,
        check=False,
    )
    after = result.stdout.strip() or before
    console.print()
    console.print(f"[green]✓[/green] Updated {before} → {after}")
    console.print(f"  [dim]Repo: {state.root}[/dim]")
    return 0
