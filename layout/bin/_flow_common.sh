# layout/bin/_flow_common.sh -- the shared preamble every layout/bin/run-*-flow.sh
# driver repeated (issue #599), the shell-side counterpart to this tree's
# layout/bin/_record_common.py.
#
# Source me from the driver's own directory, right after `set -euo pipefail`:
#
#   source "$(dirname "${BASH_SOURCE[0]}")/_flow_common.sh"
#
# Sourcing runs flow_paths, which sets LAYOUT_DIR and REPO_ROOT (the two
# path derivations that were byte-identical in all five drivers), and defines:
#
#   flow_require_klt       <script> <klt-path> [setup-hint]
#   flow_require_pdk       <script> <pdk-variant> <pin-hint> <klt-command...>
#   flow_mint_record       <script> <reports-dir> [--rel] [--suffix TEXT]
#   flow_netlist_schematic <script> <schematic> <xschem-out-dir> <klt-command...>
#
# Two conventions, both load-bearing:
#
#   * Every helper takes the CALLING driver's script name as its first
#     argument, so the diagnostics it prints keep the byte-identical
#     `run-...-flow.sh: ` prefix the inlined copies printed. `$0` cannot do
#     this job from inside a sourced function on the `source`-from-a-symlink
#     or `bash <script>` paths, and `${BASH_SOURCE[1]}` would print a whole
#     path where these messages have always printed a bare script name.
#   * A `klt` command is passed as TRAILING arguments, not read from a
#     variable, because run-cap-rail-demo-flow.sh's `klt` is a multi-word
#     array (its uvx fallback, `uvx --from <pin> klt`) while the other four
#     drivers' is a single venv path. `"$@"` covers both without the library
#     having to know which.
#
# Helpers `exit` rather than `return` on a failed guard: the inlined copies
# they replaced aborted their driver, and every driver runs under `set -e`.

_FLOW_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# flow_paths -- LAYOUT_DIR and REPO_ROOT, derived from this library's own
# location (layout/bin/_flow_common.sh) rather than from the caller's, so a
# driver needs no path derivation of its own beyond finding this file.
flow_paths() {
  LAYOUT_DIR="$(cd "$_FLOW_COMMON_DIR/.." && pwd)"
  REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
}

# flow_require_klt <script> <klt-path> [setup-hint]
#
# Refuse to run without the pinned `klt` build. With no hint the message names
# layout/bin/setup-venv.sh's default invocation; a hint is printed as a second,
# indented line (run-ldo-erc-flow.sh needs its own --requirements file).
flow_require_klt() {
  local script="$1" klt="$2" hint="${3-}"
  if [[ -x "$klt" ]]; then
    return 0
  fi
  if [[ -n "$hint" ]]; then
    echo "$script: $klt not found -- run" >&2
    echo "  $hint" >&2
  else
    echo "$script: $klt not found -- run layout/bin/setup-venv.sh first" >&2
  fi
  exit 1
}

# flow_require_pdk <script> <pdk-variant> <pin-hint> <klt-command...>
#
# Refuse to run without a resolvable PDK install. Not every driver needs one:
# run-ldo-erc-flow.sh deliberately calls neither this nor `klt pdk find`,
# because `klt erc --pdk sky130` reads its antenna-limit table out of klt
# itself rather than from a local PDK tree (see that script's header).
flow_require_pdk() {
  local script="$1" variant="$2" hint="$3"
  shift 3
  if ! "$@" pdk find --pdk "$variant" >/dev/null; then
    echo "$script: no resolvable $variant PDK -- $hint" >&2
    exit 1
  fi
}

# flow_mint_record <script> <reports-dir> [--rel] [--suffix TEXT]
#
# Mint a NEW append-only record directory and announce it. Sets SHORT_SHA,
# RECORD_ID, OUT_DIR (absolute) and OUT_REL (OUT_DIR relative to REPO_ROOT).
# Never touches an existing record: the id carries a UTC timestamp.
#
# The sha is read with `git -C "$REPO_ROOT"`, so a record id names THIS
# checkout's HEAD whatever the caller's cwd happens to be -- a record id is
# the identity of an evidence directory, and must not depend on ambient cwd.
#
#   --rel          announce OUT_REL instead of OUT_DIR
#   --suffix TEXT  append TEXT to the announcement (e.g. the layout record
#                  a derived flow consumed)
flow_mint_record() {
  local script="$1" reports_dir="$2"
  shift 2
  local rel=0 suffix="" ts_utc
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --rel) rel=1; shift ;;
      --suffix) suffix="$2"; shift 2 ;;
      *) echo "flow_mint_record: unknown argument '$1'" >&2; exit 2 ;;
    esac
  done
  ts_utc="$(date -u +%Y%m%d-%H%M%S)"
  SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
  RECORD_ID="${ts_utc}-${SHORT_SHA}"
  OUT_DIR="$reports_dir/$RECORD_ID"
  OUT_REL="${OUT_DIR#"$REPO_ROOT"/}"
  mkdir -p "$OUT_DIR"
  if (( rel )); then
    echo "$script: record $RECORD_ID -> $OUT_REL$suffix"
  else
    echo "$script: record $RECORD_ID -> $OUT_DIR$suffix"
  fi
}

# flow_netlist_schematic <script> <schematic> <xschem-out-dir> <klt-command...>
#
# Netlist <schematic> into <xschem-out-dir>, and set SCHEM_NETLIST to the
# file written (the schematic's own basename with a .spice extension, which
# is what xschem names it).
#
# `klt netlist` owns the headless xschem invocation (forced flags + timeout
# kill). That is the whole reason this step is shared rather than copied: a
# bare `xschem` does not fail when the GUI initialises, it writes a
# plausible-looking netlist and then hangs in the Tk event loop.
flow_netlist_schematic() {
  local script="$1" schematic="$2" xschem_out="$3"
  shift 3
  mkdir -p "$xschem_out"
  SCHEM_NETLIST="$xschem_out/$(basename "$schematic" .sch).spice"
  "$@" netlist -o "$SCHEM_NETLIST" --rcfile "$REPO_ROOT/sim/xschemrc" "$schematic"
  if [[ ! -f "$SCHEM_NETLIST" ]]; then
    echo "$script: expected $SCHEM_NETLIST after xschem netlisting" >&2
    exit 1
  fi
}

flow_paths
