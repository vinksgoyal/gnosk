"""The only module that talks to Ollama.

Every model call in Gnosk goes through `ask_json`. Keeping the Ollama
client behind a single tested interface means version drift, response
shape changes, and timeout quirks stay isolated here.

Configuration is read from environment variables at import time. The
canonical prefix is `GNOSK_*`; the older `VAULTSCAN_*` prefix is still
honored for users who set it before the project was renamed, and using
it emits a visible deprecation warning.
"""

from __future__ import annotations

import json
import os
import warnings
from typing import Any

import ollama

# ---------------------------------------------------------------------------
# Environment configuration
# ---------------------------------------------------------------------------

_DEPRECATION_NOTE = (
    "The VAULTSCAN_ prefix is deprecated; use GNOSK_{name} instead. "
    "The VAULTSCAN_ prefix will be removed in a future release."
)


def _env(name: str, default: str) -> str:
    """Read `GNOSK_<name>`, falling back to `VAULTSCAN_<name>` with a warning.

    Precedence: GNOSK_* > VAULTSCAN_* > default. If both are set, GNOSK
    wins silently and no warning fires.
    """
    new_key = f"GNOSK_{name}"
    old_key = f"VAULTSCAN_{name}"
    if new_key in os.environ:
        return os.environ[new_key]
    if old_key in os.environ:
        warnings.warn(
            _DEPRECATION_NOTE.format(name=name),
            UserWarning,
            stacklevel=2,
        )
        return os.environ[old_key]
    return default


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


DEFAULT_MODEL = _env("MODEL", "gemma2:2b")
DEFAULT_TIMEOUT_S = _env_float("TIMEOUT_S", 150.0)
DEFAULT_NUM_PREDICT = _env_int("NUM_PREDICT", 180)
DEFAULT_NUM_CTX = _env_int("NUM_CTX", 2048)

_RETRY_SUFFIX = (
    "\n\nPrevious response was not valid JSON. "
    "Respond with ONLY one JSON object. No prose, no fences. "
    'If you cannot answer, respond with {"error": "<reason>"}.'
)


class LLMError(RuntimeError):
    """Raised when the model fails to produce parseable JSON after retries."""


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


def _client(timeout: float) -> ollama.Client:
    # ollama-python exposes `timeout` on Client, giving a real HTTP-level
    # timeout — no dangling threads on cancellation.
    return ollama.Client(timeout=timeout)


def _call_model(prompt: str, model: str, timeout: float) -> str:
    """Thin wrapper around ollama.generate.

    This is the seam that tests monkeypatch. Everything above is pure
    logic; everything below is I/O.
    """
    response = _client(timeout).generate(
        model=model,
        prompt=prompt,
        format="json",
        options={
            "temperature": 0.1,
            "num_ctx": DEFAULT_NUM_CTX,
            "num_predict": DEFAULT_NUM_PREDICT,
        },
    )
    if isinstance(response, dict):
        return response.get("response", "")
    return getattr(response, "response", "") or ""


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        if text.startswith("json\n"):
            text = text[len("json\n"):]
        elif text.startswith("json"):
            text = text[len("json"):]
        text = text.rstrip("`").strip()
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ask_json(
    prompt: str,
    *,
    schema_hint: str = "a JSON object",
    model: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Ask the model for a JSON object. Retry once, then raise LLMError.

    `model` and `timeout` default to the module-level constants, which
    are resolved from the environment at import time.
    """
    if not prompt or not isinstance(prompt, str):
        raise ValueError("prompt must be a non-empty string")

    effective_model = model if model is not None else DEFAULT_MODEL
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_S

    full_prompt = f"{prompt}\n\nRespond with {schema_hint} as a single JSON object."

    last_raw = ""
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            raw = _call_model(full_prompt, effective_model, effective_timeout)
        except Exception as exc:
            raise LLMError(f"model call failed: {exc}") from exc
        last_raw = raw
        try:
            return _parse_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = exc
            if attempt == 2:
                break
            full_prompt = full_prompt + _RETRY_SUFFIX

    snippet = last_raw[:200].replace("\n", " ")
    raise LLMError(
        f"model did not return parseable JSON after 2 attempts: {last_err}. "
        f"Last response snippet: {snippet!r}"
    )
