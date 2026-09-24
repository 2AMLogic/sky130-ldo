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
# ---------------------------------------------------------------------------
python3 - "$MANIFEST" "$PINS" <<'PY'
import hashlib
import json
import pathlib
import sys

manifest_path, pins_path = (pathlib.Path(a) for a in sys.argv[1:3])
root = pathlib.Path.cwd()
manifest = json.loads(manifest_path.read_text())
pins = json.loads(pins_path.read_text())["pins"]

failures: list[str] = []


def norm(value):
    """Both hash spellings this repo's envelopes use, reduced to bare hex."""
    if not isinstance(value, str):
        return None
    return value[len("sha256:"):] if value.startswith("sha256:") else value


def dotted(doc, path):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# Every item the manifest cites must appear in the pin file, so a new citation
# cannot be added without also declaring what artifact it is really about.
cited_items = set(manifest.get("evidence") or {})
pinned_items = {str(p["item"]) for p in pins}
for item in sorted(cited_items - pinned_items):
    failures.append(
        f"manifest item {item}: cited, but signoff/artifact-pins.json declares "
        f"no artifact for it -- a citation with no re-hashable artifact behind "
        f"it cannot be freshness-checked by CI"
    )
for item in sorted(pinned_items - cited_items):
    failures.append(
        f"artifact-pins.json item {item}: pinned, but the manifest cites no "
        f"evidence for that item -- a stale pin for a dropped citation"
    )

for pin in pins:
    item = str(pin["item"])
    artifact = root / pin["artifact"]
    expected = norm(pin["sha256"])

    if not artifact.is_file():
        failures.append(f"item {item}: artifact {pin['artifact']!r} does not exist")
        continue
    actual = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if actual != expected:
        failures.append(
            f"item {item}: {pin['artifact']!r} hashes to sha256:{actual} today, "
            f"but signoff/artifact-pins.json pins {pin['sha256']} -- the cited "
            f"evidence moved and the citation was not re-pinned"
        )
        continue

    envelope_path = root / pin["cited_envelope"]
    if not envelope_path.is_file():
        failures.append(
            f"item {item}: cited envelope {pin['cited_envelope']!r} does not exist"
        )
        continue
    envelope = json.loads(envelope_path.read_text())

    field = pin.get("envelope_field")
    if field:
        claimed = norm(dotted(envelope, field))
        if claimed != expected:
            failures.append(
                f"item {item}: {pin['cited_envelope']!r} claims {field}="
                f"{dotted(envelope, field)!r}, but {pin['artifact']!r} is "
                f"sha256:{expected} -- the envelope is about a different "
                f"revision than the artifact committed here"
            )

    # A manifest pin is graded by `klt signoff` against the envelope's own
    # claim; re-pinning only one of the two files must not pass silently.
    entry = (manifest.get("evidence") or {}).get(item)
    manifest_hash = norm(entry.get("content_hash")) if isinstance(entry, dict) else None
    if pin.get("manifest_pinned"):
        if manifest_hash is None:
            failures.append(
                f"item {item}: artifact-pins.json says manifest_pinned, but the "
                f"manifest pins no content_hash for it"
            )
        elif manifest_hash != expected:
            failures.append(
                f"item {item}: manifest pins sha256:{manifest_hash}, "
                f"artifact-pins.json pins sha256:{expected}"
            )

# Conversely: a manifest pin must be backed by a pin declared `manifest_pinned`
# for the same item, so the manifest cannot pin a hash nothing on disk covers.
for item, entry in sorted((manifest.get("evidence") or {}).items()):
    manifest_hash = norm(entry.get("content_hash")) if isinstance(entry, dict) else None
    if manifest_hash is None:
        continue
    backing = [
        p for p in pins
        if str(p["item"]) == item and p.get("manifest_pinned")
        and norm(p["sha256"]) == manifest_hash
    ]
    if not backing:
        failures.append(
            f"manifest item {item}: pins sha256:{manifest_hash}, which no "
            f"manifest_pinned entry in signoff/artifact-pins.json covers"
        )

if failures:
    print("signoff/check.sh: pinned-hash verification FAILED", file=sys.stderr)
    for line in failures:
        print(f"  - {line}", file=sys.stderr)
    sys.exit(1)

print(f"signoff/check.sh: {len(pins)} pinned artifact(s) match their citations")
PY

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
