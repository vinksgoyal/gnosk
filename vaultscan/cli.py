"""VaultScan CLI entry point. All commands are stubs for now."""

import typer
from rich.console import Console

from vaultscan import __version__

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


if __name__ == "__main__":
    app()
