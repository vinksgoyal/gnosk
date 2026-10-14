"""Terminal presentation helpers.

All banner, spinner, and color decisions live here. The CLI module
should not embed ANSI sequences or ASCII art directly.

Every helper checks `is_interactive()` first, so piped output, log
files, and CI runs get plain text with no escape codes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from rich.console import Console

BANNER = (
    " ██████╗ ███╗   ██╗ ██████╗ ███████╗██╗  ██╗\n"
    "██╔════╝ ████╗  ██║██╔═══██╗██╔════╝██║ ██╔╝\n"
    "██║  ███╗██╔██╗ ██║██║   ██║███████╗█████╔╝ \n"
    "██║   ██║██║╚██╗██║██║   ██║╚════██║██╔═██╗ \n"
    "╚██████╔╝██║ ╚████║╚██████╔╝███████║██║  ██╗\n"
    " ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝"
)

TAGLINE = "Know what your code knows."

CATEGORY_COLORS: dict[str, str] = {
    "aadhaar": "cyan",
    "pan": "magenta",
    "email": "green",
    "phone_in": "yellow",
    "api_key": "red",
}


def is_interactive() -> bool:
    """True only when we're writing to a real terminal and color is allowed."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("GNOSK_NO_TTY"):
        return False
    return sys.stdout.isatty()


def config_dir() -> Path:
    override = os.environ.get("GNOSK_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "gnosk"


def is_first_run() -> bool:
    return not (config_dir() / "seen").exists()


def mark_seen() -> None:
    try:
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / "seen").touch()
    except OSError:
        # Read-only home dir or similar; first-run hint just shows again.
        pass


def print_banner(console: Console, version: str) -> None:
    if not is_interactive():
        return
    console.print(f"[cyan]{BANNER}[/cyan]")
    console.print(f"  [dim]{TAGLINE}[/dim]  [dim]v{version}[/dim]")
    console.print()


def color_for(category: str) -> str:
    return CATEGORY_COLORS.get(category, "white")
