"""Walk a filesystem path and run every validator against every text file.

The scanner knows nothing about individual PII categories — it just
dispatches to the validators, then annotates each Finding with the line
number where it occurred.

Known false-positive surface: the validator layer cannot tell a real
Aadhaar from a test fixture. Scanning Gnosk's own repository yields ~60
findings, almost all fixtures in tests/. Distinguishing real data from
fixtures is a job for the local model (see classifier.py).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from pathlib import Path

from gnosk.findings import Finding
from gnosk.validators import aadhaar, email, pan, phone, secrets

_VALIDATORS = (aadhaar, pan, email, phone, secrets)

_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", "bower_components",
    ".venv", "venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target",
    ".next", ".nuxt", ".svelte-kit",
    ".idea", ".vscode",
    "vendor",
    "coverage", "htmlcov",
})

_SKIP_EXTS = frozenset({
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov", ".avi", ".mkv",
    ".pdf", ".docx", ".xlsx", ".pptx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
})

_MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass(slots=True)
class FileFindings:
    path: Path
    findings: list[Finding] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.findings)


def _read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except UnicodeDecodeError:
            return None


def _is_scannable(path: Path) -> bool:
    if path.suffix.lower() in _SKIP_EXTS:
        return False
    try:
        return path.stat().st_size <= _MAX_FILE_BYTES
    except OSError:
        return False


def _line_of(text: str, offset: int) -> int:
    """Return the 1-indexed line number containing `offset`."""
    return text.count("\n", 0, offset) + 1


def scan_file(path: Path) -> FileFindings:
    """Run every validator against a single file. Never raises on I/O."""
    result = FileFindings(path=path)
    text = _read_text(path)
    if text is None:
        return result
    for validator in _VALIDATORS:
        result.findings.extend(validator.scan(text))
    result.findings = [
        replace(f, line=_line_of(text, f.start)) for f in result.findings
    ]
    result.findings.sort(key=lambda f: (f.start, f.end))
    return result


def _iter_candidate_files(root: Path) -> Iterator[Path]:
    """Yield files under `root` worth scanning. Prunes skip-dirs in-place."""
    if root.is_file():
        if _is_scannable(root):
            yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            if _is_scannable(path):
                yield path


def scan_path(root: Path) -> Iterator[FileFindings]:
    """Walk `root` and yield one FileFindings per scannable file."""
    for path in _iter_candidate_files(root):
        yield scan_file(path)
