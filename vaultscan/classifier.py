"""Ask the local model to separate real PII from test fixtures.

The deterministic validators cannot tell an Aadhaar number in
`tests/test_aadhaar.py` from one in a customer database dump. This
module asks the local model to make that call, one file at a time.

Model failures degrade to `unknown` rather than raising. Classification
is advisory; detection is not.
"""

from __future__ import annotations

from dataclasses import dataclass

from vaultscan.findings import Finding
from vaultscan.llm import LLMError, ask_json

VERDICT_REAL = "real"
VERDICT_FIXTURE = "fixture"
VERDICT_UNKNOWN = "unknown"
_VALID_VERDICTS = {VERDICT_REAL, VERDICT_FIXTURE, VERDICT_UNKNOWN}

# 2B model on CPU. Longer prompts slow down without improving accuracy.
_MAX_FILE_CHARS = 4000
_MAX_FINDINGS_PER_CALL = 30

_RUBRIC = """\
Verdicts:
- "fixture"  test data, example, placeholder, documentation, sample
- "real"     looks like actual customer/user/employee data
- "unknown"  genuinely cannot tell from the surrounding text

Signals for "fixture":
- file path contains tests/, test_, fixtures/, examples/, sample_data/
- string contains example, dummy, placeholder, sample, test, fake, foo, bar
- value is a well-known example (alice@example.com, AKIAIOSFODNN7EXAMPLE)
- surrounding code has assert, expect, mock, stub, patch

Signals for "real":
- file path looks like production code or config
- value sits in a migration, seed with real-looking records, .env, credentials
- surrounding code writes to a DB, sends an email, calls a payment API
"""


@dataclass(frozen=True, slots=True)
class ClassifiedFinding:
    """A Finding plus the model's judgment about it."""

    finding: Finding
    verdict: str          # one of VERDICT_REAL / VERDICT_FIXTURE / VERDICT_UNKNOWN
    reason: str


def _truncate(text: str, limit: int = _MAX_FILE_CHARS) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n[... file truncated for length ...]\n\n" + text[-half:]


def _build_prompt(path: str, text: str, findings: list[Finding]) -> str:
    lines = [
        "You are auditing a codebase for a privacy tool.",
        "Below is one file's content and a list of PII-looking strings",
        "found in it. For each item, decide whether it is real data",
        "belonging to an actual person, or a test fixture.",
        "",
        f"File path: {path}",
        "",
        "File content:",
        "-----",
        _truncate(text),
        "-----",
        "",
        "Findings (use these indices):",
    ]
    for i, f in enumerate(findings):
        lines.append(f'{i}. [{f.category}] "{f.value}"')
    lines.extend([
        "",
        _RUBRIC,
        "",
        'Respond with JSON: {"judgments": [{"index": <int>, '
        '"verdict": "fixture"|"real"|"unknown", "reason": "<short>"}]}',
    ])
    return "\n".join(lines)


def _parse_judgments(
    data: dict, n_findings: int
) -> list[tuple[str, str]]:
    """Return one (verdict, reason) per finding, defaulting to unknown."""
    out: list[tuple[str, str]] = [
        (VERDICT_UNKNOWN, "model gave no judgment for this item")
        for _ in range(n_findings)
    ]
    judgments = data.get("judgments")
    if not isinstance(judgments, list):
        return out
    for j in judgments:
        if not isinstance(j, dict):
            continue
        idx = j.get("index")
        verdict = j.get("verdict")
        reason = j.get("reason", "")
        if not isinstance(idx, int) or not (0 <= idx < n_findings):
            continue
        if verdict not in _VALID_VERDICTS:
            continue
        out[idx] = (verdict, str(reason)[:200])
    return out


def classify_findings(
    path: str,
    text: str,
    findings: list[Finding],
) -> list[ClassifiedFinding]:
    """Return one ClassifiedFinding per input finding.

    Never raises on model failure; failed classifications become "unknown"
    with a reason that reflects why.
    """
    if not findings:
        return []

    # If a file somehow accumulates a huge finding count, chunk the work
    # rather than blowing past the model's context window.
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
            (VERDICT_UNKNOWN, f"model call failed: {exc}"[:200])
            for _ in findings
        ]

    return [
        ClassifiedFinding(finding=f, verdict=v, reason=r)
        for f, (v, r) in zip(findings, verdicts, strict=True)
    ]
