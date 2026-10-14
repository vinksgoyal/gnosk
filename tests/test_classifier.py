"""Tests for the fixture classifier.

`ask_json` is monkeypatched; pytest never talks to Ollama.
"""

from __future__ import annotations

import pytest

from vaultscan import classifier
from vaultscan.findings import Finding


def _make_finding(cat: str, val: str, start: int = 0) -> Finding:
    return Finding(
        category=cat,
        value=val,
        start=start,
        end=start + len(val),
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

    def test_prompt_includes_path_and_each_value(self, fake_ask):
        calls, replies = fake_ask
        replies.append({"judgments": []})
        findings = [
            _make_finding("aadhaar", "234567890124"),
            _make_finding("pan", "ABCPD1234E", start=50),
        ]
        classifier.classify_findings("src/seed.py", "fake file body", findings)
        prompt = calls[0]
        assert "src/seed.py" in prompt
        assert "234567890124" in prompt
        assert "ABCPD1234E" in prompt
        assert "0. [aadhaar]" in prompt
        assert "1. [pan]" in prompt


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
        assert "no judgment" in out[1].reason

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

    def test_missing_judgments_key(self, fake_ask):
        _, replies = fake_ask
        replies.append({"something_else": True})
        findings = [_make_finding("email", "a@x.com")]
        out = classifier.classify_findings("f.py", "", findings)
        assert out[0].verdict == "unknown"

    def test_llm_error_degrades_to_unknown(self, fake_ask):
        from vaultscan.llm import LLMError

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
        # No model call should have been made.
        assert calls == []

    def test_large_file_is_truncated(self, fake_ask):
        calls, replies = fake_ask
        replies.append({"judgments": []})
        big = "A" * (classifier._MAX_FILE_CHARS * 2)
        classifier.classify_findings("f.py", big, [_make_finding("email", "x@y.z")])
        assert "truncated for length" in calls[0]

    def test_finding_count_cap_recurses(self, fake_ask):
        calls, replies = fake_ask
        # 31 findings => two calls, first reply has judgments for 30.
        replies.append({"judgments": []})
        replies.append({"judgments": []})
        findings = [_make_finding("email", f"a{i}@x.com", start=i * 20) for i in range(31)]
        out = classifier.classify_findings("f.py", "body", findings)
        assert len(out) == 31
        assert len(calls) == 2
