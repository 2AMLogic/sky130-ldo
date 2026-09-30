#!/usr/bin/env bash
# Re-grade this block's T1 state from signoff/block-manifest.json and fail if
# the committed verdict of record has rotted (issue #113).
#
# Usage:
#   bash signoff/check.sh            # verify: re-run and diff against the committed record
#   bash signoff/check.sh --write    # regenerate signoff/records/t1-tier-report.json
#
# What this guards, in order
# --------------------------
# 1. **Every pinned content_hash still matches the artifact it covers.**
#    `klt signoff` compares a manifest's pin against the *cited envelope's own*
#    `provenance.input.content_hash` -- it never opens the underlying artifact,
#    and klt 0.6.0 says so on every pinned citation it prints ("input: not
#    re-hashed ... the artifact itself was not read"). Two hand-written files
#    agreeing with each other proves nothing on its own, so this step re-hashes
#    every artifact named in signoff/artifact-pins.json and cross-checks it
#    against the envelope's own claim and against the manifest's pin. Touch the
#    layout GDS, the LVS reference netlist, the MC netlist snapshot or
#    measurements/characterization.md without re-pinning, and this fails --
#    which is the whole point: a citation that cannot rot is a citation that
#    proves nothing.
#
#    Each side of that cross-check is matched to the other *by the file it
#    names* (manifest `file` vs. pin `cited_envelope`), never by "this hash
#    turns up somewhere under this item" (issue #222). Item 11's compound
#    citation has two halves whose content_hash is legitimately identical --
#    both read the same GDS -- so a pooled hash set let either half's pin
#    satisfy the other half's check, and deleting one of the two pins outright
#    still passed. Per-file correlation is what makes each half stand on its
#    own. Implemented in signoff/verify-pins.py, with the mutation coverage
#    that proves it in signoff/tests/test_verify_pins.py.
# 2. **`klt signoff --manifest` runs clean.** Exit 0 (T1 reached) and exit 3
#    (ran fine, not yet T1) are both clean runs of the grader; 1 and 2 mean a
#    broken manifest or a tier doc this klt cannot parse.
# 3. **The committed record still matches a fresh run.** Either this block's
#    evidence moved or the checklist did. Both are real news, and neither
#    should be discoverable only by someone re-reading prose.
#
# Why klt is pinned to an exact release here
# ------------------------------------------
# `klt signoff` parses the T1 item list out of klayout-tools' own
# docs/design-evidence-tiers.md, bundled inside the installed wheel -- so the
# tool version decides which checklist this block is graded against. That list
# is not stable: it grew an eleventh item ("Power delivery (structural)",
# klayout-tools#2025) on 2026-09-17, which invalidated every hand-read that
# predates it and is exactly why klayout-tools==0.5.0 renders a ten-item report
# with no item-11 row at all. An unpinned install would therefore make the
# committed record irreproducible. KLT_VERSION below is that pin; bumping it is
# a real change to the yardstick, so expect signoff/records/t1-tier-report.json
# to move in the same commit and re-read signoff/README.md's per-item notes
# against any item the bump adds or rewords.
#
# This pin is deliberately independent of layout/requirements.txt's `klt` pin.
# That one fixes the toolchain that *produced* this repo's DRC/LVS/PEX
# evidence; this one fixes the grader that *reads* it. They move for different
# reasons and are not expected to match -- they do not today (0.2.0 vs 0.6.0).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# klayout-tools release this block is graded against. See the header above
# before changing it.
KLT_VERSION="0.6.0"

MANIFEST="signoff/block-manifest.json"
PINS="signoff/artifact-pins.json"
RECORD="signoff/records/t1-tier-report.json"

WRITE=0
if [[ "${1:-}" == "--write" ]]; then
  WRITE=1
elif [[ $# -gt 0 ]]; then
  echo "usage: bash signoff/check.sh [--write]" >&2
  exit 2
fi

# ---------------------------------------------------------------------------
# 1. Pinned hashes vs. the artifacts they claim to cover.
#
# The verification itself lives in signoff/verify-pins.py rather than in a
# heredoc here, so signoff/tests/test_verify_pins.py can run the real stage
# against a mutated pin file (issue #222). It needs nothing but python3 -- no
# klt, no PDK, no network -- which is also why `npm run check:ci` can run its
# unit coverage on every push while this script's later stages cannot.
# ---------------------------------------------------------------------------
python3 signoff/verify-pins.py "$MANIFEST" "$PINS"

# ---------------------------------------------------------------------------
# 2 + 3. Re-grade, and compare against the committed verdict of record.
# ---------------------------------------------------------------------------
FRESH="$(mktemp)"
trap 'rm -f "$FRESH"' EXIT

if command -v uvx >/dev/null 2>&1; then
  KLT=(uvx --from "klayout-tools==${KLT_VERSION}" klt)
elif command -v klt >/dev/null 2>&1 && [[ "$(klt --version 2>/dev/null)" == "klt ${KLT_VERSION}" ]]; then
  KLT=(klt)
else
  echo "signoff/check.sh: need uvx, or klt ${KLT_VERSION} on PATH." >&2
  echo "  install uv:  python3 -m pip install --user uv" >&2
  echo "  or klt:      python3 -m pip install --user 'klayout-tools==${KLT_VERSION}'" >&2
  exit 2
fi

set +e
"${KLT[@]}" signoff --manifest "$MANIFEST" --format json >"$FRESH"
rc=$?
set -e

# 0 = every T1 item met; 3 = ran fine, not yet T1. Both are a clean run of the
# grader. 1/2 mean the manifest or the tier doc could not be read at all.
if [[ "$rc" -ne 0 && "$rc" -ne 3 ]]; then
  echo "signoff/check.sh: klt signoff --manifest failed (exit $rc)" >&2
  cat "$FRESH" >&2
  exit 1
fi

if [[ "$WRITE" -eq 1 ]]; then
  python3 -c '
import json, sys
report = json.load(open(sys.argv[1]))
with open(sys.argv[2], "w") as fh:
    json.dump(report, fh, indent=2)
    fh.write("\n")
' "$FRESH" "$RECORD"
  echo "signoff/check.sh: wrote $RECORD"
  exit 0
fi

python3 - "$FRESH" "$RECORD" <<'PY'
import json
import sys

fresh = json.load(open(sys.argv[1]))
try:
    committed = json.load(open(sys.argv[2]))
except FileNotFoundError:
    print(
        f"signoff/check.sh: {sys.argv[2]} is missing -- regenerate it with "
        f"'bash signoff/check.sh --write' and commit it",
        file=sys.stderr,
    )
    sys.exit(1)

if fresh != committed:
    print(
        "signoff/check.sh: the committed T1 verdict of record is stale.\n"
        "  A fresh 'klt signoff --manifest' run no longer matches\n"
        f"  {sys.argv[2]}. That is not a tool bug: either this block's\n"
        "  evidence moved, or the checklist did. Regenerate with\n"
        "    bash signoff/check.sh --write\n"
        "  commit the result, and update signoff/README.md's reading of any\n"
        "  item whose status or reason changed.",
        file=sys.stderr,
    )
    sys.exit(1)

met = fresh.get("t1_met_count")
total = fresh.get("t1_item_count")
print(
    f"signoff/check.sh: verdict of record is current -- "
    f"T1 {met}/{total} items met, tier={fresh.get('tier')!r}"
)
PY
