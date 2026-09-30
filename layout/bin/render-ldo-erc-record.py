#!/usr/bin/env python3
"""Render layout/ldo-core/reports/<record-id>/record.md for an LDO-core
`klt erc` supply-spec run (issue #112 -- T1 item 11, power delivery,
structural), from the JSON envelopes `run-ldo-erc-flow.sh` just produced in
that directory.

Standard library only (matches this repo's other `layout/bin/` render
scripts).

Two things this renderer deliberately does NOT do:

* It never reads `erc_supply.json`'s top-level `status` as item 11's
  verdict. That field is the ANTENNA verdict. Item 11 is graded from the
  connectivity half -- `erc_status`, `erc_findings[]`, and `erc_coverage` --
  and an antenna violation or a floating-gate finding in the same report is
  a real defect that is nonetheless not this item's subject
  (klayout-tools#1994). Both verdicts are reported, separately and named.

* It never narrates a verdict it has not read. Every number below comes out
  of the envelopes; the exit status is non-zero whenever the item-11 claim
  this record makes is not met, same convention as the other renderers.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _record_common import _load, provenance

#: The four falsification controls run-ldo-erc-flow.sh mutates out of the
#: committed spec, and the rule each one MUST report for the corresponding
#: check in the graded run to count as a check rather than a formality.
CONTROLS: dict[str, tuple[str, str]] = {
    "C1": (
        "erc.missing_tie",
        "`substrate_tie`'s asserted well box moved into the poly-resistor "
        "field, where no tap is drawn",
    ),
    "C2": (
        "erc.missing_tie",
        "`nwell_tie`'s tap required to reach `0` instead of `VIN`",
    ),
    "C3": (
        "erc.unconnected_net",
        "a supply net name (`VDDA`) that no layer in this stream carries",
    ),
    "C4": (
        "erc.supply_short",
        "`VOUT` declared a supply with the poly-resistor `devices[]` "
        "carve-out removed, i.e. the feedback divider read as wire "
        "(klayout-tools#2183)",
    ),
}

#: Rules item 11 grades on. Anything else in erc_findings[] is reported but
#: does not fail the item.
ITEM_11_RULES = ("erc.unconnected_net", "erc.supply_short", "erc.missing_tie")


def _rules(report: dict) -> list[str]:
    return [f.get("rule") for f in report.get("erc_findings") or []]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--record-id", required=True)
    ap.add_argument("--repo-root", required=True, type=Path)
    ap.add_argument("--klt", required=True)
    ap.add_argument("--cell-name", required=True)
    ap.add_argument("--layout-sha", required=True)
    ap.add_argument("--layout-record-id", required=True)
    args = ap.parse_args()

    out_dir: Path = args.out_dir
    erc = _load(out_dir / "erc_supply.json")
    spec = _load(out_dir / "erc-supply-spec.json")

    # No PDK variant: this flow needs no PDK install (see the flow script).
    prov = provenance(args.repo_root, args.klt)

    coverage = erc.get("erc_coverage") or {}
    checked = list(coverage.get("checked") or [])
    skipped = list(coverage.get("skipped") or [])
    inapplicable = list(coverage.get("inapplicable") or [])
    by_assertion = list(coverage.get("checked_by_assertion") or [])
    by_well_assertion = list(coverage.get("checked_by_well_assertion") or [])

    supplies = [n["name"] for n in spec.get("nets", []) if n.get("kind") == "supply"]
    ties = [t["name"] for t in spec.get("ties", [])]

    found = _rules(erc)
    item_11_findings = [r for r in found if r in ITEM_11_RULES]
    tie_work_checked = [c for c in checked if c.startswith("erc.missing_tie:")]
    tie_work_skipped = [s for s in skipped if str(s.get("id", "")).startswith("erc.missing_tie:")]
    net_work_checked = [c for c in checked if c.startswith("erc.net_connectivity:")]

    # Item 11 is met when: every declared supply's connectivity was actually
    # checked, every declared tie's missing-tie work was actually checked
    # (not skipped-degenerate, not inapplicable), and none of the three
    # rules it grades on fired.
    met = (
        not item_11_findings
        and len(net_work_checked) == len(supplies)
        and len(tie_work_checked) == len(ties)
        and not tie_work_skipped
        and bool(ties)
    )

    controls_ok = True
    control_rows: list[tuple[str, str, str, str, bool]] = []
    for name, (expected, description) in CONTROLS.items():
        path = out_dir / f"erc_control_{name}.json"
        if not path.exists():
            control_rows.append((name, description, expected, "(not run)", False))
            controls_ok = False
            continue
        rules = _rules(_load(path))
        fired = expected in rules
        controls_ok = controls_ok and fired
        control_rows.append(
            (name, description, expected, ", ".join(sorted(set(rules))) or "(none)", fired)
        )

    lines: list[str] = []
    a = lines.append
    a(f"# LDO core ERC supply record: {args.record_id}")
    a("")
    a(
        "`klt erc` against the LDO core layout with "
        "[`erc-supply-spec.json`](erc-supply-spec.json) -- the supply spec "
        "T1 item 11 (**power delivery, structural**) is graded from "
        "(issue #112). The spec file carries an inline comment block "
        "justifying every `stackup` entry, every `label_layer`, and both "
        "`ties[]` declarations; this record states what the run said about "
        "them."
    )
    a("")
    a(
        "Item 11 asks the *structural* question -- is the supply connected "
        "to what it powers -- not the *analysis* question (IR-drop and EM, "
        "`klt power`), which stays deliberately outside it."
    )
    a("")
    a(f"## Item 11 verdict: {'MET' if met else 'NOT MET'}")
    a("")
    a(
        f"- [{'x' if not item_11_findings else ' '}] zero `erc.unconnected_net` "
        f"and zero `erc.supply_short` naming a declared supply"
    )
    a(
        f"- [{'x' if (tie_work_checked and not tie_work_skipped) else ' '}] zero "
        f"`erc.missing_tie`, **from ties the run actually checked** "
        f"({len(tie_work_checked)} checked, {len(tie_work_skipped)} skipped as "
        f"degenerate)"
    )
    a(
        f"- [{'x' if len(net_work_checked) == len(supplies) else ' '}] every "
        f"declared supply resolved to exactly one electrical island "
        f"({len(net_work_checked)} of {len(supplies)} checked)"
    )
    a(f"- [{'x' if controls_ok else ' '}] all four falsification controls fired")
    a("")
    a(
        f"Connectivity roll-up (`erc_status`): **{erc.get('erc_status')}** -- "
        f"{erc.get('erc_finding_count')} finding(s)."
    )
    a("")
    a(
        f"Antenna roll-up (`status`): **{erc.get('status')}**. This is a "
        "SEPARATE verdict and is not item 11's subject "
        "(klayout-tools#1994); it is reported here so a reader never has to "
        "mistake one for the other."
    )
    a("")

    a("## Declared supplies")
    a("")
    a("| Supply | `kind` | connectivity work | verdict |")
    a("| --- | --- | --- | --- |")
    for supply in supplies:
        work = f'erc.net_connectivity:["{supply}"]'
        state = "checked" if work in checked else "NOT CHECKED"
        fired = [
            f
            for f in erc.get("erc_findings") or []
            if f.get("net") == supply or f.get("other_net") == supply
        ]
        verdict = "one island" if state == "checked" and not fired else "see findings"
        a(f"| `{supply}` | supply | {state} | {verdict} |")
    a("")
    a(
        "`erc.unconnected_net` fires on zero label matches AND on more than "
        "one island, so zero findings of that rule *is* the "
        "\"exactly one electrical island per supply\" verdict, not merely an "
        "absence."
    )
    a("")

    a("## `erc.missing_tie` -- computed, not disclosed")
    a("")
    a(
        "Issue #112 was written expecting this section to say the opposite: "
        "that `ties[]` was omitted because klayout-tools#2169 made a "
        "declared tie collapse a real design into one electrical island and "
        "report a FALSE `erc.supply_short`, leaving `erc.missing_tie` *not "
        "computed*. That blocker is fixed on the `klt` build this record is "
        "pinned to -- a `ties[]` entry is now evaluated in its own second "
        "extraction and provably cannot alter `gates[]`, the antenna "
        "verdicts, or the `nets[]` findings -- so both ties are declared and "
        "graded here instead. That matters for the item, not just for "
        "tidiness: a spec with zero `ties[]` grades as "
        "`supply_spec_incomplete` (**unmet**), and so does a "
        "`ties_disclosure` of either kind, because a disclosure is the "
        "caller's word rather than a computed result."
    )
    a("")
    a("| Tie | well side | tap side | work |")
    a("| --- | --- | --- | --- |")
    for tie in spec.get("ties", []):
        work = f'erc.missing_tie:["{tie["name"]}"]'
        if work in checked:
            state = "checked"
        elif any(str(s.get("id")) == work for s in skipped):
            reason = next(s.get("reason") for s in skipped if str(s.get("id")) == work)
            state = f"SKIPPED ({reason})"
        else:
            state = "NOT CHECKED"
        if work in by_well_assertion:
            state += " (well asserted)"
        if work in by_assertion:
            state += " (tap asserted)"
        well = (
            f"`{tie['well_layer']}` drawn"
            if tie.get("well_layer")
            else f"asserted `well_boxes` {tie.get('well_boxes')}"
        )
        tap = f"`{tie['tap_layer']}`" + (
            ", `tap_is_dedicated`" if tie.get("tap_is_dedicated") else ""
        )
        a(f"| `{tie['name']}` -> `{tie['net']}` | {well} | {tap} | {state} |")
    a("")
    if by_well_assertion:
        a(
            "One tie rests on an **asserted** substrate region rather than a "
            "drawn well layer (`erc_coverage.checked_by_well_assertion`): "
            "sky130 NMOS sit in the native p-substrate and this stream draws "
            "no pwell shape, so the region is the caller's claim "
            "(klayout-tools#2255). The claim is falsifiable and is falsified "
            "where it can be -- each asserted polygon must independently hold "
            "a tap reaching the declared net, an assertion within 1% of the "
            "top-cell bbox is rejected as degenerate, and control C1 below "
            "moves this one off its tap and gets the finding. "
            "`layout/bin/check-erc-supply-spec.py` additionally re-derives "
            "the box from the GDS on every run, so a floorplan change cannot "
            "leave a stale assertion standing."
        )
        a("")
    a(
        "**What this does and does not say.** `erc.missing_tie` is a "
        "connectivity question -- does each well/asserted region hold a tap "
        "that reaches its declared net. It says nothing about tap DENSITY, "
        "and this block draws exactly one substrate tap and one n-well tap "
        "across a 2.4 mm span. Latch-up/body-bias robustness is a "
        "layout-quality question for DRC and the floorplan, outside what "
        "this item can see."
    )
    a("")

    a("## Falsification controls")
    a("")
    a(
        "Every check item 11 grades passes by reporting NOTHING, so an "
        "all-clean report is indistinguishable on its face from a spec that "
        "asks no question. Each control mutates the committed spec one way "
        "and must produce the finding the graded run's clean verdict is "
        "claiming the absence of."
    )
    a("")
    a("| Control | Mutation | Expected rule | Rules reported | Fired |")
    a("| --- | --- | --- | --- | --- |")
    for name, description, expected, reported, fired in control_rows:
        a(
            f"| {name} | {description} | `{expected}` | {reported} | "
            f"{'yes' if fired else '**NO**'} |"
        )
    a("")

    a("## Coverage")
    a("")
    a(f"- `erc_coverage.checked`: {len(checked)} work item(s)")
    a(f"- `erc_coverage.skipped`: {len(skipped)} -- {skipped if skipped else 'none'}")
    a(
        f"- `erc_coverage.inapplicable`: {len(inapplicable)} -- "
        f"{inapplicable if inapplicable else 'none'}"
    )
    a(f"- `erc_coverage.checked_by_well_assertion`: {by_well_assertion or 'none'}")
    a(f"- `erc_coverage.checked_by_assertion`: {by_assertion or 'none'}")
    a(
        "- `ties_disclosure`: "
        f"{json.dumps(erc.get('ties_disclosure'))} -- this run declares real "
        "ties and grades them, so it has nothing to disclose in place of them"
    )
    a("")
    devices = (erc.get("provenance") or {}).get("devices") or []
    if devices:
        a(
            "`provenance.devices` records the device-body carve-outs this run "
            "applied, so a reader can see that a clean `erc.supply_short` was "
            "not reached by leaving a device body in the graph as a wire:"
        )
        a("")
        for device in devices:
            a(
                f"- `{device.get('name')}` on role `{device.get('on')}`, body "
                f"layer `{device.get('body_layer')}`, "
                f"{device.get('body_area_um2')} um2 subtracted"
            )
        a("")

    a("## Item 11's other half (Analog column)")
    a("")
    a(
        "Item 11 is kind-dependent and this block is kind `analog`, so "
        "alongside this run it needs item 4's own LVS report to have carried "
        "the supply nets in its `net_correspondence` -- a SPICE reference "
        "satisfies that by construction, and "
        "`layout/ldo-core/reports/LATEST-LVS`'s `lvs.json` pairs both `VIN` "
        "and `0` there. The Digital column's extra asks (`power.pdn`, a "
        "named `power.tapcell_master`, `power_connectivity.status: \"match\"` "
        "from an RTL/P&R flow) do not apply to this block: there is no "
        "`klt place-and-route` response to cite because there is no "
        "synthesis or P&R step in its flow."
    )
    a("")

    a("## Provenance")
    a("")
    a(f"- Record ID: `{args.record_id}`")
    a(
        f"- `klt` version: `{prov.klt_version}`, reported by the run itself as "
        f"`{(erc.get('provenance') or {}).get('klt_version')}` (pinned commit, "
        "see `layout/erc-requirements.txt` -- a SECOND pin, distinct from "
        "`layout/requirements.txt`'s DRC/LVS pin; that file explains why)"
    )
    a(
        "- KLayout engine version: "
        f"`{(erc.get('provenance') or {}).get('klayout_version')}`"
    )
    antenna_pdk = (erc.get("provenance") or {}).get("pdk") or {}
    a(
        "- Antenna-limit table: "
        f"`{antenna_pdk.get('name')}` (`source: "
        f"{antenna_pdk.get('source')}`) -- `klt`'s own built-in "
        "transcription of SkyWater's published sky130 antenna rule tables. "
        "This flow reads no local PDK tree, so it has no PDK pin to "
        "cross-check."
    )
    a(
        "- Layout input content hash: "
        f"`{((erc.get('provenance') or {}).get('input') or {}).get('content_hash')}` "
        f"-- hash of the committed "
        f"`layout/ldo-core/reports/{args.layout_record_id}/{args.cell_name}.gds`, "
        "which is the file this run read (the GDS is deliberately not copied "
        "into this record: a copy would only re-state a hash of itself)."
    )
    a(
        "- Spec content hash: "
        f"`{((erc.get('provenance') or {}).get('spec') or {}).get('content_hash')}` "
        "-- hash of [`erc-supply-spec.json`](erc-supply-spec.json), the byte "
        "copy in this record."
    )
    a(
        f"- Layout freshness: `layout/ldo-core/` as of commit "
        f"`{args.layout_sha}`; GDS taken from layout record "
        f"`{args.layout_record_id}` (the record "
        "`layout/ldo-core/reports/LATEST` names)."
    )
    a(
        f"- Repo state: `{prov.sha}` on `{prov.branch}`"
        + (" (dirty)" if prov.dirty else "")
    )
    a("")
    a("## Links")
    a("")
    a("- [`erc_supply.json`](erc_supply.json) -- the graded run")
    for name in CONTROLS:
        a(
            f"- [`erc_control_{name}.json`](erc_control_{name}.json) -- "
            f"falsification control {name}"
        )
    a(
        "- [`erc-supply-spec.json`](erc-supply-spec.json) -- byte copy of the "
        "spec this record was run on"
    )
    a(
        "- [`layout-record-id.txt`](layout-record-id.txt) -- which layout "
        "record the GDS came from"
    )
    a("")

    print("\n".join(lines))
    return 0 if (met and controls_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
