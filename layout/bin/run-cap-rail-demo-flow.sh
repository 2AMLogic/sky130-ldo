#!/usr/bin/env bash
# layout/bin/run-cap-rail-demo-flow.sh -- mint one evidence record for the
# MiM-capacitor + supply-rail overlay demonstrator (issue #254).
#
# NOT a full-core flow: it draws the schematic's four capacitors as stacked
# MiM arrays over the planned core outline, plus the two load-current rails
# on the proposed metal assignment, then checks that geometry with
#   1. `klt drc --deck sky130`                         (curated deck)
#   2. the PDK's own sky130A_mr.drc via `klayout -b`    (official deck; it
#      also covers capm.2b/2b_a/11 and the two-adjacent-edge via
#      enclosures the curated deck documents as not modelled)
#   3. `klt extract` (devices) and `klt extract --parasitics` (coupling)
#   4. `klt lvs` against a reference derived from the schematic's own
#      xschem netlist, plus two negative controls that must NOT match.
# See layout/cap-rail-demo/README.md for what each result does and does not
# establish.
#
# Usage:
#   layout/bin/run-cap-rail-demo-flow.sh
#
# Requires: `xschem` and `klayout` on PATH, the pinned sky130A PDK
# (sim/pdk.json), and the klt pin in layout/cap-requirements.txt -- either
# installed at layout/.venv-cap (setup-venv.sh --requirements
# layout/cap-requirements.txt) or reachable through `uvx --from` (a throwaway
# environment; this script never installs anything host-wide).
set -euo pipefail

# LAYOUT_DIR/REPO_ROOT, the PDK guard, the record mint and the headless
# netlist step are shared with the other layout/bin/run-*-flow.sh drivers
# (issue #599). The uvx fallback below stays local to this script: it is the
# only driver with one.
source "$(dirname "${BASH_SOURCE[0]}")/_flow_common.sh"
BLOCK_DIR="$LAYOUT_DIR/cap-rail-demo"
CELL=cap_rail_demo
PDK_VARIANT=sky130A
REQ_FILE="$LAYOUT_DIR/cap-requirements.txt"
PINS="VOUT,VIN,EA_CZ,CL_CMP,SS,TS_CMP"
# Measured inputs: the routed layout record the #246 study measured, and the
# study's own budget (MOS-domain width, channel/row/rail heights, banks).
MEASURED_RECORD="layout/ldo-core/reports/20260924-221821-a947aa8"
BUDGET="layout/area-study/20261009-study-246/budget.json"

PIN_SPEC="$(grep -v '^[[:space:]]*#' "$REQ_FILE" | grep -v '^[[:space:]]*$' | head -1)"
if [[ -x "$LAYOUT_DIR/.venv-cap/bin/klt" ]]; then
  KLT=("$LAYOUT_DIR/.venv-cap/bin/klt")
  PY=("$LAYOUT_DIR/.venv-cap/bin/python")
elif command -v uvx >/dev/null; then
  KLT=(uvx --from "$PIN_SPEC" klt)
  PY=(uvx --from "$PIN_SPEC" python)
else
  echo "run-cap-rail-demo-flow.sh: no layout/.venv-cap and no uvx -- see layout/cap-requirements.txt" >&2
  exit 1
fi
for tool in xschem klayout; do
  command -v "$tool" >/dev/null || { echo "run-cap-rail-demo-flow.sh: $tool not on PATH" >&2; exit 1; }
done
flow_require_pdk run-cap-rail-demo-flow.sh "$PDK_VARIANT" "see sim/pdk.json" "${KLT[@]}"
PDK_KLAYOUT="$("${KLT[@]}" pdk find --pdk "$PDK_VARIANT" --format json | python3 -c 'import json,sys; print(json.load(sys.stdin)["assets"]["klayout"])')"
MR_DECK="$PDK_KLAYOUT/drc/sky130A_mr.drc"
[[ -f "$MR_DECK" ]] || { echo "run-cap-rail-demo-flow.sh: $MR_DECK not found" >&2; exit 1; }

cd "$REPO_ROOT"
flow_mint_record run-cap-rail-demo-flow.sh "$BLOCK_DIR/reports" --rel
SCHEMATIC_SHA="$(git log -1 --format=%h -- design/ldo_3v3in_1v8out.sch)"

# --- 1. schematic netlist (the capacitor list comes from here) --------------
flow_netlist_schematic run-cap-rail-demo-flow.sh \
  "$REPO_ROOT/design/ldo_3v3in_1v8out.sch" "$OUT_DIR/xschem_out" "${KLT[@]}"
NETLIST_REL="${SCHEM_NETLIST#"$REPO_ROOT"/}"

# --- 2. draw ----------------------------------------------------------------
"${PY[@]}" layout/bin/gen-cap-rail-demo.py \
  --netlist "$NETLIST_REL" \
  --floorplan "$MEASURED_RECORD/floorplan.json" \
  --measured-gds "$MEASURED_RECORD/ldo_core.gds" \
  --budget "$BUDGET" --spec spec/target-spec.md --deck sky130 \
  --out-dir "$OUT_REL" --cell-name "$CELL" > "$OUT_DIR/gen.log"

cd "$OUT_DIR"
# --- 3. DRC: curated klt deck, then the PDK's own deck ----------------------
"${KLT[@]}" drc "$CELL.gds" --deck sky130 --format json > drc.json || true
# The deck's own progress log is ~100 kB of per-layer timing and host paths;
# it stays out of the record (the result is mr-drc.lyrdb) and is left in
# $TMPDIR for inspection.
MR_LOG="$(mktemp "${TMPDIR:-/tmp}/cap-rail-mr-drc.XXXXXX")"
if ! klayout -b -r "$MR_DECK" -rd input="$CELL.gds" -rd report=mr-drc.lyrdb \
  -rd feol=true -rd beol=true -rd offgrid=true -rd floating_met=false -rd seal=false \
  > "$MR_LOG" 2>&1; then
  echo "run-cap-rail-demo-flow.sh: official DRC run failed; see $MR_LOG" >&2
  exit 1
fi
klayout -v > klayout-version.txt 2>&1 || true

# --- 4. extraction: devices, then parasitics with coupling ------------------
"${KLT[@]}" extract "$CELL.gds" --deck sky130 --top "$CELL" --pins "$PINS" \
  -o "$CELL.extract.spice" --format json > extract.json
"${KLT[@]}" extract "$CELL.gds" --deck sky130 --top "$CELL" --pins "$PINS" --parasitics \
  --critical-net EA_CZ --critical-net CL_CMP --critical-net SS --critical-net TS_CMP \
  -o "$CELL.pex.spice" --format json > pex.json

# --- 5. LVS ------------------------------------------------------------------
# The verdict compares the extracted netlist (layout.netlist shape) -- see the
# README for why the layout.file shape is also run and kept as evidence.
write_request() {  # $1 out file, $2 layout json fragment, $3 reference netlist
  cat > "$1" <<EOF
{
  "schema": "klt.lvs.request/1",
  "engine": "klayout",
  "layout": $2,
  "reference": {"netlist": "$3", "top": "$CELL"},
  "hints": {"same_nets": [["0", "0"]]},
  "options": {"combine_devices": true, "parameter_tolerance": 0.001, "anchor_top_level_pins": true}
}
EOF
}
DECLARED='"declared_pins": ["VOUT", "VIN", "EA_CZ", "CL_CMP", "SS", "TS_CMP"]'
LAYOUT_NETLIST="{\"netlist\": \"$CELL.extract.spice\", \"deck\": \"sky130\", \"top\": \"$CELL\", $DECLARED}"
LAYOUT_FILE="{\"file\": \"$CELL.gds\", \"deck\": \"sky130\", \"top\": \"$CELL\", $DECLARED}"

write_request lvs.request.json "$LAYOUT_NETLIST" reference.spice
"${KLT[@]}" lvs lvs.request.json --format json > lvs.json || true
write_request lvs-gds-shape.request.json "$LAYOUT_FILE" reference.spice
"${KLT[@]}" lvs lvs-gds-shape.request.json --format json > lvs-gds-shape.json || true

# Negative controls: each must come back `mismatch`, or the match above
# proves nothing about values / connectivity. The connectivity control moves
# C_TS's outer terminal from VIN to 0 (every net still exists on both sides,
# so the compare runs rather than erroring on a missing hint net).
sed -e 's/^\(C_COMP_M[34] VOUT EA_CZ\) [^ ]*/\1 5.000000e-11/' reference.spice > reference.neg-value.spice
sed -e 's/^\(C_TS_M[34]\) VIN TS_CMP /\1 0 TS_CMP /' reference.spice > reference.neg-net.spice
write_request lvs-neg-value.request.json "$LAYOUT_NETLIST" reference.neg-value.spice
"${KLT[@]}" lvs lvs-neg-value.request.json --format json > lvs-neg-value.json || true
write_request lvs-neg-net.request.json "$LAYOUT_NETLIST" reference.neg-net.spice
"${KLT[@]}" lvs lvs-neg-net.request.json --format json > lvs-neg-net.json || true

"${KLT[@]}" version --format json > klt-version.json

# --- 6. record ---------------------------------------------------------------
cd "$REPO_ROOT"
set +e
python3 layout/bin/render-cap-rail-record.py --out-dir "$OUT_REL" --record-id "$RECORD_ID" \
  --schematic-sha "$SCHEMATIC_SHA" --pin "$PIN_SPEC" > "$OUT_DIR/record.md"
STATUS=$?
set -e
echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST"
echo "run-cap-rail-demo-flow.sh: done (render exit $STATUS). See $OUT_REL/record.md"
exit "$STATUS"
