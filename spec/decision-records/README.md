# Decision records

One file per decision, DR-NNN-<slug>.md. See CLAUDE.md.

Numbers are unique and never reused: records are append-only, so a decision that
is overturned is *superseded* by a new record rather than edited or renumbered.

`npm run check:ci` enforces that convention via
`.loom/scripts/check-dr-numbering.sh`, which fails if two tracked files here
share a `DR-NNN` prefix, or if a `DR-*` filename does not match
`DR-NNN-<slug>.md` (exactly three digits).

**Picking the next number: read the open PRs, not just `main`.** The check is
tree-local, so it only catches a collision once both records are on the same
branch. Four open PRs once each added a different `DR-008-*.md` at the same
time (#140) — every one of them correct against `main`, where the highest
record was `DR-007`, and every one of them merging cleanly because the
filenames differed. Before claiming a number, check what open PRs have already
claimed:

```bash
gh pr list --state open --json number,files \
  --jq '.[] | {pr: .number, dr: [.files[].path | select(startswith("spec/decision-records/DR-"))]} | select(.dr | length > 0)'
```

## Status inventory

One row per tracked `DR-NNN-*.md` file. The **Status** column is the first
status word each record declares in its own `- **Status**:` metadata line,
normalized (Markdown emphasis stripped) to exactly one of `proposed`,
`ratified`, or `superseded`. This index *records* declared state; it does not
decide it. A record's own file stays authoritative, and a status transition is
made in the record itself through a decision record, never by editing this
table alone. Where the ratifying reference is ambiguous, the table says
`unresolved — see #301` rather than inferring authority from a merged PR.

`check-dr-numbering.sh` (run by `npm run check:ci`) parses only the table whose
header row is exactly the one below, and fails if a record is missing, listed
more than once, listed with a status that disagrees with its file, or if the
table names a record that does not exist.

| Record | Status | Ratifying reference | Governs |
| --- | --- | --- | --- |
| [DR-001](DR-001-pass-device-supply-framing.md) | ratified | operator ruling on #1, 2026-08-14 | pass-device family and input-rail framing (framing A) |
| [DR-002](DR-002-output-capacitor-esr-window.md) | ratified | #1 (DR-006) | output-capacitor / ESR window |
| [DR-003](DR-003-sky130-device-characterization.md) | ratified | #1 (DR-006) | pass-device characterization methodology (dropout point, sizing, Iq scope) |
| [DR-004](DR-004-corner-model-names.md) | ratified | #1 (DR-006) | verification-corner binding to sky130 model names |
| [DR-005](DR-005-thermal-shutdown-trip.md) | ratified | #1 (DR-006) | thermal-shutdown trip temperature, hysteresis, reference |
| [DR-006](DR-006-spec-ratification.md) | ratified | operator ruling (Option A), 2026-09-15 | ratification of the target specification |
| [DR-007](DR-007-psrr-stability-vs-iq.md) | proposed | unresolved — see #301 | PSRR and stability rows vs. the Iq budget |
| [DR-008](DR-008-thermal-theta-ja-integration-constraint.md) | proposed | unresolved — see #301 | Thermal row: θJA integration constraint on the package |
| [DR-009](DR-009-iq-budget.md) | proposed | unresolved — see #301 | Iq row (< 30 µA, no load and full load) |
| [DR-010](DR-010-error-amp-stays-in-tree.md) | proposed | unresolved — see #301 | error amplifier stays in-tree (reuse rule 9) |
| [DR-011](DR-011-pass-device-resize.md) | proposed | unresolved — see #301 | pass-device re-sizing (DR-003 sizing point) |
| [DR-012](DR-012-no-bandgap-reuse-lock-entry-yet.md) | proposed | unresolved — see #301 | no `reuse.lock.json` entry for the bandgap edge yet (reuse rule 9) |
