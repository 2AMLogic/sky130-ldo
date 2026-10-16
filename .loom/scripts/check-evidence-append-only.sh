#!/usr/bin/env bash
# check-evidence-append-only.sh - Fail if a branch modifies, renames, or
# deletes a committed `sim/<exp>/records/*` file (adds are fine).
#
# Rule source: `sim/README.md` "Append-only rule" -- "`records/*` files are
# never edited or deleted after creation -- this applies even to typo fixes,
# because the append-only guarantee is the whole point of an evidence trail.
# Corrections mint a new record that references the prior one via
# **Supersedes**." (#283)
#
# Why: the rule was enforced only by convention, and Champion auto-merges
# `loom:pr` with no human in the loop, so an agent "tidying" or regenerating a
# record in place would merge silently. History is clean today; this locks
# that baseline in.
#
# Escape hatch: there is intentionally NONE. A correction is a NEW record file
# whose Supersedes field names the prior record; the old file stays on disk.
#
# What it checks: `git diff --name-status -M <merge-base>..HEAD` against
# origin/main (CI's `checks` job uses fetch-depth: 0). Any path under
# `sim/*/records/` with status M, D, or R (as either the old or the new side
# of a rename) fails; status A passes. Tree-local, no forge access.
# Skipped, loudly, when no base is resolvable (no origin/main ref, no common
# ancestor) or when HEAD is already the base (on main itself).
# Override the base ref with EVIDENCE_BASE_REF (default origin/main).
#
# Scope note: layout/**/reports/ is deliberately NOT covered. layout/README.md
# calls the per-run `<record-id>/` dirs append-only, but the same directory
# holds mutable pointer files (LATEST, LATEST-LVS, LATEST-ERC) that are
# legitimately rewritten on every run, so a plain path guard would false-fail.
# Covering only the `<record-id>/` subdirs is a possible follow-up.
#
# Usage:
#   check-evidence-append-only.sh [ROOT]   Check the repo at ROOT (default:
#                                          this script's repo root).
#   check-evidence-append-only.sh --self-test
#                                          Run fixture tests in a throwaway
#                                          git repo.
#
# Exit codes: 0 = ok or skipped; 1 = a committed record was modified,
# renamed, or deleted (offenders named on stderr).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_REF="${EVIDENCE_BASE_REF:-origin/main}"

# check_root <root> -> 0 ok/skip, 1 violations
check_root() {
  local root="$1" base head
  if ! git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "check-evidence-append-only: SKIP — $root is not a git repo."
    return 0
  fi
  if ! git -C "$root" rev-parse --verify -q "$BASE_REF^{commit}" >/dev/null; then
    echo "check-evidence-append-only: SKIP — base ref '$BASE_REF' not resolvable (no append-only comparison possible)."
    return 0
  fi
  if ! base="$(git -C "$root" merge-base "$BASE_REF" HEAD 2>/dev/null)"; then
    echo "check-evidence-append-only: SKIP — no merge base between '$BASE_REF' and HEAD."
    return 0
  fi
  head="$(git -C "$root" rev-parse HEAD)"
  if [[ "$base" == "$head" ]]; then
    echo "check-evidence-append-only: SKIP — HEAD is the merge base with '$BASE_REF' (on main / no branch changes)."
    return 0
  fi

  local -a bad=()
  local status p1 p2 line
  while IFS=$'\t' read -r status p1 p2; do
    [[ -z "$status" ]] && continue
    case "${status:0:1}" in
      A) continue ;;
      R|C)
        # Rename/copy: old side (p1) is the committed record being moved.
        if [[ "${status:0:1}" == R && "$p1" =~ ^sim/[^/]+/records/ ]]; then
          bad+=("R  $p1 -> $p2")
        fi
        ;;
      *)
        if [[ "$p1" =~ ^sim/[^/]+/records/ ]]; then
          bad+=("${status:0:1}  $p1")
        fi
        ;;
    esac
  done < <(git -C "$root" diff --name-status -M "$base" HEAD)

  if [[ ${#bad[@]} -gt 0 ]]; then
    echo "COMMITTED SIM RECORD MODIFIED/RENAMED/DELETED:" >&2
    for line in "${bad[@]}"; do echo "  $line" >&2; done
    {
      echo ""
      echo "check-evidence-append-only: FAIL — sim/*/records/* are append-only evidence"
      echo "(sim/README.md \"Append-only rule\"; applies even to typo fixes). Restore the"
      echo "original file and mint a NEW record whose Supersedes names the prior one."
      echo "There is no escape hatch."
    } >&2
    return 1
  fi
  echo "check-evidence-append-only: OK — no committed sim record modified, renamed, or deleted vs $BASE_REF."
  return 0
}

self_test() {
  local tmp failures=0 status out
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  local repo="$tmp/repo" ref_saved="$BASE_REF"
  BASE_REF=main
  git init -q -b main "$repo"
  git -C "$repo" config user.email t@t
  git -C "$repo" config user.name t
  mkdir -p "$repo/sim/exp/records"
  echo one >"$repo/sim/exp/records/r1.md"
  echo two >"$repo/sim/exp/records/r2.md"
  echo x >"$repo/sim/exp/notes.md"
  git -C "$repo" add -A && git -C "$repo" commit -qm base

  expect() {
    local expected="$1" label="$2"
    set +e
    out="$(check_root "$repo" 2>&1)"
    status=$?
    set -e
    if [[ "$status" -ne "$expected" ]]; then
      echo "  FAIL: $label — expected exit $expected, got $status" >&2
      printf '%s\n' "$out" | sed 's/^/    | /' >&2
      failures=$((failures + 1))
    else
      echo "  ok: $label (exit $status)"
    fi
  }
  branch() { git -C "$repo" checkout -q main && git -C "$repo" checkout -q -b "$1"; }
  commit() { git -C "$repo" add -A && git -C "$repo" commit -qm "$1"; }

  expect 0 "on main (HEAD == base) is skipped"

  branch add-only
  echo three >"$repo/sim/exp/records/r3.md"
  echo y >>"$repo/sim/exp/notes.md"
  commit add
  expect 0 "add-only branch (plus non-record edit) passes"

  branch edit
  echo changed >>"$repo/sim/exp/records/r1.md"
  commit edit
  expect 1 "editing a committed record fails"
  printf '%s' "$out" | grep -qF "sim/exp/records/r1.md" || { echo "  FAIL: offender not named" >&2; failures=$((failures + 1)); }

  branch rename
  git -C "$repo" mv sim/exp/records/r2.md sim/exp/records/r2-renamed.md
  commit rename
  expect 1 "renaming a committed record fails"

  branch delete
  git -C "$repo" rm -q sim/exp/records/r1.md
  commit delete
  expect 1 "deleting a committed record fails"

  branch missing-base
  BASE_REF=no-such-ref
  expect 0 "unresolvable base is skipped"
  BASE_REF="$ref_saved"

  if [[ "$failures" -ne 0 ]]; then
    echo "check-evidence-append-only --self-test: FAIL ($failures assertion(s))" >&2
    return 1
  fi
  echo "check-evidence-append-only --self-test: OK"
}

if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,40p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi
if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ROOT="$1"
else
  ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || (cd "$SCRIPT_DIR/../.." && pwd))"
fi
check_root "$ROOT"
