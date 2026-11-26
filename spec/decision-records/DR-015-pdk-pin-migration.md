# DR-015: sky130 PDK pin migrates from the volare build to the ciel build

- **Status**: proposed
- **Date**: 2026-11-24
- **Author**: builder, issue #767
- **Ratifies against / input to**: issue #767 (this record does not ratify
  itself — see Status notes)
- **Supersedes**: N/A (no prior DR governs the PDK pin; `sim/pdk.json`'s pin
  was set at harness bootstrap, issue #2)

## Context

`sim/pdk.json` pinned sky130A open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
— the **volare** layout — while every worker the fleet dispatches on carries
the **ciel** store (`~/.ciel`, open_pdks `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`).
Every worker-minted record therefore ran under `--allow-pdk-mismatch` and
carries a standing `**MISMATCH vs sim/pdk.json pin**` header (e.g.
`sim/loop-gain/records/20261124-051830-d0bee518.md`) — a record that always
carries a mismatch flag stops being evidence of "PVT on the pinned PDK" (#291
pin discipline). Which store a run reads also depended on the host, the exact
first-match-wins ambiguity `klt` names in its two-install warning.

Facts the decision rests on:

- **Measurement** (the DR's own evidence,
  `sim/loop-gain/diagnostics/issue-767/`): the loop-gain testbench run twice
  at tt/27 °C/3.30 V with the same ngspice-47, once per build — **all 55
  finite measurements agree exactly (max |Δ| = 0)**; the 56th is a confirmed
  non-crossing on both. The two builds' FET model content is line-identical
  (40,651 non-comment lines, same sorted-content sha256; ciel merely splits
  `models_fet.spice` into 22 per-device includes), all 675 `sky130_fd_pr`
  files are byte-identical, and the combined `.lib` declares the same 49
  corner sections — so `process_corners` carries over unmodified. The ~0.06
  deg PM shift PR #766 saw versus the `20261029-092024` record is, to the
  printed resolution, engine-only (ngspice 42 → 47), not PDK-build.
- **Fleet direction**: ciel is the maintained successor to volare (same
  open_pdks build format and CLI shape); volare's PDK release feed stopped in
  Aug 2025. The fleet's `eda-sim` PDK manifest
  (`2AMLogic/klayout-tools` `docker/eda-sim/pdk-versions.json`) pins ciel
  `2.6.1` and open_pdks `f6eeac7…` for sky130.
- **Port parity**: the sibling `2AMLogic/sky130-bandgap` repo (same PDK, the
  harness this repo's was ported from) already pins
  `f6eeac7…` / ciel / `~/.ciel`; this move restores "same pin as
  sky130-bandgap".

## Decision

`sim/pdk.json` pins sky130A open_pdks `f6eeac7dad085ffcc829ccfd721f7b4ce39edcf7`,
installed via ciel (`ciel enable --pdk-family sky130 -l sky130_fd_pr <commit>`,
ciel 2.6.1), with `default_pdk_root` `~/.ciel`. The harness's PDK-manager leg
(corner-run resolution and `--check-env` liveness) tracks ciel instead of
volare, and every pin site moves in the same change: `sim/pdk.json`, the CI
`pdk-smoke` PDK-fetch steps, `docs/environment-setup.md`, and the prose/
comment pin references enumerated in issue #767. Existing records, netlist
snapshots and layout reports keep the build they were minted on — nothing is
re-minted or edited (append-only rule). This is **not** a spec-table change:
no row of `spec/target-spec.md` moves.

## Alternatives considered

- **Keep the volare pin and export `PDK_ROOT` to the volare store on hosts
  that have it** (issue #767 disposition 2): rejected — it keeps every run on
  a hand-provisioned store the worker spec does not guarantee (the store's
  presence is uneven across workers), keeps a discontinued toolchain, and
  leaves the mismatch flag standing on hosts without it.
- **Close as deliberate drift** (disposition 3, the class of #639/#645):
  rejected — those issues cover *tool* pins where drift is recorded per-run
  and harmless to gate semantics; here the drift flag sits on **every**
  worker-minted record, which is exactly what #291's pin discipline exists to
  prevent, and the pinned store's presence means the drift is not even forced.
- **Wait for volare's feed to resume**: rejected — it stopped in Aug 2025 and
  ciel is its maintained successor with the same build format; waiting has no
  expected payoff and the fleet (eda-sim image, gf180-trng nightly,
  sky130-bandgap) has already moved.

## Consequences

- Worker-minted records stop carrying `MISMATCH vs sim/pdk.json pin` and
  again count as pinned-PDK evidence; `--allow-pdk-mismatch` reverts to its
  designed role (deliberate off-pin experiments, e.g. the #211-era mismatch
  campaigns). Confirmed live: `sim/loop-gain/records/20261124-152314-4ddb44da.md`
  reads `matches sim/pdk.json pin` with the flag unused.
- CI's `pdk-smoke` job installs ciel instead of volare and fetches the new
  pin; the selftest `--require-pdk` PDK drift check has a pin the fleet's
  stores actually satisfy.
- The measured equivalence bounds the migration's numerical risk at zero for
  this testbench at tt; other benches' historical records are untouched and
  remain valid as written (they name the build they ran on).
- A legacy `~/.volare` store on a host is no longer a search root and can no
  longer be read by accident; `installed_commit()` still understands both
  store layouts, so old records/snapshots remain interpretable.
- Unresolved and handed onward (not this record's to settle): the ngspice/xschem
  tools pins still declare 42/3.4.4 while workers run 47/3.4.7 — #645 and
  #639 own those moves; CI green for `--require-pdk` may additionally depend
  on them.

## Status notes

Stays `proposed` until an operator ratifies the pin move on issue #767 (the
same fresh-ratification posture DR-007…DR-013 carry under #301's ruling).
The migration itself (pin sites + harness manager leg + CI fetch + docs)
landed with issue #767 so the harness is not left straddling two pins while
the record waits; ratification flips this status line, nothing else.
