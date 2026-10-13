# DEV post notes

## Numbers from Day 1 (2026-10-13)

- Hardware: Kali Linux, 2 CPU cores, 7.7 GB RAM, no GPU
- Model: gemma2:2b (1.6 GB)
- Latency for "reply with ready": ___ seconds
- Latency for simple JSON ask: ___ seconds
- Test count at end of Day 1: 78
- Validators done: aadhaar (Verhoeff), pan, email, phone (IN), secrets (12 provider patterns)
- Scanner: walks files, prunes node_modules/.git/.venv/etc, null-byte binary sniff, 5 MiB cap

## Real problems hit today

1. My hand-computed Verhoeff check digit for a test fixture was wrong;
   the validator caught it. First piece of evidence for "deterministic first."
2. Ruff flagged a premature micro-optimization (function-level import to
   avoid a circular import that didn't exist).
3. `ollama` Python client returns a different shape than the CLI suggests;
   `m.get("name")` returned ''. Wrapper in llm.py isolates this.
4. Scanner run against VaultScan's own repo: 63 findings, almost all test
   fixtures. Concrete motivation for the model layer.

## Quotes worth keeping

- "63 findings on my own repo and none of them are real. That's the problem
  the model has to solve."
