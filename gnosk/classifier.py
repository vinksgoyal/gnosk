"""Ask the local model to separate real PII from test fixtures.

The deterministic validators cannot tell an Aadhaar number in
`tests/test_aadhaar.py` from one in a customer database dump. This
module asks the local model to make that call, one batch at a time.

Prompt shape and response shape are both constrained by hardware. On a
2-core CPU running gemma2:2b, throughput is ~2 tokens/sec. We send each
finding's containing line (not the whole file) and ask for a minimal
JSON response with no reasons, so a single call stays under ~30s.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnosk.findings import Finding
from gnosk.llm import LLMError, ask_json

VERDICT_REAL = "real"
VERDICT_FIXTURE = "fixture"
VERDICT_UNKNOWN = "unknown"
_VALID_VERDICTS = {VERDICT_REAL, VERDICT_FIXTURE, VERDICT_UNKNOWN}

# Batching. Smaller = smaller prompt and smaller response = faster.
# Tuned for gemma2:2b on 2 CPU cores. Bump on faster hardware.
_MAX_FINDINGS_PER_CALL = 5
_MAX_LINE_CHARS = 140

_RULES = (
    "Rules: fixture = tests/examples/sample data (tests/, mock, "
    "alice@example.com). real = production data (config, .env, migrations). "
    "Emit one verdict per item, no reasons."
)

_SCHEMA = (
    'Reply ONLY: {"judgments":[{"index":int,"verdict":"fixture"|"real"|"unknown"}]}'
)


@dataclass(frozen=True, slots=True)
class ClassifiedFinding:
    finding: Finding
    verdict: str
    reason: str


def _extract_line_context(text: str, start: int, end: int) -> str:
    """Return the line of `text` that contains the span [start, end).

    Truncated to `_MAX_LINE_CHARS`. Returns an empty string if the span
    is out of bounds or the line is blank.
    """
    if not text:
        return ""
    if start < 0 or end < start or start > len(text):
        return ""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end].strip()
    if len(line) > _MAX_LINE_CHARS:
        line = line[:_MAX_LINE_CHARS] + "..."
    return line


def _build_prompt(path: str, text: str, findings: list[Finding]) -> str:
    """Build a compact prompt. Does not include the full file contents."""
    lines = [f"Path: {path}", _RULES, "Items:"]
    for i, f in enumerate(findings):
        ctx = _extract_line_context(text, f.start, f.end)
        if ctx:
            lines.append(f'{i}. [{f.category}] "{f.value}" | {ctx}')
        else:
            lines.append(f'{i}. [{f.category}] "{f.value}"')
    lines.append("")
    lines.append(_SCHEMA)
    return "\n".join(lines)


def _parse_judgments(data: dict, n_findings: int) -> list[tuple[str, str]]:
    """Return one (verdict, reason) per finding; default (unknown, '')."""
    out: list[tuple[str, str]] = [
        (VERDICT_UNKNOWN, "no judgment returned") for _ in range(n_findings)
    ]
    judgments = data.get("judgments")
    if not isinstance(judgments, list):
        return out
    for j in judgments:
        if not isinstance(j, dict):
            continue
        idx = j.get("index")
        verdict = j.get("verdict")
        if not isinstance(idx, int) or not (0 <= idx < n_findings):
            continue
        if verdict not in _VALID_VERDICTS:
            continue
        reason = j.get("reason")
        out[idx] = (verdict, str(reason)[:200] if reason else "")
    return out


def classify_findings(
    path: str,
    text: str,
    findings: list[Finding],
) -> list[ClassifiedFinding]:
    """Return one ClassifiedFinding per input finding.

    Never raises on model failure; failed classifications become "unknown".
    """
    if not findings:
        return []

    if len(findings) > _MAX_FINDINGS_PER_CALL:
        return (
            classify_findings(path, text, findings[:_MAX_FINDINGS_PER_CALL])
            + classify_findings(path, text, findings[_MAX_FINDINGS_PER_CALL:])
        )

    try:
        data = ask_json(_build_prompt(path, text, findings))
        verdicts = _parse_judgments(data, len(findings))
    except LLMError as exc:
        verdicts = [
            (VERDICT_UNKNOWN, f"model call failed: {str(exc)[:120]}")
            for _ in findings
        ]

    return [
        ClassifiedFinding(finding=f, verdict=v, reason=r)
        for f, (v, r) in zip(findings, verdicts, strict=True)
    ]
