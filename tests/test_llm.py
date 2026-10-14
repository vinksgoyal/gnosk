"""Tests for the Ollama wrapper.

All tests monkeypatch `_call_model`, so pytest never contacts Ollama and
never loads the model. The wrapper's contract is what we test here.
"""

from __future__ import annotations

import pytest

from vaultscan import llm


@pytest.fixture
def fake_calls(monkeypatch):
    """Record every prompt passed to _call_model and reply from a script."""
    calls: list[str] = []
    replies: list[str] = []

    def fake(prompt: str, model: str, timeout: float) -> str:
        calls.append(prompt)
        return replies.pop(0) if replies else "{}"

    monkeypatch.setattr(llm, "_call_model", fake)
    return calls, replies


class TestAskJsonHappyPath:
    def test_returns_parsed_dict(self, fake_calls):
        _, replies = fake_calls
        replies.append('{"answer": 42}')
        assert llm.ask_json("what is 6*7?") == {"answer": 42}

    def test_strips_markdown_fences(self, fake_calls):
        _, replies = fake_calls
        replies.append('```json\n{"ok": true}\n```')
        assert llm.ask_json("x") == {"ok": True}

    def test_strips_bare_fences(self, fake_calls):
        _, replies = fake_calls
        replies.append('```\n{"ok": true}\n```')
        assert llm.ask_json("x") == {"ok": True}

    def test_schema_hint_appears_in_prompt(self, fake_calls):
        calls, replies = fake_calls
        replies.append("{}")
        llm.ask_json("hi", schema_hint='{"answer": int}')
        assert '{"answer": int}' in calls[0]


class TestAskJsonRetries:
    def test_retries_once_then_succeeds(self, fake_calls):
        calls, replies = fake_calls
        replies.append("not json at all")
        replies.append('{"ok": true}')
        result = llm.ask_json("hi")
        assert result == {"ok": True}
        assert len(calls) == 2
        # Second prompt should include the retry suffix.
        assert "Previous response was not valid JSON" in calls[1]

    def test_raises_after_two_failures(self, fake_calls):
        _, replies = fake_calls
        replies.append("still not json")
        replies.append("also not json")
        with pytest.raises(llm.LLMError) as excinfo:
            llm.ask_json("hi")
        msg = str(excinfo.value)
        assert "parseable JSON" in msg
        assert "also not json" in msg

    def test_rejects_json_array(self, fake_calls):
        # format="json" sometimes lets arrays through; wrapper must reject.
        _, replies = fake_calls
        replies.append("[1, 2, 3]")
        replies.append("[4, 5, 6]")
        with pytest.raises(llm.LLMError):
            llm.ask_json("hi")


class TestAskJsonInputs:
    def test_rejects_empty_prompt(self):
        with pytest.raises(ValueError):
            llm.ask_json("")

    def test_rejects_non_string_prompt(self):
        with pytest.raises(ValueError):
            llm.ask_json(None)  # type: ignore[arg-type]


class TestTimeout:
    def test_timeout_raises_llm_error(self, monkeypatch):
        import time

        def slow(prompt: str, model: str) -> str:
            time.sleep(2.0)
            return "{}"

        monkeypatch.setattr(llm, "_call_model", slow)
        with pytest.raises(llm.LLMError) as excinfo:
            llm.ask_json("hi", timeout=0.3)
        assert "timeout" in str(excinfo.value).lower()
