"""Gnosk CLI entry point."""

from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from rich.console import Console

from gnosk import __version__
from gnosk.classifier import classify_findings
from gnosk.report import build_inventory, redact
from gnosk.scanner import FileFindings, scan_path
from gnosk.ui import (
    color_for,
    is_first_run,
    mark_seen,
    print_banner,
)

app = typer.Typer(
    name="gnosk",
    help="Know what your code knows. Offline PII scanner. Never uploads your files.",
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"gnosk {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Gnosk — local-first PII scanner."""
    if ctx.invoked_subcommand is not None:
        return
    # No subcommand — launch the interactive REPL.
    from gnosk.interactive import run as run_repl

    try:
        raise typer.Exit(code=run_repl(console))
    except KeyboardInterrupt:
        console.print("\n[dim]bye.[/dim]")
        raise typer.Exit(code=130) from None


def _collect_scan(path: Path) -> tuple[list[FileFindings], float]:
    """Walk `path`, showing a spinner while it runs. Returns (results, elapsed)."""
    results: list[FileFindings] = []
    t0 = time.monotonic()
    with console.status("[dim]scanning…[/dim]", spinner="dots") as status:
        for r in scan_path(path):
            results.append(r)
            status.update(f"[dim]scanning… {len(results)} file(s)[/dim]")
    return results, time.monotonic() - t0


def _print_summary(
    path: Path,
    results: list[FileFindings],
    elapsed: float,
    by_category: dict[str, int],
) -> None:
    total = sum(by_category.values())
    check = "[green]✓[/green]" if not total else "[bold yellow]![/bold yellow]"
    console.print(
        f"{check} Scanned [bold]{len(results)}[/bold] file(s) "
        f"in [bold]{elapsed:.2f}s[/bold]"
    )
    console.print(f"  Found [bold]{total}[/bold] finding(s)")
    console.print()

    if by_category:
        for cat in sorted(by_category):
            color = color_for(cat)
            console.print(f"  [{color}]{cat:<10}[/{color}]  {by_category[cat]}")
        console.print()

    if is_first_run():
        console.print(
            f"  [dim]▸ Write a client-ready inventory:  "
            f"gnosk report {path}[/dim]"
        )
        console.print()
        mark_seen()


@app.command()
def scan(
    path: Path = typer.Argument(..., help="File or directory to scan."),
    classify: bool = typer.Option(
        False,
        "--classify",
        help="Use the local model to flag findings as real vs test fixtures. Slow.",
    ),
) -> None:
    """Scan a file or directory for PII."""
    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(code=1)

    print_banner(console, __version__)

    results, elapsed = _collect_scan(path)

    by_category: dict[str, int] = {}
    for r in results:
        for f in r.findings:
            by_category[f.category] = by_category.get(f.category, 0) + 1

    _print_summary(path, results, elapsed, by_category)

    if classify:
        verdicts: dict[str, int] = {}
        sources: dict[str, int] = {}
        for r in results:
            if not r.findings:
                continue
            console.print(f"[dim]classifying {r.count} finding(s) in {r.path}…[/dim]")
            text = r.path.read_text(errors="replace")
            for cf in classify_findings(str(r.path), text, r.findings):
                verdicts[cf.verdict] = verdicts.get(cf.verdict, 0) + 1
                sources[cf.source] = sources.get(cf.source, 0) + 1
        if verdicts:
            console.print()
            console.print("[bold]Verdicts:[/bold]")
            for v in sorted(verdicts):
                console.print(f"  {v}: {verdicts[v]}")
            console.print()
            console.print("[bold]Decided by:[/bold]")
            for s in sorted(sources):
                console.print(f"  {s}: {sources[s]}")


@app.command()
def report(
    path: Path = typer.Argument(..., help="File or directory to scan."),
    output: Path = typer.Option(
        Path("gnosk-report.md"),
        "--output",
        "-o",
        help="Where to write the markdown inventory.",
    ),
) -> None:
    """Scan a path and write a client-ready markdown data inventory."""
    if not path.exists():
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(code=1)

    print_banner(console, __version__)
    console.print(f"Scanning [bold]{path}[/bold] …")

    results, elapsed = _collect_scan(path)

    md = build_inventory(results, project_path=str(path))
    output.write_text(md)
    console.print(f"[green]✓[/green] Wrote markdown: [bold]{output}[/bold]")

    json_path = output.with_suffix(".json")
    payload = {
        "project_path": str(path),
        "files": [
            {
                "path": str(r.path),
                "findings": [
                    {
                        "category": f.category,
                        "line": f.line,
                        "confidence": f.confidence,
                        "validator": f.validator,
                        "value_redacted": redact(f.value),
                    }
                    for f in r.findings
                ],
            }
            for r in results
            if r.findings
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2))
    console.print(f"[green]✓[/green] Wrote JSON: [bold]{json_path}[/bold]")
    console.print(f"  [dim]({elapsed:.2f}s)[/dim]")




@app.command()
def wizard() -> None:
    """Prompt-driven single-shot wizard (alternative to the REPL)."""
    from gnosk.wizard import run as run_wizard

    try:
        raise typer.Exit(code=run_wizard(console))
    except KeyboardInterrupt:
        console.print("\n[dim]Cancelled.[/dim]")
        raise typer.Exit(code=130) from None


@app.command()
def update() -> None:
    """Pull the latest Gnosk from git and reinstall."""
    from gnosk.update import run as run_update

    raise typer.Exit(code=run_update(console))


if __name__ == "__main__":
    app()
