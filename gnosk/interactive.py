"""Interactive REPL launched by `gnosk` with no arguments.

The session stays open until the user types `quit` (or Ctrl+D). Commands:

    scan <path>      scan a path, show findings in a table
    report <path>    scan and write a markdown inventory
    help             show this message
    quit / exit      leave the session

The old prompt-driven wizard is preserved as `gnosk wizard`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from gnosk import __version__
from gnosk.report import build_inventory, redact
from gnosk.scanner import FileFindings, scan_path
from gnosk.ui import color_for, print_banner

_MAX_TABLE_ROWS = 50

_HELP = """\
Commands:
  scan <path>              scan a file or folder and show findings
  report <path> [out.md]   scan and write a markdown + JSON inventory
  classify <path>          scan with local model classification (slow)
  help                     show this message
  quit, exit, :q           leave the session
"""


def _scan_with_spinner(console: Console, path: Path) -> tuple[list[FileFindings], float]:
    results: list[FileFindings] = []
    t0 = time.monotonic()
    with console.status("[dim]scanning…[/dim]", spinner="dots") as status:
        for r in scan_path(path):
            results.append(r)
            status.update(f"[dim]scanning… {len(results)} file(s)[/dim]")
    return results, time.monotonic() - t0


def _render_results(console: Console, results: list[FileFindings], elapsed: float) -> int:
    rows: list[tuple[str, int | None, str, float, str]] = []
    for r in results:
        for f in r.findings:
            rows.append((str(r.path), f.line, f.category, f.confidence, redact(f.value)))

    total = len(rows)
    console.print()
    console.print(
        f"  [green]✓[/green] Scanned [bold]{len(results)}[/bold] file(s) in "
        f"[bold]{elapsed:.2f}s[/bold] — [bold]{total}[/bold] finding(s)"
    )
    if not rows:
        console.print()
        return 0

    table = Table(show_header=True, header_style="bold", padding=(0, 1), show_edge=True)
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
            f"  [dim]… and {total - _MAX_TABLE_ROWS} more. "
            f"Write a report to see all.[/dim]"
        )
    console.print()
    return total


def _write_report(
    console: Console, path: Path, output: Path, results: list[FileFindings]
) -> None:
    output.write_text(build_inventory(results, project_path=str(path)))
    console.print(f"  [green]✓[/green] Wrote markdown: [bold]{output}[/bold]")
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
    console.print(f"  [green]✓[/green] Wrote JSON: [bold]{json_path}[/bold]")
    console.print()


def _resolve_path(raw: str) -> Path | None:
    p = Path(raw).expanduser()
    if not p.exists():
        return None
    return p.resolve()


def _dispatch(console: Console, line: str) -> bool:
    """Run one command. Return False to leave the session."""
    parts = line.strip().split()
    if not parts:
        return True
    cmd, *args = parts

    if cmd in ("quit", "exit", ":q", ":quit"):
        return False

    if cmd == "help":
        console.print(_HELP)
        return True

    if cmd == "scan":
        if not args:
            console.print("  [red]usage:[/red] scan <path>")
            return True
        path = _resolve_path(args[0])
        if path is None:
            console.print(f"  [red]Path not found:[/red] {args[0]}")
            return True
        results, elapsed = _scan_with_spinner(console, path)
        _render_results(console, results, elapsed)
        return True

    if cmd == "report":
        if not args:
            console.print("  [red]usage:[/red] report <path> [output.md]")
            return True
        path = _resolve_path(args[0])
        if path is None:
            console.print(f"  [red]Path not found:[/red] {args[0]}")
            return True
        out = Path(args[1]).expanduser() if len(args) > 1 else Path("gnosk-report.md")
        results, elapsed = _scan_with_spinner(console, path)
        _render_results(console, results, elapsed)
        if any(r.findings for r in results):
            _write_report(console, path, out, results)
        else:
            console.print("  [dim]No findings — nothing to report.[/dim]")
            console.print()
        return True

    if cmd == "classify":
        from gnosk.classifier import classify_findings

        if not args:
            console.print("  [red]usage:[/red] classify <path>")
            return True
        path = _resolve_path(args[0])
        if path is None:
            console.print(f"  [red]Path not found:[/red] {args[0]}")
            return True
        results, elapsed = _scan_with_spinner(console, path)
        _render_results(console, results, elapsed)
        files = [r for r in results if r.findings]
        if not files:
            return True
        console.print(
            "  [bold]Running local model classifier[/bold] "
            "[dim](~2 min per file on CPU)[/dim]"
        )
        verdicts: dict[str, int] = {}
        for r in files:
            console.print(f"  [dim]classifying {r.count} finding(s) in {r.path}…[/dim]")
            text = r.path.read_text(errors="replace")
            for cf in classify_findings(str(r.path), text, r.findings):
                verdicts[cf.verdict] = verdicts.get(cf.verdict, 0) + 1
        console.print()
        for v in sorted(verdicts):
            console.print(f"    {v}: {verdicts[v]}")
        console.print()
        return True

    # If the first token is a path that exists, treat it as `scan <path>`.
    as_path = Path(line.strip()).expanduser()
    if as_path.exists():
        return _dispatch(console, f"scan {line.strip()}")

    console.print(f"  [red]unknown command:[/red] {cmd}  (try `help`)")
    return True



def run(console: Console) -> int:
    """Launch the REPL. Returns a shell exit code."""
    print_banner(console, __version__)
    console.print("  [dim]Type `help` for commands, `quit` to exit.[/dim]")
    console.print()

    while True:
        try:
            line = console.input("[bold cyan]gnosk[/bold cyan][dim]›[/dim] ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            console.print("  [dim]bye.[/dim]")
            return 0
        try:
            if not _dispatch(console, line):
                console.print("  [dim]bye.[/dim]")
                return 0
        except KeyboardInterrupt:
            console.print()
            console.print("  [dim]interrupted — still in session. Type `quit` to exit.[/dim]")
            console.print()
        except Exception as exc:  # noqa: BLE001 — REPL should not die on user input
            console.print(f"  [red]error:[/red] {exc}")
            console.print()
