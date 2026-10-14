"""Email address detection.

Shape-based only. A regex can confirm an email looks like an email; it
cannot confirm the mailbox exists, is reachable, or belongs to a human.
"""

from __future__ import annotations

import re

from gnosk.findings import SOURCE_VALIDATOR, Finding

# Deliberately permissive: matches the practical subset of RFC 5322 that
# real-world addresses use. Does not match quoted local parts or IP-literal
# domains — those are vanishingly rare in codebases and invoices.
EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)


def find_email_candidates(text: str) -> list[tuple[int, int, str]]:
    if not isinstance(text, str):
        return []
    return [(m.start(), m.end(), m.group(0)) for m in EMAIL_RE.finditer(text)]


def scan(text: str) -> list[Finding]:
    out: list[Finding] = []
    for start, end, value in find_email_candidates(text):
        out.append(
            Finding(
                category="email",
                value=value,
                start=start,
                end=end,
                confidence=0.9,
                source=SOURCE_VALIDATOR,
                validator="email.shape",
                notes=None,
            )
        )
    return out
