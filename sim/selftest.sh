#!/usr/bin/env bash
#
# Harness acceptance test (issue #2). Mirrors the sibling gf180-ldo repo's
# sim/selftest.sh: proves the toolchain runs end to end rather than stubbing
# it out.
#
#   sim/selftest.sh                unit tests + smoke PVT run (no evidence written)
#   sim/selftest.sh --record       also mint an evidence record under sim/pdk-smoke/
#   sim/selftest.sh --quick        unit tests + a 3-point corner subset (faster)
#   sim/selftest.sh --require-pdk  fail (instead of skipping) if the PDK is absent
#
# Exit codes: 0 pass (or skipped sim stage), 1 something failed.

set -uo pipefail

SIM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SIM_DIR}/.." && pwd)"

RECORD=0
QUICK=0
REQUIRE_PDK=0
for arg in "$@"; do
  case "${arg}" in
    --record) RECORD=1 ;;
    --quick) QUICK=1 ;;
    --require-pdk) REQUIRE_PDK=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: ${arg}" >&2; exit 1 ;;
  esac
done

echo "== 1/3 harness unit tests (no PDK required) =="
if ! python3 -m unittest discover -s "${SIM_DIR}/tests" -t "${SIM_DIR}/tests"; then
  echo "FAIL: harness unit tests"
  exit 1
fi

echo
echo "== 2/3 environment =="
if ! python3 "${SIM_DIR}/bin/corner-run.py" --check-env; then
  if [ "${REQUIRE_PDK}" -eq 1 ]; then
    echo "FAIL: ngspice/xschem/volare and/or the sky130 PDK are not available"
    exit 1
  fi
  echo
  echo "SKIP: simulation stage -- ngspice/xschem/volare and/or the pinned sky130"
  echo "      PDK are not available. Unit tests passed. See docs/environment-setup.md"
  echo "      to install the toolchain, then re-run to exercise the end-to-end"
  echo "      PVT smoke test."
  exit 0
fi

echo
echo "== 3/3 end-to-end PVT smoke run =="
args=("${SIM_DIR}/pdk-smoke")
if [ "${QUICK}" -eq 1 ]; then
  args+=(--quick)
  # --quick is deliberately a PVT subset; the runner demands a written reason
  # before a subset run may be recorded as evidence (see sim/README.md).
  args+=(--subset-reason "sim/selftest.sh --quick: single-point harness smoke test, not a spec claim")
fi
[ "${RECORD}" -eq 1 ] || args+=(--no-write)

if ! python3 "${SIM_DIR}/bin/corner-run.py" "${args[@]}"; then
  echo "FAIL: PVT smoke run"
  exit 1
fi

echo
echo "PASS: harness is functional end to end."
