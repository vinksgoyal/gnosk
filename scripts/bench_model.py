"""Measure raw Ollama throughput on this machine.

Run once. Write the numbers into NOTES.md. They inform every prompt-shape
decision we make afterward.
"""

from __future__ import annotations

import time

import ollama

MODEL = "gemma2:2b"


def timed(prompt: str, label: str, *, num_predict: int = 100) -> None:
    t0 = time.monotonic()
    r = ollama.generate(
        model=MODEL,
        prompt=prompt,
        options={"num_ctx": 2048, "num_predict": num_predict, "temperature": 0.1},
    )
    dt = time.monotonic() - t0
    text = r.get("response", "") if isinstance(r, dict) else getattr(r, "response", "")
    eval_count = r.get("eval_count", 0) if isinstance(r, dict) else getattr(r, "eval_count", 0)
    tok_s = (eval_count / dt) if dt > 0 else 0.0
    print(f"[{label}] {dt:.1f}s for {eval_count} output tokens ({tok_s:.1f} tok/s)")
    print(f"    first 80 chars: {text[:80]!r}")


def main() -> None:
    # Warm load (first call loads model into RAM)
    timed("Say hi.", "warmup", num_predict=10)

    timed("Say hi.", "tiny", num_predict=10)
    timed("Write a haiku about rain.", "medium", num_predict=80)
    timed("A" * 2000 + "\nSummarize.", "long-prompt", num_predict=60)


if __name__ == "__main__":
    main()
