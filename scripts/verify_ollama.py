"""Verify that Ollama is running and the configured Gemma model responds.

Run this before any Gnosk code that depends on the model. If this
script fails, nothing downstream will work, and the failure will be a
foundation problem, not a Gnosk problem.

Usage:
    python scripts/verify_ollama.py
"""

from __future__ import annotations

import sys
import time

import ollama

# Chosen for 8 GB / 2-core CPU machines. gemma3:4b is better if you have
# the hardware; gemma2:2b is the pragmatic default for a laptop without
# a GPU.
MODEL = "gemma2:2b"
PROMPT = "Reply with only the word: ready"


def _extract_model_names(response: object) -> list[str]:
    """Pull model names from ollama.list() across client versions.

    Older clients return a dict; newer ones return a pydantic object with
    `.models`, and each entry may expose the name as `.name` or `.model`.
    Rather than pin to one version, accept all shapes.
    """
    models = getattr(response, "models", None)
    if models is None and isinstance(response, dict):
        models = response.get("models", [])
    if not models:
        return []

    names: list[str] = []
    for m in models:
        name = getattr(m, "model", None) or getattr(m, "name", None)
        if name is None and isinstance(m, dict):
            name = m.get("model") or m.get("name")
        if name:
            names.append(str(name))
    return names


def main() -> int:
    print("Checking Ollama at localhost:11434 ...")
    try:
        response = ollama.list()
    except Exception as exc:
        print(f"FAIL: cannot reach Ollama: {exc}")
        print("Is it running? Try: sudo systemctl start ollama")
        return 1

    names = _extract_model_names(response)
    print(f"Available models: {names}")
    if not any(n.startswith(MODEL) for n in names):
        print(f"FAIL: no model matching {MODEL!r} is pulled.")
        print(f"Try: ollama pull {MODEL}")
        return 1

    print(f"Sending test prompt to {MODEL} ...")
    t0 = time.monotonic()
    try:
        response = ollama.generate(model=MODEL, prompt=PROMPT)
    except Exception as exc:
        print(f"FAIL: model call raised: {exc}")
        return 1
    elapsed = time.monotonic() - t0

    text = ""
    if isinstance(response, dict):
        text = response.get("response", "")
    else:
        text = getattr(response, "response", "") or ""
    text = text.strip()

    print(f"Response: {text!r}")
    print(f"Latency: {elapsed:.2f}s")

    if "ready" not in text.lower():
        print("WARN: model responded but not with the expected word.")
        print("      This is usually fine — instruction-following varies.")
        return 0

    print("OK: Ollama is running and the model responds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
