"""Unit coverage for sim/bin/corner-run.py's pure helper functions.

PDK-free by design (no ngspice/xschem/volare required) so this runs on every
`npm run check:ci` invocation, including in CI where the sky130 PDK is not
installed -- see sim/selftest.sh stage 1/3.

corner-run.py is loaded by file path (not `import corner_run`) because the
CLI convention keeps the hyphenated `corner-run.py` filename, matching the
sibling sky130-bandgap repo's harness.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SIM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SIM_DIR / "bin"))  # corner-run.py imports _record_common (issue #46)
_spec = importlib.util.spec_from_file_location("corner_run", SIM_DIR / "bin" / "corner-run.py")
corner_run = importlib.util.module_from_spec(_spec)
sys.modules["corner_run"] = corner_run
_spec.loader.exec_module(corner_run)


class TestCornerId(unittest.TestCase):
    def test_id_format(self):
        c = corner_run.Corner(process="tt", temp_c=27.0, supply_v=1.8)
        self.assertEqual(c.id, "tt_27c_1.80v")

    def test_id_negative_temp(self):
        c = corner_run.Corner(process="ss", temp_c=-40.0, supply_v=1.62)
        self.assertEqual(c.id, "ss_-40c_1.62v")

    def test_id_non_integer_temp(self):
        c = corner_run.Corner(process="ff", temp_c=27.5, supply_v=1.98)
        self.assertEqual(c.id, "ff_27.5c_1.98v")


class TestFmtTemp(unittest.TestCase):
    def test_integer_temp_has_no_trailing_zero(self):
        self.assertEqual(corner_run.fmt_temp(125.0), "125")

    def test_negative_temp(self):
        self.assertEqual(corner_run.fmt_temp(-40.0), "-40")


class TestUniqueInOrder(unittest.TestCase):
    def test_dedupes_preserving_first_occurrence_order(self):
        self.assertEqual(
            corner_run.unique_in_order(["tt", "ss", "tt", "ff", "ss"]),
            ["tt", "ss", "ff"],
        )

    def test_empty(self):
        self.assertEqual(corner_run.unique_in_order([]), [])


class TestParseMeasurements(unittest.TestCase):
    def test_parses_meas_lines(self):
        log = "\n".join(
            [
                "some ngspice banner text",
                "meas_vgs = 6.306570e-01",
                "meas_isup = 1.169340e-06",
                "trailing noise",
            ]
        )
        self.assertEqual(
            corner_run.parse_measurements(log),
            {"vgs": 0.630657, "isup": 1.16934e-06},
        )

    def test_ignores_non_measurement_lines(self):
        self.assertEqual(corner_run.parse_measurements("no measurements here"), {})

    def test_handles_negative_values(self):
        log = "meas_delta = -3.5e-02"
        self.assertEqual(corner_run.parse_measurements(log), {"delta": -0.035})


class TestSignalName(unittest.TestCase):
    def test_known_signal(self):
        self.assertEqual(corner_run.signal_name(9), "SIGKILL")

    def test_unknown_signal_number(self):
        self.assertEqual(corner_run.signal_name(999), "signal 999")


class TestExitNote(unittest.TestCase):
    def test_timeout_note(self):
        note = corner_run.exit_note(-1, timed_out=True, killed_by_signal=None)
        self.assertIn("TIMEOUT", note)

    def test_signal_note(self):
        note = corner_run.exit_note(-9, timed_out=False, killed_by_signal=9)
        self.assertIn("SIGKILL", note)
        self.assertIn("OUTSIDE the harness", note)

    def test_clean_exit_has_no_note(self):
        self.assertEqual(corner_run.exit_note(0, timed_out=False, killed_by_signal=None), "")


class TestCsvHelpers(unittest.TestCase):
    def test_csv_list_strips_whitespace(self):
        self.assertEqual(corner_run.csv_list(" tt, ss ,ff"), ["tt", "ss", "ff"])

    def test_csv_floats(self):
        self.assertEqual(corner_run.csv_floats("1.62,1.8,1.98"), [1.62, 1.8, 1.98])


class TestDetectSolverDiagnostic(unittest.TestCase):
    """issue #171: corner-run.py must recognize an ngspice solver-diagnostic
    line rather than grading the corner as if the solve converged cleanly.
    See sim/README.md's "Initial-condition contract" for the three marker
    forms and why they were chosen."""

    def test_detects_singular_matrix(self):
        log = "\n".join(
            ["Note: starting op", "Warning: singular matrix:  check node xldo.ea_cz", "done"]
        )
        self.assertEqual(
            corner_run.detect_solver_diagnostic(log),
            "Warning: singular matrix:  check node xldo.ea_cz",
        )

    def test_detects_dynamic_gmin_stepping_failed(self):
        log = "Warning: Dynamic gmin stepping failed"
        self.assertEqual(corner_run.detect_solver_diagnostic(log), log)

    def test_detects_true_gmin_stepping_failed(self):
        log = "Warning: True gmin stepping failed"
        self.assertEqual(corner_run.detect_solver_diagnostic(log), log)

    def test_detects_out_of_range_for_caret(self):
        log = "Error: 3.683e+157, 2 out of range for ^"
        self.assertEqual(corner_run.detect_solver_diagnostic(log), log)

    def test_clean_log_returns_none(self):
        log = "\n".join(
            [
                "Circuit: * pdk-smoke corner deck",
                "meas_vgs = 6.306570e-01",
                "meas_isup = 1.169340e-06",
            ]
        )
        self.assertIsNone(corner_run.detect_solver_diagnostic(log))

    def test_empty_text_returns_none(self):
        self.assertIsNone(corner_run.detect_solver_diagnostic(""))

    def test_unrelated_out_of_range_form_is_not_matched(self):
        # A fourth ngspice error shape ("out of range for -") seen in some
        # committed logs is a deliberately-not-yet-matched form -- see
        # sim/README.md's "Initial-condition contract" for why the marker
        # set is these three confirmed forms and not a broader catalog.
        log = "Error: inf, -inf out of range for -"
        self.assertIsNone(corner_run.detect_solver_diagnostic(log))

    def test_against_real_committed_diagnostic_log(self):
        # sim/line-regulation/corners/20260925-114251-1f54ca6/ff_-40c_2.97v.log
        # is a real corner-run.py-produced log carrying the exact "singular
        # matrix" fingerprint issue #171 was filed against (issue #171,
        # acceptance criterion 4: verify against existing committed
        # artifacts rather than a fresh matrix re-run).
        log_path = (
            SIM_DIR
            / "line-regulation"
            / "corners"
            / "20260925-114251-1f54ca6"
            / "ff_-40c_2.97v.log"
        )
        text = log_path.read_text()
        diagnostic = corner_run.detect_solver_diagnostic(text)
        self.assertIsNotNone(diagnostic)
        self.assertIn("singular matrix", diagnostic)

    def test_against_real_committed_clean_log(self):
        # sim/pdk-smoke/corners/20260814-000938-42bbf2e/ff_-40c_1.62v.log is a
        # real corner-run.py-produced log with no solver diagnostic -- the
        # known-clean case issue #171's acceptance criterion 4 asks for.
        log_path = (
            SIM_DIR / "pdk-smoke" / "corners" / "20260814-000938-42bbf2e" / "ff_-40c_1.62v.log"
        )
        text = log_path.read_text()
        self.assertIsNone(corner_run.detect_solver_diagnostic(text))


def _fixture_experiment_and_pdk():
    """A run_corner()-shaped fixture: no PDK, no ngspice, no manifest on disk."""
    exp = corner_run.Experiment(
        dir=SIM_DIR / "pdk-smoke",  # any real dir; not read by run_corner itself
        raw={
            "slug": "test-solver-diagnostic",
            "claim": "unit test fixture",
            "schematic": "testbench/tb_pdk_smoke.sch",
            "corners": {},
            "measurements": [],
            "deck": {},
        },
    )
    exp.measurements = [
        corner_run.Measurement(name="vout", expr="v(vout)", unit="V", min=1.0, max=2.0)
    ]
    pdk = corner_run.Pdk(
        pin={},
        root=Path("/tmp/pdk-root"),
        variant="sky130A",
        dir=Path("/tmp/pdk-root/sky130A"),
        installed_commit="deadbeef",
        lib_file=Path("/tmp/pdk-root/sky130A/libs.tech/combined/sky130.lib.spice"),
    )
    corner = corner_run.Corner(process="tt", temp_c=27.0, supply_v=1.8)
    return exp, pdk, corner


def _run_corner_with_fake_ngspice(stdout: str, stderr: str = "", spiceinit: str | None = None):
    """Drive run_corner() against a stubbed ngspice, returning (result, log_text).

    `spiceinit`, when given, is written to `.spiceinit` in the scratch run
    directory first -- mirroring what main() does before the corner loop
    (`shutil.copyfile(SPICEINIT_FILE, run_dir / ".spiceinit")`).
    """
    exp, pdk, corner = _fixture_experiment_and_pdk()
    fake_proc = subprocess.CompletedProcess(
        args=["ngspice", "-b"], returncode=0, stdout=stdout, stderr=stderr
    )
    # run_corner() computes log_path.relative_to(REPO_ROOT) for the
    # returned record, so the scratch dir must live under REPO_ROOT.
    with tempfile.TemporaryDirectory(dir=corner_run.REPO_ROOT) as td:
        run_dir = Path(td)
        if spiceinit is not None:
            (run_dir / ".spiceinit").write_text(spiceinit)
        log_path = run_dir / "corner.log"
        with mock.patch.object(corner_run.subprocess, "run", return_value=fake_proc):
            result = corner_run.run_corner(exp, pdk, corner, [], run_dir, log_path, 60)
        log_text = log_path.read_text()
    return result, log_text


class TestRunCornerSolverDiagnostic(unittest.TestCase):
    """issue #171: run_corner() must force a corner to FAIL when ngspice
    emits a solver diagnostic, regardless of whether its measurements happen
    to pass their bounds, with a reason distinct from an ordinary
    measurement-bound failure -- and must not disturb the log's raw
    stdout/stderr."""

    def _run(self, stdout: str, stderr: str = ""):
        return _run_corner_with_fake_ngspice(stdout, stderr)

    def test_diagnostic_forces_fail_even_when_measurement_passes(self):
        stdout = (
            "meas_vout = 1.500000e+00\n"
            "Warning: singular matrix:  check node xldo.ea_cz\n"
        )
        result, log_text = self._run(stdout)

        # The measurement itself is within [1.0, 2.0] ...
        self.assertTrue(result["measurements"][0]["pass"])
        # ... but the corner must still FAIL, because of the diagnostic.
        self.assertFalse(result["pass"])
        self.assertEqual(
            result["solver_diagnostic"],
            "Warning: singular matrix:  check node xldo.ea_cz",
        )
        # Raw ngspice stdout/stderr is still shown unchanged in the log.
        self.assertIn("Warning: singular matrix:  check node xldo.ea_cz", log_text)
        self.assertIn("meas_vout = 1.500000e+00", log_text)
        self.assertIn("# result: FAIL", log_text)

    def test_no_diagnostic_leaves_verdict_on_measurement_bounds(self):
        stdout = "meas_vout = 1.500000e+00\n"
        result, log_text = self._run(stdout)

        self.assertTrue(result["pass"])
        self.assertIsNone(result["solver_diagnostic"])
        self.assertIn("# result: PASS", log_text)

    def test_diagnostic_reason_not_overwritten_by_measurement_bound_failure(self):
        # A corner whose measurement is ALSO out of bounds, and which ALSO
        # emits a diagnostic -- both reasons must be independently visible,
        # not one silently replacing the other.
        stdout = "meas_vout = 9.000000e+00\nWarning: Dynamic gmin stepping failed\n"
        result, _log_text = self._run(stdout)

        self.assertFalse(result["pass"])
        self.assertFalse(result["measurements"][0]["pass"])
        self.assertEqual(result["measurements"][0]["reason"], "above max 2")
        self.assertEqual(result["solver_diagnostic"], "Warning: Dynamic gmin stepping failed")


class TestCornerLogRecordsSpiceinit(unittest.TestCase):
    """issue #190: the deck is only half of what ngspice was given -- it also
    reads `.spiceinit` from the run directory, and `option klu` in there
    decides whether a corner emits a singular-matrix diagnostic at all. A
    corner log must therefore record that second input and must not claim the
    deck alone is the "exact input"."""

    SPICEINIT = "* test settings\nset ngbehavior=hsa\noption klu\n"

    def test_log_embeds_the_spiceinit_that_was_in_the_run_directory(self):
        _result, log_text = self._run_with_spiceinit()
        self.assertIn("# ==== .spiceinit (2nd input:", log_text)
        for line in self.SPICEINIT.splitlines():
            self.assertIn(f"| {line}", log_text)

    def test_log_records_the_spiceinit_hash(self):
        _result, log_text = self._run_with_spiceinit()
        digest = hashlib.sha256(self.SPICEINIT.encode("utf-8")).hexdigest()
        self.assertIn(f"# sha256: {digest}", log_text)

    def test_embedded_hash_tracks_the_file_contents(self):
        # A different `.spiceinit` must produce a different recorded hash --
        # i.e. the record reflects the settings this run actually used, not a
        # constant baked into the runner.
        _r1, log_a = self._run_with_spiceinit()
        _r2, log_b = _run_corner_with_fake_ngspice(
            "meas_vout = 1.500000e+00\n", spiceinit=self.SPICEINIT + "option noklu\n"
        )
        hash_a = re.search(r"# sha256: ([0-9a-f]{64})", log_a).group(1)
        hash_b = re.search(r"# sha256: ([0-9a-f]{64})", log_b).group(1)
        self.assertNotEqual(hash_a, hash_b)

    def test_missing_spiceinit_is_recorded_as_missing_not_silently_omitted(self):
        _result, log_text = _run_corner_with_fake_ngspice("meas_vout = 1.500000e+00\n")
        self.assertIn("# ==== .spiceinit (2nd input:", log_text)
        self.assertIn("NOT PRESENT", log_text)

    def test_deck_header_does_not_claim_to_be_the_whole_input(self):
        _result, log_text = self._run_with_spiceinit()
        self.assertNotIn("exact input given to ngspice", log_text)
        self.assertIn("# ==== deck (1st input:", log_text)

    def test_log_tells_the_reader_how_to_reproduce_the_corner(self):
        _result, log_text = self._run_with_spiceinit()
        self.assertIn("ngspice -b tt_27c_1.80v.spice", log_text)
        self.assertIn("`.spiceinit` in the SAME directory", log_text)

    def test_real_repo_spiceinit_is_what_the_provenance_block_hashes(self):
        prov = corner_run.spiceinit_provenance()
        self.assertEqual(prov["spiceinit_file"], "sim/spiceinit")
        self.assertEqual(
            prov["spiceinit_sha256"],
            hashlib.sha256((SIM_DIR / "spiceinit").read_bytes()).hexdigest(),
        )

    def test_rendered_record_names_the_solver_config(self):
        record = _minimal_record()
        record["tools"].update(corner_run.spiceinit_provenance())
        md = corner_run.render_record(record)
        self.assertIn("ngspice init settings", md)
        self.assertIn(record["tools"]["spiceinit_sha256"], md)

    def test_rendered_record_survives_a_pre_190_record_without_the_field(self):
        # Records minted before #190 carry no spiceinit fields; re-rendering
        # one must not crash (sim/ is append-only -- old records stay as-is).
        md = corner_run.render_record(_minimal_record())
        self.assertNotIn("ngspice init settings", md)

    def _run_with_spiceinit(self):
        return _run_corner_with_fake_ngspice(
            "meas_vout = 1.500000e+00\n", spiceinit=self.SPICEINIT
        )


def _minimal_record() -> dict:
    """The smallest record dict render_record() accepts (no spiceinit fields)."""
    return {
        "record_id": "20260101-000000-abcdef0",
        "timestamp": "2026-01-01T00:00:00Z",
        "author": "unit-test",
        "supersedes": "",
        "experiment": {
            "slug": "unit-test",
            "title": "unit test fixture",
            "claim": "none",
            "provenance": "schematic",
            "provenance_source": "sim/pdk-smoke/testbench/tb_pdk_smoke.sch",
            "statistical_convention": "N/A",
        },
        "pdk": {
            "root": "/tmp/pdk-root",
            "variant": "sky130A",
            "installed_commit": "deadbeef",
            "pinned_commit": "deadbeef",
            "matches_pin": True,
            "lib_file": "/tmp/pdk-root/sky130A/libs.tech/combined/sky130.lib.spice",
        },
        "tools": {
            "ngspice": "ngspice-44",
            "xschem": "xschem 3.4.5",
            "platform": "Linux 6.0 x86_64",
            "python": "3.11.0",
        },
        "git": {"sha": "abcdef0", "branch": "main", "dirty": False},
        "matrix": {
            "process": ["tt"],
            "temperature_c": [27.0],
            "supply_v": [1.8],
            "n_points": 1,
            "is_subset": False,
            "subset_reason": "",
            "points": [["tt", 27.0, 1.8]],
            "point_ids": ["tt_27c_1.80v"],
        },
        "corners": [],
        "spread_checks": [],
        "overall_pass": True,
        "links": {
            "testbench": "sim/pdk-smoke/testbench/tb_pdk_smoke.sch",
            "manifest": "sim/pdk-smoke/experiment.json",
            "netlist_snapshot": "sim/pdk-smoke/netlist-snapshots/x.spice",
            "corners_dir": "sim/pdk-smoke/corners/x/",
            "json": "sim/pdk-smoke/records/x.json",
            "record": "sim/pdk-smoke/records/x.md",
        },
    }


if __name__ == "__main__":
    unittest.main()
