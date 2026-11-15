#!/usr/bin/env bash
# Fail locally when the tree no longer matches the content hashes that T1
# item 10's attestation pins (issues #579 and #588).
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
# 10's `hygiene` entries are stamped with a `content_hash` each, and that
# hash participates in the diff -- so **any byte change to any inventoried
# hygiene file is drift**, and the PR that makes it must carry a re-mint
# commit or land red.
#
# Measured on 2026-11-14: all six re-mints of the item-10 envelope since it
# was created on 2026-11-05 were *reactive* -- they landed after a failed CI
# run, each one costing a full round trip (a red `T1 tier report` job, a
# Judge pass, a Doctor pass). This guard moves that failure to before the
# push.
#
# WHAT IT CHECKS
#
# An exact envelope-vs-tree comparison. For every path in
# item10-inventory.json's `hygiene` list, compare sha256(raw bytes of the
# file on disk) against that path's `content_hash` pin in
# item10-attestation.generic.json. A changed file, a deleted inventoried
# file, and an inventoried file with no pin in the envelope are all drift:
# the guard exits 1 naming every offending path. This answers exactly one
# question -- "your envelope does not describe your tree" -- which is the
# question stage 1b asks, and the one the diff heuristic this replaces
# (#588) could only approximate: a branch that edited a hygiene file *and*
# already carried a re-mint of an earlier edit passed while its tree was
# still drifted.
#
# WHAT IT DOES AND DOES NOT CHECK
#
# It does not verify that a re-mint is *correct* -- stage 1b already does
# that, authoritatively, and is the only thing that can. It also does not
# validate provenance, klt_version, the audit-role command checks, or the
# inventory's own provenance hashes: stage 1b's, all of them. Being wrong
# here can only ever cost a CI round trip that is already the status quo;
# being silent cannot.
#
# The hygiene list is read out of the inventory at runtime. There is no
# second copy of those paths in this file on purpose: a hardcoded copy is
# the one way this guard would silently stop covering a path later added to
# the inventory. The klayout-tools pin in the printed re-mint command is
# likewise read out of `signoff/check.sh`, so the two cannot drift apart.
#
# No klt, no network, no PDK -- python3, which `check:ci` already requires
# (git is used only to locate the repo root). (python3 rather than jq: jq is
# not otherwise a dependency of this repo's checks, and a check that cannot
# run must never look like one that passed.)
#
# USAGE
#
#     bash signoff/check-attested-hygiene.sh [--self-test]
#
# Exit 0 = the envelope matches the tree, 1 = drift (offenders named on
# stderr), 2 = the guard could not run (never a silent pass). `--self-test`
# runs the fixture suite in a throwaway directory and exits nonzero on any
# assertion failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# check_root <root> -> 0 the envelope matches the tree, 1 drift (offenders
# named on stderr), 2 the guard could not run.
check_root() {
  local root="$1"
  local inv="$root/signoff/evidence/item10-inventory.json"
  local att="$root/signoff/evidence/item10-attestation.generic.json"
  local check_sh="$root/signoff/check.sh"

  [[ -f "$inv" ]] || { echo "signoff/check-attested-hygiene.sh: inventory signoff/evidence/item10-inventory.json is missing under $root -- cannot determine the attested hygiene set" >&2; return 2; }
  [[ -f "$att" ]] || { echo "signoff/check-attested-hygiene.sh: attestation signoff/evidence/item10-attestation.generic.json is missing under $root -- re-mint it before running this guard" >&2; return 2; }
  [[ -f "$check_sh" ]] || { echo "signoff/check-attested-hygiene.sh: signoff/check.sh is missing under $root -- cannot read the klayout-tools pin" >&2; return 2; }

  local klt_version
  klt_version="$(sed -n 's/^KLT_VERSION="\([^"]*\)".*$/\1/p' "$check_sh" | head -n 1)"
  [[ -n "$klt_version" ]] || { echo "signoff/check-attested-hygiene.sh: could not read a non-empty KLT_VERSION out of signoff/check.sh" >&2; return 2; }

  local drift
  if ! drift="$(python3 - "$root" "$inv" "$att" <<'PY'
import hashlib, json, os, sys

root, inv_path, att_path = sys.argv[1:4]

def cannot_run(msg):
    print(f"signoff/check-attested-hygiene.sh: {msg}", file=sys.stderr)
    sys.exit(2)

try:
    inv = json.loads(open(inv_path, encoding="utf-8").read())
except (OSError, ValueError) as exc:
    cannot_run(f"{inv_path}: unreadable or not valid JSON: {exc}")

entries = inv.get("hygiene")
if not isinstance(entries, list) or not entries:
    cannot_run(f"{inv_path}: 'hygiene' is missing, empty, or not a list")
if not all(isinstance(e, str) and e and "\n" not in e for e in entries):
    cannot_run(f"{inv_path}: 'hygiene' must be a list of non-empty path strings")

try:
    att = json.loads(open(att_path, encoding="utf-8").read())
except (OSError, ValueError) as exc:
    cannot_run(f"{att_path}: unreadable or not valid JSON: {exc}")

pins = {}
for check in att.get("attestation", {}).get("checks", []):
    if isinstance(check, dict) and check.get("role") == "hygiene":
        pins[check.get("path")] = check.get("content_hash")

for rel in entries:
    p = os.path.join(root, rel)
    if not os.path.isfile(p):
        print(f"{rel}: inventoried hygiene file is missing from the tree")
        continue
    pin = pins.get(rel)
    if not isinstance(pin, str) or not pin.startswith("sha256:"):
        print(f"{rel}: inventoried hygiene file has no content_hash pin in the envelope")
        continue
    digest = hashlib.sha256(open(p, "rb").read()).hexdigest()
    if f"sha256:{digest}" != pin:
        print(f"{rel}: sha256 {digest} != envelope pin {pin.split(':', 1)[1]}")
PY
)"; then
    echo "signoff/check-attested-hygiene.sh: could not run the envelope-vs-tree comparison (see the error above)" >&2
    return 2
  fi

  if [[ -z "$drift" ]]; then
    echo "check-attested-hygiene: OK — every inventoried hygiene file matches its item 10 envelope content_hash pin."
    return 0
  fi

  {
    echo "signoff/check-attested-hygiene.sh: T1 item 10 attestation does not describe the tree."
    echo
    echo "The committed envelope signoff/evidence/item10-attestation.generic.json pins"
    echo "these inventoried hygiene paths by content hash, but their bytes on disk"
    echo "no longer match:"
    printf '%s\n' "$drift" | sed 's/^/  - /'
    echo
    echo "Those paths are listed in signoff/evidence/item10-inventory.json's 'hygiene'"
    echo "set, so klt stamps a content_hash on each of them and 'signoff/check.sh'"
    echo "stage 1b diffs the whole envelope. Any byte change is drift: without a"
    echo "re-mint in this same branch, the 'T1 tier report' CI job will fail with"
    echo "  signoff/check.sh: item 10 attestation drifted -- re-mint with klt signoff --attest 10"
    echo
    echo "Re-mint, then commit the re-minted envelope alongside your edit:"
    echo
    echo "  uvx --from klayout-tools==${klt_version} klt signoff --attest 10 \\"
    echo "    --inventory signoff/evidence/item10-inventory.json \\"
    echo "    -o signoff/evidence/item10-attestation.generic.json"
    echo
    echo "See signoff/README.md -> 'Attested hygiene files: a content edit is drift'."
  } >&2
  return 1
}

# --- Self-test --------------------------------------------------------------
self_test() {
  local tmp status failures=0
  tmp="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$tmp'" RETURN
  local fd="$tmp/fx"
  LAST_OUTPUT=""

  # expect_exit <expected> <label> <dir>: run check_root against a fixture
  # directory, assert the exit code, keep the output for expect_named.
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
      LAST_OUTPUT=""
      return
    fi
    echo "  ok: $label (exit $status)"
    LAST_OUTPUT="$out"
  }
  # expect_named <label> <needle>: the last expect_exit's output names <needle>.
  expect_named() {
    local label="$1" needle="$2"
    if [[ -z "$LAST_OUTPUT" ]] || ! grep -qF -- "$needle" <<<"$LAST_OUTPUT"; then
      echo "  FAIL: $label — expected the output to name '$needle'" >&2
      printf '%s\n' "$LAST_OUTPUT" | sed 's/^/    | /' >&2
      failures=$((failures + 1))
      return
    fi
    echo "  ok: $label"
  }

  # build_fixture <dir>: (re)write a minimal item-10 tree whose envelope pins
  # the sha256 of each hygiene file's CURRENT bytes -- i.e. what a correct
  # klt re-mint produces for that tree.
  build_fixture() {
    local d="$1"
    mkdir -p "$d/signoff/evidence" "$d/docs" "$d/sim" "$d/.github/workflows"
    printf '# readme\n' >"$d/README.md"
    printf 'license text\n' >"$d/LICENSE"
    printf '# env setup\n' >"$d/docs/environment-setup.md"
    printf '# sim log\n' >"$d/sim/README.md"
    printf 'on: push\n' >"$d/.github/workflows/ci.yml"
    printf '# not attested\n' >"$d/docs/other.md"
    printf 'KLT_VERSION="0.9.0"\n' >"$d/signoff/check.sh"
    python3 - "$d" <<'PY'
import hashlib, json, os, sys
d = sys.argv[1]
paths = ["README.md", "LICENSE", "docs/environment-setup.md",
         "sim/README.md", ".github/workflows/ci.yml"]
ev = os.path.join(d, "signoff", "evidence")
inv = {"schema_version": 1, "kind": "t1-attestation-inventory", "t1_item": 10,
       "description": "fixture", "hygiene": list(paths),
       "checks": [{"argv": ["npm", "run", "lint"], "timeout_s": 600, "name": "repo-lint"}]}
checks = [{"check": "present", "role": "hygiene", "path": p, "passed": True,
           "content_hash": "sha256:" +
             hashlib.sha256(open(os.path.join(d, p), "rb").read()).hexdigest()}
          for p in paths]
checks.append({"check": "command", "role": "audit", "name": "repo-lint",
               "argv": ["npm", "run", "lint"], "cwd": ".", "exit_status": 0,
               "passed": True})
att = {"schema_version": 1, "kind": "generic", "status": "pass", "t1_item": 10,
       "attestation": {"producer": "klt signoff --attest",
                       "inventory_schema_version": 1,
                       "hash_algorithm": "sha256-raw-bytes",
                       "check_count": len(checks),
                       "passed_count": len(checks), "checks": checks}}
json.dump(inv, open(os.path.join(ev, "item10-inventory.json"), "w"), indent=2)
json.dump(att, open(os.path.join(ev, "item10-attestation.generic.json"), "w"), indent=2)
PY
  }

  # drop_pin <dir> <path|ALL>: remove hygiene-role pin(s) from the envelope.
  drop_pin() {
    python3 - "$1" "$2" <<'PY'
import json, os, sys
p = os.path.join(sys.argv[1], "signoff", "evidence", "item10-attestation.generic.json")
doc = json.loads(open(p).read())
target = sys.argv[2]
cs = doc["attestation"]["checks"]
if target == "ALL":
    cs = [c for c in cs if c.get("role") != "hygiene"]
else:
    cs = [c for c in cs
          if not (c.get("role") == "hygiene" and c.get("path") == target)]
doc["attestation"]["checks"] = cs
json.dump(doc, open(p, "w"), indent=2)
PY
  }

  # inventory_mutate <dir> <missing|empty|scalar>: corrupt the inventory's
  # hygiene list so the guard must refuse to run (exit 2).
  inventory_mutate() {
    python3 - "$1" "$2" <<'PY'
import json, os, sys
p = os.path.join(sys.argv[1], "signoff", "evidence", "item10-inventory.json")
doc = json.loads(open(p).read())
mode = sys.argv[2]
if mode == "missing":
    del doc["hygiene"]
elif mode == "empty":
    doc["hygiene"] = []
elif mode == "scalar":
    doc["hygiene"] = "README.md"
json.dump(doc, open(p, "w"), indent=2)
PY
  }

  build_fixture "$fd"
  expect_exit 0 "clean fixture passes" "$fd"

  printf 'edited\n' >>"$fd/sim/README.md"
  expect_exit 1 "edited hygiene file without re-mint fails" "$fd"
  expect_named "edited file is named" "sim/README.md"

  printf 'x\n' >>"$fd/README.md"
  printf 'y\n' >>"$fd/LICENSE"
  expect_exit 1 "several drifted paths at once fail" "$fd"
  expect_named "first drifted path named" "README.md"
  expect_named "second drifted path named" "LICENSE"

  build_fixture "$fd"
  expect_exit 0 "a hygiene edit with a correct re-mint passes" "$fd"

  printf 'second edit\n' >>"$fd/sim/README.md"
  expect_exit 1 "a further edit after a re-mint fails (the #588 blind spot)" "$fd"
  expect_named "blind-spot path is named" "sim/README.md"

  rm "$fd/docs/environment-setup.md"
  expect_exit 1 "deleted inventoried path fails" "$fd"
  expect_named "deleted path is named" "docs/environment-setup.md"

  build_fixture "$fd"
  drop_pin "$fd" "sim/README.md"
  expect_exit 1 "inventoried path with no envelope pin fails" "$fd"
  expect_named "unpinned path is named" "sim/README.md"

  build_fixture "$fd"
  drop_pin "$fd" "ALL"
  expect_exit 1 "envelope with no hygiene-role entries names every path" "$fd"
  expect_named "README named" "README.md"
  expect_named "ci.yml named" ".github/workflows/ci.yml"

  build_fixture "$fd"
  printf '# not attested, edited\n' >"$fd/docs/other.md"
  expect_exit 0 "a non-inventoried file's edit passes" "$fd"

  build_fixture "$fd"
  printf 'garbage{\n' >"$fd/signoff/evidence/item10-inventory.json"
  expect_exit 2 "unparseable inventory exits 2" "$fd"

  build_fixture "$fd"; inventory_mutate "$fd" missing
  expect_exit 2 "'hygiene' missing from the inventory exits 2" "$fd"

  build_fixture "$fd"; inventory_mutate "$fd" empty
  expect_exit 2 "empty 'hygiene' list exits 2" "$fd"

  build_fixture "$fd"; inventory_mutate "$fd" scalar
  expect_exit 2 "non-list 'hygiene' exits 2" "$fd"

  build_fixture "$fd"
  rm "$fd/signoff/evidence/item10-attestation.generic.json"
  expect_exit 2 "missing attestation exits 2" "$fd"

  build_fixture "$fd"
  rm "$fd/signoff/check.sh"
  expect_exit 2 "missing signoff/check.sh exits 2" "$fd"

  build_fixture "$fd"
  printf 'KLT_VERSION=""\n' >"$fd/signoff/check.sh"
  expect_exit 2 "empty KLT pin exits 2" "$fd"

  set +e
  bash "${BASH_SOURCE[0]}" --base origin/main >/dev/null 2>&1
  status=$?
  set -e
  if [[ "$status" -ne 2 ]]; then
    echo "  FAIL: unrecognized argument — expected exit 2, got $status" >&2
    failures=$((failures + 1))
  else
    echo "  ok: unrecognized argument exits 2 (exit 2)"
  fi

  if [[ "$failures" -ne 0 ]]; then
    echo "check-attested-hygiene --self-test: FAIL ($failures assertion(s))" >&2
    return 1
  fi
  echo "check-attested-hygiene --self-test: OK"
}

# --- Entry point ------------------------------------------------------------
if [[ "${1:-}" == "--self-test" ]]; then
  self_test
  exit $?
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '/^# USAGE/,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 0
fi

if [[ $# -ge 1 ]]; then
  echo "usage: bash signoff/check-attested-hygiene.sh [--self-test|-h]" >&2
  exit 2
fi

if ! ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
  ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

check_root "$ROOT"
