#!/usr/bin/env python3
"""Issue #705 paired analysis: tables/*.csv + verdict.json over the six
campaign legs (startup/line/load x base/cand) and the two MC legs.

Classification convention (the issue's verdict deliverable): for every paired
condition the baseline outcome and the rev2 outcome are compared as

  both-pass            both DUTs meet the check
  inherited-fail       baseline fails, rev2 fails the same way (not a regression)
  improvement          baseline fails, rev2 passes
  regression           baseline passes, rev2 fails
  invalid              either side has no trustworthy measurement for the check

The startup grid keeps the two verdict axes the historic campaign separated:
the ELECTRICAL axis (vpk_v <= 1.836 V, vfloor_v >= 1.764 V, tramp_ms present)
and the strict 0 V ramp-monotonicity verdict -- the earlier record
(20261117-221657-efb6bd6b) reported electrical passes and strict monotonicity
failures on all 540 legs, so the two are never merged into one pass/fail.

Expected-vs-observed accounting is emitted for every bench so a missing trace,
leg or draw is visible: 45 corners x 12 legs = 540 startup conditions per DUT,
45 corners per regulation DUT, 200 draws per MC DUT.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "runs"
TABLES = HERE / "tables"
STARTUP_LEGS = [f"{c}_{l}_esr{e}" for c in ("c330n", "c4u7") for l in ("0ma", "50ma")
                for e in ("0", "10m", "500m")]
NAMED_CASES = {
    "ss/125C/3.30V @ 50 mA": ("ss_125c_3.30v", [l for l in STARTUP_LEGS if "_50ma_" in l]),
    "ff/27C/2.97V @ no load": ("ff_27c_2.97v", [l for l in STARTUP_LEGS if "_0ma_" in l]),
}


def load_leg(name: str) -> dict:
    return json.loads((RUNS / name / "leg.json").read_text())


def meas(result: dict, name: str) -> dict | None:
    for c in result.get("measurements", []):
        if c["name"] == name:
            return c
    return None


def ramp_leg(result: dict, leg: str) -> dict | None:
    for tr in result.get("ramp_monotonicity") or []:
        if tr.get("leg") == leg:
            return tr
    return None


def classify(base_pass: bool | None, cand_pass: bool | None) -> str:
    if base_pass is None or cand_pass is None:
        return "invalid"
    if base_pass and cand_pass:
        return "both-pass"
    if not base_pass and not cand_pass:
        return "inherited-fail"
    if not base_pass and cand_pass:
        return "improvement"
    return "regression"


def startup_axis(r: dict, leg: str) -> dict:
    """Electrical axis values for one (corner, leg): peak, floor, ramp time,
    each with its own pass/fail; plus the strict ramp verdict. Per-leg
    measurements carry the merged `<base>__<leg>` name."""
    out = {"vpk": None, "vfloor": None, "tramp_ms": None,
           "vpk_pass": None, "vfloor_pass": None, "tramp_present": None}
    for c in r.get("measurements", []):
        if c["name"] == f"vpk_v__{leg}":
            out["vpk"], out["vpk_pass"] = c.get("value"), c.get("pass")
        elif c["name"] == f"vfloor_v__{leg}":
            out["vfloor"], out["vfloor_pass"] = c.get("value"), c.get("pass")
        elif c["name"] == f"tramp_ms__{leg}":
            out["tramp_ms"] = c.get("value")
            out["tramp_present"] = c.get("value") is not None
    tr = ramp_leg(r, leg)
    out["ramp_drawdown_v"] = tr.get("max_drawdown_v") if tr else None
    out["ramp_pass"] = tr.get("pass") if tr else None
    out["electrical_pass"] = (
        None if None in (out["vpk_pass"], out["vfloor_pass"], out["tramp_present"])
        else bool(out["vpk_pass"] and out["vfloor_pass"] and out["tramp_present"]))
    return out


def startup_pair() -> dict:
    base = {r["corner_id"]: r for r in load_leg("startup-base")["results"]}
    cand = {r["corner_id"]: r for r in load_leg("startup-cand")["results"]}
    corners = sorted(base)
    rows, counts = [], {"electrical": {}, "ramp": {}}
    elec_pairs, ramp_pairs = [], []
    ext = {"base": {"vpk": [], "vfloor": [], "tramp": []}, "cand": {"vpk": [], "vfloor": [], "tramp": []}}
    for cid in corners:
        supply = base[cid]["supply_v"]
        for leg in STARTUP_LEGS:
            b, c = startup_axis(base[cid], leg), startup_axis(cand[cid], leg)
            e_cls = classify(b["electrical_pass"], c["electrical_pass"])
            r_cls = classify(b["ramp_pass"], c["ramp_pass"])
            counts["electrical"][e_cls] = counts["electrical"].get(e_cls, 0) + 1
            counts["ramp"][r_cls] = counts["ramp"].get(r_cls, 0) + 1
            elec_pairs.append((cid, leg, e_cls))
            ramp_pairs.append((cid, leg, r_cls))
            for v, store in ((b, "base"), (c, "cand")):
                if v["vpk"] is not None:
                    ext[store]["vpk"].append((v["vpk"], cid, leg))
                if v["vfloor"] is not None:
                    ext[store]["vfloor"].append((v["vfloor"], cid, leg))
                if v["tramp_ms"] is not None:
                    ext[store]["tramp"].append((v["tramp_ms"], cid, leg))
            rows.append({
                "corner": cid, "supply_v": supply, "leg": leg,
                "base_vpk_v": b["vpk"], "base_vfloor_v": b["vfloor"],
                "base_tramp_ms": b["tramp_ms"], "base_ramp_drawdown_v": b["ramp_drawdown_v"],
                "base_electrical": b["electrical_pass"], "base_ramp": b["ramp_pass"],
                "cand_vpk_v": c["vpk"], "cand_vfloor_v": c["vfloor"],
                "cand_tramp_ms": c["tramp_ms"], "cand_ramp_drawdown_v": c["ramp_drawdown_v"],
                "cand_electrical": c["electrical_pass"], "cand_ramp": c["ramp_pass"],
                "electrical_class": e_cls, "ramp_class": r_cls,
                "vout_above_vin_base": bool(b["vpk"] is not None and b["vpk"] > supply),
                "vout_above_vin_cand": bool(c["vpk"] is not None and c["vpk"] > supply),
            })
    TABLES.mkdir(exist_ok=True)
    with (TABLES / "startup_pair.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    def worst(store, key, pick=max):
        vals = ext[store][key]
        if not vals:
            return None
        v, cid, leg = pick(vals, key=lambda t: t[0])
        return {"value": v, "corner": cid, "leg": leg}
    named = {}
    for label, (cid, legs) in NAMED_CASES.items():
        entry = {}
        for store, leg_rec in (("base", base), ("cand", cand)):
            vals = [startup_axis(leg_rec[cid], l) for l in legs] if cid in leg_rec else []
            entry[store] = {
                "vpk_max": max((v["vpk"] for v in vals if v["vpk"] is not None), default=None),
                "vfloor_min": min((v["vfloor"] for v in vals if v["vfloor"] is not None), default=None),
                "tramp_max_ms": max((v["tramp_ms"] for v in vals if v["tramp_ms"] is not None), default=None),
                "electrical_pass": ([v["electrical_pass"] for v in vals] or [None]),
                "ramp_drawdown_max_v": max((v["ramp_drawdown_v"] for v in vals if v["ramp_drawdown_v"] is not None), default=None),
            }
        named[label] = entry
    return {
        "expected_conditions_per_dut": len(corners) * len(STARTUP_LEGS),
        "observed_conditions_per_dut": len(rows),
        "corners": len(corners),
        "legs_per_corner": len(STARTUP_LEGS),
        "classification_counts": counts,
        "electrical_regressions": [f"{cid}/{leg}" for cid, leg, cl in elec_pairs if cl == "regression"],
        "ramp_regressions": [f"{cid}/{leg}" for cid, leg, cl in ramp_pairs if cl == "regression"],
        "electrical_improvements": [f"{cid}/{leg}" for cid, leg, cl in elec_pairs if cl == "improvement"],
        "extrema": {s: {"max_vpk": worst(s, "vpk"), "min_vfloor": worst(s, "vfloor", min),
                        "max_tramp_ms": worst(s, "tramp")} for s in ("base", "cand")},
        "vout_above_vin": {
            "base": [f"{cid}/{leg}" for cid, leg, vb, _vc in
                     ((r["corner"], r["leg"], r["vout_above_vin_base"], r["vout_above_vin_cand"]) for r in rows) if vb],
            "cand": [f"{cid}/{leg}" for cid, leg, _vb, vc in
                     ((r["corner"], r["leg"], r["vout_above_vin_base"], r["vout_above_vin_cand"]) for r in rows) if vc],
        },
        "named_cases": named,
    }


RUN_PREFIX = {"line-regulation": "line", "load-regulation": "load"}


def regulation_pair(bench: str) -> dict:
    pfx = RUN_PREFIX[bench]
    base = {r["corner_id"]: r for r in load_leg(f"{pfx}-base")["results"]}
    cand = {r["corner_id"]: r for r in load_leg(f"{pfx}-cand")["results"]}
    corners = sorted(base)
    keys = [c["name"] for c in base[corners[0]]["measurements"]]
    rows, classes = [], {}
    extrema = {k: {"base": [], "cand": []} for k in keys}
    for cid in corners:
        row = {"corner": cid}
        for k in keys:
            b, c = meas(base[cid], k), meas(cand[cid], k)
            bp = b.get("pass") if b and b.get("value") is not None else None
            cp = c.get("pass") if c and c.get("value") is not None else None
            cls = classify(bp, cp)
            classes[k] = classes.get(k, {})
            classes[k][cls] = classes[k].get(cls, 0) + 1
            row[f"base_{k}"] = b.get("value") if b else None
            row[f"cand_{k}"] = c.get("value") if c else None
            row[f"class_{k}"] = cls
            if b and b.get("value") is not None:
                extrema[k]["base"].append((b["value"], cid))
            if c and c.get("value") is not None:
                extrema[k]["cand"].append((c["value"], cid))
        rows.append(row)
    TABLES.mkdir(exist_ok=True)
    with (TABLES / f"{bench}_pair.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    # supply-axis identity check: on line-regulation 'vsup' is a pure label
    identity = None
    if bench == "line-regulation":
        identity = {"columns_expected_identical": True}
        for k in keys:
            by_pt = {}
            for row in rows:
                pt = row["corner"].rsplit("_", 1)[0]
                by_pt.setdefault(pt, []).append(row[f"base_{k}"])
            if any(len({repr(v) for v in vals}) != 1 for vals in by_pt.values()):
                identity["columns_expected_identical"] = False
    return {
        "expected_corners_per_dut": 45,
        "observed_corners_per_dut": len(rows),
        "checks": keys,
        "classification_counts": classes,
        "regressions": {k: [r["corner"] for r in rows if r[f"class_{k}"] == "regression"]
                        for k in keys},
        "worst": {k: {s: (max(extrema[k][s], key=lambda t: abs(t[0])) if extrema[k][s] else None)
                      for s in ("base", "cand")} for k in keys},
        **({"supply_axis_identity_check": identity} if identity else {}),
    }


def mc_pair() -> dict:
    out = {}
    for v in ("base", "cand"):
        leg = load_leg(f"mc-{v}")
        a = leg["analysis"]
        out[v] = {
            "attempted": leg["provenance"]["n"],
            "returned": a["returned_samples"],
            "valid": a["valid_samples"],
            "in_window": a["in_window"],
            "out_of_window": a["out_of_window"],
            "violations": a["violations"],
            "errored_or_missing": a["errored_or_missing"],
            "stats": a["stats"],
            "seed": leg["provenance"]["seed"],
            "klt_status": leg["aggregate"]["status"],
        }
    b, c = out["base"], out["cand"]
    out["same_seed"] = b["seed"] == c["seed"]
    out["pair_verdict"] = {
        "base_window_violations": b["out_of_window"],
        "cand_window_violations": c["out_of_window"],
        "base_invalid": b["attempted"] - b["valid"],
        "cand_invalid": c["attempted"] - c["valid"],
    }
    return out


def main() -> None:
    TABLES.mkdir(exist_ok=True)
    verdict = {
        "issue": 705,
        "pinned_commit": load_leg("startup-base")["provenance"]["source_commit"],
        "benches": {
            "startup": startup_pair(),
            "line-regulation": regulation_pair("line-regulation"),
            "load-regulation": regulation_pair("load-regulation"),
            "mc-output-accuracy": mc_pair(),
        },
    }
    (HERE / "verdict.json").write_text(json.dumps(verdict, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: (v if k == "pinned_commit" else "ok") for k, v in verdict.items()}))
    s = verdict["benches"]["startup"]
    print(f"startup: {s['observed_conditions_per_dut']}/{s['expected_conditions_per_dut']} conditions; "
          f"electrical {s['classification_counts']['electrical']}; "
          f"ramp {s['classification_counts']['ramp']}")
    for bench in ("line-regulation", "load-regulation"):
        r = verdict["benches"][bench]
        n_reg = sum(len(v) for v in r["regressions"].values())
        print(f"{bench}: {r['observed_corners_per_dut']} corners; "
              f"{n_reg} check regressions total")
    mc = verdict["benches"]["mc-output-accuracy"]
    print(f"mc: base {mc['base']['valid']}/{mc['base']['attempted']} valid "
          f"({mc['base']['out_of_window']} out-of-window), "
          f"cand {mc['cand']['valid']}/{mc['cand']['attempted']} valid "
          f"({mc['cand']['out_of_window']} out-of-window)")


if __name__ == "__main__":
    main()
