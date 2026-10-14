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
4. Scanner run against Gnosk's own repo: 63 findings, almost all test
   fixtures. Concrete motivation for the model layer.

## Quotes worth keeping

- "63 findings on my own repo and none of them are real. That's the problem
  the model has to solve."

## Day 2 (2026-10-14) — model throughput reality check

Machine: 2 cores, 7.7 GB RAM, no GPU. Model: gemma2:2b.

Bench (scripts/bench_model.py):
- tiny prompt (10 tok output):   3.1 s  (3.2 tok/s)
- medium prompt:                  8.0 s  (2.9 tok/s)
- 2 KB prompt (41 tok output):   38.5 s  (1.1 tok/s)

Rule of thumb: ~2 s per 100 prompt characters on this hardware.

Implication: the original classifier prompt (~1500 chars, whole file)
timed out at 180 s. Redesign: send only a small window around each
finding, not the whole file. Target <= 400 chars => ~10 s per call.

Classifier committed at 74643c2 with the old prompt shape. Follow-up:
windowed-context prompt + smaller caps. Keep _MAX_FINDINGS_PER_CALL = 10.

## Day 3 (2026-10-15) — windowed classifier landed

Working state: classifier sends containing-line context per finding
(not whole file), asks for minimal JSON (no reasons), caps at 5
findings per call.

- Prompt: ~700 chars (was ~1500)
- Test file (8 findings, 2 calls): 125s on 2-core CPU, gemma2:2b
- Verdicts on tests/test_pan.py: 5 fixture, 3 real (some misclassify
  the same value differently across lines — 2B model limit, documented)

Experiment tried: qwen2.5:0.5b — never actually pulled, zsh `time`
parse error killed the compound command. Deferred. Not worth chasing;
125s/file is fine for demo.

Story for DEV post: "3 model calls before I realized the problem was
output tokens, not prompt tokens. Capped num_predict at 180 and dropped
reasons from the response schema. That's when it stopped timing out."
