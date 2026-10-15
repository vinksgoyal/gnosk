"""Deterministic pre-classification for findings.

Triage runs before the model. It decides what it can decide using rules,
and defers everything else. Findings triage resolves never reach the
LLM, which is what keeps a typical scan to a handful of model calls
instead of one per finding.

Rules, in order:

1. Known fixture values — addresses at reserved example domains,
   common tutorial local-parts, AWS's documented example keys — are
   fixtures. This wins over everything else.

2. API keys are always sent to the model. A provider-shaped secret can
   leak from anywhere, including a test file. Path heuristics are not
   strong enough to dismiss one.

3. Checksum-valid Aadhaar is `likely_real` (needs review) outside test
   paths — the checksum proves format validity, not that the number
   belongs to a real person. Inside a test path, a checksum-valid
   Aadhaar goes to the model: the number could be either a well-
   constructed fixture or a genuine leak, and only the model can tell.

4. Findings in test, fixture, example, sample, or spec paths are
   fixtures — unless rule 2 or rule 3 already deferred.

5. Everything else defers to the model.
"""

from __future__ import annotations

from gnosk.findings import Finding
from gnosk.validators.aadhaar import is_valid_aadhaar

VERDICT_FIXTURE = "fixture"
VERDICT_LIKELY_REAL = "likely_real"

# Path segments that indicate test, fixture, or example code.
_TEST_SEGMENTS = frozenset({
    "tests", "test", "fixtures", "fixture",
    "examples", "example", "sample_data", "samples",
    "spec", "specs", "__tests__", "testing",
})

# Reserved example domains (RFC 2606 plus common conventions).
_FIXTURE_DOMAINS = frozenset({
    "example.com", "example.org", "example.net",
    "test.local", "localhost",
})

# Email local-parts that appear in every tutorial.
_FIXTURE_LOCALPARTS = frozenset({
    "test", "user", "admin", "demo", "sample",
    "alice", "bob", "carol", "dave",
    "foo", "bar", "baz",
    "someone", "noreply",
})

# Exact values documented by vendors as examples, not real secrets.
_FIXTURE_VALUES = frozenset({
    "AKIAIOSFODNN7EXAMPLE",
    "AKIAI44QH8DHBEXAMPLE",
})


def is_test_path(path: str) -> bool:
    """True if `path` looks like test, fixture, or example code."""
    segments = path.replace("\\", "/").lower().split("/")
    for seg in segments:
        if seg in _TEST_SEGMENTS:
            return True
        stem = seg.split(".", 1)[0]
        if stem.startswith("test_") or stem.endswith("_test"):
            return True
        if ".test." in seg or ".spec." in seg:
            return True
    return False


def is_known_fixture_value(value: str) -> bool:
    """True if `value` is a documented example, not real data."""
    if value in _FIXTURE_VALUES:
        return True
    if "@" in value:
        local, _, domain = value.partition("@")
        if domain.lower() in _FIXTURE_DOMAINS:
            return True
        if local.lower() in _FIXTURE_LOCALPARTS:
            return True
    return False


def triage(finding: Finding, path: str) -> tuple[str, str] | None:
    """Return (verdict, reason) if the rules can decide, else None."""
    # Rule 1 — known fixture values win over everything.
    if is_known_fixture_value(finding.value):
        return (VERDICT_FIXTURE, "value matches a documented example")

    # Rule 2 — API keys always go to the model.
    if finding.category == "api_key":
        return None

    # Rule 3 — checksum-valid Aadhaar.
    if finding.category == "aadhaar" and is_valid_aadhaar(finding.value):
        if is_test_path(path):
            return None  # ambiguous: well-formed Aadhaar inside test code
        return (
            VERDICT_LIKELY_REAL,
            "checksum-valid Aadhaar; format only, verify with the subject",
        )

    # Rule 4 — test path dismisses the remaining categories.
    if is_test_path(path):
        return (VERDICT_FIXTURE, "path indicates test/example code")

    # Rule 5 — defer to the model.
    return None


def count_needs_model(path: str, findings: list[Finding]) -> int:
    """Count findings that the model will actually see."""
    return sum(1 for f in findings if triage(f, path) is None)
