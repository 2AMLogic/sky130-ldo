# LDO core ERC supply record: 20260923-094733-83f99b3

`klt erc` against the LDO core layout with [`erc-supply-spec.json`](erc-supply-spec.json) -- the supply spec T1 item 11 (**power delivery, structural**) is graded from (issue #112). The spec file carries an inline comment block justifying every `stackup` entry, every `label_layer`, and both `ties[]` declarations; this record states what the run said about them.

Item 11 asks the *structural* question -- is the supply connected to what it powers -- not the *analysis* question (IR-drop and EM, `klt power`), which stays deliberately outside it.

## Item 11 verdict: MET

- [x] zero `erc.unconnected_net` and zero `erc.supply_short` naming a declared supply
- [x] zero `erc.missing_tie`, **from ties the run actually checked** (2 checked, 0 skipped as degenerate)
- [x] every declared supply resolved to exactly one electrical island (2 of 2 checked)
- [x] all four falsification controls fired

Connectivity roll-up (`erc_status`): **clean** -- 0 finding(s).

Antenna roll-up (`status`): **clean**. This is a SEPARATE verdict and is not item 11's subject (klayout-tools#1994); it is reported here so a reader never has to mistake one for the other.

## Declared supplies

| Supply | `kind` | connectivity work | verdict |
| --- | --- | --- | --- |
| `VIN` | supply | checked | one island |
| `0` | supply | checked | one island |

`erc.unconnected_net` fires on zero label matches AND on more than one island, so zero findings of that rule *is* the "exactly one electrical island per supply" verdict, not merely an absence.

## `erc.missing_tie` -- computed, not disclosed

Issue #112 was written expecting this section to say the opposite: that `ties[]` was omitted because klayout-tools#2169 made a declared tie collapse a real design into one electrical island and report a FALSE `erc.supply_short`, leaving `erc.missing_tie` *not computed*. That blocker is fixed on the `klt` build this record is pinned to -- a `ties[]` entry is now evaluated in its own second extraction and provably cannot alter `gates[]`, the antenna verdicts, or the `nets[]` findings -- so both ties are declared and graded here instead. That matters for the item, not just for tidiness: a spec with zero `ties[]` grades as `supply_spec_incomplete` (**unmet**), and so does a `ties_disclosure` of either kind, because a disclosure is the caller's word rather than a computed result.

| Tie | well side | tap side | work |
| --- | --- | --- | --- |
| `nwell_tie` -> `VIN` | `64/20` drawn | `65/44`, `tap_is_dedicated` | checked |
| `substrate_tie` -> `0` | asserted `well_boxes` [[2113.0, -0.5, 2208.5, 80.5]] | `65/44`, `tap_is_dedicated` | checked (well asserted) |

One tie rests on an **asserted** substrate region rather than a drawn well layer (`erc_coverage.checked_by_well_assertion`): sky130 NMOS sit in the native p-substrate and this stream draws no pwell shape, so the region is the caller's claim (klayout-tools#2255). The claim is falsifiable and is falsified where it can be -- each asserted polygon must independently hold a tap reaching the declared net, an assertion within 1% of the top-cell bbox is rejected as degenerate, and control C1 below moves this one off its tap and gets the finding. `layout/bin/check-erc-supply-spec.py` additionally re-derives the box from the GDS on every run, so a floorplan change cannot leave a stale assertion standing.

**What this does and does not say.** `erc.missing_tie` is a connectivity question -- does each well/asserted region hold a tap that reaches its declared net. It says nothing about tap DENSITY, and this block draws exactly one substrate tap and one n-well tap across a 2.4 mm span. Latch-up/body-bias robustness is a layout-quality question for DRC and the floorplan, outside what this item can see.

## Falsification controls

Every check item 11 grades passes by reporting NOTHING, so an all-clean report is indistinguishable on its face from a spec that asks no question. Each control mutates the committed spec one way and must produce the finding the graded run's clean verdict is claiming the absence of.

| Control | Mutation | Expected rule | Rules reported | Fired |
| --- | --- | --- | --- | --- |
| C1 | `substrate_tie`'s asserted well box moved into the poly-resistor field, where no tap is drawn | `erc.missing_tie` | erc.missing_tie | yes |
| C2 | `nwell_tie`'s tap required to reach `0` instead of `VIN` | `erc.missing_tie` | erc.missing_tie | yes |
| C3 | a supply net name (`VDDA`) that no layer in this stream carries | `erc.unconnected_net` | erc.unconnected_net | yes |
| C4 | `VOUT` declared a supply with the poly-resistor `devices[]` carve-out removed, i.e. the feedback divider read as wire (klayout-tools#2183) | `erc.supply_short` | erc.supply_short | yes |

## Coverage

- `erc_coverage.checked`: 22 work item(s)
- `erc_coverage.skipped`: 0 -- none
- `erc_coverage.inapplicable`: 0 -- none
- `erc_coverage.checked_by_well_assertion`: ['erc.missing_tie:["substrate_tie"]']
- `erc_coverage.checked_by_assertion`: none
- `ties_disclosure`: null -- this run declares real ties and grades them, so it has nothing to disclose in place of them

`provenance.devices` records the device-body carve-outs this run applied, so a reader can see that a clean `erc.supply_short` was not reached by leaving a device body in the graph as a wire:

- `poly_res` on role `poly`, body layer `66/13`, 878.64 um2 subtracted

## Item 11's other half (Analog column)

Item 11 is kind-dependent and this block is kind `analog`, so alongside this run it needs item 4's own LVS report to have carried the supply nets in its `net_correspondence` -- a SPICE reference satisfies that by construction, and `layout/ldo-core/reports/LATEST-LVS`'s `lvs.json` pairs both `VIN` and `0` there. The Digital column's extra asks (`power.pdn`, a named `power.tapcell_master`, `power_connectivity.status: "match"` from an RTL/P&R flow) do not apply to this block: there is no `klt place-and-route` response to cite because there is no synthesis or P&R step in its flow.

## Provenance

- Record ID: `20260923-094733-83f99b3`
- `klt` version: `klt 0.6.0+gcb79a84fe3e4`, reported by the run itself as `0.6.0+gcb79a84fe3e4` (pinned commit, see `layout/erc-requirements.txt` -- a SECOND pin, distinct from `layout/requirements.txt`'s DRC/LVS pin; that file explains why)
- KLayout engine version: `0.30.12`
- Antenna-limit table: `sky130` (`source: built-in`) -- `klt`'s own built-in transcription of SkyWater's published sky130 antenna rule tables. This flow reads no local PDK tree, so it has no PDK pin to cross-check.
- Layout input content hash: `sha256:52307a206e6eaaa2e555dbb3aa6b62928ac2d5fab8189f9dd4f1600d220d9172` -- hash of the committed `layout/ldo-core/reports/20260825-123551-3b4e121/ldo_core.gds`, which is the file this run read (the GDS is deliberately not copied into this record: a copy would only re-state a hash of itself).
- Spec content hash: `sha256:711924df46ee1ea7761e9e539e37f988d7b15c0a76237b3abace5cda2c59af96` -- hash of [`erc-supply-spec.json`](erc-supply-spec.json), the byte copy in this record.
- Layout freshness: `layout/ldo-core/` as of commit `83f99b3`; GDS taken from layout record `20260825-123551-3b4e121` (the record `layout/ldo-core/reports/LATEST` names).
- Repo state: `83f99b32153a6905a71c21fad4544ae6ef8984c3` on `feature/issue-112` (dirty)

## Links

- [`erc_supply.json`](erc_supply.json) -- the graded run
- [`erc_control_C1.json`](erc_control_C1.json) -- falsification control C1
- [`erc_control_C2.json`](erc_control_C2.json) -- falsification control C2
- [`erc_control_C3.json`](erc_control_C3.json) -- falsification control C3
- [`erc_control_C4.json`](erc_control_C4.json) -- falsification control C4
- [`erc-supply-spec.json`](erc-supply-spec.json) -- byte copy of the spec this record was run on
- [`layout-record-id.txt`](layout-record-id.txt) -- which layout record the GDS came from

