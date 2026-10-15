"""Prompt-driven single-shot wizard. Available as `gnosk wizard`."""

from __future__ import annotations

import time
from pathlib import Path

import questionary
from rich.console import Console

from gnosk import __version__
from gnosk.report import build_inventory, redact
from gnosk.scanner import FileFindings, scan_path
from gnosk.ui import print_banner

_EXIT_CANCELLED = 130


def _scan_with_spinner(console: Console, path: Path) -> tuple[list[FileFindings], float]:
    results: list[FileFindings] = []
    t0 = time.monotonic()
    with console.status("[dim]scanning…[/dim]", spinner="dots") as status:
        for r in scan_path(path):
            results.append(r)
            status.update(f"[dim]scanning… {len(results)} file(s)[/dim]")
    return results, time.monotonic() - t0


def _write_report(console: Console, path: Path, output: Path, results: list[FileFindings]) -> None:
    import json

    output.write_text(build_inventory(results, project_path=str(path)))
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


def run(console: Console) -> int:
    print_banner(console, __version__)

    folder = questionary.path(
        "Which folder do you want to scan?",
        default=str(Path.cwd()),
        only_directories=True,
    ).ask()
    if folder is None:
        console.print("[dim]Cancelled.[/dim]")
        return _EXIT_CANCELLED

    folder_path = Path(folder).expanduser().resolve()
    if not folder_path.exists():
        console.print(f"[red]Path does not exist:[/red] {folder_path}")
        return 1

    results, elapsed = _scan_with_spinner(console, folder_path)
    total = sum(r.count for r in results)
    console.print(
        f"Scanned [bold]{len(results)}[/bold] file(s) in "
        f"[bold]{elapsed:.2f}s[/bold] — [bold]{total}[/bold] finding(s)"
    )

    if total == 0:
        return 0

    save = questionary.confirm(
        "Write a client-ready markdown inventory?", default=True
    ).ask()
    if save is None:
        console.print("[dim]Cancelled.[/dim]")
        return _EXIT_CANCELLED
    if save:
        out = questionary.text("Output file:", default="gnosk-report.md").ask()
        if out is None:
            return _EXIT_CANCELLED
        _write_report(console, folder_path, Path(out).expanduser(), results)
    return 0
