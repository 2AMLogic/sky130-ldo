#!/usr/bin/env bash
# Fail locally when a branch edits a file that T1 item 10's attestation pins by
# content hash without re-minting that attestation (issue #579).
#
# WHY THIS EXISTS
#
# `signoff/check.sh` stage 1b runs, for items 1, 9 and 10:
#
#     klt signoff --attest N --inventory …/itemN-inventory.json \
#                            --check …/itemN-attestation.generic.json
#
# `--check` re-attests and diffs the *whole* fresh envelope against the
# committed one, excluding only the producing build's version strings. Item
# 10's `hygiene` entries read as *presence* checks -- `signoff/README.md`
# states the item as those inventoried files *existing* -- but `_file_check()`
# in klt's signoff_attest.py stamps a `content_hash` onto every one of them,
# and that hash participates in the diff. So **any byte change to any inventoried hygiene file is drift**, and
# the PR that makes it must carry a re-mint commit or land red.
#
# Measured on 2026-11-14: all six re-mints of the item-10 envelope since it was
# created on 2026-11-05 were *reactive* -- they landed after a failed CI run,
# each one costing a full round trip (a red `T1 tier report` job, a Judge pass,
# a Doctor pass). This guard moves that failure to before the push.
#
# WHAT IT DOES AND DOES NOT CHECK
#
# It answers exactly one question: "you edited an attested hygiene file and did
# not re-mint." It deliberately does **not** verify that a re-mint is
# *correct* -- stage 1b already does that, authoritatively, and is the only
# thing that can. Being wrong here can only ever cost a CI round trip that is
# already the status quo; being silent cannot.
#
# The hygiene list is read out of the inventory at runtime. There is no second
# copy of those paths in this file on purpose: a hardcoded copy is the one way
# this guard would silently stop covering a path later added to the inventory.
# The klayout-tools pin in the printed re-mint command is likewise read out of
# `signoff/check.sh`, so the two cannot drift apart.
#
# No klt, no network, no PDK -- git plus python3, both of which `check:ci`
# already requires. (python3 rather than jq: jq is not otherwise a dependency
# of this repo's checks, and a check that cannot run must never look like one
# that passed.)
#
# USAGE
#
#     bash signoff/check-attested-hygiene.sh [--base REF]
#
# `--base` defaults to `origin/main`. Exit 0 = clean, 1 = unre-minted drift,
# 2 = the guard could not run (never a silent pass).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

INVENTORY="signoff/evidence/item10-inventory.json"
ATTESTATION="signoff/evidence/item10-attestation.generic.json"
CHECK_SH="signoff/check.sh"
BASE="origin/main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      [[ $# -ge 2 ]] || { echo "$0: --base needs a ref" >&2; exit 2; }
      BASE="$2"; shift 2 ;;
    -h|--help)
      sed -n '/^# USAGE/,/^$/p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)
      echo "usage: bash signoff/check-attested-hygiene.sh [--base REF]" >&2; exit 2 ;;
  esac
done

die() { echo "signoff/check-attested-hygiene.sh: $*" >&2; exit 2; }

[[ -f "$INVENTORY" ]]   || die "inventory $INVENTORY is missing -- cannot determine the attested hygiene set"
[[ -f "$ATTESTATION" ]] || die "attestation $ATTESTATION is missing -- re-mint it before running this guard"
[[ -f "$CHECK_SH" ]]    || die "$CHECK_SH is missing -- cannot read the klayout-tools pin"

# --- the attested hygiene set, read out of the inventory (never hardcoded) ---
HYGIENE="$(python3 - "$INVENTORY" <<'PY'
import json, sys
path = sys.argv[1]
try:
    doc = json.loads(open(path, encoding="utf-8").read())
except (OSError, ValueError) as exc:
    sys.exit(f"{path}: unreadable or not valid JSON: {exc}")
entries = doc.get("hygiene")
if not isinstance(entries, list) or not entries:
    sys.exit(f"{path}: 'hygiene' is missing, empty, or not a list")
if not all(isinstance(e, str) and e and "\n" not in e for e in entries):
    sys.exit(f"{path}: 'hygiene' must be a list of non-empty path strings")
print("\n".join(entries))
PY
)" || die "could not read the hygiene inventory (see the error above)"

# --- the klayout-tools pin, read out of check.sh (never a second copy) ---
KLT_VERSION="$(sed -n 's/^KLT_VERSION="\([^"]*\)".*$/\1/p' "$CHECK_SH" | head -n 1)"
[[ -n "$KLT_VERSION" ]] || die "could not read KLT_VERSION out of $CHECK_SH"

# --- resolve the base ref; fetch once if it is absent, never skip -----------
if ! git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null; then
  echo "signoff/check-attested-hygiene.sh: '$BASE' not present locally; fetching once…" >&2
  if [[ "$BASE" == origin/* ]]; then
    git fetch --quiet origin "${BASE#origin/}" 2>/dev/null || true
  else
    git fetch --quiet --all 2>/dev/null || true
  fi
  git rev-parse --verify --quiet "${BASE}^{commit}" >/dev/null \
    || die "base ref '$BASE' cannot be resolved even after a fetch.
  This guard compares your work against that ref, so it cannot run -- and a
  check that cannot run must never look like one that passed.
  Fix the remote (or pass --base <a ref that exists>) and re-run."
fi

MERGE_BASE="$(git merge-base "$BASE" HEAD 2>/dev/null)" \
  || die "no merge base between '$BASE' and HEAD (unrelated histories?) -- cannot scope the diff"

# Working tree included on purpose: the drift is worth naming before the
# commit, not only before the push. On CI the tree equals HEAD, so this is
# exactly the branch diff there.
CHANGED="$(git diff --name-only "$MERGE_BASE" --)"

# --- intersect ---------------------------------------------------------------
TOUCHED=""
while IFS= read -r path; do
  [[ -n "$path" ]] || continue
  if printf '%s\n' "$CHANGED" | grep -qxF -- "$path"; then
    TOUCHED+="${path}"$'\n'
  fi
done <<< "$HYGIENE"

[[ -n "$TOUCHED" ]] || exit 0

if printf '%s\n' "$CHANGED" | grep -qxF -- "$ATTESTATION"; then
  exit 0
fi

{
  echo "signoff/check-attested-hygiene.sh: T1 item 10 attestation drift is not re-minted."
  echo
  echo "Changed against ${BASE}, and pinned by content hash in"
  echo "${ATTESTATION}:"
  printf '%s' "$TOUCHED" | sed 's/^/  - /'
  echo
  echo "Those paths are listed in ${INVENTORY}'s 'hygiene' set, so klt stamps a"
  echo "content_hash on each of them and 'signoff/check.sh' stage 1b diffs it."
  echo "Any byte change is drift: without a re-mint in this same branch, the"
  echo "'T1 tier report' CI job will fail with"
  echo "  signoff/check.sh: item 10 attestation drifted -- re-mint with klt signoff --attest 10"
  echo
  echo "Re-mint, then commit the re-minted envelope alongside your edit:"
  echo
  echo "  uvx --from klayout-tools==${KLT_VERSION} klt signoff --attest 10 \\"
  echo "    --inventory ${INVENTORY} \\"
  echo "    -o ${ATTESTATION}"
  echo
  echo "See signoff/README.md -> 'Attested hygiene files: a content edit is drift'."
} >&2
exit 1
