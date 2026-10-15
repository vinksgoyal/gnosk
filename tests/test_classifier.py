"""Tests for the two-layer classifier.

`ask_json` is monkeypatched, so pytest never talks to Ollama. Triage
runs for real — its behavior is deterministic and fast.
"""

from __future__ import annotations

import pytest

from gnosk import classifier
from gnosk.classifier import SOURCE_MODEL, SOURCE_TRIAGE
from gnosk.findings import Finding


def _f(
    cat: str,
    val: str,
    start: int = 0,
    conf: float = 0.9,
    validator: str | None = None,
) -> Finding:
    return Finding(
        category=cat,
        value=val,
        start=start,
        end=start + len(val),
        confidence=conf,
        source="validator",
        validator=validator or f"{cat}.test",
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


class TestAllTriaged:
    def test_no_model_call_when_all_triaged(self, fake_ask):
        calls, _ = fake_ask
        findings = [
            _f("email", "someone@client.com"),
            _f("phone_in", "9876543210"),
            _f("pan", "ABCPD1234E"),
        ]
        result = classifier.classify_findings("tests/test_x.py", "body", findings)
        assert len(result) == 3
        assert all(r.verdict == "fixture" for r in result)
        assert all(r.source == SOURCE_TRIAGE for r in result)
        assert calls == []


class TestMixed:
    def test_only_untriaged_reach_model(self, fake_ask):
        calls, replies = fake_ask
        findings = [
            _f("email", "alice@example.com"),
            _f("api_key", "AKIA1234567890ABCDEF"),
        ]
        replies.append({"judgments": [{"index": 0, "verdict": "fixture"}]})
        result = classifier.classify_findings("tests/test_aws.py", "body", findings)
        assert len(result) == 2
        assert result[0].source == SOURCE_TRIAGE
        assert result[1].source == SOURCE_MODEL
        assert result[1].verdict == "fixture"
        assert len(calls) == 1
        # The deferred finding appears in the Items section; the triaged
        # one does not. (The rules block mentions alice@example.com as an
        # example of a fixture email, so a plain substring check is wrong.)
        items_section = calls[0].split("Items:", 1)[1]
        assert "AKIA1234567890ABCDEF" in items_section
        assert "alice@example.com" not in items_section

    def test_order_preserved_across_triage_and_model(self, fake_ask):
        _, replies = fake_ask
        findings = [
            _f("email", "alice@example.com"),
            _f("api_key", "AKIA1234567890ABCDEF", start=50),
            _f("phone_in", "9876543210", start=100),
        ]
        replies.append({"judgments": [{"index": 0, "verdict": "real"}]})
        result = classifier.classify_findings("tests/x.py", "body", findings)
        assert [r.finding.value for r in result] == [
            "alice@example.com",
            "AKIA1234567890ABCDEF",
            "9876543210",
        ]
        assert result[1].source == SOURCE_MODEL
        assert result[1].verdict == "real"


class TestModelBatching:
    def test_deferred_findings_batch_at_cap(self, fake_ask):
        calls, replies = fake_ask
        findings = [
            _f("api_key", f"AKIA{i:016d}", start=i * 30)
            for i in range(12)
        ]
        for _ in range(3):
            replies.append({"judgments": []})
        result = classifier.classify_findings("src/keys.py", "body", findings)
        assert len(result) == 12
        assert len(calls) == 3


class TestModelFailure:
    def test_llm_error_becomes_unknown_with_model_source(self, fake_ask):
        from gnosk.llm import LLMError

        _, replies = fake_ask
        replies.append(LLMError("simulated failure"))
        findings = [_f("api_key", "AKIA1234567890ABCDEF")]
        result = classifier.classify_findings("src/aws.py", "body", findings)
        assert result[0].verdict == "unknown"
        assert result[0].source == SOURCE_MODEL
        assert "model call failed" in result[0].reason


class TestEdges:
    def test_empty_findings_returns_empty(self, fake_ask):
        calls, _ = fake_ask
        assert classifier.classify_findings("f.py", "text", []) == []
        assert calls == []

    def test_invalid_verdict_from_model_downgrades_to_unknown(self, fake_ask):
        _, replies = fake_ask
        findings = [_f("api_key", "AKIA1234567890ABCDEF")]
        replies.append({"judgments": [{"index": 0, "verdict": "maybe"}]})
        result = classifier.classify_findings("src/aws.py", "body", findings)
        assert result[0].verdict == "unknown"

    def test_model_cannot_return_likely_real(self, fake_ask):
        _, replies = fake_ask
        findings = [_f("api_key", "AKIA1234567890ABCDEF")]
        replies.append({"judgments": [{"index": 0, "verdict": "likely_real"}]})
        result = classifier.classify_findings("src/aws.py", "body", findings)
        assert result[0].verdict == "unknown"
