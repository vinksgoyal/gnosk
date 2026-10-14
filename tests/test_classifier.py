"""Tests for the fixture classifier.

`ask_json` is monkeypatched; pytest never talks to Ollama. Prompt shape
tests are strict because prompt size drives latency on this hardware.
"""

from __future__ import annotations

import pytest

from gnosk import classifier
from gnosk.findings import Finding


def _make_finding(
    cat: str, val: str, start: int = 0, end: int | None = None
) -> Finding:
    return Finding(
        category=cat,
        value=val,
        start=start,
        end=end if end is not None else start + len(val),
        confidence=1.0,
        source="validator",
        validator=f"{cat}.test",
    )


@pytest.fixture
def fake_ask(monkeypatch):
    calls: list[str] = []
    replies: list[dict | Exception] = []

    def fake(prompt: str, **_: object) -> dict:
        calls.append(prompt)
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(classifier, "ask_json", fake)
    return calls, replies


class TestExtractLineContext:
    def test_single_line(self):
        text = 'assert is_valid_aadhaar("234567890124") is True'
        ctx = classifier._extract_line_context(text, 25, 37)
        assert ctx == text

    def test_picks_containing_line_only(self):
        text = "line one\nemail: a@x.com\nline three"
        start = text.index("a@x.com")
        ctx = classifier._extract_line_context(text, start, start + 7)
        assert ctx == "email: a@x.com"

    def test_first_line(self):
        text = "first a@x.com\nsecond"
        start = text.index("a@x.com")
        assert classifier._extract_line_context(text, start, start + 7) == "first a@x.com"

    def test_last_line_no_trailing_newline(self):
        text = "first\nlast a@x.com"
        start = text.index("a@x.com")
        assert classifier._extract_line_context(text, start, start + 7) == "last a@x.com"

    def test_truncates_long_line(self):
        long_line = "x" * 500 + " a@x.com"
        start = long_line.index("a@x.com")
        ctx = classifier._extract_line_context(long_line, start, start + 7)
        assert len(ctx) <= classifier._MAX_LINE_CHARS + 3  # +3 for '...'
        assert ctx.endswith("...")

    def test_empty_text(self):
        assert classifier._extract_line_context("", 0, 5) == ""

    def test_out_of_bounds(self):
        assert classifier._extract_line_context("abc", -1, 2) == ""
        assert classifier._extract_line_context("abc", 99, 100) == ""

    def test_blank_line_returns_empty(self):
        # Span points at whitespace-only line.
        text = "real\n   \nother"
        assert classifier._extract_line_context(text, 6, 8) == ""


class TestPromptShape:
    def test_prompt_is_compact(self, fake_ask):
        calls, replies = fake_ask
        replies.append({"judgments": []})
        text = "assert is_valid_aadhaar(\"234567890124\") is True\n" * 50
        findings = [
            _make_finding("aadhaar", "234567890124", start=i * 45)
            for i in range(5)
        ]
        classifier.classify_findings("tests/test_aadhaar.py", text, findings)
        # Prompt budget for this hardware: keep under 900 chars.
        assert len(calls[0]) < 900, f"prompt too large: {len(calls[0])} chars"

    def test_prompt_includes_path_and_values(self, fake_ask):
        calls, replies = fake_ask
        replies.append({"judgments": []})
        findings = [
            _make_finding("aadhaar", "234567890124"),
            _make_finding("pan", "ABCPD1234E", start=50),
        ]
        classifier.classify_findings("src/seed.py", "body text", findings)
        p = calls[0]
        assert "src/seed.py" in p
        assert "234567890124" in p
        assert "ABCPD1234E" in p
        assert "0. [aadhaar]" in p
        assert "1. [pan]" in p

    def test_prompt_does_not_contain_full_file(self, fake_ask):
        calls, replies = fake_ask
        replies.append({"judgments": []})
        # A distinctive marker deep in the file that no finding points to.
        marker = "UNIQUEMARKER_SHOULD_NOT_APPEAR"
        text = "filler\n" * 40 + marker + "\nmore filler"
        findings = [_make_finding("email", "a@x.com", start=0)]
        classifier.classify_findings("f.py", text, findings)
        assert marker not in calls[0]


class TestHappyPath:
    def test_two_findings_one_fixture_one_real(self, fake_ask):
        _, replies = fake_ask
        replies.append(
            {
                "judgments": [
                    {"index": 0, "verdict": "fixture", "reason": "test data"},
                    {"index": 1, "verdict": "real", "reason": "in production config"},
                ]
            }
        )
        findings = [
            _make_finding("email", "alice@example.com"),
            _make_finding("email", "admin@clientcompany.com", start=100),
        ]
        out = classifier.classify_findings("tests/a.py", "...", findings)
        assert len(out) == 2
        assert out[0].verdict == "fixture"
        assert out[1].verdict == "real"
        assert out[0].finding.value == "alice@example.com"


class TestDegradedCases:
    def test_missing_judgments_become_unknown(self, fake_ask):
        _, replies = fake_ask
        replies.append(
            {"judgments": [{"index": 0, "verdict": "fixture", "reason": "x"}]}
        )
        findings = [
            _make_finding("email", "a@x.com"),
            _make_finding("email", "b@x.com", start=20),
        ]
        out = classifier.classify_findings("f.py", "", findings)
        assert out[1].verdict == "unknown"

    def test_invalid_index_ignored(self, fake_ask):
        _, replies = fake_ask
        replies.append(
            {
                "judgments": [
                    {"index": 99, "verdict": "real", "reason": "bogus"},
                    {"index": 0, "verdict": "real", "reason": "valid"},
                ]
            }
        )
        findings = [_make_finding("email", "a@x.com")]
        out = classifier.classify_findings("f.py", "", findings)
        assert out[0].verdict == "real"

    def test_invalid_verdict_ignored(self, fake_ask):
        _, replies = fake_ask
        replies.append(
            {"judgments": [{"index": 0, "verdict": "maybe", "reason": "x"}]}
        )
        findings = [_make_finding("email", "a@x.com")]
        out = classifier.classify_findings("f.py", "", findings)
        assert out[0].verdict == "unknown"

    def test_llm_error_degrades_to_unknown(self, fake_ask):
        from gnosk.llm import LLMError

        _, replies = fake_ask
        replies.append(LLMError("simulated failure"))
        findings = [_make_finding("email", "a@x.com")]
        out = classifier.classify_findings("f.py", "", findings)
        assert out[0].verdict == "unknown"
        assert "model call failed" in out[0].reason


class TestBoundaries:
    def test_empty_findings_returns_empty(self, fake_ask):
        calls, _ = fake_ask
        assert classifier.classify_findings("f.py", "text", []) == []
        assert calls == []

    def test_finding_count_cap_recurses(self, fake_ask):
        calls, replies = fake_ask
        # 20 findings with cap of 5 => 4 calls (5 + 5 + 5 + 5).
        for _ in range(4):
            replies.append({"judgments": []})
        findings = [
            _make_finding("email", f"a{i}@x.com", start=i * 20) for i in range(20)
        ]
        out = classifier.classify_findings("f.py", "body", findings)
        assert len(out) == 20
        assert len(calls) == 4
