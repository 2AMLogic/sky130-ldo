# Commands that produced this record (issue #319)

Run from the repository root of the `feature/issue-319` worktree. `PDK_ROOT` points at the pinned volare install, with `sky130A` at open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`. Every `klt sim` call is made by `layout/cap-study/run-cap-study.py`. The exact argv is in each run directory's `submission.json`, and the request klt received is in its `request.json`.

```bash
R=layout/cap-study/20261011-094917-7a4e0cc
export PDK_ROOT=$HOME/.volare

# 1. Netlist the testbench (xschem) and write the six op-point requests and the C(V) netlist
python3 layout/cap-study/run-cap-study.py prepare --record $R

# 2. Op-point grid on the batch fleet. The first job was refused (runner 0.5.0 vs
#    client 0.7.0); the script stops after a failed job and never falls back to a
#    local run.
python3 layout/cap-study/run-cap-study.py op --record $R

# 3. Nominal single-unit probes (local, one corner each)
python3 layout/cap-study/run-cap-study.py op-local --record $R --point tt,27,3.3,0
python3 layout/cap-study/run-cap-study.py op-local --record $R --point tt,27,3.3,50

# 4. Varactor C(V), tt / 27 C, single unit (local)
python3 layout/cap-study/run-cap-study.py cv --record $R --backend local
#    The corner x temperature grid (`cv --backend batch`) was NOT submitted:
#    step 2 showed the fleet runner refuses this client.

# 5. Assemble matrix.json (deterministic; no timestamps)
python3 layout/cap-study/run-cap-study.py matrix --record $R
```

Per-number derivation:

| Number | Derived by |
|---|---|
| MiM density | `mim_rows()`: `parse_params` + `eval_corner_param` on `parameters_cap_{nom,low,high}.spice`; law checked by `mim_subckt_formula_ok` |
| vpp density | `vpp_rows()`: `vpp_ctot` (the model's `ctot_a` with the rescap `__lin` corner factors) / `mag_bbox` (flat `.mag` bounding box) |
| Varactor SOA | `var_soa` on `sky130_fd_pr__cap_var_{lvt,hvt}.model.spice` |
| Varactor C(V) | `.meas ac ... find vi(n_<point>)` in `cv/local_tt_27c/response.json` -> `c_from_vi` |
| Plate voltages | `.meas tran ... avg v(<node>) from=199m to=200m` in `op/*/*/response.json` |
| Areas / beside totals | `area_for`, `beside_total_um2` against `layout/area-study/20261009-study-246/budget.json` scenario D |
| Verdicts / outcome | `fit_verdict`, `outcome` |

Before the run used here, one local C(V) attempt was discarded because the harness had a bug. That attempt was never committed. ngspice's `ac lin 2 a b` returns a single row, so every `.meas ac ... at=` failed. The request now uses `lin 3`.
