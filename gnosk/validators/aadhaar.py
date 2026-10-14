"""Aadhaar number validation using the Verhoeff checksum.

Aadhaar is a 12-digit identifier issued by UIDAI in India. The last digit
is a Verhoeff checksum over the first 11. The first digit is always 2-9;
0 and 1 are not issued.

This module validates *format and checksum only*. It says nothing about
whether an Aadhaar number belongs to a real person, and its output must
never be used to log, store, or transmit Aadhaar numbers verbatim.
"""

from __future__ import annotations

import re

from gnosk.findings import SOURCE_VALIDATOR, Finding

# 12 digits total; first is 2-9; word boundaries so we don't match inside
# longer digit runs (e.g. a 16-digit order ID).
AADHAAR_RE = re.compile(r"\b[2-9]\d{11}\b")

# Verhoeff algorithm tables. Do not edit these by hand.
_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def _verhoeff_is_valid(digits: str) -> bool:
    """Return True if `digits` (a str of 0-9) passes the Verhoeff checksum."""
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def is_valid_aadhaar(number: str) -> bool:
    """Return True if `number` is a well-formed Aadhaar with a valid checksum.

    Tolerates spaces and hyphens as separators (people write them a lot).
    Does NOT confirm the Aadhaar belongs to a real person.
    """
    if not isinstance(number, str):
        return False
    cleaned = number.replace(" ", "").replace("-", "")
    if len(cleaned) != 12 or not cleaned.isdigit():
        return False
    if cleaned[0] in "01":
        return False
    return _verhoeff_is_valid(cleaned)


def find_aadhaar_candidates(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, match) for every Aadhaar-shaped substring.

    "Shaped" means 12 digits, first is 2-9. The checksum is NOT verified
    here — callers decide whether to keep checksum-invalid candidates.
    Returning near-misses is deliberate: during remediation it's useful to
    surface a number that looks like an Aadhaar but fails the checksum, so
    the user can investigate.
    """
    if not isinstance(text, str):
        return []
    return [(m.start(), m.end(), m.group(0)) for m in AADHAAR_RE.finditer(text)]


def scan(text: str) -> list[Finding]:
    """Return a Finding for every Aadhaar-shaped substring in `text`.

    Checksum-valid matches get confidence 1.0. Shaped matches that fail
    the checksum get confidence 0.3 and a note — they are surfaced on
    purpose so a human can investigate near-misses.
    """
    out: list[Finding] = []
    for start, end, value in find_aadhaar_candidates(text):
        ok = _verhoeff_is_valid(value)
        out.append(
            Finding(
                category="aadhaar",
                value=value,
                start=start,
                end=end,
                confidence=1.0 if ok else 0.3,
                source=SOURCE_VALIDATOR,
                validator="aadhaar.verhoeff",
                notes=None if ok else "checksum failed; possible near-miss",
            )
        )
    return out
