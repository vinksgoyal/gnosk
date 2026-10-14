"""Generate a client-facing data inventory from scan results.

The inventory is markdown. Values are redacted to first-2 + last-2
characters so the report can be shared with a client without itself
becoming a PII leak. Line numbers point at exact locations.

This module does not scan and does not call the model. It takes
FileFindings and returns a string.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from gnosk.findings import Finding
from gnosk.scanner import FileFindings


def redact(value: str) -> str:
    """Return `value` with its middle replaced by asterisks.

    Values shorter than 4 characters are fully masked — first-2 + last-2
    would reveal too much.
    """
    if len(value) < 4:
        return "*" * len(value)
    return value[:2] + "*" * (len(value) - 4) + value[-2:]


def _line_display(f: Finding) -> str:
    return str(f.line) if f.line is not None else "?"


def build_inventory(
    scan_results: list[FileFindings],
    *,
    project_path: str,
    scan_date: date | None = None,
) -> str:
    """Return a markdown data inventory suitable for a client email."""
    when = scan_date or date.today()
    total_files = len(scan_results)
    files_with_findings = sum(1 for r in scan_results if r.findings)
    total = sum(r.count for r in scan_results)

    by_cat: dict[str, int] = defaultdict(int)
    for r in scan_results:
        for f in r.findings:
            by_cat[f.category] += 1

    lines: list[str] = []
    lines.append("# Gnosk Data Inventory")
    lines.append("")
    lines.append(f"- Project: `{project_path}`")
    lines.append(f"- Scanned: {when.isoformat()}")
    lines.append(f"- Files scanned: {total_files}")
    lines.append(f"- Files with findings: {files_with_findings}")
    lines.append(f"- Total findings: {total}")
    lines.append("")

    if total == 0:
        lines.append(
            "No PII-shaped data was detected. This does not guarantee the "
            "project is free of personal data — it means the detectors did "
            "not find any patterns they recognize."
        )
        lines.append("")
    else:
        lines.append("## Summary by category")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|---|---:|")
        for cat in sorted(by_cat):
            lines.append(f"| {cat} | {by_cat[cat]} |")
        lines.append("")

        lines.append("## Findings by file")
        lines.append("")
        for r in sorted(scan_results, key=lambda x: str(x.path)):
            if not r.findings:
                continue
            lines.append(f"### `{r.path}`")
            lines.append("")
            lines.append("| Line | Category | Confidence | Value (redacted) |")
            lines.append("|---:|---|---:|---|")
            for f in sorted(r.findings, key=lambda x: x.start):
                lines.append(
                    f"| {_line_display(f)} | {f.category} | "
                    f"{f.confidence:.2f} | `{redact(f.value)}` |"
                )
            lines.append("")

    lines.append("## Disclaimer")
    lines.append("")
    lines.append(
        "This inventory is informational only. Gnosk is a developer tool, "
        "not a compliance certification, legal advice, or a substitute for "
        "a formal audit. Values are redacted to avoid the report itself "
        "becoming a PII leak. Every pattern match should be verified by a "
        "human before it is treated as fact."
    )
    lines.append("")
    return "\n".join(lines)
