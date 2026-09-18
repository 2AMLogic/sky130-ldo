# DR-004: Binding the DRAFT verification-corner set to sky130 model names

- **Status**: **ratified** — corner-name binding ratified by #1 (DR-006),
  pending operator PR approval per the 2026-08-19 ratification-via-PR
  standing policy ([2AMLogic/2am#357](https://github.com/2AMLogic/2am/issues/357)).
- **Date**: 2026-08-14
- **Author**: Builder agent (drafted per #10)
- **Ratifies against / input to**: #1 (Ratify the target spec — operator-only,
  the T1 gate)
- **Supersedes**: none

## Context

`spec/target-spec.md` §"Verification corners (DRAFT)" states an abstract
process axis — `{tt, ff, ss, fs, sf}` — mirrored from `2AMLogic/gf180-ldo`,
crossed with `T {−40, 27, 125} °C` and `Vin {2.97, 3.3, 3.63} V`, and says
plainly: "The exact sky130 corner-model names and any binding-corner
assignments... are to be fixed at ratification." That is open item 4. This
record is that binding.

The pinned PDK is `sky130A`, open_pdks `c6d73a35f524070e85faff4a6a9eef49553ebc2b`
(`sim/pdk.json`, same pin DR-001 used). `sim/pdk.json`'s `process_corners` list
— `["tt", "ss", "ff", "sf", "fs", "ll", "hh"]` — is already annotated as
"verified against the `.lib` sections of `libs.tech/combined/sky130.lib.spice`
for this pinned commit," and `sim/bin/corner-run.py` already knows how to drive
any of them via a `.lib "<models>" <corner>` include. Re-reading that file at
the pin confirms the header comment and the section list directly:

```
* tt  --- Typical N/P device, nominal resistance, nominal capacitance
* ss  --- Slow  N/P device, nominal resistance, nominal capacitance
* sf  --- Slow N/Fast P device, nominal resistance, nominal capacitance
* fs  --- Fast N/Slow P device, nominal resistance, nominal capacitance
* ff  --- Fast N/Fast P device, nominal resistance, nominal capacitance
* ll  --- Typical N/P device, low resistance, low capacitance
* hl  --- Typical N/P device, high resistance, low capacitance
* lh  --- Typical N/P device, low resistance, high capacitance
* hh  --- Typical N/P device, high resistance, high capacitance
```

(`.lib tt` / `.lib ss` / `.lib ff` / `.lib sf` / `.lib fs` / `.lib ll` /
`.lib hh` are the literal section names at lines 82, 163, 136, 109, 190, 217,
244 of `libs.tech/combined/sky130.lib.spice`; `ss_ll`, `ss_hl`, ..., the
`_mm` mismatch sections and `mc` Monte Carlo also exist but are not part of
this binding — see "Alternatives considered".) Each corner section
`.include`s a matching per-device corner file, e.g. `.lib sf` pulls in
`sky130_fd_pr__pfet_g5v0d10v5__sf.corner.spice` and
`sky130_fd_pr__nfet_g5v0d10v5__sf.corner.spice` — confirmed by grepping
`libs.tech/ngspice/corners/sf.spice` at the pin — so the DRAFT spec's abstract
`sf`/`fs`/etc. labels are not placeholders needing translation; they are
already sky130's own section names, reused unmodified by the DRAFT (which
copied gf180-ldo's axis, and gf180mcu happens to use the same five-letter
convention).

## Decision

**Bind the DRAFT's process axis `{tt, ff, ss, fs, sf}` directly to the
identically-named `.lib` sections in `libs.tech/combined/sky130.lib.spice`
at the pinned open_pdks commit — no renaming or translation is needed. Bind
the temperature axis `{−40, 27, 125} °C` to ngspice's `.temp` directive (not
a named PDK section) and the `Vin` axis `{2.97, 3.3, 3.63} V` to the
`.param vsup=` mechanism `sim/bin/corner-run.py` already injects — both are
numeric, not name, bindings, and the DRAFT's own numbers are already correct.**
`ll` and `hh` (and the combined `ss_ll`-style, `_mm`, and `mc` sections) are
named as available in the pinned library but are explicitly **not** bound by
this record — see Consequences.

This is a naming/wiring resolution, not a numeric ratification: it does not
set or change any spec-row number, and it is a **recommendation for #1 to
rule on**, like DR-001 and DR-003.

### The caveat this record exists to record

The header comment's English gloss — "sf = Slow N / Fast P", "fs = Fast N /
Slow P" — invites reading the corner name as a direct predictor of which
corner is worst for a PMOS-dominated circuit (e.g. "P is fast in `sf`, so
`sf` should never be the pass-device's binding corner"). **DR-003's screening
of `sky130_fd_pr__pfet_g5v0d10v5` at this repo's sizing point falsifies that
shortcut for this device**: R_on·W and \|V_th\| both group by the corner
name's *first* letter, not the second, across all five corners, three
temperatures, and both bias points DR-003 tested — `{ss, sf}` cluster high
(worse, i.e. slower-looking), `{ff, fs}` cluster low (better), with `sf`
marginally the single worst point in the tested grid and `fs` essentially
tied with `ff` for best. That is the opposite grouping a literal reading of
the header gloss would predict for a PMOS pass device. DR-003's appendix has
the deck and the full data table; this record does not re-derive it, only
draws the naming conclusion: **the corner-name binding this record delivers
is a name-to-section binding, not a name-to-severity binding** — no spec row
or design decision may infer which corner binds from the letters alone. It
must be measured, per device, per bias point, as DR-003 illustrates.

## Alternatives considered

- **Invent sky130-specific corner labels for the spec table** (e.g. relabeling
  to avoid the gf180-mirrored letters). Rejected — the existing five-letter
  set already *is* sky130's real section name set (confirmed above), so there
  is nothing to invent; renaming would only add a translation step between
  the spec and `sim/pdk.json`/`corner-run.py`, which already agree.
- **Trim the swept set** (e.g. drop `sf`/`fs`, sweep only `{tt, ss, ff}`) to
  shrink the corner matrix, on the theory that `ss` alone captures the
  "PMOS-slow" case the header gloss assigns it. Rejected — DR-003's data
  shows `sf` is at least as bad as `ss` for this device (within screening
  resolution, arguably marginally worse), so dropping it would silently
  exclude a co-binding corner. This is exactly the gap DR-001 flagged as
  unconfirmed ("fs/sf corners... have not been screened") and DR-003 now
  shows the gap was real, not a formality.
- **Trust the header's N/P gloss to assign the binding corner analytically**
  without simulation. Rejected — directly contradicted by DR-003's data for
  this device at this bin; the gloss may hold for other devices or other
  bins, but this record cannot certify that and does not try to.
- **Bind `ll`/`hh` (and `_mm`/`mc`) into the matrix now**, since they exist in
  the pinned library and are already listed in `sim/pdk.json`. Deferred, not
  rejected — no resistor-dependent spec row (feedback divider, current-limit
  sense resistor) has a decision record or a topology yet, so binding
  resistor-skew corners into the *MOS* verification matrix this record is
  scoped to would be premature and unenforceable. The names are confirmed
  available for whichever record specifies the resistor-based rows.
- **Bind the mismatch (`_mm`) and Monte Carlo (`mc`) sections** for a future
  statistical/offset claim (e.g. feedback-divider mismatch, amplifier offset).
  Named as available, not bound — no such claim exists yet in the DRAFT spec
  to bind them to.

## Consequences

- Once #1 ratifies this record, `spec/target-spec.md`'s "Verification
  corners (DRAFT)" section's process axis needs no textual change — the five
  letters it already states are the correct, real sky130 `.lib` section
  names — but should gain the naming-severity caveat above, so a future
  implementer does not shortcut the sweep by reading the letters.
- Unblocks any future sky130-ldo stability/dropout/PSRR testbench to call
  `sim/bin/corner-run.py --process tt,ss,ff,sf,fs` directly, with the same
  `experiment.json` manifest convention `sim/pdk-smoke` already exercises —
  no per-experiment corner-name translation layer is needed.
- Confirms the T and Vin axes require no PDK-name binding at all, only the
  numeric lists the DRAFT already states (`{−40, 27, 125} °C`,
  `{2.97, 3.3, 3.63} V`) — a small but real closing of part of item 4's
  ambiguity.
- Explicitly leaves `ll`, `hh`, the combined resistor/cap-skew sections, the
  `_mm` mismatch sections, and `mc` Monte Carlo **unbound** by this record.
  Whichever record specifies the feedback-divider or current-limit-sense
  resistor topology should either extend this record's binding or draft its
  own — this record does not foreclose either path.
- Hands to design, unresolved: DR-003 narrows but does not close which of
  `ss`/`sf` at 125 °C is the true worst case for the pass device; this record
  only establishes that both names resolve to real, already-wired PDK
  sections, not which one wins.

## Status notes

**Ratified by DR-006 / #1, pending operator PR approval (2026-08-19).** The
binding above — process axis to the five named `.lib` sections, T and Vin
axes to their existing numeric lists — is ratified as stated; it did not
itself change any spec-row number, and ratification does not change that. If
a future record wants a different corner subset (e.g. including mismatch or
Monte Carlo sections for a specific claim), a superseding record follows
rather than an edit to this one.
