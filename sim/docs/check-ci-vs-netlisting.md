## `check:ci` vs. netlisting the LDO core (issue #38)

`#35` and `#36` were developed in parallel and each added an EN-gated PMOS
clamp instance named `M_ENP4` on different nets. Merged, `design/
ldo_3v3in_1v8out.sch` netlisted two devices with the same instance name, and
ngspice refused every deck outright (`device already exists, bail out` — see
the "Which record set is authoritative" note above). Nothing in `npm run
check:ci` caught it, because nothing headless ever netlisted the LDO core's
own schematic.

`npm run check:ci` now runs
`.loom/scripts/check-xschem-duplicate-instance-names.sh` — a static regex
lint (no PDK/xschem/ngspice) over tracked `design/*.sch` files that flags any
two component instances sharing the same `name=` value, following
`.loom/scripts/check-xschem-embedded-quotes.sh`'s existing pattern (see
`.github/workflows/ci.yml`'s self-check-inventory header comment). This
closes the fast, per-push feedback gap completely for the class of hazard
that bit #35/#36 (a duplicate instance name), with a clear message naming
the file and the duplicated name instead of ngspice's confusing
netlist-line-number error.

**Whether `corner-run.py --dry-run` also catches this (a second,
PDK-gated liveness layer) was verified empirically while implementing this
check: it does not.** `--dry-run` only netlists via xschem and prints the
deck — xschem's netlister emits the duplicate-`name=` deck silently (exit 0,
no stderr) without rejecting it; the "device already exists, bail out" error
is raised only once ngspice elaborates the deck. A real corner run (e.g.
`corner-run.py sim/load-transient --quick --no-write`) does reproduce the
exact original failure (every corner returns `FAIL` with `n/a`
measurements, and the underlying ngspice run hits the same "device already
exists, bail out" error the incident report shows). Wiring one of the
LDO-instantiating testbenches (`load-transient`, `psrr-dc`,
`dropout-vs-load`) into the PDK-gated `pdk-smoke` job as a second liveness
layer therefore remains a legitimate follow-up (defense-in-depth, catching
the same class of hazard again at PDK-run time), but it would need a real
`--no-write` run, not `--dry-run` — and it is not needed to close this
issue's gap, since the headless lint above already catches every push,
including on machines with no PDK.

