#!/usr/bin/env bash
#
# Gnosk installer.
#
# Usage:
#   ./install.sh
#
# What it does:
#   1. Verifies Python 3.11+ is available
#   2. Creates a virtualenv in ./.venv
#   3. Installs Gnosk into that venv
#   4. Symlinks `gnosk` into ~/.local/bin so you can run it anywhere
#      without activating the venv
#   5. Warns (but does not fail) if Ollama is not installed — only
#      `gnosk scan --classify` needs it
#
# Idempotent: safe to re-run.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${REPO_DIR}/.venv"
BIN_DIR="${HOME}/.local/bin"
LOG_FILE="${REPO_DIR}/.install.log"
MIN_PY_MINOR=11

# ---------- styling ----------
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BOLD=$'\033[1m';  DIM=$'\033[2m'
  RED=$'\033[31m';  GREEN=$'\033[32m'
  YEL=$'\033[33m';  CYAN=$'\033[36m'
  RESET=$'\033[0m'
else
  BOLD=""; DIM=""; RED=""; GREEN=""; YEL=""; CYAN=""; RESET=""
fi

ok()    { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
bad()   { printf "  ${RED}✗${RESET} %s\n" "$1"; }
warn()  { printf "  ${YEL}!${RESET} %s\n" "$1"; }
info()  { printf "  ${DIM}·${RESET} %s\n" "$1"; }
head()  { printf "\n${BOLD}%s${RESET}\n" "$1"; }

die() {
  bad "$1"
  [ -n "${2:-}" ] && printf "    ${DIM}%s${RESET}\n" "$2"
  exit 1
}

# ---------- spinner ----------
# Usage: run_with_spinner "message" cmd args...
run_with_spinner() {
  local msg="$1"; shift
  local frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0

  "$@" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  while kill -0 "$pid" 2>/dev/null; do
    printf "\r  ${CYAN}%s${RESET} %s" "${frames[$i]}" "$msg"
    i=$(( (i + 1) % ${#frames[@]} ))
    sleep 0.08
  done
  wait "$pid"
  local rc=$?
  printf "\r\033[K"
  return $rc
}

# ---------- banner ----------
cat <<'BANNER'

  ██████╗ ███╗   ██╗ ██████╗ ███████╗██╗  ██╗
 ██╔════╝ ████╗  ██║██╔═══██╗██╔════╝██║ ██╔╝
 ██║  ███╗██╔██╗ ██║██║   ██║███████╗█████╔╝
 ██║   ██║██║╚██╗██║██║   ██║╚════██║██╔═██╗
 ╚██████╔╝██║ ╚████║╚██████╔╝███████║██║  ██╗
  ╚═════╝ ╚═╝  ╚═══╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝
  Know what your code knows.

BANNER

printf "${DIM}Installing Gnosk into %s${RESET}\n" "$REPO_DIR"

# ---------- 1. python ----------
head "Checking Python"

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done

if [ -z "$PYTHON_BIN" ]; then
  die "No python3 found on PATH." \
      "Install it first:  sudo apt install python3 python3-venv"
fi

PY_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
PY_MAJOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')"
PY_MINOR="$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')"

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt "$MIN_PY_MINOR" ]; }; then
  die "Python $PY_VERSION is too old. Gnosk needs 3.${MIN_PY_MINOR}+." \
      "On Debian/Kali:  sudo apt install python3.${MIN_PY_MINOR} python3.${MIN_PY_MINOR}-venv"
fi

if ! "$PYTHON_BIN" -c 'import venv' >/dev/null 2>&1; then
  die "The venv module is missing from Python $PY_VERSION." \
      "On Debian/Kali:  sudo apt install python3-venv"
fi

ok "Python $PY_VERSION at $(command -v "$PYTHON_BIN")"

# ---------- 2. ollama (optional) ----------
head "Checking Ollama (optional)"

if command -v ollama >/dev/null 2>&1; then
  ok "Ollama found at $(command -v ollama)"
  if ollama list 2>/dev/null | grep -q '^gemma'; then
    ok "A Gemma model is pulled"
  else
    warn "No Gemma model pulled yet. To enable --classify:"
    info "ollama pull gemma2:2b"
  fi
else
  warn "Ollama not found. Gnosk's deterministic scanner will work,"
  info "but --classify (real-vs-fixture judgment) needs it."
  info "Install:  curl -fsSL https://ollama.com/install.sh | sh"
fi

# ---------- 3. venv ----------
head "Creating virtual environment"

if [ -d "$VENV_DIR" ] && [ -x "$VENV_DIR/bin/python" ]; then
  info "Reusing existing venv at .venv/"
else
  if ! run_with_spinner "Creating .venv/" "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    echo
    bad "Failed to create the virtualenv."
    printf "    ${DIM}Last lines from %s:${RESET}\n" "$LOG_FILE"
    tail -n 20 "$LOG_FILE" | sed 's/^/      /'
    exit 1
  fi
  ok "Created .venv/"
fi

# ---------- 4. pip install ----------
head "Installing Gnosk"

VENV_PIP="${VENV_DIR}/bin/pip"
VENV_PY="${VENV_DIR}/bin/python"

if ! run_with_spinner "Resolving dependencies (this can take a minute)" \
     "$VENV_PIP" install --upgrade pip; then
  echo
  bad "pip self-upgrade failed."
  printf "    ${DIM}Last lines from %s:${RESET}\n" "$LOG_FILE"
  tail -n 20 "$LOG_FILE" | sed 's/^/      /'
  exit 1
fi

if ! run_with_spinner "Installing gnosk + dev dependencies" \
     "$VENV_PIP" install -e "${REPO_DIR}[dev]"; then
  echo
  bad "pip install failed."
  printf "    ${DIM}Last lines from %s:${RESET}\n" "$LOG_FILE"
  tail -n 20 "$LOG_FILE" | sed 's/^/      /'
  exit 1
fi

if [ ! -x "${VENV_DIR}/bin/gnosk" ]; then
  die "Install finished but the gnosk entry point is missing." \
      "Try:  rm -rf .venv && ./install.sh"
fi
ok "Installed into $(echo "$VENV_DIR" | sed "s|$HOME|~|")"

# ---------- 5. symlink ----------
head "Linking command"

mkdir -p "$BIN_DIR"
ln -sf "${VENV_DIR}/bin/gnosk" "${BIN_DIR}/gnosk"
ok "Linked to ${BIN_DIR}/gnosk"

if ! echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
  warn "${BIN_DIR} is not on your PATH."
  info "Add this to your shell rc (~/.zshrc or ~/.bashrc):"
  printf "    ${DIM}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}\n"
  info "Then restart your shell, or run:  export PATH=\"\$HOME/.local/bin:\$PATH\""
else
  ok "${BIN_DIR} is already on your PATH"
fi

# ---------- 6. done ----------
head "Done"

if command -v gnosk >/dev/null 2>&1; then
  ok "Run:  gnosk scan ~/some-project"
  info "Or:   gnosk report ~/some-project --output inventory.md"
  info "Full help:  gnosk --help"
else
  warn "gnosk is installed but not yet on PATH in this shell."
  info "Run:  ${BIN_DIR}/gnosk --version"
fi
printf "\n"
