# LDO core LVS record: 20260817-234828-e500d71

First `klt extract` + `klt lvs` attempt against the real LDO layout (issue #17), comparing `layout/ldo-core/reports/20260817-204734-0e12b14/ldo_core.gds` (issue #15) against a reference netlist mechanically translated from `design/ldo_3v3in_1v8out.sch`'s own xschem netlist (issues #14/#22) by `layout/bin/gen-ldo-reference-netlist.py`.

## Overall verdict: MISMATCH -- not LVS-clean

- [ ] `klt lvs` reports `status: match`

**This does not satisfy issue #17's acceptance criteria (`status: match`).** The root cause is not a `klt` defect -- see "Root cause" below. Filed as a real, committed negative result (`CLAUDE.md`'s "Verification is the product": append-only evidence, not a silently-dropped attempt), with a follow-on issue tracking the layout work a clean match needs.

## Flow

1. `xschem -n -q -x -s -o ... design/ldo_3v3in_1v8out.sch` -- headless netlist, same invocation `design/README.md`'s "Validating this schematic" section documents.
2. `layout/bin/gen-ldo-reference-netlist.py` translates that netlist into an LVS reference (MOS model names -> `klt extract`'s generic `nfet`/`pfet` classes, `W_total = W * mult`; resistor model names pass through unchanged; capacitors dropped -- no `klt gen` capacitor generator exists).
3. `klt extract ldo_core.gds --deck sky130 --top ldo_core`
4. `klt lvs` (extracted layout vs. the translated reference).

## Results

| Stage | Status | Detail |
| --- | --- | --- |
| Extract | extracted | device_count=49, net_count=119, pin_count=1, device_counts={'nfet': 8, 'pfet': 37, 'res_high_po': 1, 'res_xhigh_po': 3} |
| LVS | mismatch | mismatch_count=210, category_counts={'device.body_unverified': 1, 'device.unmatched': 71, 'net.unmatched': 137, 'topology': 1}, nets(layout/reference/matched)={'layout': 119, 'reference': 18, 'matched': 0}, devices(layout/reference/matched)={'layout': 49, 'reference': 28, 'matched': 0}, pins(layout/reference/matched)={'layout': 1, 'reference': 4, 'matched': 5} |

## Root cause

Three independent, well-understood gaps -- any one of them alone would already prevent a match; together they explain the full LVS result above (0 of 18 reference nets, 0 of 28 reference devices matched):

1. **The layout is stale relative to the schematic.** `layout/ldo-core/` (issue #15) was floorplanned from `design/ldo_3v3in_1v8out.sch` as it stood before issue #22 added the current-limit and soft-start circuitry -- the branch #15 built from was based on commit `0e12b14`, before `4bda2cb` (#22) landed on `main`. The floorplan's device table (`layout/ldo-core/floorplan.md`) still lists only the pre-#22 device set. **11 active MOS devices** added by #22 have no `klt gen` block at all: `M_SENSE`, `M_CLN1`, `M_CLN2`, `M_CLP`, `M_CLIM`, `M_ENP3`, `M_INVP`, `M_INVN`, `M_SSDIS`, `M_SSCHG`, `M_IN2S`.
2. **`M_PASS`'s drawn width does not match the corrected schematic value.** `design/README.md`'s "Pass-device width correction" note explains the `mult` parameter is load-bearing (`W_total = W * mult`, not `W` alone); `layout/bin/gen-ldo-blocks.py`'s `MOS_DEVICES` table still passes only `w_um=100` with no `mult`, so the drawn `M_PASS` block is 100um wide, not the schematic's corrected 2500um.
3. **No inter-block routing exists.** `klt gen-compose` only places the 15 blocks it does draw -- `layout/ldo-core/floorplan.md`'s "Explicitly out of scope" section documents this as a deliberate #15 scope boundary ("a real, separate design task in its own right"). The extracted netlist's own `pin_count: 1` (vs. the schematic's 4 top-level ports) is the direct evidence: with no metal connecting the placed blocks, almost nothing reaches the top-level cell boundary.

None of this is a `klt` tool defect -- `klt extract`/`klt lvs` produced a coherent, correctly-reasoned mismatch report against the layout exactly as drawn; the gap is real, physical layout content that does not exist yet. No `2AMLogic/klayout-tools` filing follows from this record. The one `device.body_unverified` warning in `lvs.json` reproduces the already-documented, already-filed "no NMOS substrate-tap extraction" deck limitation (`layout/README.md`) -- not a new finding.

**Follow-on**: extending the floorplan to cover the #22 devices, correcting `M_PASS`'s width, and adding inter-block routing is tracked as its own issue (linked from #17) -- out of this issue's own "routine" scope, matching `layout/ldo-core/floorplan.md`'s own characterization of routing as "a real, separate design task in its own right ... not a mechanical follow-on to placement."

## Provenance

- Record ID: `20260817-234828-e500d71`
- `klt` version: `klt 0.2.0` (pinned commit, see `layout/requirements.txt`)
- KLayout engine version: `0.30.10`
- PDK: `sky130A`, `open_pdks c6d73a35f524070e85faff4a6a9eef49553ebc2b`
- PDK pin cross-check: compare `version` above against `sim/pdk.json`'s `open_pdks_commit` -- this flow does not itself enforce the pin, consistent with `layout/README.md`'s trivial-cell flow.
- Schematic freshness: `design/ldo_3v3in_1v8out.sch` as of commit `de276ad`.
- Layout freshness: `layout/ldo-core/` as of commit `9fb6861`; GDS taken from layout record `20260817-204734-0e12b14`.
- Repo state: `e500d71072c02f1e39a3cabe4e0793e8a997609c` on `feature/issue-17` (dirty)

## Links

- [`ldo_core.gds`](ldo_core.gds) -- copy of the layout record's composed GDS
- [`xschem_out/ldo_3v3in_1v8out.spice`](xschem_out/ldo_3v3in_1v8out.spice) -- headless schematic netlist
- [`reference.spice`](reference.spice) -- translated LVS reference
- [`extract.json`](extract.json), [`ldo_core.extract.spice`](ldo_core.extract.spice)
- [`lvs.request.json`](lvs.request.json), [`lvs.json`](lvs.json)
- [`report.md`](report.md) -- `klt report --format github-summary` rendering of `lvs.json`

