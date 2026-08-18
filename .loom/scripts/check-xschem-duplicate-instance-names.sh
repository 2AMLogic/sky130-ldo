#!/usr/bin/env bash
# check-xschem-duplicate-instance-names.sh - Fail if any tracked design/*.sch
# file instantiates two components with the same `name=` value.
#
# Why (#38): xschem's netlister does not itself reject a schematic that
# instantiates two components under the same `name=` (e.g. two `M_ENP4`
# transistors) -- it happily emits a netlist with two device lines sharing
# the same instance name. ngspice only catches this once it elaborates the
# deck, with a confusing, netlist-line-number error far from the schematic
# authoring mistake:
#
#   m.xldo.xm_enp4.msky130_fd_pr__pfet_g5v0d10v5 ... device already exists, bail out
#
# This happened for real: #35 (thermal shutdown) and #36 (rail-to-rail
# error-amp output stage) were developed in parallel and each added an
# EN-gated PMOS clamp named `M_ENP4` on different nets. Each was fine on its
# own branch; merged, the block's own netlist became unusable, and nothing
# in `npm run check:ci` caught it because no headless check ever netlists
# `design/*.sch` itself. This check catches the hazard at authoring/review
# time -- with a clear, specific message naming the file and the duplicated
# instance name -- instead of at simulation time, and needs no PDK, xschem,
# or ngspice.
#
# What it checks: within each tracked `design/*.sch` file, every component
# instance line (`C {<symbol>} x y rot flip {name=<value> ...}`) has a
# `name=` attribute as the first thing after the opening `{` -- true for
# every instance in this repo today, single-line or multi-line attribute
# block alike (verified against design/ldo_3v3in_1v8out.sch). Any two
# instances in the same file sharing the same exact `name=` value are
# flagged. This intentionally only scopes to `C {...}` component-instance
# `name=` attributes, not other `name=`-shaped text that can appear
# elsewhere in a `.sch` file (e.g. inside a `code_shown`/comment block),
# and it compares names only within a single file, not across files --
# multiple testbenches instantiating a device named e.g. `M1` in
# unrelated top-level schematics is not a collision.
#
# Usage:
#   check-xschem-duplicate-instance-names.sh [ROOT]
#     ROOT  Repository root to scan tracked design/*.sch files under.
#           Defaults to `git rev-parse --show-toplevel`, then the script's
#           own repo root.
#
# Exit codes: 0 = no duplicate instance names found (or nothing to check);
# 1 = one or more design/*.sch files contain two component instances with
#     the same `name=` value (offenders named with file:line on stderr).

set -euo pipefail

# --- Resolve ROOT -----------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ROOT="$1"
else
  if ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    :
  else
    # .loom/scripts/ -> .loom/ -> repo root
    ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
  fi
fi

# --- Collect tracked design/*.sch files -------------------------------------
mapfile -t FILES < <(git -C "$ROOT" ls-files 'design/*.sch' 2>/dev/null || true)

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "check-xschem-duplicate-instance-names: no tracked design/*.sch files under $ROOT — nothing to check (ok)."
  exit 0
fi

found=0

for rel in "${FILES[@]}"; do
  file="$ROOT/$rel"
  [[ -f "$file" ]] || continue

  declare -A seen_line=()
  lineno=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    lineno=$((lineno + 1))

    # Component instance lines: `C {<symbol>} x y rot flip {name=<value> ...`
    # -- name= is always the first attribute right after the opening `{`,
    # whether the attribute block closes on this line or continues on
    # following lines (a multi-line C {...} block).
    if [[ "$line" =~ ^C\ \{[^}]*\}.*\{name=([A-Za-z0-9_]+)([[:space:]].*)?$ ]]; then
      name="${BASH_REMATCH[1]}"

      if [[ -n "${seen_line[$name]:-}" ]]; then
        echo "DUPLICATE INSTANCE NAME: ${rel}:${lineno}" >&2
        echo "  name=${name} already used at ${rel}:${seen_line[$name]}" >&2
        echo "  line: ${line}" >&2
        found=1
      else
        seen_line[$name]=$lineno
      fi
    fi
  done < "$file"
done

if [[ "$found" -ne 0 ]]; then
  echo "" >&2
  echo "check-xschem-duplicate-instance-names: FAIL — one or more design/*.sch" >&2
  echo "files instantiate two components under the same name=. xschem's netlister" >&2
  echo "does not reject this; it silently emits a netlist with two device lines" >&2
  echo "sharing the same instance name, and ngspice only fails at elaboration" >&2
  echo "time with a confusing 'device already exists, bail out' error far from" >&2
  echo "the schematic authoring mistake (see #38). Rename one of the duplicated" >&2
  echo "instances so every name= value is unique within the schematic." >&2
  exit 1
fi

echo "check-xschem-duplicate-instance-names: OK — no duplicate instance names found in ${#FILES[@]} tracked design/*.sch file(s)."
exit 0
