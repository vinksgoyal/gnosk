# Gnosk

> Built for the [Hacktoberfest Open-Source AI Challenge Week 2](https://dev.to/challenges/hacktoberfest-week2-2026-10-12). [Read the write-up →](https://dev.to/vinksgoyal/gnosk-know-what-your-code-knows-cgd)

**Know what your code knows.**

Offline PII scanner for freelance devs and small agencies. Scans a
codebase for Aadhaar, PAN, phone numbers, emails, and API keys, then
writes a redacted data inventory you can hand to a client.
**Everything runs on your machine.** No file, path, or snippet ever
leaves the laptop.

## Install

    git clone https://github.com/vinksgoyal/gnosk
    cd gnosk
    ./install.sh

The script checks Python, creates a virtualenv, installs the package,
and symlinks `gnosk` into `~/.local/bin` so you never have to `source`
anything. Re-running is safe.

## Use

    gnosk                       # interactive REPL
    gnosk scan ./my-project     # quick scan
    gnosk scan ./p --classify   # add local model verdicts
    gnosk report ./p            # write a client-ready inventory (md + json)
    gnosk update                # pull latest, reinstall
    gnosk --help                # full command list

## Why this exists

Freelancers and small agencies in India are increasingly asked by
clients to sign data-protection clauses under the DPDP Act. Enterprise
DLP tools cost more than a freelancer's monthly income. Cloud-based
scanners require uploading the exact data you're trying to protect.

Gnosk is the local-first alternative: run one command, get a report you
can hand to a client, keep your files where they are.

## How it works

1. **Deterministic validators first.** Aadhaar (Verhoeff checksum), PAN
   format, Indian phone and email shapes, 12 provider API-key patterns.
   Fast, auditable, no model needed.

2. **Triage rules decide what they can.** Known fixture values, test
   paths, and checksum-valid Aadhaar are resolved without the model.
   Only ambiguous findings reach step 3.

3. **Local open-weight model last (Gemma via Ollama).** Handles what
   regex and rules cannot: is this email a test fixture or a real
   client contact? Runs on your machine, no cloud calls.

Nothing leaves the laptop. You can unplug the network cable and Gnosk
still works — except for `--classify`, which talks only to localhost.

## What Gnosk is NOT

- **Not** a compliance certification.
- **Does not** claim your project is "DPDP compliant."
- **Does not** replace a lawyer, a DPO, or a formal audit.

It produces a *readiness* report — a starting point for a conversation
with your client or your CA. Any wording in the generated report that
implies guaranteed compliance is a bug; please file it.

## Requirements

- Python 3.11+
- Linux/macOS (Windows untested)
- **Optional:** [Ollama](https://ollama.com) running locally with a
  Gemma model pulled (`ollama pull gemma2:2b`). Required only for
  `--classify` and the REPL's `classify` command.

Verify the model with `python scripts/verify_ollama.py` before using
model-dependent commands.

## Update

    gnosk update

Refuses to run if you have uncommitted changes; uses the venv's own pip
so it can't cross-install; re-verifies the version after pulling.

## License

MIT. See LICENSE.

## Disclaimer

Gnosk is a developer tool. Its output is informational only and does not
constitute legal advice or a compliance certification. You are
responsible for how you use and share its reports.
