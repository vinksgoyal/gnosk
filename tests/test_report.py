"""Tests for the markdown data inventory generator."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from gnosk.findings import Finding
from gnosk.report import build_inventory, redact
from gnosk.scanner import FileFindings


def _f(
    cat: str,
    val: str,
    line: int,
    start: int = 0,
    conf: float = 1.0,
) -> Finding:
    return Finding(
        category=cat,
        value=val,
        start=start,
        end=start + len(val),
        confidence=conf,
        source="validator",
        validator=f"{cat}.test",
        line=line,
    )


class TestRedact:
    def test_long_value_keeps_edges(self):
        assert redact("ABCDEFGHIJ") == "AB******IJ"

    def test_short_value_fully_masked(self):
        assert redact("abc") == "***"
        assert redact("a") == "*"

    def test_four_char_value(self):
        assert redact("abcd") == "abcd"

    def test_does_not_leak_middle(self):
        out = redact("234567890124")
        assert "5678" not in out
        assert out.startswith("23")
        assert out.endswith("24")


class TestEmptyScan:
    def test_no_findings_message(self):
        out = build_inventory(
            [FileFindings(path=Path("a.py"))],
            project_path="./proj",
            scan_date=date(2026, 10, 15),
        )
        assert "# Gnosk Data Inventory" in out
        assert "Total findings: 0" in out
        assert "No PII-shaped data was detected" in out

    def test_disclaimer_always_present(self):
        out = build_inventory([], project_path="./x", scan_date=date(2026, 1, 1))
        assert "not a compliance certification" in out
        assert "redacted" in out.lower()


class TestWithFindings:
    def test_summary_table(self):
        results = [
            FileFindings(
                path=Path("src/seed.py"),
                findings=[
                    _f("aadhaar", "234567890124", line=4),
                    _f("aadhaar", "234567890124", line=10, start=200),
                    _f("pan", "ABCPD1234E", line=12, start=400, conf=0.7),
                ],
            ),
        ]
        out = build_inventory(
            results, project_path="./proj", scan_date=date(2026, 10, 15)
        )
        assert "Total findings: 3" in out
        assert "| aadhaar | 2 |" in out
        assert "| pan | 1 |" in out

    def test_per_file_section(self):
        results = [
            FileFindings(
                path=Path("src/config.py"),
                findings=[_f("email", "admin@client.com", line=7)],
            ),
        ]
        out = build_inventory(
            results, project_path="./proj", scan_date=date(2026, 10, 15)
        )
        assert "### `src/config.py`" in out
        assert "| 7 | email | 1.00 |" in out

    def test_values_are_redacted_in_output(self):
        raw = "234567890124"
        results = [
            FileFindings(
                path=Path("f.py"),
                findings=[_f("aadhaar", raw, line=1)],
            ),
        ]
        out = build_inventory(
            results, project_path="./p", scan_date=date(2026, 10, 15)
        )
        assert raw not in out

    def test_file_without_findings_not_listed(self):
        results = [
            FileFindings(path=Path("a.py")),
            FileFindings(
                path=Path("b.py"),
                findings=[_f("email", "x@y.com", line=1)],
            ),
        ]
        out = build_inventory(
            results, project_path="./p", scan_date=date(2026, 10, 15)
        )
        assert "### `a.py`" not in out
        assert "### `b.py`" in out

    def test_files_sorted(self):
        results = [
            FileFindings(path=Path("z.py"), findings=[_f("email", "a@b.c", line=1)]),
            FileFindings(path=Path("a.py"), findings=[_f("email", "d@e.f", line=1)]),
        ]
        out = build_inventory(
            results, project_path="./p", scan_date=date(2026, 10, 15)
        )
        assert out.index("### `a.py`") < out.index("### `z.py`")

    def test_missing_line_shows_question_mark(self):
        f = Finding(
            category="email",
            value="a@b.c",
            start=0,
            end=5,
            confidence=0.9,
            source="validator",
            validator="email.test",
        )
        results = [FileFindings(path=Path("f.py"), findings=[f])]
        out = build_inventory(
            results, project_path="./p", scan_date=date(2026, 10, 15)
        )
        assert "| ? | email |" in out


class TestLineAnnotation:
    def test_scanner_sets_line_number(self, tmp_path: Path):
        from gnosk.scanner import scan_file

        p = tmp_path / "x.py"
        p.write_text("line one\nline two\nemail: a@b.com\nline four\n")
        result = scan_file(p)
        [f] = [x for x in result.findings if x.category == "email"]
        assert f.line == 3

    def test_line_is_one_indexed(self, tmp_path: Path):
        from gnosk.scanner import scan_file

        p = tmp_path / "x.txt"
        p.write_text("a@b.com\n")
        [f] = [x for x in scan_file(p).findings if x.category == "email"]
        assert f.line == 1
