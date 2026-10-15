"""Tests for the Ollama wrapper and its environment configuration.

All tests monkeypatch `_call_model`, so pytest never contacts Ollama and
never loads the model.
"""

from __future__ import annotations

import importlib
import warnings

import pytest

from gnosk import llm


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


# ---------------------------------------------------------------------------
# Environment resolution
# ---------------------------------------------------------------------------


class TestEnvHelper:
    def test_default_used_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("GNOSK_MODEL", raising=False)
        monkeypatch.delenv("VAULTSCAN_MODEL", raising=False)
        assert llm._env("MODEL", "fallback") == "fallback"

    def test_gnosk_prefix_wins(self, monkeypatch):
        monkeypatch.setenv("GNOSK_MODEL", "gnosk-value")
        monkeypatch.delenv("VAULTSCAN_MODEL", raising=False)
        assert llm._env("MODEL", "fallback") == "gnosk-value"

    def test_vaultscan_fallback_emits_warning(self, monkeypatch):
        monkeypatch.delenv("GNOSK_MODEL", raising=False)
        monkeypatch.setenv("VAULTSCAN_MODEL", "old-value")
        with pytest.warns(UserWarning, match="VAULTSCAN_ prefix is deprecated"):
            assert llm._env("MODEL", "fallback") == "old-value"

    def test_gnosk_set_suppresses_warning_even_if_vaultscan_set(self, monkeypatch):
        monkeypatch.setenv("GNOSK_MODEL", "new-value")
        monkeypatch.setenv("VAULTSCAN_MODEL", "old-value")
        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning becomes an error
            assert llm._env("MODEL", "fallback") == "new-value"

    def test_int_reader(self, monkeypatch):
        monkeypatch.delenv("VAULTSCAN_NUM_PREDICT", raising=False)
        monkeypatch.setenv("GNOSK_NUM_PREDICT", "64")
        assert llm._env_int("NUM_PREDICT", 999) == 64

    def test_float_reader(self, monkeypatch):
        monkeypatch.delenv("VAULTSCAN_TIMEOUT_S", raising=False)
        monkeypatch.setenv("GNOSK_TIMEOUT_S", "12.5")
        assert llm._env_float("TIMEOUT_S", 1.0) == 12.5

    def test_invalid_int_raises(self, monkeypatch):
        monkeypatch.delenv("VAULTSCAN_NUM_PREDICT", raising=False)
        monkeypatch.setenv("GNOSK_NUM_PREDICT", "not-a-number")
        with pytest.raises(ValueError):
            llm._env_int("NUM_PREDICT", 100)


class TestModuleConstantsReload:
    """The module-level constants should reflect the env at import time."""

    def _reload(self, monkeypatch, **env):
        for k in (
            "GNOSK_MODEL",
            "VAULTSCAN_MODEL",
            "GNOSK_TIMEOUT_S",
            "VAULTSCAN_TIMEOUT_S",
        ):
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        importlib.reload(llm)
        return llm

    def test_defaults(self, monkeypatch):
        m = self._reload(monkeypatch)
        assert m.DEFAULT_MODEL == "gemma2:2b"
        assert m.DEFAULT_TIMEOUT_S == 150.0
        assert m.DEFAULT_NUM_PREDICT == 180
        assert m.DEFAULT_NUM_CTX == 2048

    def test_gnosk_model_override(self, monkeypatch):
        m = self._reload(monkeypatch, GNOSK_MODEL="qwen2.5:0.5b")
        assert m.DEFAULT_MODEL == "qwen2.5:0.5b"

    def test_vaultscan_model_fallback_warns(self, monkeypatch):
        for k in ("GNOSK_MODEL", "GNOSK_TIMEOUT_S"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("VAULTSCAN_MODEL", "legacy-model")

        with pytest.warns(UserWarning, match="VAULTSCAN_ prefix is deprecated"):
            importlib.reload(llm)
        assert llm.DEFAULT_MODEL == "legacy-model"


# ---------------------------------------------------------------------------
# ask_json behavior
# ---------------------------------------------------------------------------


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
