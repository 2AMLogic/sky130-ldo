#!/usr/bin/env bash
# layout/bin/run-ldo-lvs-flow.sh -- run `klt extract` against the committed
# LDO-core layout and `klt lvs` against a reference netlist mechanically
# derived from design/ldo_3v3in_1v8out.sch's own xschem netlist (issue #17).
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/bin/run-ldo-lvs-flow.sh
#
# Requires: layout/.venv (see setup-venv.sh), `xschem` on PATH with the
# pinned sky130A PDK resolvable (same pin as sim/pdk.json), and a landed
# ldo-core layout record (layout/ldo-core/reports/LATEST).
#
# IMPORTANT: as of this repo's first run (issue #17), this reports
# `status: mismatch`, not `match` -- the committed ldo-core layout
# (layout/ldo-core/reports/<record-id>/, issue #15) is a placed-but-unrouted
# floorplan skeleton built against an earlier revision of the schematic
# (before issue #22 added current-limit/soft-start devices), so it neither
# has the full device set nor any inter-block routing. See the rendered
# record.md's "Root cause" section and layout/ldo-core/floorplan.md's
# "Explicitly out of scope" note. This script exists so the *next* run --
# once a follow-on issue extends the floorplan and adds routing -- is a
# one-command re-check, not a redesign of the LVS pipeline.
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
BLOCK_DIR="$LAYOUT_DIR/ldo-core"
KLT="$LAYOUT_DIR/.venv/bin/klt"
CELL=ldo_core
PDK_VARIANT=sky130A
SCHEMATIC="$REPO_ROOT/design/ldo_3v3in_1v8out.sch"

if [[ ! -x "$KLT" ]]; then
  echo "run-ldo-lvs-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-ldo-lvs-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

if ! command -v xschem >/dev/null; then
  echo "run-ldo-lvs-flow.sh: xschem not found on PATH -- needed to netlist the schematic" >&2
  exit 1
fi

LAYOUT_RECORD_ID="$(cat "$BLOCK_DIR/reports/LATEST")"
LAYOUT_RECORD_DIR="$BLOCK_DIR/reports/$LAYOUT_RECORD_ID"
if [[ ! -f "$LAYOUT_RECORD_DIR/$CELL.gds" ]]; then
  echo "run-ldo-lvs-flow.sh: $LAYOUT_RECORD_DIR/$CELL.gds not found -- run layout/bin/run-ldo-layout-flow.sh first" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-ldo-lvs-flow.sh: record $RECORD_ID -> $OUT_DIR (layout from $LAYOUT_RECORD_ID)"

SCHEMATIC_SHA="$(git -C "$REPO_ROOT" log -1 --format=%h -- design/ldo_3v3in_1v8out.sch design/README.md)"
LAYOUT_SHA="$(git -C "$REPO_ROOT" log -1 --format=%h -- layout/ldo-core)"

cp "$LAYOUT_RECORD_DIR/$CELL.gds" "$OUT_DIR/$CELL.gds"
echo "$LAYOUT_RECORD_ID" > "$OUT_DIR/layout-record-id.txt"

# --- 1. Netlist the schematic headlessly (same invocation design/README.md
#         documents for validating the schematic) -----------------------------
XSCHEM_OUT="$OUT_DIR/xschem_out"
mkdir -p "$XSCHEM_OUT"
xschem -n -q -x -s -o "$XSCHEM_OUT" --rcfile "$REPO_ROOT/sim/xschemrc" "$SCHEMATIC"
SCHEM_NETLIST="$XSCHEM_OUT/ldo_3v3in_1v8out.spice"
if [[ ! -f "$SCHEM_NETLIST" ]]; then
  echo "run-ldo-lvs-flow.sh: expected $SCHEM_NETLIST after xschem netlisting" >&2
  exit 1
fi
MISSING_COUNT="$(grep -c MISSING "$SCHEM_NETLIST" || true)"
echo "run-ldo-lvs-flow.sh: schematic netlist MISSING count = $MISSING_COUNT"

# --- 2. Translate the schematic netlist into an LVS reference -------------
python3 "$LAYOUT_DIR/bin/gen-ldo-reference-netlist.py" \
  --netlist "$SCHEM_NETLIST" --subckt-name "$CELL" --ports "VOUT VREF EN VIN" \
  -o "$OUT_DIR/reference.spice"

# --- 3. Extract the composed layout ----------------------------------------
"$KLT" extract "$OUT_DIR/$CELL.gds" --deck sky130 --top "$CELL" \
  -o "$OUT_DIR/$CELL.extract.spice" --format json > "$OUT_DIR/extract.json"

# --- 4. LVS: extracted layout vs. schematic-derived reference --------------
cat > "$OUT_DIR/lvs.request.json" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": { "file": "$CELL.gds", "deck": "sky130", "top": "$CELL" },
  "reference": { "netlist": "reference.spice", "top": "$CELL" }
}
EOF
"$KLT" lvs "$OUT_DIR/lvs.request.json" --format json > "$OUT_DIR/lvs.json" || true

# --- 5. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/lvs.json" --format github-summary > "$OUT_DIR/report.md"

# --- 6. Record summary (honest pass/fail verdict, root-caused if mismatch) -
# render-ldo-lvs-record.py exits non-zero when the verdict is not a clean
# LVS match -- captured deliberately (not `set -e` fatal) so the record.md
# it already wrote before returning is preserved as evidence either way.
set +e
python3 "$LAYOUT_DIR/bin/render-ldo-lvs-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --cell-name "$CELL" \
  --schematic-sha "$SCHEMATIC_SHA" --layout-sha "$LAYOUT_SHA" \
  --layout-record-id "$LAYOUT_RECORD_ID" \
  > "$OUT_DIR/record.md"
RECORD_STATUS=$?
set -e

echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST-LVS"

echo "run-ldo-lvs-flow.sh: done. See $OUT_DIR/record.md"
exit "$RECORD_STATUS"
