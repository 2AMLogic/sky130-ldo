#!/usr/bin/env bash
# Source or run me: creates/refreshes a venv with a pinned `klt` build from
# one of layout/'s requirements files.
#
#   layout/bin/setup-venv.sh          # create if missing, otherwise no-op
#   layout/bin/setup-venv.sh --force  # reinstall even if <venv>/bin/klt exists
#
# Defaults to layout/requirements.txt -> layout/.venv (the DRC/LVS/PEX flow).
# `--requirements <file>` selects a different pin and, unless `--venv <dir>`
# overrides it, a venv named after that file: layout/erc-requirements.txt ->
# layout/.venv-erc. layout/erc-requirements.txt explains why the ERC flow
# needs its own pin rather than sharing the DRC/LVS one.
#
#   layout/bin/setup-venv.sh --requirements layout/erc-requirements.txt
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FORCE=0
REQUIREMENTS="$LAYOUT_DIR/requirements.txt"
VENV=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    --requirements) REQUIREMENTS="$2"; shift 2 ;;
    --venv) VENV="$2"; shift 2 ;;
    *) echo "setup-venv.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

# Accept a repo-relative or absolute requirements path.
[[ "$REQUIREMENTS" = /* ]] || REQUIREMENTS="$(cd "$LAYOUT_DIR/.." && pwd)/$REQUIREMENTS"
if [[ ! -f "$REQUIREMENTS" ]]; then
  echo "setup-venv.sh: no such requirements file: $REQUIREMENTS" >&2
  exit 1
fi

if [[ -z "$VENV" ]]; then
  REQ_BASE="$(basename "$REQUIREMENTS")"
  case "$REQ_BASE" in
    requirements.txt) VENV="$LAYOUT_DIR/.venv" ;;
    # `erc-requirements.txt` -> `.venv-erc`
    *-requirements.txt) VENV="$LAYOUT_DIR/.venv-${REQ_BASE%-requirements.txt}" ;;
    *) echo "setup-venv.sh: cannot derive a venv name from $REQUIREMENTS -- pass --venv" >&2; exit 2 ;;
  esac
fi

if [[ -x "$VENV/bin/klt" && "$FORCE" -eq 0 ]]; then
  echo "setup-venv.sh: $VENV already has klt installed (pass --force to reinstall)"
  "$VENV/bin/klt" --version
  exit 0
fi

echo "setup-venv.sh: creating $VENV from $REQUIREMENTS"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
# `--force-reinstall` is load-bearing on the `--force` path: the requirements
# files pin `klayout-tools` by git *commit*, but pinned commits can share a
# package *version*, so plain `pip install -r` sees the requirement as
# already satisfied and leaves the OLD build in place. A pin bump would then
# appear to install while changing nothing.
"$VENV/bin/pip" install --quiet --force-reinstall --no-deps -r "$REQUIREMENTS"
"$VENV/bin/pip" install --quiet -r "$REQUIREMENTS"

echo "setup-venv.sh: installed"
"$VENV/bin/klt" --version
"$VENV/bin/klt" pdk find --pdk sky130A || {
  echo "setup-venv.sh: WARNING: no resolvable sky130A PDK install found." >&2
  echo "  See sim/pdk.json for this repo's pinned install command." >&2
}
