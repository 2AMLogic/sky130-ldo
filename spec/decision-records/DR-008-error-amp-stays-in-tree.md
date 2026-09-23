# DR-008: the error amplifier stays in-tree — `2AMLogic/sky130-opamp` is not a drop-in (2am reuse rule 9)

- **Status**: **proposed** — an editorial/ledger record, carried for ratification
  via the PR that lands it (Judge review + Champion/operator merge) per the
  2026-08-19 canary spec/DR ratification-via-PR standing policy
  ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)), the same path
  DR-003/DR-004/DR-005 used. Nothing here is binding until that PR merges.
  Status-line wart, stated rather than left to bite (the same one DR-004 carries
  in `sky130-opamp`): merging the PR does not rewrite the line above, so a merged
  copy of this record still reads `proposed` — treat that as a drafting artifact
  of the ratification mechanism, not as an unratified decision.
- **Date**: 2026-09-23
- **Author**: Builder agent (drafted per #123)
- **Ratifies against / input to**: #123 (2am reuse rule 9 — adopt-or-record for
  the in-tree error amplifier). This record **sets no numeric row** in
  `spec/target-spec.md` and proposes no change to one; it records a reuse
  decision and is the `decision` target of `reuse.lock.json`'s `in_tree` entry.
- **Supersedes**: none — eighth decision record in this repo; touches no earlier
  record. DR-001 (pass-device and supply framing) is cited as a binding input,
  not revised.

## Context

[`2AMLogic/2am`](https://github.com/2AMLogic/2am)'s `repos.yml` records
`consumes: [sky130-opamp, sky130-bandgap]` on this repo, and cross-cutting reuse
rule 9 ([`2am/REUSE.md`](https://github.com/2AMLogic/2am/blob/main/REUSE.md),
ratified [2am#899](https://github.com/2AMLogic/2am/issues/899), widened
2026-09-21 to same-PDK sub-blocks) makes that edge a **recorded** fact on both
ends: a block a repo designs in-tree although a same-PDK sibling builds one gets
an explicit adopt-or-keep answer, not silent duplication. Until #123 this repo
carried no `reuse.lock.json` and no record naming either sibling.

The block in question: this repo's **error amplifier**, embedded in
`design/ldo_3v3in_1v8out.sch`. The sibling: **`2AMLogic/sky130-opamp`**, whose
whole job is a standalone op-amp on the same PDK. This record covers **only**
that edge; the separate `sky130-bandgap` consumption edge (a bandgap reference,
not an amplifier) is deliberately out of scope here and needs its own entry.

**This block, as built** (`design/ldo_3v3in_1v8out.sch` @ `b53a8e7`, unchanged
since PR #90):

- Single-stage current-mirror ("symmetric") OTA, promoted from a 5-transistor
  OTA by #25. It is *deliberately* one gain stage: both turnaround nodes
  (`EA_D2`, `PB`) are diode-loaded, so the loop keeps the two-pole
  (`EA_OUT`, `VOUT`) shape its Miller-plus-nulling-resistor compensation is
  designed for (`design/README.md` §"Closed in #25: light-load regulation").
- Its **second gain stage is the LDO's own common-source pass device** — the
  amplifier is not a standalone cell with a published port contract; it has no
  `.sym`, no subcircuit boundary, and no port list to compare against.
- Every active device is `sky130_fd_pr__pfet_g5v0d10v5` /
  `sky130_fd_pr__nfet_g5v0d10v5` — the whole amplifier and bias chain, not just
  the pass device (`design/README.md`, "All active devices are …"). DR-001
  (framing (A), **ratified** by the operator's ruling on #1, 2026-08-14) is why:
  *"the amplifier's output stage cannot be core-flavor regardless, since the
  pass gate must swing to VIN"*. `VIN` is 3.3 V ±10% (3.63 V worst case).

**The sibling, as built — re-verified live for this record on 2026-09-23**, not
carried over from #123's 2026-09-21 research (`2AMLogic/sky130-opamp` head
`ad365aaf034b9b54707d061c083d65d3a9ec1333`):

- `design/opamp_core.sch` and `spec/decision-records/DR-001-topology-and-cl.md`
  were both last modified at `177ff9ee75398045e0d8daf138c508fc9afa001c`
  (2026-09-15, its #15) — i.e. **no topology change since #123's research**;
  every commit since is a Loom resync or the #31/DR-004 documentation pass.
- Topology confirmed from its committed netlist
  (`design/netlist/opamp_core.spice`): NMOS input pair (`XM1`/`XM2`),
  non-cascoded PMOS current-mirror load (`XM3`/`XM4`), NMOS tail (`XM5`) from a
  diode-connected `ibias` reference (`XMB1`), Class-A PMOS common-source output
  stage (`XM6`) with an NMOS sink (`XM7`), and nulling-resistor Miller
  compensation (`XRz` + `XCc`) — a **two-stage Miller-compensated standalone**
  op-amp, ports `vdd vss inn inp out ibias`.
- Device flavor confirmed device-by-device from the same netlist: **every**
  transistor is `sky130_fd_pr__nfet_01v8` or `sky130_fd_pr__pfet_01v8`. Its
  `CLAUDE.md` scopes the block to 1.8 V-core CMOS, its DR-001 states "no 3.3 V
  I/O-flavor variant is opened here", and its #14's acceptance criteria
  explicitly forbid any `g5v0d10v5` device.
- Maturity, for completeness: schematic + PVT-corner benches exist (its #17,
  closed), but its own GBW / fall-slew / output-swing rows are not met yet (its
  #20, #22 — both open as of 2026-09-23). This is context, not a reason for the
  decision below; the decision would be the same against a fully-converged
  sibling.

## Decision

**Kept.** This repo's error amplifier stays in-tree; `2AMLogic/sky130-opamp` is
not adopted for this position, and no `imports` entry is created.
`reuse.lock.json` records this as `{"block": "error-amplifier", "sibling":
"2AMLogic/sky130-opamp", "status": "kept", "decision": "<this file>"}`.

The decision rests on three independent grounds, any one of which alone blocks a
drop-in:

**(a) Topology mismatch.** This position is a *single-stage* symmetric OTA whose
second gain stage is the pass device, embedded with no port contract; the sibling
is a *two-stage* Miller-compensated standalone cell with its own output stage and
its own internal compensation. Dropping it in would not replace this amplifier —
it would replace the amplifier *and* insert a second high-impedance node ahead of
the pass stage, a three-pole loop. This repo has already **measured** what that
costs: #22 built and screened a PMOS common-source second gain stage on this
exact loop and measured a **351 mV pp limit cycle** at `C_out = 0.33 µF` / 50 mA
/ `VIN = 3.63 V`, which survived every compensation remedy tried (`C_COMP` = 10p
and 30p, a Miller cap around stage 2, a lower-gain stage 1, a higher stage-2 bias
current); #107 (closed 2026-09-15, verified-negative) re-examined that result as
its Candidate B and declined to re-spend a build cycle on it without a materially
different compensation architecture. The current single-stage topology measures
3.8 mV pp at the same corner. This is an in-repo verified-negative against the
*shape* the sibling is, not a guess about it.

**(b) Device-flavor mismatch, forced by a real supply difference.** This
amplifier runs on 5 V-gate `*_g5v0d10v5` devices because its output must swing
the pass gate to `VIN` (3.63 V worst case) — ratified framing (A), DR-001. The
sibling is 1.8 V-core `*_01v8` **exclusively**, by its own `CLAUDE.md`, its
DR-001 scope, and its #14's acceptance criteria. This is not a re-sizing
exercise: a core-flavor output stage cannot reach this node at any sizing, and
the sibling's own DR-004 (2026-09-22) already scores this repo's Rails row as
**not met**, with "the 3.3 V I/O flavor is named-not-opened" standing as an open
item there. Filed on the sibling as `2AMLogic/sky130-opamp`#36 (below).

**(c) The sibling itself already reached this conclusion, in writing, about this
exact schematic.** `2AMLogic/sky130-opamp`#14 (closed), §"Precedent (same PDK,
does not transfer as topology)":

> `sky130-bandgap/design/error_amp.sch` and
> `sky130-ldo/design/ldo_3v3in_1v8out.sch` are this repo's nearest same-PDK
> xschem entry precedent for tool usage and symbol/subcircuit conventions —
> `spec/porting-plan.md` §3 already establishes neither schematic transfers as a
> topology source (both are sized for a different supply voltage and a narrow
> internal role). Use them only for xschem mechanics (symbol creation,
> hierarchy, netlist export), not for device sizing or topology.

Its DR-004 restates the same finding from the other direction ("Not the same
block (recorded once, by name)"). Both ends of the edge therefore agree, and
this record is the consumer-side half being written down rather than left
implicit.

## Alternatives considered

- **Adopt the sibling (`imports` entry, in-tree copy removed).** The case for it
  is real and worth stating: one amplifier maintained once, on a PDK where both
  repos pay for their own characterization, and the sibling's two-stage Miller
  topology is exactly the "higher-DC-gain architecture" DR-007's Consequences
  section named as the most plausible route out of this block's PSRR/stability
  gap. Not chosen: it fails on rails before topology is even reached (ground
  (b) — a 1.8 V-core output stage cannot drive a 3.63 V pass gate), and the
  topology it would import is the one #22 *measured* oscillating on this loop
  (ground (a)). Adoption would require the sibling to open a 5 V-gate flavor
  **and** this loop to acquire a materially different compensation architecture
  — two independent, unbuilt prerequisites, not an integration task.
- **`status: evaluate` — defer until the sibling converges on its own spec
  (#20/#22 there).** Not chosen: waiting would be right if the blocker were
  *performance*, but it is rails and topology shape, and neither moves when the
  sibling closes its GBW/slew gaps. Rule 9's own step 1 exists precisely so the
  question is visible without waiting; leaving it `evaluate` here would imply an
  open question that the evidence above has already closed, and would make the
  next auditor re-derive all of it. (If the sibling *opens* a 5 V-gate flavor —
  `sky130-opamp`#36 — that is a new fact, and the right response is a superseding
  record, not an edit to this one.)
- **Adopt only the sibling's compensation sizing / gm-ID method rather than the
  cell.** Not chosen, and worth separating from adoption proper: its
  `sim/gm-id-characterization` method is genuinely reusable, but its *numbers*
  are `*_01v8` at `VDD = 1.8 V` and transfer to nothing here. Borrowing method
  is not a rule-9 reuse edge and needs no lock entry; borrowing numbers would be
  a correctness error. Nothing is imported either way.
- **Record the decision in `design/README.md` prose instead of a decision
  record.** Not chosen: `CLAUDE.md` routes this class of decision through
  `spec/` with a record, `reuse.lock.json`'s `kept` status **requires** an
  existing `decision` file (`2am/scripts/reuse-check.py` fails without one), and
  `design/README.md` is already long enough that a reuse decision would be
  unfindable in it.

## Consequences

- **`reuse.lock.json` now exists** at the repo root with one `in_tree` entry, and
  this repo's end of the rule-9 edge is closed. `2am/scripts/reuse-check.py
  <repo-dir>` validates it offline; a future `adopting`/superseding decision
  edits the lock entry and files a **new** record rather than editing this one.
- **A requirement travelled to the sibling, not just into this file.** Rule 9
  step 4 ("its consumers are its spec") is satisfied by
  [`2AMLogic/sky130-opamp`#36](https://github.com/2AMLogic/sky130-opamp/issues/36),
  filed from here: both same-PDK consumers need a 3.3 V-rail / 5 V-gate
  amplifier position that the sibling's ratified 1.8 V-core scope does not
  serve. It asks for either an opened `g5v0d10v5` flavor behind its own decision
  record **or** a standing "does not serve this position" record — deliberately
  not presuming which.
- **Cost accepted: this repo keeps maintaining its own amplifier**, including
  its own characterization evidence, and the fleet keeps two same-PDK amplifiers
  alive. That duplication is now a *recorded* choice with an argument attached,
  which is what rule 9 asks for; it is not made cheaper by this record.
- **This record settles reuse, not design.** It does **not** close, reopen, or
  weaken any of the block's failing rows (PSRR, stability, dropout, load
  transient, output accuracy — `measurements/characterization.md`), and it does
  not endorse the current topology as sufficient. If a future pass adopts a
  materially different compensation architecture and a second gain stage becomes
  viable, ground (a) weakens — ground (b) does not, unless `sky130-opamp`#36
  lands a 5 V-gate flavor. **Both** would have to change before adoption is even
  evaluable, and that evaluation belongs to a superseding record.
- **Handed to design unresolved**: nothing new. This record introduces no design
  obligation and asks for no schematic change; the open design questions it
  touches (higher-DC-gain architecture, crossover-raising compensation) were
  already owned by DR-007 and #107's verified-negative conclusion and are
  unchanged by it.
- **Drift is detectable, deliberately.** Every sibling fact above is pinned to a
  commit (`ad365aaf…` head, `177ff9ee…` for the schematic and its DR-001) and
  this block to `b53a8e7`. If either head moves the amplifier or the device
  flavor, re-evaluation is findable rather than silent — the same convention the
  sibling's DR-004 adopted for its verdict stamps.

## Status notes

- Stays `proposed` until the PR carrying it is approved and merged (Judge review
  + Champion/operator merge), which is the ratifying act under the 2026-08-19
  ratification-via-PR standing policy ([2am#357](https://github.com/2AMLogic/2am/issues/357)).
  This record does not self-ratify, and — see the status-line wart above — the
  merged copy will still read `proposed`.
- Because it sets no `spec/target-spec.md` row, it is **not** input to #1's
  ratification gate and does not wait on it. `spec/target-spec.md` is unmodified
  by the PR that lands this record.
- `reuse.lock.json`'s `in_tree` entry points at this file by path; renaming or
  removing this file breaks `reuse-check.py`. A later decision (adopt, or a
  changed sibling scope via `sky130-opamp`#36) produces **DR-009+** marking this
  record superseded — this file is never edited to match a later outcome
  (`CLAUDE.md`, append-only records).
- Out of scope, tracked elsewhere: the `sky130-bandgap` consumption edge
  (`repos.yml` records it; it is a bandgap reference, not this amplifier) has no
  lock entry yet and is not decided here — it is a different shape (this repo
  builds no reference at all; `VREF` is an external port), tracked as **#136**.
