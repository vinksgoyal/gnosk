"""Classify findings as real data or test fixtures.

Two-layer pipeline:

  1. `gnosk.triage.triage` runs deterministic rules.
  2. Findings triage cannot decide are sent to the local model.

Only the second step costs time. On a typical scan, most findings are
resolved by triage, so the model sees a handful of items rather than
one per finding.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnosk.findings import Finding
from gnosk.llm import LLMError, ask_json
from gnosk.triage import triage

VERDICT_REAL = "real"
VERDICT_LIKELY_REAL = "likely_real"
VERDICT_FIXTURE = "fixture"
VERDICT_UNKNOWN = "unknown"

# Verdicts the model is allowed to emit. `likely_real` is triage-only.
_MODEL_VERDICTS = {VERDICT_REAL, VERDICT_FIXTURE, VERDICT_UNKNOWN}

# Source of a ClassifiedFinding's verdict.
SOURCE_TRIAGE = "triage"
SOURCE_MODEL = "model"

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
    """A Finding plus a verdict and where the verdict came from."""

    finding: Finding
    verdict: str
    reason: str
    source: str  # SOURCE_TRIAGE or SOURCE_MODEL


def _extract_line_context(text: str, start: int, end: int) -> str:
    """Return the line of `text` that contains the span [start, end)."""
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
        if verdict not in _MODEL_VERDICTS:
            continue
        reason = j.get("reason")
        out[idx] = (verdict, str(reason)[:200] if reason else "")
    return out


def classify_findings(
    path: str,
    text: str,
    findings: list[Finding],
) -> list[ClassifiedFinding]:
    """Return one ClassifiedFinding per input finding, in the same order.

    Never raises on model failure; failed model calls degrade to
    `unknown` with source `model`. Triage never fails.
    """
    if not findings:
        return []

    slots: list[ClassifiedFinding | None] = [None] * len(findings)
    needs_model: list[int] = []

    # Phase 1 — triage.
    for i, f in enumerate(findings):
        t = triage(f, path)
        if t is None:
            needs_model.append(i)
            continue
        verdict, reason = t
        slots[i] = ClassifiedFinding(
            finding=f, verdict=verdict, reason=reason, source=SOURCE_TRIAGE
        )

    # Phase 2 — model, in batches.
    for start in range(0, len(needs_model), _MAX_FINDINGS_PER_CALL):
        batch_indices = needs_model[start : start + _MAX_FINDINGS_PER_CALL]
        batch = [findings[i] for i in batch_indices]
        try:
            data = ask_json(_build_prompt(path, text, batch))
            verdicts = _parse_judgments(data, len(batch))
        except LLMError as exc:
            verdicts = [
                (VERDICT_UNKNOWN, f"model call failed: {str(exc)[:120]}")
                for _ in batch
            ]
        for local_i, global_i in enumerate(batch_indices):
            verdict, reason = verdicts[local_i]
            slots[global_i] = ClassifiedFinding(
                finding=findings[global_i],
                verdict=verdict,
                reason=reason,
                source=SOURCE_MODEL,
            )

    return [s for s in slots if s is not None]
