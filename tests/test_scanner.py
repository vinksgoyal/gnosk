"""Tests for the filesystem scanner."""

from pathlib import Path

from gnosk.scanner import scan_file, scan_path


def test_scan_file_finds_aadhaar(tmp_path: Path) -> None:
    f = tmp_path / "data.txt"
    f.write_text("ID: 234567890124")
    result = scan_file(f)
    assert any(x.category == "aadhaar" for x in result.findings)


def test_scan_file_finds_multiple_categories(tmp_path: Path) -> None:
    f = tmp_path / "config.py"
    f.write_text('EMAIL = "alice@example.com"\nTOKEN = "ghp_' + "A" * 36 + '"\n')
    result = scan_file(f)
    categories = {x.category for x in result.findings}
    assert {"email", "api_key"} <= categories


def test_scan_file_returns_empty_for_clean_file(tmp_path: Path) -> None:
    f = tmp_path / "README.md"
    f.write_text("Just prose. Nothing to see here.")
    assert scan_file(f).count == 0


def test_scan_file_skips_binary(tmp_path: Path) -> None:
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01AKIAIOSFODNN7EXAMPLE")
    assert scan_file(f).count == 0


def test_scan_file_latin1_fallback(tmp_path: Path) -> None:
    f = tmp_path / "latin.txt"
    f.write_bytes("café alice@example.com".encode("latin-1"))
    result = scan_file(f)
    assert any(x.category == "email" for x in result.findings)


def test_scan_path_walks_directory(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("email: alice@example.com")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("phone: 9876543210")
    results = list(scan_path(tmp_path))
    assert len(results) == 2
    values = {f.value for r in results for f in r.findings}
    assert "alice@example.com" in values
    assert "9876543210" in values


def test_scan_path_skips_node_modules(tmp_path: Path) -> None:
    nm = tmp_path / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("email: bad@example.com")
    (tmp_path / "app.js").write_text("email: good@example.com")
    results = list(scan_path(tmp_path))
    assert len(results) == 1
    assert results[0].path.name == "app.js"


def test_scan_path_skips_binary_extensions(tmp_path: Path) -> None:
    (tmp_path / "image.png").write_bytes(b"\x89PNG AKIAIOSFODNN7EXAMPLE")
    (tmp_path / "text.txt").write_text("clean")
    names = [r.path.name for r in scan_path(tmp_path)]
    assert "image.png" not in names
    assert "text.txt" in names


def test_scan_path_accepts_single_file(tmp_path: Path) -> None:
    f = tmp_path / "one.txt"
    f.write_text("email: alice@example.com")
    results = list(scan_path(f))
    assert len(results) == 1
    assert results[0].path == f


def test_findings_sorted_by_offset(tmp_path: Path) -> None:
    f = tmp_path / "mixed.txt"
    f.write_text("email: alice@example.com and phone 9876543210")
    result = scan_file(f)
    starts = [x.start for x in result.findings]
    assert starts == sorted(starts)


def test_scanner_skips_tool_directories(tmp_path: Path) -> None:
    """Tool-generated session dirs and caches must not be walked."""
    for d in (".backboard", ".cache"):
        sub = tmp_path / d / "nested"
        sub.mkdir(parents=True)
        (sub / "log.jsonl").write_text('"price": "0.0000008125"')
    (tmp_path / "real.py").write_text("EMAIL = 'real@client.com'")

    results = list(scan_path(tmp_path))
    names = [r.path.name for r in results]
    assert "log.jsonl" not in names
    assert "real.py" in names
