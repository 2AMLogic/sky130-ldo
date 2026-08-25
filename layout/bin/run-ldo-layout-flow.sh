#!/usr/bin/env bash
# layout/bin/run-ldo-layout-flow.sh -- regenerate the sky130 LDO core
# regulation loop's layout (issues #15/#33): one `klt gen` block per active
# device in design/ldo_3v3in_1v8out.sch, placed via `klt gen-compose`
# (placement.strategy: "explicit"), wired net-for-net by gen-ldo-blocks.py's
# channel router, and checked for DRC cleanliness. LVS is a separate driver
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
# Requires: layout/.venv (see setup-venv.sh), `xschem` on PATH, and a
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
  > "$OUT_DIR/gen-ldo-blocks.log"

# --- 3. DRC the routed layout against the sky130 deck ----------------------
"$KLT" drc "$OUT_DIR/$CELL.gds" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 4. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" --format github-summary > "$OUT_DIR/report.md"

# --- 5. Record summary (pass/fail verdict, evidence-record style) ----------
python3 "$LAYOUT_DIR/bin/render-ldo-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --cell-name "$CELL" \
  --schematic-sha "$SCHEMATIC_SHA" \
  > "$OUT_DIR/record.md"

# Keep a "latest" pointer, mirroring trivial-cell/reports/LATEST.
echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"

echo "run-ldo-layout-flow.sh: done. See $OUT_DIR/record.md"
