# Environment setup

Reproducible bring-up for this repo's open-source flow: xschem (schematic
capture / netlisting) + ngspice (simulation) against the sky130 PDK (fetched
via [volare](https://github.com/efabless/volare)), plus
[klayout-tools](https://github.com/2AMLogic/klayout-tools) (`klt`) for the
layout / DRC / LVS flow. Follow this doc verbatim from a fresh checkout on a
machine that already has `xschem`/`ngspice`/`volare`/`python3` on `PATH` (see
"Toolchain versions" below for what a from-scratch install looks like).

This doc is issue #2's deliverable: a fresh checkout can run the env check,
the sim selftest, and the trivial-cell DRC/LVS flow by following the steps
below.

## Toolchain versions (recorded 2026-08-13)

| Tool | Version | Install path |
|---|---|---|
| xschem | `XSCHEM V3.4.7` | `/opt/homebrew/bin/xschem` (Homebrew) |
| ngspice | `ngspice-47` | `/opt/homebrew/bin/ngspice` (Homebrew) |
| volare | `v0.20.6` | `/opt/homebrew/bin/volare` (Homebrew, via pip/pipx-managed formula) |
| klt (via `layout/bin/setup-venv.sh`) | `klt 0.2.0` | `layout/.venv/bin/klt`, pinned by `layout/requirements.txt` |

Same shared-machine toolchain the sibling
[`sky130-bandgap`](https://github.com/2AMLogic/sky130-bandgap) repo bootstrapped
(its `docs/environment-setup.md` has the from-scratch install notes if
`xschem`/`ngspice`/`volare` are genuinely absent — this is a shared
machine-level resource, not sky130-ldo-specific, so **do not reinstall
speculatively**; verify first):

```sh
xschem --version   # expect: XSCHEM V3.4.7 ...
ngspice --version  # expect: ngspice-47 ...
volare --version   # expect: Volare v0.20.6 ...
```

## 1. Fetch + enable the sky130 PDK via volare

```sh
volare ls-remote --pdk sky130   # lists open_pdks build commits, newest first
volare fetch  --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b
volare enable --pdk sky130 c6d73a35f524070e85faff4a6a9eef49553ebc2b
```

**Pinned PDK version** (see `sim/pdk.json`, the single source of truth this
repo's harness reads back):

- PDK family: `sky130`
- open_pdks build commit: `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- Variant: `sky130A`
- Chosen because: this is the same open_pdks commit the sibling
  `sky130-bandgap` repo already pinned (same PDK, issue #2 ports its
  harness), which keeps PVT/model provenance consistent across the 2AM Logic
  canary ports of this block family.

After `volare enable`, confirm the variant resolved:

```sh
ls -la ~/.volare | grep sky130
# sky130A -> volare/sky130/versions/c6d73a35f524070e85faff4a6a9eef49553ebc2b/sky130A
```

## 2. Environment check

```sh
python3 sim/bin/corner-run.py --check-env
```

Expected output: `ngspice`, `xschem`, `volare` each report `OK` with a
version string, and `PDK` reports `OK` with the resolved path and
`matches sim/pdk.json pin`. Exit code `0`. If anything reports `MISSING`,
fix that specific piece (missing tool on `PATH`, or PDK not enabled per step
1) before continuing — `--check-env` never touches the toolchain, it only
diagnoses it.

`PDK_ROOT`/`PDK` resolution order (same for `--check-env`, the corner runner,
and interactive use): `$PDK_ROOT` env → `volare path` → `default_pdk_root` in
`sim/pdk.json`; `$PDK` env → `variant` in `sim/pdk.json`.

## 3. Sim harness selftest (end-to-end xschem + ngspice)

```sh
sim/selftest.sh --quick
```

Runs, in order: (1) `sim/tests/`'s PDK-free unit tests for the corner
runner's pure helpers, (2) the environment check from step 2 — skips stage 3
gracefully if the toolchain/PDK are unavailable, unless `--require-pdk` is
passed, and (3) a real 3-point PVT subset of `sim/pdk-smoke` — actual
`xschem` netlisting and `ngspice` simulation, not a stub, run with
`--no-write` so it does not mint new append-only evidence on every
invocation. Expect `PASS: harness is functional end to end.` and exit `0`.

To run the full 45-point PVT matrix and mint a real evidence record instead:

```sh
python3 sim/bin/corner-run.py sim/pdk-smoke
```

This writes `sim/pdk-smoke/records/<record-id>.{md,json}`, a netlist
snapshot, and 45 per-corner logs — see `sim/README.md` for the full record
format and the append-only rule.

### Driving the tools by hand

```sh
source sim/bin/pdk-env.sh      # exports PDK_ROOT, PDK, SKY130_MODEL_LIB, XSCHEM_RCFILE
xschem --rcfile "$XSCHEM_RCFILE" sim/pdk-smoke/testbench/tb_pdk_smoke.sch
cp sim/spiceinit ./.spiceinit  # ngspice needs these settings to read PDK libs
```

## 4. Layout: klt DRC/LVS trivial-cell flow

**No LDO layout yet** — this step proves the `klt` layout/DRC/LVS driver
works on this repo, on a trivial known-good cell. The LDO's own layout is
future work once `spec/target-spec.md` is ratified (issue #1) and the design
is drawn.

```sh
layout/bin/setup-venv.sh          # once, or after bumping layout/requirements.txt
layout/bin/run-trivial-cell-flow.sh
```

Writes a fresh, timestamped record under
`layout/trivial-cell/reports/<record-id>/` and updates
`layout/trivial-cell/reports/LATEST`. Read that record's `record.md` — expect
`## Overall verdict: PASS` with all four checkboxes checked (DRC clean, LVS
match on the known-good reference, LVS mismatch on both negative controls).
See `layout/README.md` for the full flow explanation and directory layout.

## 5. Full repo check (headless, no PDK)

```sh
npm run check:ci
```

Runs JSON syntax checks on every `sim/**/*.json`, shell syntax checks
(`bash -n`) on the harness scripts, `py_compile` over every tracked Python
file under `sim/`/`layout/`, `sim/tests/`'s unit suite, and the embedded-quote
xschem authoring check. Headless — does not need the PDK or `klt` installed,
so this is what CI runs on every push (see `.github/workflows/ci.yml`); steps
2-4 above (which do need the toolchain and PDK) run in CI's separate
PDK-gated `pdk-smoke` job (nightly / manual dispatch / opt-in via the
`run-pdk-smoke` PR label).

## Troubleshooting

- **`SKYWATER_MODELS: unable to resolve variable`** / the `.lib` path in a
  netlisted deck is literally `$::SKYWATER_MODELS/...` (not expanded to a
  real path): `PDK_ROOT`/`PDK` aren't exported in the shell running
  `xschem`, or the `--rcfile sim/xschemrc` flag was omitted.
- **`Warning: PDK_ROOT environment variable is set but path not found`**
  (printed by the PDK's own `xschemrc`): `$PDK_ROOT`/`$PDK` don't resolve to
  a real install, or `volare enable` hasn't been run for the pinned hash
  above.
- **xschem opens a GUI window instead of running headless**: pass `-x`
  (no X) in addition to `-n -q` when driving `xschem` by hand — the corner
  runner already does this.
- **`corner-run.py: error: installed PDK ... but sim/pdk.json pins ...`**:
  a different open_pdks commit is enabled than the one pinned in
  `sim/pdk.json`. Either `volare enable` the pinned commit (step 1), or pass
  `--allow-pdk-mismatch` if a deliberate mismatch run is intended (the
  record will say so).
- **`run-trivial-cell-flow.sh: ... klt not found`**: run
  `layout/bin/setup-venv.sh` first (it installs the pinned `klt` build into
  `layout/.venv`, gitignored).
