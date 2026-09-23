#!/usr/bin/env bash
# layout/bin/run-ldo-erc-flow.sh -- run `klt erc` against the committed
# LDO-core layout with layout/ldo-core/erc-supply-spec.json, the supply spec
# T1 item 11 (power delivery, structural) is graded from (issue #112).
#
# Usage:
#   layout/bin/setup-venv.sh --requirements layout/erc-requirements.txt
#   layout/bin/run-ldo-erc-flow.sh
#   layout/bin/run-ldo-erc-flow.sh --layout-record 20260825-123551-3b4e121
#
# Requires layout/.venv-erc (its own pin -- see layout/erc-requirements.txt
# for why the ERC flow cannot share the DRC/LVS pin) and a landed ldo-core
# layout record (layout/ldo-core/reports/LATEST). No PDK install is needed:
# `klt erc --pdk sky130` reads its antenna-limit table from klt's own
# built-in transcription of SkyWater's published rule tables, not from a
# local PDK tree.
#
# What a run produces, in a NEW append-only record directory:
#
#   erc_supply.json            the graded run -- item 11's evidence
#   erc_control_C[1-4].json    four FALSIFICATION controls (see below)
#   erc-supply-spec.json       byte copy of the spec this record was run on
#   layout-record-id.txt       which layout record the GDS came from
#   record.md                  human-readable verdict + provenance
#
# WHY THE CONTROLS. Every check item 11 grades passes by reporting NOTHING:
# zero erc.unconnected_net, zero erc.supply_short, zero erc.missing_tie. An
# all-clean report is therefore indistinguishable, on its face, from a spec
# that asks no question at all -- which is exactly the failure mode
# klayout-tools#2199/#2255 built their degeneracy gates against. So each run
# also mutates the committed spec four ways and records that the mutation
# DOES fire:
#
#   C1  substrate_tie's asserted well box moved into the poly-resistor
#       field, where no tap is drawn        -> expect erc.missing_tie
#   C2  nwell_tie's tap required to reach `0` instead of `VIN`
#                                            -> expect erc.missing_tie
#   C3  a supply net name no layer carries   -> expect erc.unconnected_net
#   C4  VOUT declared a supply with the poly-resistor devices[] carve-out
#       removed, i.e. the feedback divider read as wire
#                                            -> expect erc.supply_short
#
# C4 is also the direct demonstration that the devices[] carve-out is doing
# real work rather than masking: re-adding devices[] with VOUT still
# declared a supply clears the short (klayout-tools#2183).
set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$LAYOUT_DIR/.." && pwd)"
BLOCK_DIR="$LAYOUT_DIR/ldo-core"
VENV="$LAYOUT_DIR/.venv-erc"
KLT="$VENV/bin/klt"
CELL=ldo_core
PDK=sky130
SPEC="$BLOCK_DIR/erc-supply-spec.json"

LAYOUT_RECORD_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --layout-record) LAYOUT_RECORD_ID="$2"; shift 2 ;;
    *) echo "run-ldo-erc-flow.sh: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

if [[ ! -x "$KLT" ]]; then
  echo "run-ldo-erc-flow.sh: $KLT not found -- run" >&2
  echo "  layout/bin/setup-venv.sh --requirements layout/erc-requirements.txt" >&2
  exit 1
fi

[[ -n "$LAYOUT_RECORD_ID" ]] || LAYOUT_RECORD_ID="$(cat "$BLOCK_DIR/reports/LATEST")"
LAYOUT_RECORD_DIR="$BLOCK_DIR/reports/$LAYOUT_RECORD_ID"
GDS="$LAYOUT_RECORD_DIR/$CELL.gds"
if [[ ! -f "$GDS" ]]; then
  echo "run-ldo-erc-flow.sh: $GDS not found -- run layout/bin/run-ldo-layout-flow.sh first" >&2
  exit 1
fi

TS_UTC="$(date -u +%Y%m%d-%H%M%S)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
RECORD_ID="${TS_UTC}-${SHORT_SHA}"
OUT_DIR="$BLOCK_DIR/reports/$RECORD_ID"
mkdir -p "$OUT_DIR"
echo "run-ldo-erc-flow.sh: record $RECORD_ID -> $OUT_DIR (layout from $LAYOUT_RECORD_ID)"

LAYOUT_SHA="$(git -C "$REPO_ROOT" log -1 --format=%h -- layout/ldo-core)"

# The GDS is deliberately NOT copied into this record: item 11 wants the
# report's own input content-hash to match the COMMITTED layout, and a copy
# would only re-state a hash of itself. layout-record-id.txt names the
# record the hash belongs to instead.
echo "$LAYOUT_RECORD_ID" > "$OUT_DIR/layout-record-id.txt"
cp "$SPEC" "$OUT_DIR/erc-supply-spec.json"

# --- 1. Pre-flight: does the spec still describe this layout? --------------
# Two of the spec's declarations are claims ABOUT the layout that klt erc
# cannot re-derive (the omitted met3+ levels, and the asserted substrate
# region). Fail loudly here rather than mint a record against a stale spec.
"$VENV/bin/python" "$LAYOUT_DIR/bin/check-erc-supply-spec.py" \
  --gds "$GDS" --spec "$SPEC" --top "$CELL"

# --- 2. The graded run ------------------------------------------------------
# `klt erc` exits 3 when the ANTENNA verdict is `violations`; that verdict is
# not item 11's subject (klayout-tools#1994) and the record renderer reads
# the JSON's own erc_status for the item-11 answer, so the exit code is
# captured rather than fatal.
set +e
"$KLT" erc "$GDS" "$SPEC" --pdk "$PDK" --top "$CELL" --format json \
  > "$OUT_DIR/erc_supply.json"
ERC_RC=$?
set -e
if [[ ! -s "$OUT_DIR/erc_supply.json" ]]; then
  echo "run-ldo-erc-flow.sh: klt erc produced no JSON (exit $ERC_RC)" >&2
  exit 1
fi
echo "run-ldo-erc-flow.sh: klt erc exit $ERC_RC"

# --- 3. Falsification controls ---------------------------------------------
# Each control is a mutation of the COMMITTED spec, generated here rather
# than committed as four more hand-maintained files: a stale control that
# silently stopped mutating the real spec would be worse than no control.
CONTROL_DIR="$(mktemp -d)"
trap 'rm -rf "$CONTROL_DIR"' EXIT
"$VENV/bin/python" - "$SPEC" "$CONTROL_DIR" <<'PY'
import copy
import json
import sys

spec_path, out_dir = sys.argv[1], sys.argv[2]
with open(spec_path) as handle:
    base = json.load(handle)


def tie(spec, name):
    return next(t for t in spec["ties"] if t["name"] == name)


c1 = copy.deepcopy(base)
tie(c1, "substrate_tie")["well_boxes"] = [[1000.0, -0.5, 1100.0, 80.5]]

c2 = copy.deepcopy(base)
tie(c2, "nwell_tie")["net"] = "0"

c3 = copy.deepcopy(base)
c3["nets"].append({"name": "VDDA", "kind": "supply"})

c4 = copy.deepcopy(base)
c4.pop("devices", None)
c4["nets"].append({"name": "VOUT", "kind": "supply"})

for name, spec in (("C1", c1), ("C2", c2), ("C3", c3), ("C4", c4)):
    with open(f"{out_dir}/{name}.json", "w") as handle:
        json.dump(spec, handle, indent=2)
PY

for CONTROL in C1 C2 C3 C4; do
  set +e
  "$KLT" erc "$GDS" "$CONTROL_DIR/$CONTROL.json" --pdk "$PDK" --top "$CELL" \
    --format json > "$OUT_DIR/erc_control_$CONTROL.json"
  set -e
  echo "run-ldo-erc-flow.sh: control $CONTROL recorded"
done

# --- 4. Record summary (honest verdict; non-zero when item 11 is not met) ---
set +e
python3 "$LAYOUT_DIR/bin/render-ldo-erc-record.py" \
  --out-dir "$OUT_DIR" --record-id "$RECORD_ID" --repo-root "$REPO_ROOT" \
  --klt "$KLT" --cell-name "$CELL" \
  --layout-sha "$LAYOUT_SHA" --layout-record-id "$LAYOUT_RECORD_ID" \
  > "$OUT_DIR/record.md"
RECORD_STATUS=$?
set -e

echo "$RECORD_ID" > "$BLOCK_DIR/reports/LATEST-ERC"

echo "run-ldo-erc-flow.sh: done. See $OUT_DIR/record.md"
exit "$RECORD_STATUS"
