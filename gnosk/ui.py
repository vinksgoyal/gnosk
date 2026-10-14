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
    print_signature(console)

def color_for(category: str) -> str:
    return CATEGORY_COLORS.get(category, "white")


SIGNATURE_NAME = "Vinks Goyal"


def signature_text(name: str = SIGNATURE_NAME):
    """Return a Rich Text with a rainbow gradient across `by <name>`.

    Imported lazily so ui.py stays importable when Rich isn't present
    in some future context (e.g. tests that only exercise config_dir).
    """
    import colorsys

    from rich.text import Text

    full = f"by {name}"
    n = max(len(full) - 1, 1)
    text = Text()
    for i, ch in enumerate(full):
        hue = (i / n) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 1.0)
        style = f"rgb({int(r * 255)},{int(g * 255)},{int(b * 255)})"
        text.append(ch, style=style)
    return text


def print_signature(console: Console) -> None:
    """Print the author signature under the banner. TTY-only."""
    if not is_interactive():
        return
    console.print(signature_text(), justify="left")
    console.print()
