#!/usr/bin/env bash
# sim/pex-post-layout/bin/run-pex.sh -- regenerate the testbench pair from
# the current schematic + landed layout, then run `klt pex` against the
# landed LDO-core layout and record the result (issue #20).
#
# Usage:
#   sim/pex-post-layout/bin/run-pex.sh [--klt <path-to-klt>]
#
# Requires: a `klt` implementing `klt pex` (Epic #709 Phase 1a) --
# `layout/requirements.txt`'s pinned `layout/.venv/bin/klt` predates this
# verb (no `pex` in its `<command>` list as of this experiment; see
# README.md), so this defaults to the ambient `klt` on PATH unless
# --klt overrides it. `xschem` on PATH with the pinned sky130A PDK
# resolvable (same pin as sim/pdk.json).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$EXP_DIR/../.." && pwd)"

KLT="${KLT:-klt}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --klt) KLT="$2"; shift 2 ;;
    *) echo "run-pex.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

if ! command -v "$KLT" >/dev/null 2>&1 && [[ ! -x "$KLT" ]]; then
  echo "run-pex.sh: klt not found at '$KLT' -- pass --klt <path> or put a klt implementing 'pex' on PATH" >&2
  exit 1
fi

if ! "$KLT" pex --help >/dev/null 2>&1; then
  echo "run-pex.sh: '$KLT' does not implement 'klt pex' -- see README.md's klt-pin note" >&2
  exit 1
fi

if ! command -v xschem >/dev/null 2>&1; then
  echo "run-pex.sh: xschem not found on PATH -- needed to netlist the schematic" >&2
  exit 1
fi

# Export PDK_ROOT/PDK so the request's `models.lib: "$PDK_ROOT/..."` (see
# README.md's "models.lib bug" note) resolves the same pinned sky130.lib.spice
# this repo's other sim/ testbenches use.
# shellcheck disable=SC1091
source "$REPO_ROOT/sim/bin/pdk-env.sh"

LAYOUT_DIR="$REPO_ROOT/layout"
BLOCK_DIR="$LAYOUT_DIR/ldo-core"
CELL=ldo_core
PDK_VARIANT=sky130A

LATEST_LVS_ID="$(cat "$BLOCK_DIR/reports/LATEST-LVS")"
LATEST_LVS_DIR="$BLOCK_DIR/reports/$LATEST_LVS_ID"
GDS="$LATEST_LVS_DIR/$CELL.gds"
if [[ ! -f "$GDS" ]]; then
  echo "run-pex.sh: $GDS not found" >&2
  exit 1
fi

TESTBENCH_DIR="$EXP_DIR/testbench"

# Append-only evidence: if a prior record already exists, this run
# supersedes it (record the pointer rather than overwriting).
PRIOR_RECORD_ID=""
if compgen -G "$EXP_DIR/records/*.json" >/dev/null; then
  PRIOR_RECORD_ID="$(basename "$(ls -1 "$EXP_DIR"/records/*.json | sort | tail -1)" .json)"
  echo "run-pex.sh: this run will supersede prior record $PRIOR_RECORD_ID"
fi

echo "run-pex.sh: regenerating testbench pair against $LATEST_LVS_ID's layout"
python3 "$SCRIPT_DIR/gen-pex-testbench.py" \
  --klt "$KLT" --gds "$GDS" --repo-root "$REPO_ROOT" \
  --outdir "$TESTBENCH_DIR" --pdk "$PDK_VARIANT"

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
echo "run-pex.sh: record $RECORD_ID"

# Same evidence layout as sim/dropout-vs-load, sim/mc-output-accuracy, etc.:
# flat per-record-id files under purpose-named directories, not a
# per-record subdirectory.
REQ_PATH="$EXP_DIR/klt-requests/$RECORD_ID.request.json"
RESP_SIM_PATH="$EXP_DIR/klt-responses/$RECORD_ID.sim-schematic.json"
RESP_PEX_PATH="$EXP_DIR/klt-responses/$RECORD_ID.pex.json"
NETLIST_DUT_PATH="$EXP_DIR/netlist-snapshots/$RECORD_ID.schematic-dut.spice"
NETLIST_EXTRACT_PATH="$EXP_DIR/netlist-snapshots/$RECORD_ID.pex.extract.spice"
RECORD_JSON_PATH="$EXP_DIR/records/$RECORD_ID.json"
RECORD_MD_PATH="$EXP_DIR/records/$RECORD_ID.md"

cp "$TESTBENCH_DIR/tb_pex_post_layout.request.json" "$REQ_PATH"
cp "$TESTBENCH_DIR/ldo_core_schematic_dut.spice" "$NETLIST_DUT_PATH"

# Scratch/per-corner artifacts (ngspice logs/decks) -- gitignored (sim/build/,
# same convention sim/bin/corner-run.py's own testbenches use), NOT inside
# layout/ (read-only dependency) or the committed testbench/ directory.
BUILD_DIR="$REPO_ROOT/sim/build/pex-post-layout/$RECORD_ID"
mkdir -p "$BUILD_DIR/sim" "$BUILD_DIR/pex"

echo "run-pex.sh: running the schematic-side leg standalone (klt sim) for its own record"
set +e
"$KLT" sim "$TESTBENCH_DIR/tb_pex_post_layout.request.json" \
  --outdir "$BUILD_DIR/sim" \
  --format json > "$RESP_SIM_PATH" 2> "$BUILD_DIR/sim-schematic.stderr.log"
SIM_EXIT=$?
set -e
echo "run-pex.sh: klt sim (schematic-side) exit code $SIM_EXIT"

echo "run-pex.sh: running klt pex (schematic + extracted legs + delta)"
set +e
"$KLT" pex "$GDS" "$TESTBENCH_DIR/tb_pex_post_layout.request.json" \
  --deck sky130 --top "$CELL" --pdk "$PDK_VARIANT" \
  --outdir "$BUILD_DIR/pex" \
  -o "$NETLIST_EXTRACT_PATH" \
  --format json > "$RESP_PEX_PATH" 2> "$BUILD_DIR/pex.stderr.log"
PEX_EXIT=$?
set -e
echo "run-pex.sh: klt pex exit code $PEX_EXIT (0=all pass, 3=a delta[] row failed its own limits, 4=a delta[] row errored, 1=hard failure -- see docs/cli/pex.md's Exit codes)"

# klt pex writes its JSON envelope to stdout on every documented exit code
# except a hard failure (1), where it goes to stderr instead -- fall back so
# the record always carries the actual error, not an empty file.
if [[ ! -s "$RESP_PEX_PATH" && -s "$BUILD_DIR/pex.stderr.log" ]]; then
  cp "$BUILD_DIR/pex.stderr.log" "$RESP_PEX_PATH"
fi

python3 "$SCRIPT_DIR/render-pex-record.py" \
  --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --layout-record-id "$LATEST_LVS_ID" \
  --sim-schematic-response "$RESP_SIM_PATH" --sim-schematic-exit "$SIM_EXIT" \
  --pex-response "$RESP_PEX_PATH" --pex-exit "$PEX_EXIT" \
  --request "$REQ_PATH" \
  --supersedes "$PRIOR_RECORD_ID" \
  --out-json "$RECORD_JSON_PATH" --out-md "$RECORD_MD_PATH"

echo "run-pex.sh: done -> $RECORD_MD_PATH"
