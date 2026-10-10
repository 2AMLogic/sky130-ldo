#!/usr/bin/env bash
# layout/bin/run-ldo-layout-flow.sh -- regenerate the sky130 LDO core
# regulation loop's layout (issues #15/#33): one `klt gen` block per active
# device in design/ldo_3v3in_1v8out.sch, placed via `klt gen-compose`
# (placement.strategy: "explicit"), wired net-for-net by gen-ldo-blocks.py's
# channel router, and checked for DRC cleanliness under BOTH the curated klt
# deck and the PDK's own official sky130A_mr.drc (issue #260; a record is PASS
# only if both are clean, and the script exits nonzero otherwise). LVS is a separate driver
# (run-ldo-lvs-flow.sh, issue #17) run against this flow's output; see
# layout/ldo-core/floorplan.md for the floorplan and routing rationale.
#
# The device set is read from the schematic's own headless xschem netlist,
# not from a table checked into this repo -- the layout cannot describe a
# different device set than the schematic (issue #33; a hand-maintained
# table is exactly what went stale and produced #17's first mismatch).
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/bin/run-ldo-layout-flow.sh
#
# Requires: layout/.venv (see setup-venv.sh), `xschem` and `klayout` on PATH, and a
# resolvable sky130A PDK install (same pin as sim/pdk.json; `volare enable
# --pdk sky130 <sha>`).
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
BLOCK_DIR="$LAYOUT_DIR/ldo-core"
KLT="$LAYOUT_DIR/.venv/bin/klt"
CELL=ldo_core
PDK_VARIANT=sky130A
SCHEMATIC="$REPO_ROOT/design/ldo_3v3in_1v8out.sch"
PINS="VOUT,VREF,EN,VIN"

if [[ ! -x "$KLT" ]]; then
  echo "run-ldo-layout-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-ldo-layout-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

if ! command -v xschem >/dev/null; then
  echo "run-ldo-layout-flow.sh: xschem not found on PATH -- needed to netlist the schematic this layout is generated from" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-ldo-layout-flow.sh: record $RECORD_ID -> $OUT_DIR"

# Schematic-only: tracks the exact same path `measurements/
# build_characterization_report.py`'s freshness check compares against
# (`SCHEMATIC_FILE`, the .sch alone). Including design/README.md here used
# to also fold in that doc's own last-touched commit, which meant a
# README-only edit (documentation, no device-geometry change) could bump
# this beyond the checker's notion of "current" and mark an up-to-date
# layout STALE for no schematic-content reason (issue #89).
SCHEMATIC_SHA="$(git -C "$REPO_ROOT" log -1 --format=%h -- design/ldo_3v3in_1v8out.sch)"

# --- 1. Netlist the schematic headlessly (this layout's device set) --------
XSCHEM_OUT="$OUT_DIR/xschem_out"
mkdir -p "$XSCHEM_OUT"
xschem -n -q -x -s -o "$XSCHEM_OUT" --rcfile "$REPO_ROOT/sim/xschemrc" "$SCHEMATIC"
SCHEM_NETLIST="$XSCHEM_OUT/ldo_3v3in_1v8out.spice"
if [[ ! -f "$SCHEM_NETLIST" ]]; then
  echo "run-ldo-layout-flow.sh: expected $SCHEM_NETLIST after xschem netlisting" >&2
  exit 1
fi

# --- 2. Generate every device's klt gen block, compose, and route ----------
# Run under layout/.venv: the router draws its own wiring with `klayout.db`,
# a `klt` dependency rather than a system-python one.
"$LAYOUT_DIR/.venv/bin/python" "$LAYOUT_DIR/bin/gen-ldo-blocks.py" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --out-dir "$OUT_DIR" --cell-name "$CELL" \
  --netlist "$SCHEM_NETLIST" --pins "$PINS" \
  --spec "$REPO_ROOT/spec/target-spec.md" --deck sky130 \
  > "$OUT_DIR/gen-ldo-blocks.log"

# --- 3. DRC the routed layout: curated klt deck, then the PDK's own deck ----
# Two separate gates on the same ldo_core.gds (issue #260). The curated deck
# is a hand-transcribed subset; the official `sky130A_mr.drc` is what a
# tapeout would be checked against. Neither failure aborts the flow here: both
# results are retained in the record, which renders FAIL and makes this script
# exit nonzero (see the end).
"$KLT" drc "$OUT_DIR/$CELL.gds" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# Official deck: same invocation and switches as run-cap-rail-demo-flow.sh
# (FEOL/BEOL/offgrid on; floating-metal and seal off). The run is recorded in
# mr-drc.run.json whether or not it succeeds; the renderer treats a missing
# deck, missing klayout, nonzero exit, or absent/malformed/empty report as an
# ERROR, never as a clean result (a zero exit alone proves nothing).
MR_DECK_NAME=sky130A_mr.drc
PDK_KLAYOUT="$("$KLT" pdk find --pdk "$PDK_VARIANT" --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["assets"]["klayout"])')"
MR_DECK="${LDO_MR_DECK:-$PDK_KLAYOUT/drc/$MR_DECK_NAME}"  # override: tests only
MR_SWITCHES="feol=true beol=true offgrid=true floating_met=false seal=false"
MR_DECK_PRESENT=false; MR_KLAYOUT_FOUND=false; MR_RC=null; MR_SHA=""; MR_KLAYOUT_VERSION=""
if [[ -f "$MR_DECK" ]]; then
  MR_DECK_PRESENT=true
  MR_SHA="$(sha256sum "$MR_DECK" | cut -d' ' -f1)"
fi
if command -v klayout >/dev/null; then MR_KLAYOUT_FOUND=true; fi
if [[ "$MR_DECK_PRESENT" == true && "$MR_KLAYOUT_FOUND" == true ]]; then
  MR_KLAYOUT_VERSION="$(klayout -v 2>&1 | head -1 || true)"
  # The deck's progress log is ~100 kB of per-layer timing and host paths: it
  # stays in $TMPDIR; only its tail is kept, and only when the run fails.
  MR_LOG="$(mktemp "${TMPDIR:-/tmp}/ldo-core-mr-drc.XXXXXX")"
  set +e
  klayout -b -r "$MR_DECK" -rd "input=$OUT_DIR/$CELL.gds" -rd "report=$OUT_DIR/mr-drc.lyrdb" \
    -rd feol=true -rd beol=true -rd offgrid=true -rd floating_met=false -rd seal=false \
    > "$MR_LOG" 2>&1
  MR_RC=$?
  set -e
  if [[ "$MR_RC" -ne 0 ]]; then tail -n 40 "$MR_LOG" > "$OUT_DIR/mr-drc.error.txt"; fi
fi
python3 - "$OUT_DIR/mr-drc.run.json" "$MR_DECK_NAME" "$MR_DECK_PRESENT" "$MR_KLAYOUT_FOUND" \
  "$MR_RC" "$MR_SHA" "$MR_KLAYOUT_VERSION" "$MR_SWITCHES" <<'PYEOF'
import json, sys
out, name, present, found, rc, sha, ver, sw = sys.argv[1:9]
json.dump({
    "schema": "ldo-official-drc-run/1",
    "deck_name": name, "deck_present": present == "true", "klayout_found": found == "true",
    "exit_code": None if rc == "null" else int(rc),
    "deck_sha256": sha or None, "klayout_version": ver or None,
    "switches": sw, "report": "mr-drc.lyrdb",
}, open(out, "w"), indent=1)
PYEOF

# Attribute any official markers (best effort: a diagnosis failure must not
# mask the DRC verdict, and the renderer notes its absence).
if [[ -s "$OUT_DIR/mr-drc.lyrdb" ]]; then
  "$LAYOUT_DIR/.venv/bin/python" "$LAYOUT_DIR/bin/diagnose-official-drc.py" \
    --gds "$OUT_DIR/$CELL.gds" --lyrdb "$OUT_DIR/mr-drc.lyrdb" \
    --out "$OUT_DIR/official-drc-diagnosis.json" \
    || echo "run-ldo-layout-flow.sh: WARNING: diagnosis failed (record will say so)" >&2
fi

# --- 4. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" --format github-summary > "$OUT_DIR/report.md" || true

# --- 5. Record summary (pass/fail verdict, evidence-record style) ----------
# A FAIL verdict must not skip the pointer update or the message: the record
# of a failing run is retained evidence.
set +e
python3 "$LAYOUT_DIR/bin/render-ldo-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --cell-name "$CELL" \
  --schematic-sha "$SCHEMATIC_SHA" \
  > "$OUT_DIR/record.md"
STATUS=$?
set -e

# `LATEST` names the NEWEST record, PASS or FAIL (mirrors the cap-rail
# demonstrator): a failing record is the truthful current state, and the
# verdict a reader sees through the pointer is the record's own. (Before #260
# a failing render aborted the script ahead of this line, leaving the pointer
# on the previous record.) Earlier records are never rewritten.
echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"

echo "run-ldo-layout-flow.sh: done (render exit $STATUS). See $OUT_DIR/record.md"
exit "$STATUS"
