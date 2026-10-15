"""Interactive TUI shown when `gnosk` runs with no arguments.

Flow:
    1. ask which folder to scan (tab-completion for paths)
    2. ask quick vs deep (deep runs the local model)
    3. scan with spinner
    4. show results in a table
    5. offer to write the report

Ctrl+C at any prompt exits cleanly with status 130.
"""

from __future__ import annotations

import time
from pathlib import Path

import questionary
from rich.console import Console
from rich.table import Table

from gnosk import __version__
from gnosk.classifier import classify_findings
from gnosk.report import build_inventory, redact
from gnosk.scanner import FileFindings, scan_path
from gnosk.ui import color_for, print_banner

_MAX_TABLE_ROWS = 50
_EXIT_CANCELLED = 130


def _scan_with_spinner(
    console: Console, path: Path
) -> tuple[list[FileFindings], float]:
    results: list[FileFindings] = []
    t0 = time.monotonic()
    with console.status("[dim]scanning…[/dim]", spinner="dots") as status:
        for r in scan_path(path):
            results.append(r)
            status.update(f"[dim]scanning… {len(results)} file(s)[/dim]")
    return results, time.monotonic() - t0


def _render_results_table(
    console: Console, results: list[FileFindings], elapsed: float
) -> int:
    rows: list[tuple[str, int | None, str, float, str]] = []
    for r in results:
        for f in r.findings:
            rows.append((str(r.path), f.line, f.category, f.confidence, redact(f.value)))

    total = len(rows)
    console.print()
    console.print(
        f"Scanned [bold]{len(results)}[/bold] file(s) in "
        f"[bold]{elapsed:.2f}s[/bold] — found [bold]{total}[/bold] finding(s)"
    )
    console.print()

    if not rows:
        console.print("[green]✓ No findings.[/green]")
        return 0

    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("File", style="dim", no_wrap=True, overflow="fold")
    table.add_column("Line", justify="right")
    table.add_column("Category")
    table.add_column("Conf", justify="right", style="dim")
    table.add_column("Value (redacted)")

    for path, line, cat, conf, val in rows[:_MAX_TABLE_ROWS]:
        color = color_for(cat)
        table.add_row(
            path,
            str(line) if line is not None else "?",
            f"[{color}]{cat}[/{color}]",
            f"{conf:.2f}",
            val,
        )

    console.print(table)
    if total > _MAX_TABLE_ROWS:
        console.print(
            f"[dim]… and {total - _MAX_TABLE_ROWS} more. "
            f"Write a report to see all.[/dim]"
        )
    return total


def _run_classifier(console: Console, results: list[FileFindings]) -> None:
    verdicts: dict[str, int] = {}
    files_with_findings = [r for r in results if r.findings]
    if not files_with_findings:
        return
    console.print()
    console.print(
        "[bold]Running local model classifier[/bold] "
        "[dim](this is slow on CPU — ~2 min per file)[/dim]"
    )
    for r in files_with_findings:
        console.print(f"  [dim]classifying {r.count} finding(s) in {r.path}…[/dim]")
        text = r.path.read_text(errors="replace")
        for cf in classify_findings(str(r.path), text, r.findings):
            verdicts[cf.verdict] = verdicts.get(cf.verdict, 0) + 1
    console.print()
    console.print("[bold]Classifier verdicts:[/bold]")
    for v in sorted(verdicts):
        console.print(f"  {v}: {verdicts[v]}")


def _write_report(
    console: Console, path: Path, output: Path, results: list[FileFindings]
) -> None:
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
    """Launch the interactive wizard. Returns a shell exit code."""
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

    mode = questionary.select(
        "Scan mode?",
        choices=[
            questionary.Choice(
                "Quick scan — deterministic validators only (fast)", value="quick"
            ),
            questionary.Choice(
                "Deep scan — adds local model classification (slow)", value="deep"
            ),
        ],
        default="quick",
    ).ask()
    if mode is None:
        console.print("[dim]Cancelled.[/dim]")
        return _EXIT_CANCELLED

    results, elapsed = _scan_with_spinner(console, folder_path)
    _render_results_table(console, results, elapsed)

    if mode == "deep" and any(r.findings for r in results):
        _run_classifier(console, results)

    if not any(r.findings for r in results):
        return 0

    save = questionary.confirm(
        "Write a client-ready markdown inventory?", default=True
    ).ask()
    if save is None:
        console.print("[dim]Cancelled.[/dim]")
        return _EXIT_CANCELLED

    if save:
        out = questionary.text(
            "Output file:", default="gnosk-report.md"
        ).ask()
        if out is None:
            console.print("[dim]Cancelled.[/dim]")
            return _EXIT_CANCELLED
        _write_report(console, folder_path, Path(out).expanduser(), results)

    return 0
