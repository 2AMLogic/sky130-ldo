# DR-012: no `reuse.lock.json` entry for the `sky130-bandgap` edge yet — `VREF` is an unbuilt external port (2am reuse rule 9)

- **Status**: **proposed** — an editorial/ledger record, carried for ratification
  via the PR that lands it (Judge review + Champion/operator merge) per the
  2026-08-19 canary spec/DR ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)), the same path
  DR-003/DR-004/DR-005/DR-010 used. Nothing here is binding until that PR merges.
- **Date**: 2026-09-23
- **Author**: Builder agent (drafted per #136)
- **Ratifies against / input to**: #136 (2am reuse rule 9 — the `sky130-ldo` ->
  `sky130-bandgap` consumption edge in `2am/repos.yml`'s `consumes:
  [sky130-opamp, sky130-bandgap]` list), split out from #123/DR-010 which
  covered only the `sky130-opamp` half. This record **sets no numeric row** in
  `spec/target-spec.md` and proposes no change to one; it records why this
  repo's `reuse.lock.json` (added by DR-010) carries no entry for the
  `sky130-bandgap` edge today.
- **Supersedes**: none — twelfth decision record in this repo; touches no
  earlier record. DR-010 is cited as a sibling precedent (the same edge-family,
  the other half), not revised.

## Context

`2AMLogic/2am`'s `repos.yml` records `consumes: [sky130-opamp, sky130-bandgap]`
on this repo (confirmed live, `repos.yml` on the `2am` feature branch that adds
`REUSE.md` — `2am#899` is not yet merged to `2am`'s `main` as of 2026-09-23, but
the `consumes` line itself is the pre-existing fact this record answers to).
Cross-cutting reuse rule 9 (`2am/REUSE.md`, `2am#899`) asks that a `consumes`
edge either resolve into a pinned `imports` entry, or — for the narrower
"in-tree duplication" case its "Adopt or record" ledger targets — an `in_tree`
adopt-or-keep entry. #123/DR-010 already closed this repo's `sky130-opamp` half
of the same `consumes` line: an in-tree error amplifier, kept, with an argument.

The `sky130-bandgap` half is a different shape, not a smaller version of the
same question:

- **There is no in-tree bandgap/reference block in this repo to adopt or keep.**
  `design/README.md`'s "VREF interface caveat" section states plainly: this
  block "does not design a bandgap/reference generator — `VREF` is an external
  port, standing in for a future reference-generator block." The OP checks in
  that same section use `VREF = 1.2V` as an **illustrative placeholder**, not a
  claimed or implemented reference. Nothing is duplicated, because nothing
  reference-generating exists here at all.
- **Rule 9's `in_tree` mechanism targets duplication, not every `consumes`
  line.** `2am/REUSE.md`'s "Adopt or record" ledger step is triggered by "a
  consumer that already carries an in-tree block a same-PDK sibling now
  builds" (verified against a local checkout of the `2am` feature branch that
  introduces it). With no in-tree reference here, there is nothing for that
  mechanism to evaluate — reaching for `in_tree: evaluate` would misdescribe
  the interface (it would read as "we have a reference and haven't decided
  whether to keep it," which is false; we have no reference at all).
  `reuse-check.py`'s own `imports` schema also cannot apply: it requires a
  pinned 40-hex `commit` and per-file `sha256` stamps
  (`2am/scripts/reuse-check.py`, `check_repo()`), and nothing from
  `sky130-bandgap` is fetched, vendored, or wired into this repo's schematic
  today — there are no bytes to pin.
- **`sky130-bandgap`#286 is not this edge's counterpart.** It is closed, and
  addresses a different rule-9 pairing entirely: `sky130-bandgap`'s own in-tree
  `error_amp` block versus the sibling `2AMLogic/sky130-opamp` — the same
  error-amplifier duplication question DR-010 resolves for *this* repo, but on
  `sky130-bandgap`'s side of a different edge. A search of that repo's issues
  for "sky130-ldo" (`gh issue list --repo 2AMLogic/sky130-bandgap --search
  "sky130-ldo" --state all`, 2026-09-23) returns exactly one hit, its closed
  #62 (a layout/LVS issue, unrelated to reuse). **No `sky130-bandgap`-side issue
  currently addresses "consumed by `sky130-ldo`."**

The three candidate shapes #136 laid out: (a) no lock entry, recording the edge
as an unrealized future dependency; (b) an `imports` entry once a reference is
actually wired in (needs a pinned commit and file hashes that do not exist
yet); (c) an `in_tree: evaluate` entry only if this repo ever builds its own
reference. This record picks among them.

## Decision

**(a).** No `reuse.lock.json` entry is added for the `sky130-bandgap` edge.
`reuse.lock.json` (added by DR-010) is unmodified by this record — it keeps its
single `error-amplifier` / `sky130-opamp` `in_tree` entry and gains no second
entry here. The edge is instead recorded as an **unrealized future
dependency** in prose, in two places: this record, and a new paragraph in
`design/README.md`'s "VREF interface caveat" section cross-linking here.

This is not a decision to ignore the edge — `repos.yml` still lists it, and
this record is exactly the "record" `2am/repos.yml`'s consumers-track-their-own
edges convention asks for when there is nothing yet to pin. It is a decision
that neither of rule 9's two lock-entry shapes (`in_tree`, `imports`) currently
describes this repo's actual relationship to `sky130-bandgap`, which today is:
*a named future dependency on an external port, not yet backed by any bytes
in either direction*.

## Alternatives considered

- **(b) An `imports` entry, pinned to `sky130-bandgap`'s current head.**
  Rejected: nothing is fetched or vendored from `sky130-bandgap` into this
  repo — no file, no netlist, no numeric value. `reuse-check.py`'s `imports`
  schema requires `from`, a 40-hex `commit`, `mode: fetched|vendored`, and a
  non-empty `files` list of upstream/local/sha256 stamps; there is nothing
  here to populate any of those fields honestly. Fabricating a pin against
  bytes that are not actually used would misrecord the interface as "this
  repo's `VREF` behavior is pinned to `sky130-bandgap` commit `X`" when it is
  not — `VREF` remains a free ideal-source port at the schematic level,
  unaffected by anything `sky130-bandgap` does internally. This is also the
  clean-room-relevant alternative: an `imports` entry would invite exactly the
  kind of "inspect the sibling's actual reference voltage to justify a pin"
  work `CLAUDE.md`'s clean-room rule forbids until a real integration is
  proposed and scoped on its own terms.
- **(c) An `in_tree: evaluate` entry.** Rejected: this status means "we have an
  in-tree instance of this block and haven't decided adopt-vs-keep" (DR-010's
  own use of `status: kept` follows the same schema). This repo has no in-tree
  reference-generator instance at all — `evaluate` would assert a block exists
  here that does not, which is a worse misdescription than no entry. If this
  repo ever grows its own on-chip bandgap/reference (candidate (c)'s actual
  trigger), that is a new design decision needing its own record and its own
  `in_tree` entry at that time — not something to pre-stage now against a
  block that has not been proposed.
- **`in_tree: evaluate` naming the *external port* itself as the "block."**
  Considered as a middle path (record the interface without claiming an
  in-tree implementation) but rejected: rule 9's `in_tree` array names blocks a
  repo "designs" (DR-010: "the block a same-PDK sibling now builds"); `VREF` is
  a port declaration, not a block this repo designs, and stretching the schema
  to cover it would make the ledger harder to read for every other repo that
  audits it mechanically.
- **Silence — leave the edge unrecorded anywhere in this repo.** Rejected as
  the one candidate #136 itself ruled out: `repos.yml`'s `consumes` line is a
  standing fact, and letting it have no answer anywhere in this repo (not even
  a "no entry, and here is why") is exactly the gap 2am#899's fleet audit found
  costly elsewhere (its own Context section: undocumented cross-repo
  assumptions cost real debug time on other canaries). The "VREF interface
  caveat" section already carried the substance of this answer implicitly;
  this record and its cross-link make it explicit and findable by
  `reuse-check.py`'s human readers, even though the tool itself has nothing to
  validate here.

## Consequences

- **`reuse.lock.json` is unchanged by this record** — it keeps DR-010's single
  `in_tree` entry and gains no `sky130-bandgap` entry. `2am/scripts/
  reuse-check.py <repo-dir>` has nothing new to validate; running it after this
  record lands should be byte-identical in outcome to running it against
  DR-010 alone (confirmed in the Test plan below).
- **The open interface question is now cross-linked, not just implicit.**
  `design/README.md`'s "VREF interface caveat" section gains an explicit
  pointer to this record and to #136, so a future reader (or auditor) does not
  have to re-derive "why no lock entry" from first principles.
- **This record is provisional against events outside this repo's control.**
  If a future issue proposes wiring an actual `sky130-bandgap` output into this
  schematic (candidate (b)) or this repo grows its own in-tree reference
  (candidate (c)), **this record is superseded by a new one** (`DR-013+`) that
  adds the appropriate `reuse.lock.json` entry — this file is not edited to
  match that later outcome (`CLAUDE.md`, append-only records).
- **Nothing about `VREF`'s real value is settled here.** This record is about
  *how the reuse edge is recorded*, not about what `VREF` should be — that
  open interface item (`design/README.md`, "VREF interface caveat") is
  unchanged and still belongs to whichever future issue adds a reference
  generator or a testbench-level ideal source.
- **Handed to design unresolved**: nothing new. This record introduces no
  design obligation and touches no schematic, spec row, or `sim/` record.
- **Cross-links established, per #136's own request**: this record cites #123
  and DR-010 (the sibling half of the same `consumes` line) and
  `2AMLogic/sky130-bandgap`#286 (checked and found *not* to be this edge's
  counterpart, so it is cited here as a negative result rather than a positive
  cross-reference).

## Status notes

- Stays `proposed` until the PR carrying it is approved and merged (Judge
  review + Champion/operator merge), which is the ratifying act under the
  2026-08-19 ratification-via-PR standing policy
  ([2am#357](https://github.com/2AMLogic/2am/issues/357)).
- Because it sets no `spec/target-spec.md` row and adds no `reuse.lock.json`
  entry, it is **not** input to #1's ratification gate and does not wait on
  it.
- Re-evaluate this record (via a superseding `DR-013+`) if any of: (1) a
  future issue proposes an actual `sky130-bandgap` import into this schematic,
  (2) this repo grows its own in-tree bandgap/reference block, or (3)
  `2AMLogic/sky130-bandgap` opens an issue that names this repo as its own end
  of this specific edge (none exists as of 2026-09-23 — see Context).
