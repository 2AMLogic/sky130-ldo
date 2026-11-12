# DRC-only record (issue #564)

`klt drc layout/ldo-core/reports/20261112-110205-820ba8b3/ldo_core.gds --deck sky130 --format json`,
run from the repository root, so the envelope records the GDS repo-relative
(`file.path`, `scope: repo`) and `klt signoff` can re-hash it from any checkout.

- Input GDS: `20261112-110205-820ba8b3/ldo_core.gds`, `sha256:5e6171873b24b8d4c7af6f55d59600d84099cd13790c8320d8ccf074e657c1ca` (not regenerated).
- Result: `status: clean`, `violation_count: 0` (curated `sky130` deck only; no official-deck run here).
- Same verdict and GDS as `20261112-110205-820ba8b3/drc.json`, which stays in place unedited as an append-only record (its `file` is an absolute worktree path, so it graded `input_verified: null`).
- Engine: klayout 0.30.13 (klt warned it differs from the 0.30.12 the tool was tested against; the verdict is unaffected).
