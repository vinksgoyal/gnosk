"""Indian mobile phone number detection.

Indian mobile numbers are 10 digits, first digit 6-9. They are often
written with a +91 country code, sometimes with a leading 0 for domestic
dialing, and frequently with spaces or hyphens.

No checksum exists, so confidence is deliberately lower than Aadhaar or
PAN. Ten-digit runs show up inside order IDs and timestamps; a match here
is a hint, not a fact.
"""

from __future__ import annotations

import re

from gnosk.findings import SOURCE_VALIDATOR, Finding

# Forms covered:
#   +91 9876543210   +91-9876543210   +919876543210
#   0 9876543210     09876543210
#   9876543210       98765 43210      98765-43210
# First digit after country code / leading zero is 6-9.
_PHONE_RE = re.compile(
    r"(?<!\d)"                                   # no digit immediately before
    r"(?:\+91[\s\-]?|0)?"                        # optional country code or trunk 0
    r"([6-9]\d{4}[\s\-]?\d{5})"                  # 10-digit Indian mobile
    r"(?!\d)"                                    # no digit immediately after
)


def find_phone_candidates(text: str) -> list[tuple[int, int, str]]:
    if not isinstance(text, str):
        return []
    return [(m.start(), m.end(), m.group(0)) for m in _PHONE_RE.finditer(text)]






def _zero_count(digits: str) -> int:
    return digits.count("0")


def scan(text: str) -> list[Finding]:
    out: list[Finding] = []
    for start, end, value in find_phone_candidates(text):
        # Isolate the 10-digit payload, stripping separators and any
        # country code / trunk zero.
        digits = value.replace(" ", "").replace("-", "").replace("+91", "")
        if digits.startswith("0"):
            digits = digits[1:]
        # A real Indian mobile number almost never has 5 or more zeros.
        # Number-shaped strings inside machine-generated JSON (per-token
        # prices like 0.0000008125, IEEE-754 fractions) do this
        # constantly. Drop them rather than report them as low-confidence.
        if _zero_count(digits) >= 5:
            continue
        out.append(
            Finding(
                category="phone_in",
                value=value,
                start=start,
                end=end,
                confidence=0.6,
                source=SOURCE_VALIDATOR,
                validator="phone.in_shape",
                notes="no checksum; may be a coincidental 10-digit run",
            )
        )
    return out
