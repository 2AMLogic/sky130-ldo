## Experiment and solver freshness (#237)

A record's *schematic* freshness (`measurements/build_characterization_report.py`
re-netlists the testbench and compares it with the committed netlist snapshot)
says nothing about the other inputs of a run: the experiment manifest's
analyses, measurement expressions and bounds, the declared matrix, and the
solver settings. #237 adds a second, **headless** freshness dimension for them
(no xschem, no PDK). The report shows the two as separate reasons: the
`Inputs` column / `Experiment/solver inputs:` clause, and the existing
`Freshness` column / `Freshness:` clause.

### The fingerprint

New campaign records (`corner-run.py` and `mc-run.py`) carry an
`input_fingerprint` block: `version` (currently `1`), `kind` (`pvt` or `mc`),
per-dimension `sections` (sha256 of a deterministic, sorted-key JSON
serialization, numerically-equal spellings such as `27`/`27.0` normalized) and
an overall `sha256`. It is built in `sim/bin/_record_common.py` from an
explicit **allow-list** of execution-relevant keys; prose keys (`claim`,
`title`, `note`, `unit`, `corners_note`, whole-line `*` comments inside
`deck.analyses`, ...) are not in it, so editing them never invalidates a
simulation.

| Backend | Dimension | Fields (allow-list) |
|---|---|---|
| PVT | `analyses` | `deck.options`, `deck.params`, `deck.analyses` (code lines only) |
| PVT | `measurements` | per measurement `name`, `expr`, `min`, `max`; `spread_checks` `measurement`, `min_spread` |
| PVT | `matrix` | `corners.process`, `.temperature_c`, `.supply_v`, `quick_subset` |
| PVT | `solver` | sha256 of `sim/spiceinit` (the same hash as `tools.spiceinit_sha256`, #190) |
| MC | `analyses` | `mc_analysis.kind`, `.args` |
| MC | `measurements` | per measurement `name`, `spice`, `limits` |
| MC | `matrix` | `mc_corner.process`, `.temperature_c`, `.vsup` |
| MC | `netlist_patch` | each substitution's `match`, `replace`, `count` |

Backend-specific on purpose: MC has **no** `solver` dimension. `klt sim` runs
ngspice under its own configuration, and nothing here shows it reads
`sim/spiceinit`, so claiming that file as an MC input would be a fabricated
dependency; the report states "solver settings: not applicable (klt backend)".
MC's `n`/`vary`/`k_sigma`/`seed` are CLI-overridable and are already recorded
in the record's `monte_carlo_request`, so they are not compared against the
manifest's defaults. Changing any allow-list or the serialization requires
bumping `INPUT_FINGERPRINT_VERSION`; a record of another version is reported
`unverified`, never matched or mismatched.

### How the report uses it

`check_input_freshness()` compares each dimension of the cited record with the
current `experiment.json` and `sim/spiceinit`: `fresh` (all match), `STALE`
(names the changed dimensions) or `unverified` (names the dimensions the record
carries no provenance for). It runs under `--no-netlist-freshness` and
`--ignore-sim-freshness` too (the Inputs column is *not* normalized), so CI
detects manifest/solver drift without a PDK; only the xschem re-netlist is
skipped there.

**Legacy records are never edited.** Every record minted before #237 reports
`unverified: analyses, measurements, matrix[, solver] -- no input fingerprint in
this legacy record`. A legacy PVT record that already recorded
`tools.spiceinit_sha256` (#190) still gets its `solver` dimension compared.
Nothing was re-run for #237 and no historic verdict changed; the next campaign
for each experiment is what turns its Inputs cell to `fresh`.
