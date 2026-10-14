"""Shared structured output type for all Gnosk detectors.

Every detector — deterministic validator or local model — emits `Finding`
objects. Nothing downstream should ever need to know which kind of
detector produced a Finding except by reading `.source`.
"""

from __future__ import annotations

from dataclasses import dataclass

SOURCE_VALIDATOR = "validator"
SOURCE_MODEL = "model"


@dataclass(frozen=True, slots=True)
class Finding:
    """One detected piece of potentially-sensitive data.

    `start` and `end` are character offsets into whatever text was
    scanned. `value` is the raw matched substring — callers are
    responsible for redacting it before writing to disk or stdout.

    `line` is 1-indexed and optional; validators leave it as None and the
    scanner fills it in, since only the scanner has the source text.
    """

    category: str
    value: str
    start: int
    end: int
    confidence: float
    source: str
    validator: str
    notes: str | None = None
    line: int | None = None
