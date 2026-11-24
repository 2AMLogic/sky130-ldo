# Issue #767 — same-engine, two-PDK loop-gain measurement (volare `c6d73a35…` vs ciel `f6eeac7…`)

The measurement DR-015's pin migration rests on: the existing loop-gain
testbench run twice at `tt` / 27 °C / 3.30 V with the **same ngspice on the
same host in the same session** (local `ngspice-47`, KLU, `sim/spiceinit`),
once against each open_pdks build. Produced on dispatch worker `loom-worker`
(8-vCPU shared host; single-corner local runs only, per host rules) at repo
commit `4ddb44da` on `feature/issue-767`, **clean tree at run time** (both
legs ran before any re-pin edit of this branch).

## Record header

- **PDK leg A (pin at run time)**: sky130A @ open_pdks
  `c6d73a35f524070e85faff4a6a9eef49553ebc2b` (the volare store,
  `~/.volare/sky130A`), then the `sim/pdk.json` pin — run made with no
  `--allow-pdk-mismatch`.
- **PDK leg B (the fleet build)**: sky130A @ open_pdks
  `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7` (the ciel store,
  `~/.ciel/sky130A`), run with `--allow-pdk-mismatch` against the then-pin.
- **Engine**: `ngspice-47` both legs (same binary; the console banner and the
  logs' deck blocks agree). Netlisting: XSCHEM V3.4.7 both legs, each against
  its own `PDK_ROOT`. The declared tools pin (ngspice 42, xschem 3.4.4) is the
  recorded drift, WARN-only, that never gates a measurement (#291).
- Each leg's deck embeds its own `.lib` line (provenance is in the retained
  logs below, not asserted):
  - leg A: `.lib "/home/ubuntu/.volare/sky130A/libs.tech/combined/sky130.lib.spice" tt`
  - leg B: `.lib "/home/ubuntu/.ciel/sky130A/libs.tech/combined/sky130.lib.spice" tt`

## Commands (this worktree, clean tree)

```bash
PDK_ROOT=$HOME/.volare PDK=sky130A python3 sim/bin/corner-run.py sim/loop-gain \
  --backend local --process tt --temp 27 --supply 3.30 --no-write \
  --subset-reason 'issue 767 two-PDK measurement, leg A (volare c6d73a35 = pin at run time)'
PDK_ROOT=$HOME/.ciel   PDK=sky130A python3 sim/bin/corner-run.py sim/loop-gain \
  --backend local --process tt --temp 27 --supply 3.30 --no-write --allow-pdk-mismatch \
  --subset-reason 'issue 767 two-PDK measurement, leg B (ciel f6eeac7)'
```

Values were extracted from the retained full corner logs' FULL-precision
`meas_<name> = <value>` print lines (7 significant digits), never the `.6g`
console summary — same convention as `diagnostics/issue-757/paired/local/`:

```bash
grep -E '^meas_[a-z0-9_]+ = ' <log>   # -> paired/local/values-{volare,ciel}.json
```

## Result — all 55 measurements bit-identical, max |Δ| = 0

`paired/local/values-volare.json` and `values-ciel.json` (committed beside
this README) hold 55 named results each; `delta-summary.json` is computed
from them:

- **55/55 finite measurements agree exactly (Δ = 0.0 on every row)**: 18 PMs,
  17 GMs, 18 vout seeds, leg-1 fc, leg-1 DC gain — at the 7-significant-digit
  printed resolution.
- The 56th named result, `gm_c47_esr500m_1ma_db` (`ac11.gmdb`), is a
  **confirmed non-crossing on both legs** (`measure gmdb find(AT) : out of
  interval` in both logs) — agreement about absence, not a missing value.
- Bench grade FAIL both legs (PM below the 45 deg minimum at several legs) —
  identical grades, identical failing legs, unchanged in kind from the
  `20261029-092024` and `20261124-051830` records.

## Why the two builds agree: the model content is identical, only the packaging differs

Measured on this host's two stores (both present):

- All 675 `sky130_fd_pr` `.spice` files under `libs.ref/` are byte-identical
  (per-file sha256 sets match exactly).
- `libs.tech/combined/continuous/models_fet.spice`: the ciel build splits it
  into 22 per-device `.include` files; the volare build embeds one monolith.
  Concatenated and stripped of comments/blanks, both are the **same 40,651
  lines in different order** — sorted-content sha256
  `e400c9312ff38f3fc3a9ec1a351f333599ebb26639df27169ebb686686f429f9` for
  both.
- `libs.tech/combined/sky130.lib.spice` declares the same 49 `.lib` corner
  sections in both builds (tt/ss/ff/sf/fs/ll/hh/… all present, so
  `sim/pdk.json`'s `process_corners` list carries over unmodified).

So the two open_pdks builds package the same skywater model sources
differently; the deck's tt solve cannot tell them apart. This also resolves
the issue's "suspected consequence": the ~0.06 deg PM shift PR #766's
diagnostics README attributed to "the PDK build + engine change" is, to the
printed resolution, **engine-only** (ngspice 42 → 47) — the PDK-build term is
exactly zero at this corner.

## Post-re-pin confirmation (same branch, after the pin moved)

`sim/loop-gain/records/20261124-152314-4ddb44da.md` — same single corner,
`--backend local`, `PDK_ROOT` unset (default resolution), **no
`--allow-pdk-mismatch`**: the record header reads
`sky130A @ open_pdks f6eeac7… (matches sim/pdk.json pin)`, and its 55 values
are the same numbers again. On this two-store host the resolution went to
`~/.ciel` via `sim/pdk.json`'s `default_pdk_root` (and via `ciel path` when
the CLI is on PATH) — the legacy `~/.volare` store is not a search root and
was never consulted, which is the first-match-wins ambiguity klt warns about,
closed for this harness.

## Artifacts

- `paired/local/volare-tt_27c_3.30v.fail.log` (sha256
  `f7f0f9f15b2e534fd1e94f0b806622a5de42500544f1a053a7d847ea86f32994`)
- `paired/local/ciel-tt_27c_3.30v.fail.log` (sha256
  `41d9de339e77a2c157bceb4d4e8579d6b334ee256275a28755c76db71db1b0ef`)
- `paired/local/values-volare.json`, `paired/local/values-ciel.json`,
  `paired/local/delta-summary.json`

Related: #767, DR-015, `sim/loop-gain/diagnostics/issue-757/` (the
local/fleet engine-pair precedent this mirrors), #639, #645.
