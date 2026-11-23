"""Deck-delta patcher coverage for sim/bin/enp-soft-release-709.py (issue #751).

Simulator-free: the patcher and the CLI's tau-to-capacitance conversion are
pure text transforms over a synthetic deck, loaded via _sim_script_loader like
test_rcz_shelf_691.py. No ngspice, xschem, or PDK is touched.
"""

from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))
from _sim_script_loader import load_script  # noqa: E402

screen = load_script("enp_soft_release_709", SIM_DIR / "bin" / "enp-soft-release-709.py")

BODY = [
    "* synthetic deck: enp soft-release patcher (issue #751)",
    ".subckt ldo VOUT VREF EN VIN",
    "XM_ENP EA_OUT EN VIN VIN sky130_fd_pr__pfet_01v8 W=10 L=0.5",
    "+ m=1",
    # same drain and gate as the target: a prefix match would rewrite this card too
    "XM_ENP2 EA_OUT EN VIN VIN sky130_fd_pr__pfet_01v8 W=2 L=0.5 m=1",
    "XM_ENP3 EA_OUT PB VIN VIN sky130_fd_pr__pfet_01v8 W=2 L=0.5 m=1",
    "XM_ENP4 PB EN VIN VIN sky130_fd_pr__nfet_01v8 W=1 L=0.5 m=1",
    "XM_ENP5 PB EN VIN VIN sky130_fd_pr__pfet_01v8 W=2 L=0.5 m=1",
    "  XR_FB  VOUT EA_CZ  200k m=1",
    ".ends",
    ".end",
]
PATCHED = "XM_ENP EA_OUT GENP VIN VIN sky130_fd_pr__pfet_01v8 W=10 L=0.5"


def enp_expected(c_card: str) -> list[str]:
    return BODY[:2] + [PATCHED, "+ m=1", "RM_ENPS GENP EN 100000", c_card] + BODY[4:]


class Patcher(unittest.TestCase):
    def test_base_returns_the_body_unchanged(self):
        self.assertEqual(screen.variant_body(BODY, "base", 1e-9), BODY)

    def test_enp_rewrites_only_the_target_gate(self):
        out = screen.variant_body(BODY, "enp", 1e-9)
        self.assertEqual(out, enp_expected("CM_ENPS GENP VIN 1e-09"))

    def test_enp_keeps_the_continuation_attached_and_orders_the_rc_cards(self):
        out = screen.variant_body(BODY, "enp", 1e-9)
        i = out.index(PATCHED)
        self.assertEqual(out[i + 1], BODY[3])
        self.assertEqual(out[i + 2], "RM_ENPS GENP EN 100000")
        self.assertEqual(out[i + 3], "CM_ENPS GENP VIN 1e-09")
        self.assertEqual(out[i + 4], BODY[4])


class Cli(unittest.TestCase):
    def test_tau_us_converts_to_capacitance_on_the_emitted_deck(self):
        bodies = {}

        def fake_run_corner(exp, pdk, corner, body, run_dir, log_path, timeout):
            bodies[corner.id] = list(body)
            return {
                "measurements": [],
                "ramp_monotonicity": [
                    {"leg": "leg0", "max_drawdown_v": 1e-4, "status": "PASS", "reasons": []}
                ],
                "pass": True,
                "ngspice_exit": 0,
            }

        exp = types.SimpleNamespace(raw={}, schematic=Path("dut.sch"))
        with tempfile.TemporaryDirectory() as tmp:
            spiceinit = Path(tmp) / "spiceinit"
            spiceinit.write_text("* synthetic spiceinit\n")
            with (
                mock.patch.object(screen.cr, "load_pin", return_value={}),
                mock.patch.object(screen.cr, "resolve_pdk", return_value=object()),
                mock.patch.object(screen.cr, "load_experiment", return_value=exp),
                mock.patch.object(
                    screen.cr, "window_legs", return_value=[{"id": "leg0", "cout_f": 1e-6}]
                ),
                mock.patch.object(
                    screen.cr, "netlist_with_xschem", return_value=Path(tmp) / "netlist.spice"
                ),
                mock.patch.object(screen.cr, "netlist_body", return_value=list(BODY)),
                mock.patch.object(screen.cr, "run_corner", side_effect=fake_run_corner),
                mock.patch.object(screen, "BUILD_DIR", Path(tmp) / "build"),
                mock.patch.object(screen, "SPICEINIT_FILE", spiceinit),
                redirect_stdout(io.StringIO()),
            ):
                rc = screen.main(
                    ["--variants", "enp", "--corners", "tt", "--tau-us", "300"]
                )
        self.assertEqual(rc, 0)
        self.assertEqual(list(bodies), ["tt_27c_3.30v"])
        self.assertEqual(
            bodies["tt_27c_3.30v"], enp_expected("CM_ENPS GENP VIN 3e-09")
        )


if __name__ == "__main__":
    unittest.main()
