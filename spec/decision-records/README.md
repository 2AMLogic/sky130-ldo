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
