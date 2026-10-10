## `sim/selftest.sh` — the harness acceptance test

Mirrors the sibling `gf180-ldo` repo's `sim/selftest.sh` (same three-stage
shape, adapted to this harness's single-script `corner-run.py` convention
instead of a `sim/harness/` package):

1. **Unit tests** (`sim/tests/`) — PDK-free, always run.
2. **Environment** (`corner-run.py --check-env`) — skips stage 3 (exit 0) if
   the toolchain/PDK are missing, unless `--require-pdk` is passed.
3. **End-to-end PVT run** against `pdk-smoke` — real xschem + ngspice, not a
   stub. `--quick` runs a 3-point subset instead of the full 45-point matrix;
   `--record` mints a real evidence record instead of using `--no-write`.

`sim/selftest.sh --quick --require-pdk` (without `--record`) runs in the
PDK-gated `pdk-smoke` CI job (nightly / `workflow_dispatch` / opt-in
`run-pdk-smoke` PR label) so it exercises the real toolchain without minting
new append-only evidence on every run — but it does **not** run on every
push. `npm run check:ci` (the headless, no-PDK job that *does* run on every
push/PR) never invokes `sim/selftest.sh` at all, and `sim/selftest.sh`'s own
`pdk-smoke` end-to-end stage netlists a standalone diode-tied device
testbench, not `design/ldo_3v3in_1v8out.sch` — so neither one is a liveness
check for the LDO core's own netlist. See "check:ci vs. netlisting the LDO
core" below for the check that is.

