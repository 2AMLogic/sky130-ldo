#!/usr/bin/env python3
"""Issue #704 paired dynamic-response campaign: baseline vs #692 rev2 candidate.

Supplies the dynamic-response evidence for the #702 rev2 adoption review:
loop-gain stability (42-condition tt/27C/3.30V grid per DUT over the DR-002
C_out/ESR window and the light-load band), the 1<->50 mA load step over the
six-condition C_out/ESR window grid at the load-transient manifest's own
quick_subset PVT points, and PSRR at 1 kHz/100 kHz at 1 mA and 50 mA over the
psrr-dc manifest's full 45-point PVT matrix. One pinned production schematic
revision (`design/ldo_3v3in_1v8out.sch`) is netlisted once per bench; the
candidate copy gets `apply_candidate(raw, 2)` from the #692 campaign's
committed candidate module (NTAIL 7 um / 2 fingers) and every paired deck is
required to pass `check_candidate(raw, edited)` with an empty problem list.
Bench stimulus, compensation and settings are otherwise identical between the
two DUTs of every pair. All multi-corner evidence goes through
`klt sim --backend batch` (no local fallback); the only local ngspice runs are
the single-corner syntax/debug probes. This is a diagnostic under
`sim/loop-gain/diagnostics/`: no records/ entry is minted, no production file
changes, the ratified spec rows are quoted, never re-targeted.

Bench routes (each the validated adapter for its bench):
  loop   sim/loop-gain via the fc fleet-campaign request pattern
         (sim/bin/bias-retopo-pvt.py / sim/bin/rcz-shelf-691.py): per leg one
         single-AC request, COUT/HESR/RLOAD rewritten as netlist edits, loop
         gain recovered from the ELG_DEN probe VCVS as klt transfer metrics;
         plus one op-gate request per DUT whose 7 reset op-steps (one per
         load) record the DC bias each AC leg linearizes around.
  psrr   sim/psrr-dc via the bias-retopo-pvt psrr pattern: per (load, supply)
         one 3-point `ac lin 3 1e3 1e5` request (15 corners each), PSRR read
         as -.meas vdb(vout) at 1e3/1e5; plus one op-gate request per supply.
         The bench's own load network (C_out 1 uF / ESR 10 mOhm) is left at
         its netlisted values.
  loadstep  sim/load-transient via corner-run.py's own batch backend and the
         #326 window-grid adapter (sim/bin/batch_window_grid.py): one
         single-step tran request per (leg, quick corner). The candidate's
         deck drops the three `.ic` tokens that name nodes the overlay
         removes (EA_TAIL/EA_D1/EA_D2); the other eight seed tokens are
         byte-identical and the vout_pre gate (1.764-1.836 V) still proves
         each transient starts on the regulating branch.
  loop-decoupled  the issue's loop-gain extraction check for rev2's
         VREF-driven bias: selected worst legs re-run with XM_VRF's gate
         moved to an internal DC-1.2 V / AC-0 source (VVREFB), so the VREF
         injection reaches the loop only through the input pair -- the same
         single-entry condition the extraction's derivation assumes. Near-
         crossing agreement between the as-drawn and decoupled margins is
         the check; disagreement flags the affected margins unresolved.

Usage (see commands.sh for the as-executed order):
    python3 campaign.py syntax-probe
    python3 campaign.py loop base|rev2
    python3 campaign.py loop-decoupled <leg>...
    python3 campaign.py psrr base|rev2
    python3 campaign.py loadstep base|rev2
    python3 campaign.py analyze
"""
from __future__ import annotations

import argparse
import difflib
import importlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../sim/loop-gain/diagnostics/issue-704
SIM = HERE.parents[2]
REPO = SIM.parent
sys.path.insert(0, str(SIM / "bin"))
sys.path.insert(0, str(SIM / "dropout-vs-load" / "diagnostics" / "issue-692-20261120-235900"))
import _fleet_campaign as fc  # noqa: E402
import _probe_common as pc  # noqa: E402
from _corner_model import detect_solver_diagnostic  # noqa: E402
from _record_common import is_finite_number  # noqa: E402

cr = pc.load_corner_run()
cand = importlib.import_module("candidate")  # the #692 committed overlay module
CANDIDATE_PY = Path(cand.__file__).resolve()

REV = 2                 # NTAIL W=7 um / nf=2 (the #692 evidence-driven revision)
DUT_SHA_PATHS = (       # provenance: the design + benches + pins this campaign pins
    "design/ldo_3v3in_1v8out.sch",
    "sim/loop-gain/testbench",
    "sim/load-transient/testbench",
    "sim/psrr-dc/testbench",
    "sim/pdk.json",
    "sim/xschemrc",
)

# The loop-gain grid the issue's acceptance table fixes: tt / 27 C / 3.30 V,
# loads {0,10,30,100,300 uA, 1 mA, 50 mA} x C_out {0.33,4.7 uF} x ESR {0,10m,500m}.
VSUP = 3.30
LOOP_CORNER = [("tt", 27.0)]
LOADS = {
    "0mA": "1e12",
    "10uA": "180k",
    "30uA": "60k",
    "100uA": "18k",
    "300uA": "6k",
    "1mA": "1800",
    "50mA": "36",
}
LOOP_CAP = {"c033": "0.33u", "c47": "4.7u"}
LOOP_ESR = {"esr0": 0.0, "esr10m": 0.01, "esr500m": 0.5}
VOUT_OP_MIN, VOUT_OP_MAX = 1.62, 1.98   # loop-gain bench's seeded VOUT gate (1.8 V +/-10%)
PSRR_LOADS = {"1ma": "1.8k", "50ma": "36"}
PSRR_MEAS = [("p1k", 1e3, 50.0), ("p100k", 1e5, 20.0)]
PSRR_SUPPLIES = [2.97, 3.30, 3.63]
LOADSTEP_QUICK = [("tt", 27.0, 3.3), ("ss", -40.0, 2.97), ("ff", 125.0, 3.63)]
# The three .ic tokens naming nodes the rev2 overlay removes (load-transient bench).
IC_STALE = re.compile(r"v\(xldo\.(EA_TAIL|EA_D1|EA_D2)\)=\S+", re.I)

MECH = (
    "Paired baseline-vs-rev2 dynamic-response evidence for #702: rev2 is the #692 overlay "
    "(NMOS-input OTA + VREF-referenced bias, NTAIL W=7 um nf=2) applied to the pinned "
    "production schematic's netlist copy; compensation (C_COMP 150 pF, XR_CZ 0.42x52 um "
    "xhigh_po) is byte-identical in both DUTs of every pair."
)


# ---------------------------------------------------------------- provenance
def git_clean_check() -> str:
    sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
    ).strip()
    subprocess.run(
        ["git", "diff", "--quiet", sha, "--", *DUT_SHA_PATHS], cwd=REPO, check=True
    )
    return sha


def sha(b: bytes) -> str:
    return pc.sha(b)


def comp_cards(body: str) -> dict[str, str]:
    """The DUT compensation cards a paired deck must share (proof, not assumption)."""
    out = {}
    for name in ("C_COMP", "XR_CZ"):
        hits = [ln for ln in body.splitlines() if ln.split(" ")[0].upper() == name]
        if len(hits) != 1:
            raise SystemExit(f"expected exactly one {name} card, found {len(hits)}")
        out[name] = hits[0]
    return out


def variant_body_fc(tb: str, variant: str, outdir: Path) -> tuple[str, str, dict]:
    """Netlist bench `tb` once; return (raw, edited, provenance dict).

    `edited` is the candidate copy (`apply_candidate(raw, REV)`) when variant
    is `rev2`, else the untouched raw body. The overlay's preservation checks
    must return an empty list or nothing runs.
    """
    _pdk, pdk_root, _env = fc.preamble(1, outdir, allow_existing=True)
    raw = fc.netlist(tb, outdir, pdk_root)
    if variant == "base":
        return raw, raw, {"variant": "base", "notes": [], "problems": []}
    if variant != "rev2":
        raise SystemExit(f"unknown variant {variant!r}")
    edited, notes = cand.apply_candidate(raw, REV)
    problems = cand.check_candidate(raw, edited)
    if problems:
        raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    return raw, edited, {"variant": f"rev{REV}", "notes": notes, "problems": problems}


def deck(body: str, vsup: float) -> str:
    """Wrap a netlist body as a runnable deck at supply `vsup` (fc.deck's
    structure, this campaign's own banner: these requests are new, so there
    is no committed-record byte parity to preserve)."""
    return (
        f"* issue #704 paired dynamic-response bench (baseline vs rev2)\n"
        f".param vsup={vsup}\n.option wnflag=1\n{body}.end\n"
    )


def loadstep_bodies(variant: str, pdk) -> tuple[str, str, dict]:
    """Netlist the load-transient bench once; apply the rev2 overlay (plus the
    minimal .ic adaptation) to the candidate copy."""
    exp = cr.load_experiment(SIM / "load-transient")
    with tempfile.TemporaryDirectory(prefix="i704-nl-") as nl:
        net = cr.netlist_with_xschem(exp.schematic, Path(nl), pdk)
        raw = "\n".join(cr.netlist_body(net)) + "\n"
    if variant == "base":
        return raw, raw, {"variant": "base", "notes": [], "problems": [],
                          "ic_adaptation": None}
    edited, notes = cand.apply_candidate(raw, REV)
    problems = cand.check_candidate(raw, edited)
    if problems:
        raise SystemExit("candidate invariant check failed: " + "; ".join(problems))
    # Drop only the .ic tokens naming nodes the overlay removes; ngspice
    # refuses the WHOLE .ic card once any named node is gone (measured).
    lines = []
    for ln in edited.splitlines():
        if ln.startswith(".ic "):
            ln = IC_STALE.sub("", ln)
            while "  " in ln:
                ln = ln.replace("  ", " ")
            ln = ln.rstrip()
        lines.append(ln)
    return raw, "\n".join(lines) + "\n", {
        "variant": f"rev{REV}", "notes": notes, "problems": problems,
        "ic_adaptation": ("dropped .ic tokens v(xldo.EA_TAIL), v(xldo.EA_D1), "
                          "v(xldo.EA_D2) (nodes the rev2 overlay removes; ngspice "
                          "rejects the whole .ic card otherwise); the other eight "
                          "seed tokens are byte-identical"),
    }


def decouple_bias(text: str) -> str:
    """Rev2 extraction-check edit: XM_VRF's gate moves from VREF (the bench's
    AC-1 injection node) to an internal VREFB held at DC 1.2 V / AC 0, so the
    injected disturbance reaches the loop only through the input pair, exactly
    the single-entry condition the loop-gain derivation assumes."""
    old = "XM_VRF PBR VREF NVR 0 "
    new = "XM_VRF PBR VREFB NVR 0 "
    if text.count(old) != 1 or text.count(new.rstrip()) != 0:
        raise SystemExit("XM_VRF gate card not in expected form for the decoupling edit")
    text = text.replace(old, new, 1)
    text = fc.insert_in_subckt(text, "VVREFB VREFB 0 DC 1.2 AC 0")
    return text


def fc_provenance(tb: str, raw: str, edited: str, prov: dict) -> dict:
    return {
        **prov,
        "bench": tb,
        "dut_sch_sha256": sha((REPO / "design" / "ldo_3v3in_1v8out.sch").read_bytes()),
        "testbench_sha256": sha(
            (SIM / tb.replace("tb_", "").replace("_", "-") / "testbench" / f"{tb}.sch").read_bytes()
        ),
        "experiment_json_sha256": sha(
            (SIM / tb.replace("tb_", "").replace("_", "-") / "experiment.json").read_bytes()
        ),
        "candidate_py": str(CANDIDATE_PY.relative_to(REPO)),
        "candidate_py_sha256": sha(CANDIDATE_PY.read_bytes()),
        "netlist_raw_sha256": sha(raw.encode()),
        "netlist_edited_sha256": sha(edited.encode()),
        "compensation_cards": comp_cards(edited),
    }


# ------------------------------------------------------------------ requests
def ohms(text: str) -> float:
    return float(text[:-1]) * 1e3 if text.endswith("k") else float(text)


def write_request(out: Path, key: str, body: str, corners, shape, vsup: float) -> tuple[str, Path]:
    pdk = json.loads((SIM / "pdk.json").read_text())
    net = out / "requests" / f"{key}.spice"
    net.parent.mkdir(parents=True, exist_ok=True)
    net.write_text(deck(body, vsup))
    req = fc.base_request(net.resolve(), pdk, corners, shape=shape)
    path = net.with_suffix(".json")
    path.write_text(json.dumps(req, indent=2) + "\n")
    return key, path


def op_steps(loads: dict[str, str]) -> list[dict]:
    return [
        {
            "name": "op_" + load,
            "reset": True,
            "analysis": {"kind": "op", "args": ""},
            "alter": {"RLOAD": ohms(r)},
            "measurements": [{"name": "vout", "expr": "v(vout)", "unit": "V"}],
        }
        for load, r in loads.items()
    ]


def loop_jobs(out: Path, body: str) -> list[tuple[str, Path]]:
    probed = fc.insert_loop_gain_probe(body)
    shape = {
        "analysis": {"kind": "ac", "args": "dec 30 1e-2 1e9"},
        "measurements": fc.LOOP_TRANSFER_MEAS,
    }
    jobs = []
    for cap, cv in LOOP_CAP.items():
        for en, ev in LOOP_ESR.items():
            for load, lr in LOADS.items():
                key = f"loop-{cap}-{en}-{load}"
                b = fc.sub_line(probed, "COUT", f"COUT VOUT VESR {cv} m=1")
                b = fc.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {ev:g}")
                b = fc.sub_line(b, "RLOAD", f"RLOAD VOUT 0 {lr} m=1")
                jobs.append(write_request(out, key, b, LOOP_CORNER, shape, VSUP))
    jobs.append(
        write_request(
            out,
            "op-gate",
            fc.sub_line(probed, "RLOAD", "RLOAD VOUT 0 1800 m=1"),
            LOOP_CORNER,
            {"analysis_steps": op_steps(LOADS)},
            VSUP,
        )
    )
    return jobs


def psrr_jobs(out: Path, body: str) -> list[tuple[str, Path]]:
    meas = [
        {"name": n, "spice": f".meas ac {n} find vdb(vout) at={f:g}"} for n, f, _ in PSRR_MEAS
    ]
    jobs = []
    for v in PSRR_SUPPLIES:
        corners = [(p, t) for p in fc.PROCESS for t in (-40.0, 27.0, 125.0)]
        for load, r in PSRR_LOADS.items():
            key = f"psrr-{load}-v{v:.2f}"
            b = fc.sub_line(body, "RLOAD", f"RLOAD VOUT 0 {r} m=1")
            jobs.append(
                write_request(
                    out, key, b, corners,
                    {"analysis": {"kind": "ac", "args": "lin 3 1e3 1e5"}, "measurements": meas},
                    v,
                )
            )
        jobs.append(
            write_request(
                out, f"op-gate-v{v:.2f}", body, corners,
                {"analysis_steps": op_steps(PSRR_LOADS)}, v,
            )
        )
    return jobs


def loop_decoupled_jobs(out: Path, body: str, legs: list[str]) -> list[tuple[str, Path]]:
    decoupled = fc.insert_loop_gain_probe(decouple_bias(body))
    shape = {
        "analysis": {"kind": "ac", "args": "dec 30 1e-2 1e9"},
        "measurements": fc.LOOP_TRANSFER_MEAS,
    }
    jobs = []
    for leg in legs:
        cap, en, load = leg.split("-", 2)
        key = f"decoupled-{cap}-{en}-{load}"
        b = fc.sub_line(decoupled, "COUT", f"COUT VOUT VESR {LOOP_CAP[cap]} m=1")
        b = fc.sub_line(b, "HESR", f"HESR VESRS 0 VESRSENSE {LOOP_ESR[en]:g}")
        b = fc.sub_line(b, "RLOAD", f"RLOAD VOUT 0 {LOADS[load]} m=1")
        jobs.append(write_request(out, key, b, LOOP_CORNER, shape, VSUP))
    return jobs


def submit(jobs: list[tuple[str, Path]], out: Path, env: dict, workers: int) -> dict:
    errors: list[dict] = []
    list(fc.submit_all([(k, {}, p) for k, p in jobs], out, env, workers, errors))
    return {e["key"]: e["error"] for e in errors}


# --------------------------------------------------------------- fc grading
def response(out: Path, key: str) -> dict:
    path = out / "responses" / key / "klt.stdout"
    if path.exists() and path.stat().st_size:
        try:
            data = json.loads(path.read_text())
        except ValueError:
            return {"reason": "invalid klt response JSON"}
        if isinstance(data, dict):
            return data
    return {}


def corner_data(resp: dict, process: str, temp: float):
    job = resp.get("environment", {}).get("remote", {}).get("job_id")
    matches = [
        c for c in resp.get("corners", [])
        if (c.get("process"), c.get("temperature_c")) == (process, temp)
    ]
    if len(matches) != 1:
        return {}, job, resp.get("reason") or ("duplicate corner" if matches else "missing corner")
    return matches[0], job, None if job else "missing fleet job ID"


def measurements(corner: dict) -> dict:
    values = {}
    for m in corner.get("measurements", []):
        name, v = m["name"], m.get("value")
        values[name] = (
            v if name not in values and m.get("status") == "pass" and is_finite_number(v) else None
        )
    return values


def solver_reason(corner: dict):
    for diag in corner.get("diagnostics", []):
        line = detect_solver_diagnostic(str(diag.get("message", "")))
        if line:
            return f"solver diagnostic: {line}"
    return None


def transfer_row(resp: dict, process: str, temp: float) -> dict:
    c, job, reason = corner_data(resp, process, temp)
    values = measurements(c)
    reason = reason or solver_reason(c)
    for diag in c.get("diagnostics", []):
        if diag.get("severity") == "error":
            reason = reason or diag.get("message") or diag.get("code") or "error diagnostic"
    if c.get("status") not in ("pass", "fail"):
        reason = reason or f"corner {c.get('status')}"
    row = {n: values.get(n) for n in ("pm", "gm", "fc", "dc")}
    missing = [n for n, v in row.items() if v is None]
    if missing:
        reason = reason or f"missing or invalid {', '.join(missing)}"
    row.update(job_id=job, reason=reason)
    return row


def op_gate(out: Path, key_prefix: str, load: str, process: str, temp: float):
    """Why the DC bias a psrr/loop AC point linearized around is not a
    regulating state, or None. Keys tried: `<key_prefix>` (single request)."""
    resp = response(out, key_prefix)
    c, _job, reason = corner_data(resp, process, temp)
    if reason:
        return f"operating point: {reason}"
    reason = solver_reason(c)
    if reason:
        return f"operating point {reason}"
    vout = measurements(c).get(f"op_{load}.vout")
    if vout is None:
        return "operating point: missing VOUT"
    if not VOUT_OP_MIN <= vout <= VOUT_OP_MAX:
        return f"operating point: non-regulating VOUT {vout:.3f} V"
    return None


# ------------------------------------------------------- local syntax probes
def build_local_deck(body: str, ctl: str, vsup: float, process: str = "tt",
                     temp_c: float = 27.0) -> str:
    pdk = cr.resolve_pdk(cr.load_pin())
    return (
        f"* issue #704 local single-corner syntax probe (not campaign evidence)\n"
        f".param vsup={vsup}\n.option wnflag=1\n.temp {temp_c:g}\n"
        f'.lib "{pdk.lib_file}" {process}\n'
        f"{body}.control\n{ctl}\n.endc\n.end\n"
    )


def run_probe(tag: str, deck_text: str) -> dict:
    out = HERE / "runs" / "syntax-probe" / tag
    if (out / "result.json").exists():
        print(tag, "already probed (append-only): skipped")
        return json.loads((out / "result.json").read_text())
    if out.exists():
        raise SystemExit(f"{out} exists without result.json: append-only")
    out.mkdir(parents=True)
    (out / "deck.spice").write_text(deck_text)
    (out / ".spiceinit").write_text((SIM / "spiceinit").read_text())
    log, elapsed, rcode = pc.run_ngspice_deck(out, timeout=900)
    (out / "ngspice.log").write_text(log)
    cards = {}
    for m in re.finditer(r"^\s*(meas_)?([A-Za-z_0-9.]+)\s*=\s*([-0-9.eE+]+)", log, re.M):
        cards[m.group(2)] = float(m.group(3))
    rec = {
        "tag": tag, "ngspice_exit": rcode, "elapsed_s": round(elapsed, 1),
        "solver_diagnostic": cr.detect_solver_diagnostic(log),
        "cards": cards,
        "deck_sha256": sha(deck_text.encode()),
        "source_commit": pc.git_provenance(REPO),
    }
    (out / "result.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    keep = {k: v for k, v in cards.items()
            if k in ("fc", "phc", "gmdb", "dcg", "p1k", "p100k", "vseed", "v_pre")}
    print(tag, "exit", rcode, json.dumps(keep), "n_cards", len(cards))
    return rec


LOOP_PROBE_CTL = """save all
set units=degrees
op
let vseed = v(vout)
print vseed
ac dec 30 1e-2 1e9
let lg = v(xldo.fb)/(1-v(xldo.fb))
let lgdb = db(lg)
let lgph = cph(lg)
meas ac fc when lgdb=0 cross=1
meas ac phc find lgph when lgdb=0 cross=1
meas ac gmdb find lgdb when lgph=-180 cross=1
let dcg = lgdb[0]
print dcg
"""

PSRR_PROBE_CTL = """save all
op
let vseed = v(vout)
print vseed
ac lin 3 1e3 1e5
let p1k = -vdb(vout)[0]
let p100k = -vdb(vout)[2]
print p1k p100k
"""


def syntax_probe() -> None:
    """ONE local ngspice -b per (bench, variant): the loop-gain bench at its
    0.33 uF / 10 mOhm / 50 mA leg, the psrr bench at 1 mA, and the load-step
    bench at one corner with the manifest's own deck. Validates the candidate
    decks (and the .ic adaptation) before anything is submitted."""
    scratch = HERE / "runs" / "syntax-probe"
    scratch.mkdir(parents=True, exist_ok=True)
    for bench, tb in (("loop", "tb_loop_gain"), ("psrr", "tb_psrr_dc")):
        raw, edited, prov = variant_body_fc(tb, "rev2", scratch)
        (scratch / f"{tb}.raw.spice").write_text(raw)
        (scratch / f"{tb}.rev2.spice").write_text(edited)
        (scratch / f"{tb}.rev2.diff").write_text("".join(difflib.unified_diff(
            raw.splitlines(True), edited.splitlines(True), "raw", "rev2")))
        print(f"{tb}: check_candidate problems={prov['problems']} notes={len(prov['notes'])}")
        for name, body in (("base", raw), ("rev2", edited)):
            b = body
            if bench == "loop":
                b = fc.sub_line(b, "RLOAD", "RLOAD VOUT 0 36 m=1")
                ctl = LOOP_PROBE_CTL
            else:
                b = fc.sub_line(b, "RLOAD", "RLOAD VOUT 0 1.8k m=1")
                ctl = PSRR_PROBE_CTL
            run_probe(f"{bench}-{name}", build_local_deck(b, ctl, VSUP))
    # load-transient: the manifest's own deck (all six legs, one corner)
    pdk = cr.resolve_pdk(cr.load_pin())
    exp = cr.load_experiment(SIM / "load-transient")
    raw, edited, prov = loadstep_bodies("rev2", pdk)
    (scratch / "tb_load_transient.raw.spice").write_text(raw)
    (scratch / "tb_load_transient.rev2.spice").write_text(edited)
    (scratch / "tb_load_transient.rev2.diff").write_text("".join(difflib.unified_diff(
        raw.splitlines(True), edited.splitlines(True), "raw", "rev2")))
    print(f"tb_load_transient: check_candidate problems={prov['problems']} "
          f"notes={len(prov['notes'])} ic_adaptation={bool(prov['ic_adaptation'])}")
    for name, body in (("base", raw), ("rev2", edited)):
        deck_text = cr.build_deck(exp, pdk, cr.Corner("tt", 27.0, 3.3), body.splitlines())
        run_probe(f"loadstep-{name}", deck_text)


# ------------------------------------------------------------- batch stages
def fc_stage(bench: str, variant: str, jobs_fn, extra: dict | None = None) -> int:
    out = HERE / "runs" / bench / variant
    tb = {"loop": "tb_loop_gain", "psrr": "tb_psrr_dc"}[bench]
    _pdk, _root, env = fc.preamble(WORKERS, out)   # refuses an existing record dir
    out.mkdir(parents=True)
    sha_head = git_clean_check()
    raw, edited, prov = variant_body_fc(tb, variant, out)
    (out / "netlist.raw.spice").write_text(raw)
    (out / "netlist.edited.spice").write_text(edited)
    if variant == "rev2":
        (out / "netlist.diff").write_text("".join(difflib.unified_diff(
            raw.splitlines(True), edited.splitlines(True), "netlist.raw.spice", "netlist.edited.spice")))
    meta = {
        "bench": bench, **fc_provenance(tb, raw, edited, prov),
        "head": sha_head, "klt": subprocess.check_output(["klt", "--version"], text=True).strip(),
        "mechanism": MECH, "errors": {},
    }
    if extra:
        meta.update(extra)
    (out / "provenance.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    jobs = jobs_fn(out, edited if variant == "rev2" else raw)
    meta["errors"] = submit(jobs, out, env, WORKERS)
    (out / "provenance.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
    print(f"[{bench}/{variant}] {len(jobs)} requests, {len(meta['errors'])} submit failures")
    return 1 if meta["errors"] else 0


def loadstep_stage(variant: str) -> int:
    """The load-transient window grid at the manifest's quick_subset, batch."""
    out = HERE / "runs" / "loadstep" / variant
    if out.exists():
        raise SystemExit(f"{out} exists: append-only")
    pdk = cr.resolve_pdk(cr.load_pin())
    pin = cr.load_pin()
    sha_head = git_clean_check()
    exp = cr.load_experiment(SIM / "load-transient")
    raw, edited, prov = loadstep_bodies(variant, pdk)
    body = edited.splitlines()
    out.mkdir(parents=True)
    (out / "netlist.raw.spice").write_text(raw)
    (out / "netlist.edited.spice").write_text(edited)
    if variant == "rev2":
        (out / "netlist.diff").write_text("".join(difflib.unified_diff(
            raw.splitlines(True), edited.splitlines(True), "netlist.raw.spice", "netlist.edited.spice")))
    matrix = [cr.Corner(p, float(t), float(v)) for p, t, v in LOADSTEP_QUICK]
    prepared = cr.prepare_batch_requests(exp, pdk, matrix, True, body, out, 300)
    results, logs, execution = cr.run_batch(exp, pdk, pin, prepared, matrix, out, 300, False)
    rec = {
        "bench": "load-transient", "variant": variant,
        "candidate_rev": REV if variant == "rev2" else None,
        "matrix": [[c.process, c.temp_c, c.supply_v] for c in matrix],
        "corner_ids": [c.id for c in matrix],
        "results": results, "execution": execution,
        "provenance": {
            "head": sha_head,
            "source_commit": pc.git_provenance(REPO),
            "driver_sha256": sha(Path(__file__).read_bytes()),
            **fc_provenance("tb_load_transient", raw, edited, prov),
            "pdk": {"open_pdks_commit": pdk.installed_commit, "matches_pin": pdk.matches_pin,
                    "lib_sha256": sha(Path(pdk.lib_file).read_bytes())},
            "tools": cr.tool_versions(),
        },
    }
    (out / "leg.json").write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n")
    for cid, text in logs.items():
        (out / "logs").mkdir(exist_ok=True)
        (out / "logs" / f"{cid}.log").write_text(text)
    n_pass = sum(1 for r in results if r["pass"])
    print(f"[loadstep/{variant}] {n_pass}/{len(results)} corners harness-pass; "
          f"jobs: {', '.join(str(r.get('job_id')) for r in execution['requests'])}")
    return 0


WORKERS = 2


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["syntax-probe", "loop", "loop-decoupled", "psrr",
                                     "loadstep", "analyze"])
    ap.add_argument("variant", nargs="?", choices=["base", "rev2"])
    ap.add_argument("--legs", nargs="*", help="loop-decoupled: cap-esr-load legs, e.g. c033-esr10m-0mA")
    a = ap.parse_args()
    if a.mode == "syntax-probe":
        syntax_probe()
        return 0
    if a.mode == "loop":
        assert a.variant
        return fc_stage("loop", a.variant, loop_jobs)
    if a.mode == "psrr":
        assert a.variant
        return fc_stage("psrr", a.variant, psrr_jobs)
    if a.mode == "loadstep":
        assert a.variant
        return loadstep_stage(a.variant)
    if a.mode == "loop-decoupled":
        if not a.legs:
            raise SystemExit("loop-decoupled needs --legs")
        out = HERE / "runs" / "loop" / "rev2-decoupled"
        _pdk, _root, env = fc.preamble(WORKERS, out)   # refuses an existing record dir
        out.mkdir(parents=True)
        sha_head = git_clean_check()
        _raw, edited, prov = variant_body_fc("tb_loop_gain", "rev2", out)
        decoupled = decouple_bias(edited)
        (out / "netlist.rev2.spice").write_text(edited)
        (out / "netlist.rev2-decoupled.spice").write_text(decoupled)
        (out / "netlist.decoupled.diff").write_text("".join(difflib.unified_diff(
            edited.splitlines(True), decoupled.splitlines(True),
            "netlist.rev2.spice", "netlist.rev2-decoupled.spice")))
        meta = {
            "bench": "loop", "variant": f"rev{REV}-decoupled",
            **fc_provenance("tb_loop_gain", _raw, edited, prov),
            "head": sha_head,
            "klt": subprocess.check_output(["klt", "--version"], text=True).strip(),
            "mechanism": MECH,
            "extraction_check": (
                "XM_VRF gate moved to internal VREFB (DC 1.2 V, AC 0): the VREF injection "
                "then enters the loop only through the input pair, the single-entry "
                "condition the loop-gain derivation assumes for baseline"),
            "legs": a.legs, "errors": {},
        }
        (out / "provenance.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        meta["errors"] = submit(loop_decoupled_jobs(out, edited, a.legs), out, env, WORKERS)
        (out / "provenance.json").write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n")
        print(f"[loop/rev2-decoupled] {len(a.legs)} requests, {len(meta['errors'])} failures")
        return 1 if meta["errors"] else 0
    if a.mode == "analyze":
        raise SystemExit("analyze lives in analyze.py")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
