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
#   3. status/index (#292): each record's `- **Status**:` line yields a first
#      status word (Markdown emphasis ignored) that is exactly `proposed`,
#      `ratified` or `superseded`; and the README "Status inventory" table
#      (header `| Record | Status | Ratifying reference | Governs |`) lists
#      every record exactly once with the same status, and names no record
#      that does not exist. Ratification authority is NOT inferred here.
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

INDEX_HEADER_RE='^\|[[:space:]]*Record[[:space:]]*\|[[:space:]]*Status[[:space:]]*\|[[:space:]]*Ratifying reference[[:space:]]*\|[[:space:]]*Governs[[:space:]]*\|[[:space:]]*$'

# declared_status <file> -> prints first status word (lowercased as written),
# or nothing if there is no `- **Status**:` field / no word after it.
declared_status() {
  local line
  line="$(grep -m1 -E '^- \*\*Status\*\*:' "$1" || true)"
  [[ -z "$line" ]] && return 0
  line="${line#*:}"                 # drop "- **Status**" and the colon
  line="${line//[*_\`]/}"           # ignore Markdown emphasis / code ticks
  if [[ "$line" =~ ^[^[:alnum:]]*([[:alnum:]-]+) ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  fi
}

# check_status_index <root> <rel-file>... -> 0 ok / 1 problems (stderr)
check_status_index() {
  local root="$1"; shift
  local -a files=("$@")
  local bad=0 rel base num st
  local -A file_status=() file_path=()

  for rel in "${files[@]}"; do
    base="$(basename "$rel")"
    [[ "$base" =~ ^DR-([0-9]{3})-.+\.md$ ]] || continue
    num="DR-${BASH_REMATCH[1]}"
    [[ -n "${file_path[$num]:-}" ]] && continue   # duplicates reported elsewhere
    file_path[$num]="$rel"
    st="$(declared_status "$root/$rel")"
    if [[ -z "$st" ]]; then
      echo "MISSING DECISION-RECORD STATUS: $rel has no '- **Status**:' value" >&2
      bad=1
    elif [[ "$st" != "proposed" && "$st" != "ratified" && "$st" != "superseded" ]]; then
      echo "INVALID DECISION-RECORD STATUS: $rel declares '$st' (allowed: proposed, ratified, superseded)" >&2
      bad=1
    else
      file_status[$num]="$st"
    fi
  done

  local readme="$root/$RECORDS_DIR/README.md"
  if [[ ! -f "$readme" ]]; then
    echo "MISSING DECISION-RECORD INDEX: $RECORDS_DIR/README.md not found" >&2
    return 1
  fi

  local in_table=0 seen_header=0 line c1 c2 id
  local -A idx_status=() idx_count=()
  while IFS= read -r line; do
    if [[ $in_table -eq 0 ]]; then
      if [[ "$line" =~ $INDEX_HEADER_RE ]]; then in_table=1; seen_header=1; fi
      continue
    fi
    [[ "$line" =~ ^\| ]] || { in_table=0; continue; }
    [[ "$line" =~ ^\|[[:space:]]*-+ ]] && continue   # separator row
    IFS='|' read -r _ c1 c2 _ <<<"$line"
    if [[ "$c1" =~ DR-([0-9]{3}) ]]; then
      id="DR-${BASH_REMATCH[1]}"
    else
      echo "MALFORMED INDEX ROW in $RECORDS_DIR/README.md: no DR-NNN in '$line'" >&2
      bad=1; continue
    fi
    c2="${c2//[*_\`[:space:]]/}"
    idx_count[$id]=$(( ${idx_count[$id]:-0} + 1 ))
    idx_status[$id]="$c2"
  done <"$readme"

  if [[ $seen_header -eq 0 ]]; then
    echo "MISSING DECISION-RECORD INDEX TABLE: $RECORDS_DIR/README.md has no 'Record | Status | Ratifying reference | Governs' table" >&2
    return 1
  fi

  local n
  for n in $(printf '%s\n' "${!file_path[@]}" | sort); do
    if [[ -z "${idx_count[$n]:-}" ]]; then
      echo "RECORD NOT INDEXED: $n (${file_path[$n]}) has no row in the README status inventory" >&2
      bad=1
    elif [[ "${idx_count[$n]}" -gt 1 ]]; then
      echo "RECORD INDEXED MORE THAN ONCE: $n appears ${idx_count[$n]} times in the README status inventory" >&2
      bad=1
    elif [[ -n "${file_status[$n]:-}" && "${idx_status[$n]}" != "${file_status[$n]}" ]]; then
      echo "STATUS MISMATCH: $n (${file_path[$n]}) declares '${file_status[$n]}' but the README index says '${idx_status[$n]}'" >&2
      bad=1
    fi
  done
  for n in $(printf '%s\n' "${!idx_count[@]}" | sort); do
    if [[ -z "${file_path[$n]:-}" ]]; then
      echo "INDEX NAMES NONEXISTENT RECORD: $n is in the README status inventory but no tracked $RECORDS_DIR/$n-*.md exists" >&2
      bad=1
    fi
  done
  return $bad
}

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

  check_status_index "$root" "${files[@]}" || found=1

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

  echo "check-dr-numbering: OK — ${#files[@]} decision record(s), all well-named, uniquely numbered, with a valid status matching the README index."
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


  # mk_dr <dir> <NNN> <slug> <status-line-body>: write a minimal record.
  mk_dr() { printf '# DR-%s: t\n\n- **Status**: %s\n' "$2" "$4" >"$1/DR-$2-$3.md"; }
  # mk_index <dir> <row>...: write a README with the inventory table.
  mk_index() {
    local d="$1"; shift
    {
      echo "# Decision records"; echo
      echo "| Record | Status | Ratifying reference | Governs |"
      echo "| --- | --- | --- | --- |"
      printf '%s\n' "$@"
    } >"$d/README.md"
  }

  # Case 1: a clean, well-numbered set passes.
  local clean="$tmp/clean/$RECORDS_DIR"
  mkdir -p "$clean"
  : >"$clean/TEMPLATE.md"
  mk_dr "$clean" 001 alpha '**ratified** — by #1'
  mk_dr "$clean" 002 beta 'proposed — not self-ratifying'
  mk_index "$clean" \
    '| [DR-001](DR-001-alpha.md) | ratified | #1 | a |' \
    '| [DR-002](DR-002-beta.md) | proposed | unresolved — see #301 | b |'
  expect_exit 0 "clean tree passes (README.md/TEMPLATE.md ignored)" "$tmp/clean"

  # Case 2: two files sharing DR-008 fail, and BOTH are named.
  local dup="$tmp/dup/$RECORDS_DIR"
  mkdir -p "$dup"
  mk_dr "$dup" 007 psrr proposed
  mk_dr "$dup" 008 iq-budget proposed
  mk_dr "$dup" 008 thermal proposed
  mk_index "$dup" '| [DR-007](DR-007-psrr.md) | proposed | x | y |' \
    '| [DR-008](DR-008-iq-budget.md) | proposed | x | y |'
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
  mk_dr "$repo/$RECORDS_DIR" 001 alpha 'proposed'
  mk_index "$repo/$RECORDS_DIR" '| [DR-001](DR-001-alpha.md) | proposed | x | y |'
  git -C "$repo" add "$RECORDS_DIR/DR-001-alpha.md" "$RECORDS_DIR/README.md"
  mk_dr "$repo/$RECORDS_DIR" 001 untracked-clone 'proposed' 
  expect_exit 0 "untracked collision in a git repo is ignored" "$repo"
  git -C "$repo" add "$RECORDS_DIR/DR-001-untracked-clone.md"
  expect_exit 1 "tracked collision in a git repo fails" "$repo"

  # --- status / index cases (#292) ---
  # expect_msg <needle>...: the last expect_exit output must contain each.
  expect_msg() {
    local label="$1" n; shift
    for n in "$@"; do
      if ! printf '%s' "${LAST_OUTPUT:-}" | grep -qF -- "$n"; then
        echo "  FAIL: $label — diagnostic does not mention '$n'" >&2
        failures=$((failures + 1))
      fi
    done
  }
  # status_fixture <name> -> sets $sf to a root with DR-001 (ratified) and
  # DR-002 (proposed), correctly indexed; caller then mutates it.
  status_fixture() {
    local d="$tmp/$1/$RECORDS_DIR"
    mkdir -p "$d"
    mk_dr "$d" 001 alpha '**ratified** — by #1'
    mk_dr "$d" 002 beta '_proposed_ — pending'
    mk_index "$d" \
      '| [DR-001](DR-001-alpha.md) | ratified | #1 | a |' \
      '| [DR-002](DR-002-beta.md) | proposed | unresolved — see #301 | b |'
    sf="$tmp/$1"; sfd="$d"
  }
  local sf sfd

  status_fixture s_ok
  expect_exit 0 "valid inventory passes (emphasis variants tolerated)" "$sf"

  status_fixture s_badword
  mk_dr "$sfd" 002 beta '**draft** — not a legal word'
  expect_exit 1 "invalid status word fails" "$sf"
  expect_msg "invalid status" "DR-002-beta.md" "draft"

  status_fixture s_nostatus
  printf '# DR-002: t\n' >"$sfd/DR-002-beta.md"
  expect_exit 1 "missing status field fails" "$sf"
  expect_msg "missing status" "DR-002-beta.md"

  status_fixture s_omit
  mk_dr "$sfd" 003 gamma 'proposed'
  expect_exit 1 "record omitted from the index fails" "$sf"
  expect_msg "omitted" "DR-003" "NOT INDEXED"

  status_fixture s_mismatch
  mk_dr "$sfd" 002 beta 'ratified'
  expect_exit 1 "index status disagreeing with the file fails" "$sf"
  expect_msg "mismatch" "DR-002" "declares 'ratified'" "index says 'proposed'"

  status_fixture s_extra
  printf '%s\n' '| [DR-009](DR-009-ghost.md) | proposed | x | y |' >>"$sfd/README.md"
  expect_exit 1 "index entry for a nonexistent record fails" "$sf"
  expect_msg "extra" "DR-009" "NONEXISTENT"

  status_fixture s_dup
  printf '%s\n' '| [DR-001](DR-001-alpha.md) | ratified | #1 | a |' >>"$sfd/README.md"
  expect_exit 1 "duplicate index row fails" "$sf"
  expect_msg "dup" "DR-001" "MORE THAN ONCE"

  status_fixture s_notable
  printf '# Decision records\n\nno table\n' >"$sfd/README.md"
  expect_exit 1 "README without the inventory table fails" "$sf"

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
