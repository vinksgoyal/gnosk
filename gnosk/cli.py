"""Gnosk CLI entry point."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from gnosk import __version__
from gnosk.classifier import classify_findings
from gnosk.report import build_inventory, redact
from gnosk.scanner import scan_path

app = typer.Typer(
    name="gnosk",
    help="Know what your code knows. Offline PII scanner. Never uploads your files.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"gnosk {__version__}")
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
    """Gnosk — local-first PII scanner."""


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

    files_scanned = 0
    total = 0
    by_category: dict[str, int] = {}
    verdicts: dict[str, int] = {}

    for result in scan_path(path):
        files_scanned += 1
        for f in result.findings:
            total += 1
            by_category[f.category] = by_category.get(f.category, 0) + 1

        if classify and result.findings:
            text = result.path.read_text(errors="replace")
            console.print(
                f"[dim]Classifying {result.count} finding(s) in {result.path}...[/dim]"
            )
            for cf in classify_findings(str(result.path), text, result.findings):
                verdicts[cf.verdict] = verdicts.get(cf.verdict, 0) + 1

    console.print(f"Scanned [bold]{files_scanned}[/bold] file(s).")
    console.print(f"Found [bold]{total}[/bold] finding(s).")
    if by_category:
        console.print()
        for cat in sorted(by_category):
            console.print(f"  {cat}: {by_category[cat]}")
    if verdicts:
        console.print()
        console.print("[bold]Classifier verdicts:[/bold]")
        for v in sorted(verdicts):
            console.print(f"  {v}: {verdicts[v]}")


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

    console.print(f"Scanning [bold]{path}[/bold] ...")
    results = list(scan_path(path))

    md = build_inventory(results, project_path=str(path))
    output.write_text(md)
    console.print(f"Wrote markdown: [bold]{output}[/bold]")

    # Raw JSON alongside, with values redacted so the JSON is safe to share.
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
    console.print(f"Wrote JSON: [bold]{json_path}[/bold]")


if __name__ == "__main__":
    app()
