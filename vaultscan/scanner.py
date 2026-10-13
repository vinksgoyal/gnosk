"""Walk a filesystem path and run every validator against every text file.

The scanner knows nothing about individual PII categories — it just
dispatches to the validators and collects what they return. Adding a new
validator is a one-line change to `_VALIDATORS`.
Known false-positive surface, observed on 2026-10-13 by scanning
VaultScan's own repository: the validator layer cannot tell a real
Aadhaar from a test fixture. A clean run on VaultScan's own source
produced ~60 findings, almost all of them sample data in tests/.
Distinguishing real customer data from fixtures is a job for the local
model (see docs/ for the model contract). Do not try to patch this with
more regex; a path-based rule would be brittle and would miss fixtures
embedded in non-test files.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from vaultscan.findings import Finding
from vaultscan.validators import aadhaar, email, pan, phone, secrets

# Every module here must expose `scan(text: str) -> list[Finding]`.
_VALIDATORS = (aadhaar, pan, email, phone, secrets)

# Directory names to prune entirely during the walk.
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

# Extensions that are never scannable text.
_SKIP_EXTS = frozenset({
    # Bytecode / native
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".o", ".a",
    # Archives
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
    # Audio / video
    ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".mov", ".avi", ".mkv",
    # Documents handled by dedicated parsers later
    ".pdf", ".docx", ".xlsx", ".pptx",
    # Fonts
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    # Databases
    ".db", ".sqlite", ".sqlite3",
    # Lockfiles
    ".lock",
})

_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MiB


@dataclass(slots=True)
class FileFindings:
    """Findings from a single file. Empty list means the file was clean."""

    path: Path
    findings: list[Finding] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.findings)


def _read_text(path: Path) -> str | None:
    """Return decoded text, or None if the file looks binary or unreadable."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    # Null byte in the first block is the classic binary signal.
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


def scan_file(path: Path) -> FileFindings:
    """Run every validator against a single file. Never raises on I/O."""
    result = FileFindings(path=path)
    text = _read_text(path)
    if text is None:
        return result
    for validator in _VALIDATORS:
        result.findings.extend(validator.scan(text))
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
