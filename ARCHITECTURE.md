# Gnosk — Project Handoff

**Know what your code knows.**

Offline PII scanner for freelance devs and small agencies. Scans a
codebase, finds PII-shaped data (Aadhaar, PAN, phone numbers, emails,
API keys), and writes a redacted data inventory a freelancer can hand
to a client. Everything runs on the user's machine. No cloud calls at
scan time.

This document is the single source of truth for anyone (human or
agent) making changes to Gnosk.

---

## 1. Non-negotiable constraints

These are why the tool exists. Breaking any of them defeats the product.

1. **No network calls at scan time.** Scanning must work with the
   network unplugged. Ollama runs on localhost; that's the only
   "network" allowed, and it's optional.
2. **Never claim legal compliance.** No output, README, or error
   message may say "DPDP compliant", "certified", or "audit-ready".
   The word is "readiness". The disclaimer is load-bearing.
3. **Values are always redacted in output.** Any file written to disk
   must contain redacted values, not raw PII. The report must never
   become the leak.
4. **Deterministic validators run first.** The model is a second pass
   for judgment calls, not detection. If the model is unavailable, the
   deterministic layer must still work.
5. **Model failures degrade to `unknown`, never raise.** A scan that
   hits an LLM error must still complete.

---

## 2. Target user and machine

- **User:** freelance dev or small agency in India, 1–3 people,
  handling client data (CRUD apps, internal tools, small e-commerce).
- **Their machine:** often a budget laptop. This project is developed
  and tested on a 2-core Intel (2nd gen), 7.7 GB RAM, no GPU, Kali.
- **Implication:** every design decision that costs CPU or RAM must be
  justified. Long prompts, big models, and full-screen TUIs are
  expensive on this hardware.

---

## 3. Architecture
CLI (typer): scan | report | wizard | update | REPL (no args)
│
▼
Scanner (scanner.py)

walks files, skips binary/skip-dirs/oversize

runs every validator on text content

context filters: hex-run suppression, entropy checks

annotates findings with line numbers
│
┌────┴────┐
▼ ▼
Validators Triage Classifier (LLM)
(regex+math)(rules) (gemma2:2b via Ollama)
optional, degrades to "unknown"
│ │
└────┬────┘
▼
Report (report.py): markdown + redacted JSON

text

**The core idea:** deterministic validation is cheap and honest.
Triage rules resolve what they can. Only genuinely ambiguous findings
reach the model. This is what makes the AI a specialist, not a
bolt-on.

---

## 4. File map
gnosk/
├── init.py # version = "0.0.1"
├── cli.py # typer app, all subcommands
├── findings.py # Finding dataclass (the shared type)
├── scanner.py # file walker + context filters
├── report.py # markdown + JSON report generator
├── triage.py # deterministic pre-classification
├── classifier.py # orchestrates triage + LLM
├── llm.py # THE ONLY module that talks to Ollama
├── interactive.py # REPL for gnosk (no args)
├── wizard.py # prompt-driven wizard (gnosk wizard)
├── update.py # gnosk update implementation
├── ui.py # banner, signature, TTY guards
└── validators/
├── aadhaar.py # Verhoeff checksum
├── pan.py # format + holder code
├── email.py # shape only
├── phone.py # Indian mobile shape + entropy filter
└── secrets.py # 12 provider API-key shapes

tests/ # 215 tests, all pure (no network, no model)
scripts/
├── verify_ollama.py # smoke test for local model
└── bench_model.py # throughput measurement
install.sh # one-command installer
site/ # landing page + Render config

text

---

## 5. The Finding type

Everything flows through `gnosk/findings.py`:

```python
@dataclass(frozen=True, slots=True)
class Finding:
    category: str          # "aadhaar", "pan", "email", "phone_in", "api_key"
    value: str             # raw matched text — redact before output
    start: int             # char offset into the scanned text
    end: int
    confidence: float      # 0.0–1.0, honest values only
    source: str            # "validator" or "model"
    validator: str         # e.g. "aadhaar.verhoeff"
    notes: str | None = None
    line: int | None = None  # set by scanner, not validators
Rule: validators don't set line — only the scanner does. If you
add a validator, ignore line. Finding is frozen; use
dataclasses.replace(...) to annotate.

6. Confidence values — do not lie
Validator	Confidence	Why
aadhaar.verhoeff (checksum valid)	1.00	Mathematical proof
aadhaar.verhoeff (checksum fail)	0.30	Shaped but fails math
pan.format (holder code valid)	0.70	PAN has no public checksum
pan.format (holder code invalid)	0.30	Shaped but wrong type code
email.shape	0.90	Shape well-defined, mailbox unverifiable
phone.in_shape	0.60	No checksum, 10-digit runs are common
secrets.*	0.95	Provider prefixes are deliberate
The Aadhaar 1.00 is the only honest 1.00 in the codebase.

7. Triage rules
Run before the model. See gnosk/triage.py.

Known fixture values — reserved example domains, tutorial
local-parts, AWS's documented example keys — are fixtures. Wins
over everything else.

API keys always defer to the model. A provider-shaped secret
can leak from anywhere, including a test file.

Checksum-valid Aadhaar is likely_real outside test paths
(format proves validity, not personhood). Inside a test path it
defers to the model — could be fixture, could be leak.

Test/fixture/example/spec paths dismiss the remaining
categories.

Everything else defers to the model.

Verdicts carry a source of triage or model. likely_real is
triage-only; the model cannot return it.

8. Model strategy (hardware-constrained)
gemma2:2b on 2 CPU cores. Measured throughput:

Prompt size	Wall time
tiny (~50 chars)	3.1 s
medium (~300 chars)	8.0 s
2 KB	38.5 s
Rule of thumb: ~2 s per 100 prompt characters.

Design consequences:

Never send whole files. Send only the containing line of each
finding, truncated to 140 chars.

Cap num_predict at 180.

No reason field in classifier responses (they cost tokens).

Batch cap: 5 findings per call.

Timeout: 150 s.

The classifier does not send every finding — triage resolves most.

Config is read from GNOSK_* env vars, with VAULTSCAN_* fallback +
deprecation warning.

9. The context filters (the hard part)
Three classes of false positive have been hunted down. Every one came
from running the tool on real data, not test fixtures.

9.1 Hex-run suppression (scanner.py:_is_inside_hex_run)
A 64-char SHA256 hash contains ~55 overlapping 10-digit windows,
several matching the phone regex [6-9]\d{9}. Fires constantly on
lock files and metadata caches.

Fix: if a finding's span is entirely hex and sits inside a run
of ≥32 hex chars, suppress. The entirely-hex condition matters —
GitHub tokens contain non-hex characters and must survive.

9.2 Entropy filter (validators/phone.py, validators/aadhaar.py)
Real phones don't have 5+ zeros. LLM pricing decimals do
(0.0000008125 → 8125000000).

Fix: if digit payload contains ≥5 zeros, suppress.

9.3 Tool-directory skip (scanner.py:_SKIP_DIRS)
.backboard, .cache, .sessions contain machine output that is
pure noise. Added to skip list.

Do not add more regex to fix false positives. The pattern matches
are correct. Context is the problem, and context belongs in the
scanner.

10. Testing conventions
215 tests, all pure. No test makes a network call, runs git, or
loads the model.

_call_model in llm.py is the seam for faking Ollama.

ask_json in classifier.py is the seam for faking the classifier.

REPL tests use Console(file=StringIO()) and monkeypatch
console.input.

First-run detection is isolated via GNOSK_CONFIG_DIR.

Run: pytest -q && ruff check .

11. Commit and code conventions
Conventional Commits: feat:, fix:, docs:, refactor:,
test:, chore:.

Ruff line length 100. Rules E F I UP B.

typer.Argument and typer.Option are marked immutable so B008
doesn't fire.

No bare except Exception except in REPL dispatch (marked
# noqa: BLE001).

Type hints everywhere, from __future__ import annotations at top.

12. Known issues and landmines
Renaming the repo directory breaks the venv. Python venvs embed
absolute paths. Fix: rm -rf .venv && ./install.sh.

.install.log is a runtime artifact — it's in .gitignore.
gnosk update sees untracked files as local changes.

--classify on a folder of test fixtures is slow. Many
checksum-valid Aadhaar fixtures go to the model by rule 3. For a
demo, use a folder with a mix of fixtures and one or two
production-path findings.

13. Current state (as of 2026-10-15)
Working end-to-end:

gnosk (no args) → REPL with persistent session

gnosk scan <path> → findings summary, colored categories

gnosk scan <path> --classify → triage + model verdicts, showing
the split between triaged and model-bound findings

gnosk report <path> --output X.md → markdown + redacted JSON

gnosk wizard → prompt-driven single-shot

gnosk update → git pull + reinstall, refuses on dirty tree

./install.sh → one-command install, symlink to ~/.local/bin/gnosk

Landing page at site/index.html

Not yet done:

.tech custom domain pointed at Render

Demo video recorded

DEV post written

First-user feedback collected

PDF report export (optional, skipped)

Test count: 215 passing.

14. If you're asked to make a change
Before you code:

Does it break a non-negotiable constraint (§1)? If yes, don't.

Does it add a network call at scan time? If yes, don't.

Does it claim compliance? If yes, don't.

Does it send more tokens to the model than necessary? Re-read §8.

Does it introduce a false-positive class? Test against
~/Hacktoberfest/birdbuddy (should return 0 findings) and
tests/ (should return 100+).

After you code:

pytest -q && ruff check . — must be green.

Add a test for the specific change. No exceptions.

Conventional Commit.

Update this doc if §4, §6, §7, §8, §9, or §13 changed.

15. The story for the DEV post
Three classes of false positive were found by running the tool on real
data:

SHA256 fragments in a Hacktoberfest project (birdbuddy) matched
the phone regex 14 times. All from a single hash.

The hex-run fix was too aggressive — the test suite caught it
eating GitHub PATs. Required a second condition: the span itself
must be hex.

LLM gateway logs produced phone-shaped decimal fragments from
per-token prices (0.0000008125 → 8125000000). Required an
entropy filter and a skip-directory entry.

The lesson: test fixtures stay green; real code exposes bugs.

If you're an agent making changes: the next false positive is out
there. Run the tool on real folders, not just tests/.
