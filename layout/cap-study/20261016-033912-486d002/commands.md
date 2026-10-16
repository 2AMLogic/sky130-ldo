# Commands that produced this record (issue #398)

Run from the repository root of the `feature/issue-398` worktree. `PDK_ROOT=$HOME/.volare`. All runs are single-corner `--backend local`.

```bash
R=layout/cap-study/20261016-033912-486d002
S=layout/cap-study/20261016-004951-5125358/op/requests
cp $S/v2.97_50ma.spice $R/probe/
# req_default.json = $S/v2.97_50ma.json with corners {process:[ff], temperature_c:[27.0]}
# and netlist "v2.97_50ma.spice"
klt sim $R/probe/req_default.json -o $R/probe/default_run1 --backend local --format json
klt sim $R/probe/req_default.json -o $R/probe/default_run2 --backend local --format json
```

Variants: each `probe/<name>.spice` is the deck with one line prepended, and `probe/req_<name>.json` points at it.

| name | prepended line / change |
|---|---|
| `tight` | `.options reltol=1e-4 abstol=1e-13 vntol=1e-7` |
| `gear` | `.options method=gear` |
| `fine_step` | none; request `analysis.args` = `1u 200m uic` |
| `ic_vout_2p7` | `.ic v(vout)=2.7` |
| `ic_vout_0p5` | `.ic v(vout)=0.5` |
| `ic_old_state` | `.ic v(vout)=2.7169 v(xldo.ea_cz)=1.5207 v(xldo.cl_cmp)=2.1275 v(xldo.ts_cmp)=2.9438 v(xldo.ss)=2.97` |

```bash
for k in tight gear fine_step ic_vout_2p7 ic_vout_0p5 ic_old_state; do
  klt sim $R/probe/req_$k.json -o $R/probe/$k --backend local --format json
done
grep -rE '^v_(vout|cl_cmp|ea_cz)' $R/probe/*/
```

Absolute home paths in the saved files were replaced by `~`, `$PDK_ROOT` and `<record>`. No batch submission was made.
