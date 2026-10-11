#!/usr/bin/env python3
"""Issue #357 physical dropout candidate: netlist-level transformation of the DUT.

Bench copies only -- design/ldo_3v3in_1v8out.sch is never touched. The candidate
is applied to the xschem netlist of any repo testbench that instantiates the DUT
subcircuit `ldo_3v3in_1v8out`. Every removed or rewired card is matched against
its exact, committed baseline text (EXPECTED below); a missing, duplicated or
drifted card is a hard error, never a silent partial edit.

Candidate (joint change, both halves always applied together):

  A. Low-headroom error amplifier. The PMOS-input pair (gate common mode
     VREF = 1.2 V, so the PMOS tail needs VIN >~ 1.2 + |Vgs_p| + Vdsat ~ 2.6 V at
     tt/27 C) is replaced by an NMOS-input symmetrical OTA whose tail sits BELOW
     the input common mode (NTAIL ~ VREF - Vgs_n), so its compliance no longer
     depends on VIN at all; the PMOS loads only need VIN >~ |Vgs_p| + ~0.45 V.
     The tail is biased from a VREF-referenced V-to-I (not from the VIN-scaled
     R_BIAS), so its current is ~VIN-independent.
       FB side  : XM_NIN1 (gate FB)  in series with XM_NIN1C (gate VIN, matching device)
                  -> PMOS diode XM_PD1 -> XM_PO1 pulls EA_OUT UP
       REF side : XM_NIN2 (gate VREF) in series with XM_NIN2S (gate SS, soft-start)
                  -> PMOS diode XM_PD2 -> XM_PO2 -> NMOS diode XM_NMD -> XM_NMO pulls EA_OUT DOWN
     Soft-start: with NMOS inputs, a parallel SS device would select max(VREF, SS);
     a SERIES SS device starves the reference side while SS < VREF, so the loop
     tracks ~min(VREF, SS) as the PMOS-pair parallel device did. XM_NIN1C (gate
     VIN) mirrors that series device on the FB side (both are triode switches once
     SS has charged to ~VIN).
  B. Re-referenced current-limit clamp. XM_CLP (the comparator's reference
     current source) keeps its drain/source/geometry but its gate moves from the
     VIN-scaled BIASP to PBR, the PMOS diode of the VREF-referenced V-to-I, so the
     clamp threshold stays put as VIN falls instead of collapsing with R_BIAS.
     XM_PBR is a copy of XM_BIASP1's geometry, so at 3.3 V the reference current
     is set to ~XM_BIASP1's baseline current (the 3.3 V trip point is preserved,
     not re-targeted).
  C. (rev 1 only) EN-low pull-ups XM_ENP6 (PBR) and XM_ENP7 (ND2), copies of XM_ENP5,
     so every new PMOS gate node is defined when disabled -- the committed design's own
     pattern (XM_ENP2/ENP3/ENP4/ENP5/ENP). See REV for the rev1 bias re-sizing.

Untouched (verified by check_candidate): XM_PASS (geometry and connections), every
external port, R_BIAS/NB/BIASP chain, XM_SENSE/XM_CLN1/XM_CLN2/XM_CLIM/XM_ENP3/C_CL,
the whole thermal-shutdown block, XM_TSHUT, soft-start (XM_SSCHG/XM_SSDIS/C_SS),
EN gating (XM_ENN/XM_ENN2/XM_ENP/XM_ENP2/XM_ENP4/XM_INVP/XM_INVN), C_COMP/R_CZ, divider.
XM_ENP5 keeps its role (EN-low pull-up of the output-stage PMOS mirror gate) on the
renamed gate node ND1. VREF only drives gates (no DC current); every new branch
returns to the EN-gated pseudo-ground AMP_ENN and is powered from VIN.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "bin"))
import _probe_common as pc  # noqa: E402

SUBCKT_HEAD = ".subckt ldo_3v3in_1v8out VOUT VREF EN VIN"
NF = "sky130_fd_pr__nfet_g5v0d10v5"
PF = "sky130_fd_pr__pfet_g5v0d10v5"
_C = "\n+ nrd={n} nrs={n} sa=0 sb=0 sd=0 mult=1 m=1"

# Exact committed baseline text of every card the candidate removes or rewires.
EXPECTED = {
    "XM_TAIL": 'XM_TAIL EA_TAIL BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=40 nf=8 ad=5.8\n+ as=7.25 pd=42.32 ps=52.9\n+ nrd=0.00725 nrs=0.00725 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_IN1": 'XM_IN1 EA_D1 FB EA_TAIL VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_IN2": 'XM_IN2 EA_D2 VREF EA_TAIL VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_IN2S": 'XM_IN2S EA_D2 SS EA_TAIL VIN sky130_fd_pr__pfet_g5v0d10v5 L=2 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIR1": 'XM_MIR1 EA_D1 EA_D1 AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=4 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIR2": 'XM_MIR2 EA_OUT EA_D1 AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=4 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIR3": 'XM_MIR3 EA_D2 EA_D2 AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=4 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIR4": 'XM_MIR4 PB EA_D2 AMP_ENN 0 sky130_fd_pr__nfet_g5v0d10v5 L=4 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIRP1": 'XM_MIRP1 PB PB VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=4 W=20 nf=4 ad=2.9\n+ as=4.35 pd=21.16 ps=31.74\n+ nrd=0.0145 nrs=0.0145 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_MIRP2": 'XM_MIRP2 EA_OUT PB VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=4 W=20 nf=4 ad=2.9\n+ as=4.35 pd=21.16 ps=31.74\n+ nrd=0.0145 nrs=0.0145 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_ENP5": 'XM_ENP5 PB EN VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=0.5 W=2 nf=1 ad=0.58\n+ as=0.58 pd=4.58 ps=4.58\n+ nrd=0.145 nrs=0.145 sa=0 sb=0 sd=0 mult=1 m=1',
    "XM_CLP": 'XM_CLP CL_CMP BIASP VIN VIN sky130_fd_pr__pfet_g5v0d10v5 L=1 W=10 nf=2 ad=1.45\n+ as=2.9 pd=10.58 ps=21.16\n+ nrd=0.029 nrs=0.029 sa=0 sb=0 sd=0 mult=1 m=1',
}
REMOVED = ["XM_TAIL", "XM_IN1", "XM_IN2", "XM_IN2S", "XM_MIR1", "XM_MIR2", "XM_MIR3",
           "XM_MIR4", "XM_MIRP1", "XM_MIRP2"]
REWIRED = {  # name -> (old node text, new node text) on the card's FIRST physical line
    "XM_ENP5": ("XM_ENP5 PB EN VIN VIN ", "XM_ENP5 ND1 EN VIN VIN "),
    "XM_CLP": ("XM_CLP CL_CMP BIASP VIN VIN ", "XM_CLP CL_CMP PBR VIN VIN "),
}
# Cards that must survive byte-identical (pass device + protection + enable + bias).
PRESERVED = ["XM_PASS", "XM_SENSE", "XM_CLN1", "XM_CLN2", "XM_CLIM", "XM_ENP3", "C_CL",
             "XM_TSHUT", "XM_ENP4", "C_TS", "XM_TSPS", "XM_TSD1", "XM_TSD2", "XM_TSPR",
             "XM_TSR1", "XM_RCTAIL", "XM_RCN1", "XM_RCN2", "XM_RCD1", "XM_RCD2", "XM_RCC1",
             "XM_RCC2", "XM_RCEA", "XM_RCEB", "XM_RCOP", "XM_RCOS", "XM_RCEO",
             "XR_BIAS", "XM_BIASN1", "XM_BIASN2", "XM_BIASP1", "XM_ENN", "XM_ENP2",
             "XM_ENN2", "XM_ENP", "XM_INVP", "XM_INVN", "XM_SSDIS", "XM_SSCHG", "C_SS",
             "C_COMP", "XR_CZ", "XR_FB_A", "XR_FB_B", "XR_FB_C"]

# Nodes the candidate may introduce (all internal to the subcircuit).
NEW_NODES = {"PBR", "NVR", "NBR", "NTAIL", "NX1", "NX2", "ND1", "ND2", "NM"}
# Nodes allowed on the terminals of a new card besides NEW_NODES.
ALLOWED_EXISTING = {"VIN", "VREF", "FB", "SS", "EN", "EA_OUT", "AMP_ENN", "0"}
# Gate-only nodes: they may appear only on a new device's gate terminal.
GATE_ONLY = {"VREF", "FB", "SS", "EN"}


def geom(w: float, nf: int, l: float) -> str:
    """xschem's sky130 symbol geometry formulas (reproduces the committed cards,
    see the test fixture): ad/as/pd/ps from W/nf and finger parity, nrd=nrs=0.29/W."""
    wf = w / nf
    ad = int((nf + 1) / 2) * wf * 0.29
    as_ = int((nf + 2) / 2) * wf * 0.29
    pd = 2 * int((nf + 1) / 2) * (wf + 0.29)
    ps = 2 * int((nf + 2) / 2) * (wf + 0.29)
    n = 0.29 / w
    return (f"L={l:g} W={w:g} nf={nf} ad={ad:.6g}\n+ as={as_:.6g} pd={pd:.6g} ps={ps:.6g}"
            + _C.format(n=f"{n:.6g}"))


NFET_GEOM = {"L1W10": geom(10, 2, 1)}
PFET_GEOM = {"L1W10": geom(10, 2, 1)}

# Revision table: rev 0 is the derived candidate; rev 1 is the single
# evidence-driven revision the issue permits. Values are per-revision, explicit.
REV = {
    0: {"xr_vr_l": 169.0,  # from runs/sz01_vref_vi: Vs(2.1 uA)=0.288 V -> 137 kohm at ~810 ohm/um
        "pbr_w": 10.0, "pbr_nf": 2, "pbn_w": 5.0, "nbr_w": 4.0, "ntail_w": 12.0, "ntail_nf": 3,
        "en_pullups": False},
    # rev 1 -- driven by rev0 evidence only (README section 5):
    #  * iq_cand_r0_3p3: iq_full_load_ua = 30.86 uA > 30 uA (baseline 27.61 uA) -> cut the bias
    #    overhead (I_R + XM_PBN branch) from ~3.2 uA to ~1.3 uA. XM_PBR W 10 -> 2.5 so that the
    #    unchanged XM_CLP (W=10) mirrors I_R up (measured ratio ~3.0, runs/sz03_headroom_rev1,
    #    not the nominal 4) and keeps rev0's ~2.3 uA clamp reference; I_R 2.13 -> ~0.77 uA
    #    (R_VR from runs/sz01_vref_vi: Vs(0.773 uA)=0.3275 V -> 424 kohm at the 771 ohm/um
    #    measured in sz03 -> L=550 um). XM_PBN W 5 -> 1.75 (measured ~0.68 uA in sz04) into
    #    XM_NBR W=2.5, XM_NTAIL unchanged (4.8:1 -> ~3.26 uA tail, rev0 had 3.28 uA).
    #    Derivation (DC sizing benches only, all retained, none graded): sz03 (L=805: CLP
    #    1.65 uA, too low), sz04 (L=550, PBN 1.75 / NBR 2: CLP 2.37 uA ok, tail 4.10 uA too
    #    high), sz05 (PBN 1.0 / NBR 1.5: narrow-width PMOS carried 0.59 uA, tail 4.85 uA ->
    #    rejected), sz06 = confirmation of this sizing, computed from the MEASURED sz04 ratios
    #    (the NMOS tail/NBR ratio tracked W exactly in rev0, sz04 and sz05). Then locked.
    #  * en_cand_r0_3p3: singular-matrix diagnostic in the disabled (EN=0) state -> give the two
    #    new PMOS gate nodes that float when disabled (PBR, ND2) the same EN-low pull-up every
    #    PMOS gate node of the committed design has (copies of XM_ENP5's geometry).
    1: {"xr_vr_l": 550.0,
        "pbr_w": 2.5, "pbr_nf": 1, "pbn_w": 1.75, "nbr_w": 2.5, "ntail_w": 12.0, "ntail_nf": 3,
        "en_pullups": True},
}
ENP5_GEOM = "L=0.5 W=2 nf=1 ad=0.58\n+ as=0.58 pd=4.58 ps=4.58\n+ nrd=0.145 nrs=0.145 sa=0 sb=0 sd=0 mult=1 m=1"


def _rev(rev):
    if rev not in REV:
        raise ValueError(f"unknown candidate revision {rev}")
    r = REV[rev]
    if r["xr_vr_l"] is None:
        raise ValueError(f"rev{rev}: XR_VR length not yet derived")
    return r


def ntail_geom(rev):
    r = REV[rev]
    return geom(r["ntail_w"], r["ntail_nf"], 2)


def bias_cards(rev: int) -> list[str]:
    """VREF-referenced V-to-I (I_R = (VREF - Vgs(XM_VRF)) / R_VR) and its mirrors."""
    r = _rev(rev)
    return [
        f"XM_VRF PBR VREF NVR 0 {NF} " + geom(10, 2, 1),
        f"XR_VR NVR AMP_ENN 0 sky130_fd_pr__res_high_po W=0.42 L={r['xr_vr_l']:g} mult=1 m=1",
        f"XM_PBR PBR PBR VIN VIN {PF} " + geom(r["pbr_w"], r["pbr_nf"], 1),
        f"XM_PBN NBR PBR VIN VIN {PF} " + geom(r["pbn_w"], 1, 1),
        f"XM_NBR NBR NBR AMP_ENN 0 {NF} " + geom(r["nbr_w"], 1, 2),
    ]


def amp_cards(rev: int) -> list[str]:
    r = _rev(rev)
    return [
        f"XM_NTAIL NTAIL NBR AMP_ENN 0 {NF} " + ntail_geom(rev),
        f"XM_NIN1 NX1 FB NTAIL 0 {NF} " + geom(10, 2, 2),
        f"XM_NIN1C ND1 VIN NX1 0 {NF} " + geom(10, 2, 1),
        f"XM_NIN2 NX2 VREF NTAIL 0 {NF} " + geom(10, 2, 2),
        f"XM_NIN2S ND2 SS NX2 0 {NF} " + geom(10, 2, 1),
        f"XM_PD1 ND1 ND1 VIN VIN {PF} " + geom(20, 4, 4),
        f"XM_PO1 EA_OUT ND1 VIN VIN {PF} " + geom(20, 4, 4),
        f"XM_PD2 ND2 ND2 VIN VIN {PF} " + geom(20, 4, 4),
        f"XM_PO2 NM ND2 VIN VIN {PF} " + geom(20, 4, 4),
        f"XM_NMD NM NM AMP_ENN 0 {NF} " + geom(10, 2, 4),
        f"XM_NMO EA_OUT NM AMP_ENN 0 {NF} " + geom(10, 2, 4),
    ]


def enable_cards(rev: int) -> list[str]:
    if not _rev(rev)["en_pullups"]:
        return []
    return [f"XM_ENP6 PBR EN VIN VIN {PF} " + ENP5_GEOM,
            f"XM_ENP7 ND2 EN VIN VIN {PF} " + ENP5_GEOM]


def new_cards(rev: int) -> list[str]:
    return bias_cards(rev) + amp_cards(rev) + enable_cards(rev)


# ------------------------------------------------------------- transformation
def subckt_span(lines: list[str]) -> tuple[int, int]:
    heads = [i for i, ln in enumerate(lines) if ln == SUBCKT_HEAD]
    if len(heads) != 1:
        raise ValueError(f"expected exactly one '{SUBCKT_HEAD}' line, found {len(heads)}")
    s = heads[0]
    for j in range(s + 1, len(lines)):
        if lines[j].strip().lower() == ".ends":
            return s, j
    raise ValueError("DUT subcircuit has no .ends")


def card_tokens(card: str) -> list[str]:
    """Token sequence of one logical card with its `+` continuation markers removed.
    Exact at the SPICE level and independent of where the netlister wraps lines
    (xschem 3.4.4 and 3.4.7 wrap the same card differently)."""
    toks = []
    for k, ln in enumerate(card.split("\n")):
        if k and not ln.startswith("+"):
            raise ValueError("card text spans more than one logical line")
        toks += (ln[1:] if k else ln).split()
    return toks


def card_text(lines, name, lo=0, hi=None):
    """Exact text of the single card `name ` inside lines[lo:hi]; error if 0 or >1."""
    hi = len(lines) if hi is None else hi
    sub = lines[lo:hi]
    hits = [(s, e) for s, e in pc.logical_lines(sub) if sub[s].startswith(name + " ")]
    if len(hits) != 1:
        raise ValueError(f"expected exactly one card '{name}' in the DUT, found {len(hits)}")
    s, e = hits[0]
    return lo + s, lo + e, "\n".join(sub[s:e])


def apply_candidate(text: str, rev: int) -> tuple[str, list[str]]:
    """Return (edited netlist text, notes). Raises ValueError on any mismatch."""
    lines = text.splitlines()
    s, e = subckt_span(lines)
    for name in list(EXPECTED):
        _a, _b, got = card_text(lines, name, s, e)
        if card_tokens(got) != card_tokens(EXPECTED[name]):
            raise ValueError(f"card {name} does not match its committed baseline text:\n{got}")
    body = lines[s:e]
    existing_nodes = set()
    for a, b in pc.logical_lines(body):
        toks = body[a].split()
        if toks and toks[0][0] in "XxMmCcRr":
            existing_nodes.update(t.upper() for t in toks[1:5])
    clash = NEW_NODES & existing_nodes
    if clash:
        raise ValueError(f"new node names already exist in the DUT: {sorted(clash)}")
    notes = []
    out = list(lines)
    # remove (back to front so indices stay valid)
    spans = sorted((card_text(out, n, s, e)[:2] + (n,) for n in REMOVED), reverse=True)
    for a, b, n in spans:
        del out[a:b]
        notes.append(f"removed {n}")
    s, e = subckt_span(out)
    for n, (old, new) in REWIRED.items():
        a, b, _t = card_text(out, n, s, e)
        if not out[a].startswith(old):
            raise ValueError(f"{n}: expected first line to start {old!r}")
        out[a] = new + out[a][len(old):]
        notes.append(f"rewired {n}: '{old.strip()}' -> '{new.strip()}'")
    s, e = subckt_span(out)
    block = [f"* --- issue #357 candidate rev{rev}: VREF-referenced bias + NMOS-input OTA (diagnostic) ---"]
    for c in new_cards(rev):
        block += c.split("\n")
        notes.append("added " + c.split()[0])
    out[e:e] = block
    return "\n".join(out) + "\n", notes


# --------------------------------------------------------------------- checks
def _cards(lines):
    s, e = subckt_span(lines)
    body = lines[s + 1:e]
    res = {}
    for a, b in pc.logical_lines(body):
        if not body[a] or body[a].startswith("*"):
            continue
        name = body[a].split()[0]
        if name in res:
            raise ValueError(f"duplicate card {name} in DUT")
        res[name] = "\n".join(body[a:b])
    return res


def check_candidate(raw: str, edited: str) -> list[str]:
    """Structural invariants of an edited netlist vs its raw source. Returns a
    list of problems (empty = all invariants hold)."""
    p = []
    rl, el = raw.splitlines(), edited.splitlines()
    try:
        rc, ec = _cards(rl), _cards(el)
    except ValueError as ex:
        return [str(ex)]
    if el.count(SUBCKT_HEAD) != 1:
        p.append("DUT port list changed")
    for n in PRESERVED:
        if rc.get(n) is None:
            p.append(f"{n} missing from raw netlist")
        elif ec.get(n) != rc[n]:
            p.append(f"{n} not byte-identical after the edit")
    for n in REMOVED:
        if n in ec:
            p.append(f"{n} still present")
    for n, (old, new) in REWIRED.items():
        if n not in ec or not ec[n].startswith(new) or ec[n][len(new):] != rc[n][len(old):]:
            p.append(f"{n} not rewired exactly as declared")
    added = sorted(set(ec) - set(rc))
    for n in added:
        toks = ec[n].split()
        nodes = [t.upper() for t in toks[1:5]] if n.startswith("XM") else [t.upper() for t in toks[1:3]]
        for k, nd in enumerate(nodes):
            if nd in NEW_NODES:
                continue
            if nd not in ALLOWED_EXISTING:
                p.append(f"{n}: terminal node {nd} is not an allowed existing node")
            if nd in GATE_ONLY and not (n.startswith("XM") and k == 1):
                p.append(f"{n}: {nd} used on a non-gate terminal (would draw DC current)")
        if n.startswith("XM") and nodes[3] not in ("VIN", "0"):
            p.append(f"{n}: body {nodes[3]} is not VIN/0")
        if n.startswith("XM") and toks[5] not in (NF, PF):
            p.append(f"{n}: device type {toks[5]} is not a sky130 g5v0d10v5 device")
    # every new branch must be VIN-powered: a supply terminal reaching any rail other
    # than VIN / 0 / AMP_ENN is forbidden (no auxiliary rails, VREF not a supply)
    rails = set()
    for ln in el:
        if re.match(r"^[VI]\w*\s", ln) and "VINA" in ln.upper():
            rails.add("VINA")
    if rails:
        p.append("auxiliary rail present: " + ", ".join(sorted(rails)))
    return p
