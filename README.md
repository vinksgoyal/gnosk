# Gnosk

**Know what your code knows.**

Offline PII leak scanner for freelance devs and small agencies.

Gnosk scans a codebase, a folder of documents, or a database dump for
personally identifiable information (PII) — Aadhaar, PAN, phone numbers,
emails, addresses, API keys — and produces a data inventory plus a
client-ready "DPDP readiness" report. **Everything runs on your machine.**
No file, path, or snippet ever leaves the laptop.

> Status: early development. Nothing here works yet.

## Why this exists

Freelancers and small agencies in India are increasingly asked by clients to
sign data-protection clauses under the DPDP Act. Enterprise DLP tools cost
more than a freelancer's monthly income. Cloud-based scanners require
uploading the exact data you're trying to protect.

Gnosk is the local-first alternative: run one command, get a report you
can hand to a client, keep your files where they are.

## How it works

1. **Deterministic validators first.** Regex + checksum validation
   (Aadhaar Verhoeff, PAN format, phone/email patterns, common API-key
   shapes) catch what can be caught with certainty. Fast, auditable, no
   model needed.
2. **Local open-weight model second (Gemma via Ollama).** Used only for
   what regex can't do: reading source code to map where personal data
   flows, separating real customer data from test fixtures, and drafting
   the data inventory and the client-facing readiness report.
3. **Nothing leaves the machine.** No network calls at scan time. You can
   unplug the network cable and Gnosk still works.

## What Gnosk is NOT

- It is **not** a compliance certification.
- It does **not** claim your project is "DPDP compliant."
- It does **not** replace a lawyer, a DPO, or a formal audit.

It produces a *readiness* report — a starting point for a conversation with
your client or your CA. Any wording in the generated report that implies
guaranteed compliance is a bug; please file it.

## Requirements (planned)

- Python 3.11+
- [Ollama](https://ollama.com) running locally
- A Gemma model pulled. Tested on `gemma2:2b` (1.6 GB); a 4B or larger
  model is recommended if your machine has the RAM and cores for it.
- At least 8 GB RAM; the model runs on CPU, no GPU required.
- Linux/macOS (Windows untested)

Run `python scripts/verify_ollama.py` to confirm the model is reachable
before using any model-dependent commands.

## Install

    git clone https://github.com/vinksgoyal/gnosk
    cd gnosk
    ./install.sh

That's it. The script checks Python, creates a virtualenv, installs the
package, and symlinks `gnosk` into `~/.local/bin` so you never have to
`source` anything. Re-running is safe.

Ollama is optional — the deterministic scanner works without it. To
enable `--classify` (local model judgment):

    curl -fsSL https://ollama.com/install.sh | sh
    ollama pull gemma2:2b

## Update

    cd gnosk
    git pull
    pip install -e .

(A `gnosk update` subcommand is on the roadmap.)

## Usage (planned)

    gnosk scan ./my-client-project
    gnosk report --format pdf

## License

MIT. See LICENSE.

## Disclaimer

Gnosk is a developer tool. Its output is informational only and does not
constitute legal advice or a compliance certification. You are responsible
for how you use and share its reports.
