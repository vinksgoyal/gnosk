"""API-key and access-token detection for common providers.

Only patterns with a deliberate, distinctive prefix are matched. Generic
"high-entropy string" detection is intentionally not here: it belongs in
its own module with a tunable entropy threshold, because without one it
fires on git SHAs, UUIDs, base64 blobs, and CSS hashes.

Prefixes matched:
    AWS access key ID         AKIA...          (also ASIA..., AGPA...)
    GitHub personal token     ghp_...          (also gho_, ghu_, ghs_, ghr_)
    GitHub fine-grained PAT   github_pat_...
    OpenAI API key            sk-...           (long)
    Anthropic API key         sk-ant-...
    Stripe secret key         sk_live_...      (also sk_test_)
    Stripe publishable key    pk_live_...      (also pk_test_)
    Slack bot/user token      xox[baprs]-...
"""

from __future__ import annotations

import re

from gnosk.findings import SOURCE_VALIDATOR, Finding

# Ordered list of (name, compiled pattern). Names appear in the Finding's
# `validator` field so the report can tell the user which provider leaked.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA|AGPA)[0-9A-Z]{16}\b")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_oauth", re.compile(r"\bgho_[A-Za-z0-9]{36}\b")),
    ("github_user", re.compile(r"\bghu_[A-Za-z0-9]{36}\b")),
    ("github_server", re.compile(r"\bghs_[A-Za-z0-9]{36}\b")),
    ("github_refresh", re.compile(r"\bghr_[A-Za-z0-9]{36,}\b")),
    ("github_fine_grained", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("openai_api_key", re.compile(r"\bsk-[A-Za-z0-9]{40,}\b")),
    ("anthropic_api_key", re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{40,}\b")),
    ("stripe_secret", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{24,}\b")),
    ("stripe_publishable", re.compile(r"\bpk_(?:live|test)_[A-Za-z0-9]{24,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
]


def find_secret_candidates(text: str) -> list[tuple[int, int, str, str]]:
    """Return (start, end, value, key_kind) for every matching secret."""
    if not isinstance(text, str):
        return []
    hits: list[tuple[int, int, str, str]] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            hits.append((m.start(), m.end(), m.group(0), kind))
    # Stable order by position so downstream dedup is deterministic.
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits


def scan(text: str) -> list[Finding]:
    out: list[Finding] = []
    for start, end, value, kind in find_secret_candidates(text):
        out.append(
            Finding(
                category="api_key",
                value=value,
                start=start,
                end=end,
                confidence=0.95,
                source=SOURCE_VALIDATOR,
                validator=f"secrets.{kind}",
                notes=f"provider pattern: {kind}",
            )
        )
    return out
