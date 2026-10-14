"""PAN (Permanent Account Number) format validation.

A PAN is 10 characters: 5 uppercase letters, 4 digits, 1 uppercase letter.
The 4th letter encodes the holder type (individual, company, trust, etc.).
The 10th letter is a check character, but the algorithm is not public, so
Gnosk can only validate format and holder code — not authenticity.

This module does NOT verify that a PAN belongs to a real person or entity.
"""

from __future__ import annotations

import re

from gnosk.findings import SOURCE_VALIDATOR, Finding

# 10 characters: 5 letters, 4 digits, 1 letter. Word boundaries only.
PAN_RE = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")

# 4th character: holder type.
#   P Individual        C Company         H HUF
#   F Firm / LLP        A AOP             T Trust
#   B BOI               L Local Authority J Artificial Juridical Person
#   G Government
VALID_HOLDER_CODES = frozenset("PCHFATBLJG")


def is_valid_pan(value: str) -> bool:
    """Return True if `value` is a format-valid PAN with a known holder code.

    This does NOT confirm the PAN is real. PAN has no public checksum.
    """
    if not isinstance(value, str):
        return False
    if not PAN_RE.fullmatch(value):
        return False
    return value[3] in VALID_HOLDER_CODES


def find_pan_candidates(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, match) for every PAN-shaped substring in `text`."""
    if not isinstance(text, str):
        return []
    return [(m.start(), m.end(), m.group(0)) for m in PAN_RE.finditer(text)]


def scan(text: str) -> list[Finding]:
    """Return a Finding for every PAN-shaped substring in `text`.

    Format-valid PANs get confidence 0.7, not 1.0: there is no public
    checksum, so a shaped match could still be a random string.
    """
    out: list[Finding] = []
    for start, end, value in find_pan_candidates(text):
        holder_ok = value[3] in VALID_HOLDER_CODES
        out.append(
            Finding(
                category="pan",
                value=value,
                start=start,
                end=end,
                confidence=0.7 if holder_ok else 0.3,
                source=SOURCE_VALIDATOR,
                validator="pan.format",
                notes=(
                    "format-only; PAN has no public checksum"
                    if holder_ok
                    else f"unknown holder code {value[3]!r}"
                ),
            )
        )
    return out
