# Issue #323 diagnostic bench copies (tt / 27 C / 3.30 V / 50 mA)

Diagnostic only -- not a record, not part of any characterization selection.
Baseline record: `../../records/20261011-092557-7a4e0cc.{md,json}`.

- `baseline.deck.spice` -- verbatim extract of the deck corner-run.py gave ngspice for that record.
- `make_probe_deck.py <out> <edit> <dat>` -- adds extra `save`s + `wrdata` (probe0, edit `none`) and, for the
  named edit, one explicit intervention. Production `design/ldo_3v3in_1v8out.sch` is never touched.
  - `none`        probe0: instrumented baseline (dropout_v = 0.397658 V, identical to the record).
  - `ideal_tail`  probe A: XM_TAIL replaced by ideal 3.2744 uA source from a separate 3.3 V rail.
  - `no_clamps`   probe B: XM_CLIM and XM_TSHUT drains moved off EA_OUT (1 Gohm bleeds to ground).
- `probe*.deck.spice`, `probe*.stdout.log`, `probe*.dat.gz` (wrdata: time,value pairs), `probe*.analysis.txt`
  (from `analyze.py probeX.dat full traj`; gunzip first).
- Reproduce: copy `.spiceinit` next to the deck, `ngspice -b probeX.deck.spice`.
