"""The only module that talks to Ollama.

Every model call in VaultScan goes through `ask_json`. Keeping the Ollama
client behind a single tested interface means version drift, response
shape changes, and timeout quirks stay isolated here.

The caller supplies a prompt and a short hint describing the expected JSON
shape. The model is instructed to emit JSON; the response is parsed,
validated as a dict, and returned. On parse failure the call is retried
once with a stricter prompt before raising `LLMError`.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

import ollama

DEFAULT_MODEL = os.environ.get("VAULTSCAN_MODEL", "gemma2:2b")
DEFAULT_TIMEOUT_S = 180.0
_RETRY_SUFFIX = (
    "\n\nYour previous response was not valid JSON. "
    "Respond with ONLY a single JSON object. "
    "No prose, no markdown fences, no explanation. "
    "If you cannot answer, respond with {\"error\": \"<short reason>\"}."
)


class LLMError(RuntimeError):
    """Raised when the model fails to produce parseable JSON after retries."""


def _call_model(prompt: str, model: str) -> str:
    """Thin wrapper around ollama.generate.

    This is the seam that tests monkeypatch. Everything above this line is
    pure logic; everything below is I/O.
    """
    response = ollama.generate(
        model=model,
        prompt=prompt,
        format="json",
        options={"temperature": 0.1},
    )
    if isinstance(response, dict):
        return response.get("response", "")
    return getattr(response, "response", "") or ""


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse `raw` as a JSON object. Raise ValueError on anything else."""
    text = raw.strip()
    # Some models still wrap output in ```json fences despite format="json".
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


def _generate_with_timeout(prompt: str, model: str, timeout: float) -> str:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_call_model, prompt, model)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            # We cannot kill the worker thread; it will finish on its own.
            # The caller, however, gets a clean timeout.
            raise LLMError(f"model call exceeded {timeout:.0f}s timeout") from exc


def ask_json(
    prompt: str,
    *,
    schema_hint: str = "a JSON object",
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT_S,
) -> dict[str, Any]:
    """Ask the model for a JSON object. Retry once, then raise LLMError.

    `schema_hint` is appended to the prompt as a one-line reminder of the
    expected shape. It is guidance, not enforcement; the enforcement is
    the JSON parse below.
    """
    if not prompt or not isinstance(prompt, str):
        raise ValueError("prompt must be a non-empty string")

    full_prompt = f"{prompt}\n\nRespond with {schema_hint} as a single JSON object."

    last_raw = ""
    last_err: Exception | None = None
    for attempt in (1, 2):
        raw = _generate_with_timeout(full_prompt, model, timeout)
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
