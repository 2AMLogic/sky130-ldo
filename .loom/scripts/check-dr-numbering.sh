#!/usr/bin/env bash
# check-dr-numbering.sh - Fail if two decision records under
# spec/decision-records/ claim the same DR-NNN number.
#
# Why (#140): `spec/decision-records/README.md` states the convention -- "One
# file per decision, DR-NNN-<slug>.md" -- but nothing enforced the NNN being
# unique, and under parallel sweeps that is not hypothetical. On 2026-09-23
# four open PRs each added a *different* `DR-008-*.md` simultaneously (#132
# `thermal-theta-ja-integration-constraint`, #134 `iq-budget`, #137
# `error-amp-stays-in-tree`, #139 `pass-device-resize`). Each was correct at
# the moment it picked "the next free number", because each checked against
# `main`, where the highest record was `DR-007`.
#
# Nothing caught it:
#   * git does not conflict -- the filenames differ, so the diffs are disjoint
#     and every one of them merges cleanly;
#   * `npm run check:ci` had no decision-record lint at all;
#   * Champion auto-merges `loom:pr` with no human in the loop, so two
#     approvals landing in the same window is all it takes.
#
# Records here are append-only (CLAUDE.md), so a duplicate number is not
# cheaply undone once merged -- it has to be superseded, and meanwhile every
# unqualified "DR-008" reference in prose is ambiguous. This check is
# deliberately tree-local: it turns "four PRs racing silently" into "the
# second one to rebase fails CI", which is the outcome worth buying. It does
# NOT look at open PRs (that would need forge access and is noted in #140 as a
# possible later step).
#
# This mirrors `check-xschem-duplicate-instance-names.sh` (#38), the repo's
# existing guard against the same failure class: a parallel-branch content
# collision that git's merge cannot see because the colliding files are
# physically different.
#
# What it checks, over every *tracked* file under `spec/decision-records/`
# whose name starts with `DR-`:
#   1. the filename matches `DR-NNN-<slug>.md` (exactly three digits, then a
#      non-empty slug) -- a malformed name like `DR-08-foo.md` would otherwise
#      slip past the duplicate check by not sharing a prefix with
#      `DR-008-bar.md`;
#   2. no two files share the same `DR-NNN` number.
# Files that do not start with `DR-` (README.md, TEMPLATE.md) are ignored.
#
# Usage:
#   check-dr-numbering.sh [ROOT]     Check the repository rooted at ROOT
#                                    (default: this script's repo root).
#   check-dr-numbering.sh --self-test
#                                    Run the built-in fixture tests, proving
#                                    the check both fires on a collision and
#                                    stays quiet on a clean tree.
#
# Exit codes: 0 = every decision record is well-named and uniquely numbered
# (or there is nothing to check); 1 = a duplicate number and/or a malformed
# filename was found (offenders named on stderr).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECORDS_DIR="spec/decision-records"

# --- The check --------------------------------------------------------------
# check_root <root> -> 0 ok / 1 problems found (messages on stderr)
check_root() {
  local root="$1"
  local -a files=()

  # Tracked files only when ROOT is a git repo (the CI case); fall back to a
  # filesystem walk so a plain directory -- e.g. a --self-test fixture -- can
  # be checked too.
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    mapfile -t files < <(git -C "$root" ls-files "$RECORDS_DIR/DR-*" 2>/dev/null || true)
  elif [[ -d "$root/$RECORDS_DIR" ]]; then
    mapfile -t files < <(cd "$root" && find "$RECORDS_DIR" -maxdepth 1 -name 'DR-*' -type f | sort)
  fi

  if [[ ${#files[@]} -eq 0 ]]; then
    echo "check-dr-numbering: no tracked $RECORDS_DIR/DR-* files under $root — nothing to check (ok)."
    return 0
  fi

  local found=0
  local -A owner=()       # DR-NNN -> first file seen with that number
  local -A dup_files=()   # DR-NNN -> space-separated list of all colliding files

  local rel base num
  for rel in "${files[@]}"; do
    base="$(basename "$rel")"

    if [[ ! "$base" =~ ^DR-([0-9]{3})-.+\.md$ ]]; then
      echo "MALFORMED DECISION-RECORD FILENAME: $rel" >&2
      echo "  expected DR-NNN-<slug>.md with exactly three digits (see $RECORDS_DIR/README.md)" >&2
      found=1
      continue
    fi

    num="DR-${BASH_REMATCH[1]}"

    if [[ -n "${owner[$num]:-}" ]]; then
      if [[ -z "${dup_files[$num]:-}" ]]; then
        dup_files[$num]="${owner[$num]}"
      fi
      dup_files[$num]="${dup_files[$num]} $rel"
      found=1
    else
      owner[$num]="$rel"
    fi
  done

  if [[ ${#dup_files[@]} -gt 0 ]]; then
    local n f
    for n in $(printf '%s\n' "${!dup_files[@]}" | sort); do
      echo "DUPLICATE DECISION-RECORD NUMBER: $n is claimed by more than one file" >&2
      for f in ${dup_files[$n]}; do
        echo "  $f" >&2
      done
    done
  fi

  if [[ "$found" -ne 0 ]]; then
    {
      echo ""
      echo "check-dr-numbering: FAIL — $RECORDS_DIR/ violates the"
      echo "one-file-per-decision, DR-NNN-<slug>.md convention. Decision records are"
      echo "append-only (CLAUDE.md), so a duplicate number cannot be cheaply undone"
      echo "once merged — it has to be superseded, and every unqualified \"DR-NNN\""
      echo "reference in prose stays ambiguous meanwhile. Note that a parallel branch"
      echo "can claim a number that is still free on main (#140), so renumber against"
      echo "the numbers claimed by open PRs too, not just against main."
    } >&2
    return 1
  fi

  echo "check-dr-numbering: OK — ${#files[@]} decision record(s), all well-named and uniquely numbered."
  return 0
}

# --- Self-test --------------------------------------------------------------
self_test() {
  local tmp status failures=0
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN

  # expect_exit <expected> <label> <fixture-dir>
  expect_exit() {
    local expected="$1" label="$2" dir="$3" out
    set +e
    out="$(check_root "$dir" 2>&1)"
    status=$?
    set -e
    if [[ "$status" -ne "$expected" ]]; then
      echo "  FAIL: $label — expected exit $expected, got $status" >&2
      printf '%s\n' "$out" | sed 's/^/    | /' >&2
      failures=$((failures + 1))
      return
    fi
    echo "  ok: $label (exit $status)"
    LAST_OUTPUT="$out"
  }

  # Case 1: a clean, well-numbered set passes.
  local clean="$tmp/clean/$RECORDS_DIR"
  mkdir -p "$clean"
  : >"$clean/README.md"
  : >"$clean/TEMPLATE.md"
  : >"$clean/DR-001-alpha.md"
  : >"$clean/DR-002-beta.md"
  expect_exit 0 "clean tree passes (README.md/TEMPLATE.md ignored)" "$tmp/clean"

  # Case 2: two files sharing DR-008 fail, and BOTH are named.
  local dup="$tmp/dup/$RECORDS_DIR"
  mkdir -p "$dup"
  : >"$dup/DR-007-psrr.md"
  : >"$dup/DR-008-iq-budget.md"
  : >"$dup/DR-008-thermal.md"
  expect_exit 1 "duplicate DR-008 fails" "$tmp/dup"
  local msg="${LAST_OUTPUT:-}"
  for expect in "DR-008" "DR-008-iq-budget.md" "DR-008-thermal.md"; do
    if ! printf '%s' "$msg" | grep -qF "$expect"; then
      echo "  FAIL: duplicate message does not mention '$expect'" >&2
      failures=$((failures + 1))
    fi
  done
  if printf '%s' "$msg" | grep -qF "DR-007-psrr.md"; then
    echo "  FAIL: duplicate message wrongly implicates the non-colliding DR-007" >&2
    failures=$((failures + 1))
  fi

  # Case 3: a malformed number (DR-08-) fails rather than silently dodging
  # the duplicate check against DR-008.
  local bad="$tmp/bad/$RECORDS_DIR"
  mkdir -p "$bad"
  : >"$bad/DR-008-good.md"
  : >"$bad/DR-08-short.md"
  expect_exit 1 "malformed DR-08- filename fails" "$tmp/bad"

  # Case 4: an empty/absent records directory is a no-op, not a failure.
  mkdir -p "$tmp/empty"
  expect_exit 0 "absent records directory is a no-op" "$tmp/empty"

  # Case 5: the git-tracked path is what CI exercises — an UNTRACKED colliding
  # file in a real git repo must not fail the check (and a tracked one must).
  local repo="$tmp/repo"
  mkdir -p "$repo/$RECORDS_DIR"
  git -C "$repo" init -q
  : >"$repo/$RECORDS_DIR/DR-001-alpha.md"
  git -C "$repo" add "$RECORDS_DIR/DR-001-alpha.md"
  : >"$repo/$RECORDS_DIR/DR-001-untracked-clone.md"
  expect_exit 0 "untracked collision in a git repo is ignored" "$repo"
  git -C "$repo" add "$RECORDS_DIR/DR-001-untracked-clone.md"
  expect_exit 1 "tracked collision in a git repo fails" "$repo"

  if [[ "$failures" -ne 0 ]]; then
    echo "check-dr-numbering --self-test: FAIL ($failures assertion(s))" >&2
    return 1
  fi
  echo "check-dr-numbering --self-test: OK"
  return 0
}

# --- Entry point ------------------------------------------------------------
if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,60p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi

if [[ $# -ge 1 && -n "${1:-}" ]]; then
  ROOT="$1"
else
  if ! ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    # .loom/scripts/ -> .loom/ -> repo root
    ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
  fi
fi

check_root "$ROOT"
