#!/usr/bin/env bash
# layout/bin/run-ldo-layout-flow.sh -- regenerate the sky130 LDO core
# regulation loop's placed floorplan skeleton (issue #15): one `klt gen`
# block per active device in design/ldo_3v3in_1v8out.sch (issue #14),
# composed via `klt gen-compose` (placement.strategy: "explicit") and
# checked for DRC cleanliness. NOT an LVS-verified result -- inter-block
# routing and LVS are issue #17's job; see layout/ldo-core/floorplan.md for
# the full scope boundary and floorplan rationale.
#
# Usage:
#   layout/bin/setup-venv.sh          # once, or after bumping requirements.txt
#   layout/bin/run-ldo-layout-flow.sh
#
# Requires: layout/.venv (see setup-venv.sh) and a resolvable sky130A PDK
# install (same pin as sim/pdk.json; `volare enable --pdk sky130 <sha>`).
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
BLOCK_DIR="$LAYOUT_DIR/ldo-core"
KLT="$LAYOUT_DIR/.venv/bin/klt"
CELL=ldo_core
PDK_VARIANT=sky130A

if [[ ! -x "$KLT" ]]; then
  echo "run-ldo-layout-flow.sh: $KLT not found -- run layout/bin/setup-venv.sh first" >&2
  exit 1
fi

if ! "$KLT" pdk find --pdk "$PDK_VARIANT" >/dev/null; then
  echo "run-ldo-layout-flow.sh: no resolvable $PDK_VARIANT PDK -- see sim/pdk.json for the pin" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-ldo-layout-flow.sh: record $RECORD_ID -> $OUT_DIR"

SCHEMATIC_SHA="$(git -C "$REPO_ROOT" log -1 --format=%h -- design/ldo_3v3in_1v8out.sch design/README.md)"

# --- 1. Generate every device's klt gen block and compose the floorplan ---
python3 "$LAYOUT_DIR/bin/gen-ldo-blocks.py" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --out-dir "$OUT_DIR" --cell-name "$CELL" \
  > "$OUT_DIR/gen-ldo-blocks.log"

# --- 2. DRC the composed floorplan against the sky130 deck -----------------
"$KLT" drc "$OUT_DIR/$CELL.gds" --deck sky130 --format json > "$OUT_DIR/drc.json" || true

# --- 3. Combined human-readable report --------------------------------------
"$KLT" report "$OUT_DIR/drc.json" --format github-summary > "$OUT_DIR/report.md"

# --- 4. Record summary (pass/fail verdict, evidence-record style) ----------
python3 "$LAYOUT_DIR/bin/render-ldo-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --pdk-variant "$PDK_VARIANT" --cell-name "$CELL" \
  --schematic-sha "$SCHEMATIC_SHA" \
  > "$OUT_DIR/record.md"

# Keep a "latest" pointer, mirroring trivial-cell/reports/LATEST.
echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"

echo "run-ldo-layout-flow.sh: done. See $OUT_DIR/record.md"
