"""VaultScan CLI entry point."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from vaultscan import __version__
from vaultscan.scanner import scan_path

app = typer.Typer(
    name="vaultscan",
    help="Offline PII leak scanner. Runs locally, never uploads your files.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"vaultscan {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """VaultScan — local-first PII scanner."""


@app.command()
def scan(
    path: Path = typer.Argument(..., help="File or directory to scan."),
) -> None:
    """Scan a file or directory for PII. Prints a summary only for now."""
    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(code=1)

    files_scanned = 0
    total = 0
    by_category: dict[str, int] = {}

    for result in scan_path(path):
        files_scanned += 1
        for f in result.findings:
            total += 1
            by_category[f.category] = by_category.get(f.category, 0) + 1

    console.print(f"Scanned [bold]{files_scanned}[/bold] file(s).")
    console.print(f"Found [bold]{total}[/bold] finding(s).")
    if by_category:
        console.print()
        for cat in sorted(by_category):
            console.print(f"  {cat}: {by_category[cat]}")


if __name__ == "__main__":
    app()
