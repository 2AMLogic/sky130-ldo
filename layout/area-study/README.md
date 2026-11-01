# `layout/area-study/` -- area budget and compaction feasibility (issue #246)

Generated study records, kept apart from the append-only `sim/` evidence and the
`layout/ldo-core/reports/` layout records. Each `<record-id>/` holds
`budget.json` (machine-readable) and `report.md`. Records are never edited; a
rerun mints a new directory.

Mint one: `python3 layout/bin/ldo-area-budget-4cap.py [--record-id ID]` (reads
only committed records). Everything is a geometric estimate computed from
existing evidence; nothing here is DRC/LVS/PEX verified, the ratified `< 0.1 mm^2`
Area row is unchanged, and no resistor value or transistor size is altered.

The #246 generator (`ldo-area-budget.py`) was removed once the #459 script
superseded it; its record `20261009-study-246/` is kept as historical evidence,
and the reproduce block in its `report.md` refers to that removed script.

Latest: `20261028-study-459/report.md` (supersedes `20261009-study-246/report.md`, which is kept).
