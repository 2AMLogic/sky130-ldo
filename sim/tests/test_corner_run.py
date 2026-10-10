"""Unit coverage for sim/bin/corner-run.py's pure helper functions.

PDK-free by design (no ngspice/xschem/volare required) so this runs on every
`npm run check:ci` invocation, including in CI where the sky130 PDK is not
installed -- see sim/selftest.sh stage 1/3.

corner-run.py is loaded by file path (not `import corner_run`) because the
CLI convention keeps the hyphenated `corner-run.py` filename, matching the
sibling sky130-bandgap repo's harness.
"""

from __future__ import annotations

import datetime
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


class TestToolVersionPin(unittest.TestCase):
    """Issue #291: ngspice/xschem versions are declared in sim/pdk.json and checked."""

    def test_parse_versions(self):
        self.assertEqual(
            corner_run.parse_tool_version("ngspice", "ngspice-42 : Circuit level simulation program"), "42"
        )
        self.assertEqual(corner_run.parse_tool_version("xschem", "XSCHEM V3.4.4"), "3.4.4")
        self.assertIsNone(corner_run.parse_tool_version("xschem", "not found"))

    def test_compare_flags_only_drift(self):
        declared = {"ngspice": "42", "xschem": "3.4.4"}
        ok = {"ngspice": "ngspice-42 : x", "xschem": "XSCHEM V3.4.4"}
        self.assertEqual(corner_run.compare_tool_versions(declared, ok), [])
        drift = corner_run.compare_tool_versions(declared, {**ok, "xschem": "XSCHEM V3.4.5"})
        self.assertEqual(drift, [("xschem", "3.4.4", "3.4.5")])
        gone = corner_run.compare_tool_versions(declared, {"ngspice": "ngspice-42 : x"})
        self.assertEqual([d[0] for d in gone], ["xschem"])

    def test_pin_declares_tools(self):
        self.assertEqual(set(corner_run.declared_tool_versions(corner_run.load_pin())), {"ngspice", "xschem"})

    def _check_env(self, require_pdk, xschem_line):
        lines = {"ngspice": "ngspice-42 : x", "xschem": xschem_line, "volare": "1.0"}
        pdk = mock.Mock(matches_pin=True, installed_commit="c", dir="d", lib_file="l")
        with mock.patch.object(corner_run.shutil, "which", return_value="/bin/x"), \
             mock.patch.object(corner_run, "first_line", side_effect=lambda cmd: lines[cmd[0]]), \
             mock.patch.object(corner_run, "load_pin", return_value={"tools": {"ngspice": "42", "xschem": "3.4.4"}}), \
             mock.patch.object(corner_run, "resolve_pdk", return_value=pdk), \
             mock.patch("builtins.print") as pr:
            rc = corner_run.check_env(require_pdk=require_pdk)
        return rc, "\n".join(str(c.args[0]) for c in pr.call_args_list if c.args)

    def test_drift_warns_locally_and_fails_under_require_pdk(self):
        rc, out = self._check_env(False, "XSCHEM V3.4.5")
        self.assertEqual(rc, 0)
        self.assertIn("WARN xschem drifted from declared 3.4.4 to 3.4.5", out)
        rc, out = self._check_env(True, "XSCHEM V3.4.5")
        self.assertEqual(rc, 1)
        self.assertIn("FAIL xschem drifted from declared 3.4.4 to 3.4.5", out)

    def test_baseline_is_clean(self):
        rc, out = self._check_env(True, "XSCHEM V3.4.4")
        self.assertEqual(rc, 0)
        self.assertNotIn("drifted", out)


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


class TestEvalXschemExprs(unittest.TestCase):
    """xschem 3.4.4 writes raw expr('...') templates; ngspice 42 cannot read
    them (issue #288). They must evaluate to what xschem 3.4.7 writes."""

    RAW = (
        "XM1 VG VG 0 0 sky130_fd_pr__nfet_01v8 L=0.5 W=2 nf=1 "
        "ad=expr('int((@nf + 1)/2) * @W / @nf * 0.29') as=expr('int((@nf + 2)/2) * @W / @nf * 0.29')\n"
        "+ pd=expr('2*int((@nf + 1)/2) * (@W / @nf + 0.29)') ps=expr('2*int((@nf + 2)/2) * (@W / @nf + 0.29)') "
        "nrd=expr('0.29 / @W ')\n"
        "+ nrs=expr('0.29 / @W ') sa=0 sb=0 sd=0 mult=1 m=1\n"
    )

    def test_matches_xschem_347_output(self):
        text, n = corner_run.eval_xschem_exprs(self.RAW)
        self.assertEqual(n, 6)
        self.assertNotIn("expr(", text)
        for want in ("ad=0.58", "as=0.58", "pd=4.58", "ps=4.58", "nrd=0.145", "nrs=0.145"):
            self.assertIn(want, text)

    def test_noop_without_expr(self):
        plain = "R1 VDD VG 1meg m=1\nV1 VDD 0 'vsup'\n"
        self.assertEqual(corner_run.eval_xschem_exprs(plain), (plain, 0))

    def test_unknown_parameter_left_visible(self):
        raw = "X1 a b m W=2 ad=expr('@nope * 2')\n"
        text, n = corner_run.eval_xschem_exprs(raw)
        self.assertEqual((text, n), (raw, 0))

    def test_refuses_unsafe_expression(self):
        raw = "X1 a b m W=2 ad=expr('__import__(1)')\n"
        self.assertEqual(corner_run.eval_xschem_exprs(raw)[1], 0)


# --------------------------------------------------------------------------
# issue #298: opt-in `klt sim` batch backend (smoke-only), all mocked
# --------------------------------------------------------------------------

import contextlib
import io
import json
import shutil

SMOKE_NETLIST = "** sch_path: x\nV1 VDD 0 'vsup'\nR1 VDD vg 1Meg\nXM1 vg vg 0 0 sky130_fd_pr__nfet_01v8\n.end\n"


class FakeKlt:
    """Stands in for subprocess.run: answers `klt sim` from the request, fails the
    test if ngspice (or anything else) is launched."""

    def __init__(self, test, pin, mutate=None, rc=0, stdout=None, raise_exc=None):
        self.test, self.pin, self.mutate, self.rc = test, pin, mutate, rc
        self.stdout, self.raise_exc = stdout, raise_exc
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if cmd[0] != "/fake/klt":
            self.test.fail(f"unexpected launch: {cmd}")
        if self.raise_exc:
            raise self.raise_exc
        req_path = Path(cmd[2])
        outdir = Path(cmd[cmd.index("-o") + 1])
        req = json.loads(req_path.read_text())
        vsup = float(re.search(r"\.param vsup=(\S+)", Path(req["netlist"]).read_text()).group(1))
        corners = []
        for i, (p, t) in enumerate((p, t) for p in req["corners"]["process"] for t in req["corners"]["temperature_c"]):
            vgs = 0.6 + {"tt": 0, "ss": -0.03, "ff": 0.03, "sf": 0.01, "fs": -0.01}[p] + 0.0004 * t
            logp = outdir / f"{p}_{t}.log"
            outdir.mkdir(parents=True, exist_ok=True)
            logp.write_text(f"ngspice log {p} {t}\nmeas_vgs = {vgs}\n")
            corners.append({
                "corner_id": f"{p}/{t:g}C", "process": p, "temperature_c": t, "status": "pass",
                "runtime_s": 1.5, "diagnostics": [],
                "artifacts": {"log": str(logp)},
                "measurements": [
                    {"name": "meas_vgs", "value": vgs, "unit": "V", "status": "pass"},
                    {"name": "meas_isup", "value": (vsup - vgs) / 1e6, "unit": "A", "status": "pass"},
                ],
            })
        resp = {
            "status": "pass", "corners": corners, "corner_count": len(corners),
            "environment": {"engine": "ngspice", "engine_version": "42",
                            "remote": {"provider": "aws-batch-fleet", "job_id": f"klt-sim-{abs(hash(str(req_path))) % 10**6:06x}"}},
            "provenance": {"klt_version": "0.7.0", "pdk": {"version": self.pin["open_pdks_commit"]}},
        }
        if self.mutate:
            self.mutate(resp, req)
        out = self.stdout if self.stdout is not None else json.dumps(resp)
        return subprocess.CompletedProcess(cmd, self.rc, stdout=out, stderr="")


class BatchHarness(unittest.TestCase):
    """A scratch repo root holding a copy of sim/pdk-smoke, with the PDK, xschem,
    git and tool-version lookups mocked."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        sim = self.tmp / "sim"
        sim.mkdir()
        shutil.copytree(SIM_DIR / "pdk-smoke", sim / "pdk-smoke",
                        ignore=shutil.ignore_patterns("records", "corners", "netlist-snapshots"))
        shutil.copyfile(SIM_DIR / "spiceinit", sim / "spiceinit")
        self.pin = corner_run.load_pin()
        pdk_dir = self.tmp / "pdkroot" / "sky130A"
        (pdk_dir / "libs.tech/combined").mkdir(parents=True)
        lib = pdk_dir / self.pin["ngspice_lib"]
        lib.write_text("* lib\n")
        self.pdk = corner_run.Pdk(self.pin, self.tmp / "pdkroot", "sky130A", pdk_dir,
                                  self.pin["open_pdks_commit"], lib)
        self.fake = FakeKlt(self, self.pin)
        self.exp_dir = sim / "pdk-smoke"

        def fake_netlist(schematic, out_dir, pdk):
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / (schematic.stem + ".spice")
            p.write_text(SMOKE_NETLIST)
            return p

        tools = {"ngspice": "ngspice-42 : x", "xschem": "XSCHEM V3.4.4", "platform": "p", "python": "3",
                 "declared": {"ngspice": "42", "xschem": "3.4.4"}, "on_baseline": True}
        patches = [
            mock.patch.object(corner_run, "REPO_ROOT", self.tmp),
            mock.patch.object(corner_run, "BUILD_DIR", self.tmp / "build"),
            mock.patch.object(corner_run, "SPICEINIT_FILE", sim / "spiceinit"),
            mock.patch.object(corner_run, "load_pin", return_value=self.pin),
            mock.patch.object(corner_run, "resolve_pdk", side_effect=lambda pin: self.pdk),
            mock.patch.object(corner_run, "netlist_with_xschem", side_effect=fake_netlist),
            mock.patch.object(corner_run, "git_state", return_value={"sha": "abc1234", "branch": "b", "dirty": False}),
            mock.patch.object(corner_run, "tool_versions", side_effect=lambda: dict(tools)),
            mock.patch.object(corner_run, "default_author", return_value="tester"),
            mock.patch.object(corner_run, "klt_binary", return_value="/fake/klt"),
            mock.patch.object(corner_run.subprocess, "run", side_effect=lambda *a, **k: self.fake(*a, **k)),
            # ticking clock: every run mints a fresh record id (a consumed id
            # stays reserved, issue #310), so repeated main() calls don't collide
            mock.patch.object(corner_run, "datetime", self._ticking_datetime()),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def _ticking_datetime():
        real = corner_run.datetime
        ticks = iter(range(10**6))
        fake = mock.Mock(wraps=real)
        fake.now.side_effect = lambda tz=None: real(2026, 6, 1, tzinfo=corner_run.timezone.utc) + \
            datetime.timedelta(seconds=next(ticks))
        return fake

    def run_main(self, *argv, expect_exit=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            if expect_exit is HarnessErr:
                with self.assertRaises(corner_run.HarnessError) as cm:
                    corner_run.main([str(self.exp_dir), *argv])
                return cm.exception, out.getvalue(), err.getvalue()
            rc = corner_run.main([str(self.exp_dir), *argv])
        return rc, out.getvalue(), err.getvalue()

    def records(self):
        return sorted((self.exp_dir / "records").glob("*.json"))

    def klt_calls(self):
        return [c for c in self.fake.calls if c[0][0] == "/fake/klt"]


HarnessErr = object()
QUICK = ["--quick", "--subset-reason", "test"]


class TestBatchGrouping(unittest.TestCase):
    def test_full_matrix_is_three_supply_requests_of_45_unique_points(self):
        exp = corner_run.load_experiment(SIM_DIR / "pdk-smoke")
        args = corner_run.parse_args([str(SIM_DIR / "pdk-smoke")])
        matrix, _ = corner_run.build_matrix(exp, args, corner_run.load_pin())
        groups = corner_run.group_batch_requests(matrix, False)
        self.assertEqual([g.supply_v for g in groups], [1.62, 1.8, 1.98])
        for g in groups:
            self.assertEqual(len(g.process), 5)
            self.assertEqual(g.temperature_c, [-40.0, 27.0, 125.0])
        pts = {(c.process, c.temp_c, c.supply_v) for g in groups for c in g.corners}
        self.assertEqual(len(pts), 45)
        self.assertEqual(sum(len(g.corners) for g in groups), 45)

    def test_quick_is_three_singletons_not_27_points(self):
        exp = corner_run.load_experiment(SIM_DIR / "pdk-smoke")
        args = corner_run.parse_args([str(SIM_DIR / "pdk-smoke"), "--quick"])
        matrix, subset = corner_run.build_matrix(exp, args, corner_run.load_pin())
        groups = corner_run.group_batch_requests(matrix, True)
        self.assertTrue(subset)
        self.assertEqual([(g.process, g.temperature_c, g.supply_v) for g in groups],
                         [(["tt"], [27.0], 1.8), (["ss"], [-40.0], 1.62), (["ff"], [125.0], 1.98)])

    def test_cartesian_cli_override_groups_by_supply(self):
        exp = corner_run.load_experiment(SIM_DIR / "pdk-smoke")
        args = corner_run.parse_args([str(SIM_DIR / "pdk-smoke"), "--process", "tt,ss",
                                      "--temp", "27", "--supply", "1.8,1.62"])
        matrix, subset = corner_run.build_matrix(exp, args, corner_run.load_pin())
        groups = corner_run.group_batch_requests(matrix, False)
        self.assertTrue(subset)
        self.assertEqual([g.supply_v for g in groups], [1.8, 1.62])
        self.assertEqual([g.process for g in groups], [["tt", "ss"]] * 2)


class TestBatchRefusals(BatchHarness):
    def test_other_slug_refused_before_any_launch(self):
        raw = json.loads((self.exp_dir / "experiment.json").read_text())
        raw["slug"] = "load-regulation"
        (self.exp_dir / "experiment.json").write_text(json.dumps(raw))
        err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("bounded", str(err))
        self.assertEqual(self.fake.calls, [])
        corner_run.netlist_with_xschem.assert_not_called()

    def test_changed_smoke_shape_refused(self):
        for edit in (lambda r: r["deck"].update(analyses=["op", "dc"]),
                     lambda r: r["measurements"][0].update(expr="v(vg)*2")):
            raw = json.loads((SIM_DIR / "pdk-smoke" / "experiment.json").read_text())
            edit(raw)
            (self.exp_dir / "experiment.json").write_text(json.dumps(raw))
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("supported smoke shape", str(err))
        self.assertEqual(self.fake.calls, [])
        corner_run.netlist_with_xschem.assert_not_called()

    def test_default_backend_is_local(self):
        self.assertEqual(corner_run.parse_args(["x"]).backend, "local")
        self.assertEqual(corner_run.parse_args(["x", "--backend", "local"]).backend, "local")


class TestBatchRequests(BatchHarness):
    def test_dry_run_prints_requests_without_submission_or_writes(self):
        rc, out, _ = self.run_main("--backend", "batch", "--dry-run", "--timeout", "77")
        self.assertEqual(rc, 0)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(out.count('"analysis"'), 3)
        self.assertFalse((self.exp_dir / "records").exists())
        self.assertFalse((self.exp_dir / "klt-requests").exists())

    def test_request_and_netlist_content(self):
        rc, _, _ = self.run_main("--backend", "batch", "--quick", "--subset-reason", "t", "--no-write")
        self.assertEqual(rc, 0)
        self.assertEqual(len(self.klt_calls()), 3)
        cmd, kw = self.klt_calls()[0]
        self.assertEqual(cmd[:2], ["/fake/klt", "sim"])
        self.assertEqual(cmd[cmd.index("--backend") + 1], "batch")
        self.assertEqual(cmd[cmd.index("--format") + 1], "json")
        self.assertEqual(kw["env"]["PDK_ROOT"], str(self.pdk.root))
        req = json.loads(Path(cmd[2]).read_text())
        self.assertEqual(req["engine"], "ngspice")
        self.assertEqual(req["models"], {"pdk": "sky130A", "lib": self.pin["ngspice_lib"]})
        self.assertEqual(req["corners"], {"process": ["tt"], "temperature_c": [27.0]})
        self.assertEqual(req["analysis"], {"kind": "op", "args": ""})
        self.assertEqual(req["measurements"], [
            {"name": "meas_vgs", "expr": "v(vg)", "unit": "V"},
            {"name": "meas_isup", "expr": "-i(v1)", "unit": "A"}])
        self.assertEqual(req["options"]["timeout_s"], 300)
        self.assertTrue(req["options"]["keep_artifacts"])
        self.assertNotIn("monte_carlo", req)
        init = [ln for ln in (SIM_DIR / "spiceinit").read_text().splitlines() if ln.strip()]
        self.assertEqual(req["options"]["ngspice_init"], init)
        self.assertTrue(any(ln.startswith("*") for ln in init))  # comments retained
        body = Path(req["netlist"]).read_text().splitlines()
        self.assertEqual(body[0], ".param vsup=1.8")
        self.assertIn(".option wnflag=1", body)
        self.assertIn(".save all", body)
        self.assertIn("V1 VDD 0 'vsup'", body)
        self.assertNotIn(".end", [b.lower() for b in body])
        # supplies of the three singleton requests are exact
        sup = [re.search(r"vsup=(\S+)", Path(json.loads(Path(c[0][2]).read_text())["netlist"]).read_text()).group(1)
               for c in self.klt_calls()]
        self.assertEqual(sup, ["1.8", "1.62", "1.98"])

    def test_full_matrix_makes_three_requests(self):
        rc, _, _ = self.run_main("--backend", "batch", "--no-write")
        self.assertEqual(rc, 0)
        reqs = [json.loads(Path(c[0][2]).read_text()) for c in self.klt_calls()]
        self.assertEqual(len(reqs), 3)
        self.assertTrue(all(len(r["corners"]["process"]) == 5 and len(r["corners"]["temperature_c"]) == 3
                            for r in reqs))


class TestBatchRecord(BatchHarness):
    def test_passing_run_writes_a_record_with_provenance_in_matrix_order(self):
        rc, out, _ = self.run_main("--backend", "batch")
        self.assertEqual(rc, 0, out)
        (rec_path,) = self.records()
        rec = json.loads(rec_path.read_text())
        self.assertTrue(rec["overall_pass"])
        self.assertEqual(rec["backend"], "batch")
        ids = [r["corner_id"] for r in rec["corners"]]
        self.assertEqual(ids, rec["matrix"]["point_ids"])
        self.assertEqual(len(set(ids)), 45)
        self.assertIsNone(rec["corners"][0]["ngspice_exit"])
        self.assertEqual(len(rec["execution"]["requests"]), 3)
        self.assertEqual(rec["execution"]["requested_backend"], "batch")
        md = rec_path.with_suffix(".md").read_text()
        self.assertIn("aws-batch-fleet", md)
        self.assertIn("klt-sim-", md)
        self.assertIn("remote executor, not this machine", md)
        self.assertIn("ngspice-42 (remote executor", md)
        self.assertIn("klt-responses", md)
        self.assertNotIn("ngspice exit 0", md)
        self.assertNotIn("clean nonzero exit", md)
        for sub in ("klt-requests", "klt-responses", "klt-request-netlists"):
            self.assertEqual(len(list((self.exp_dir / sub).iterdir())), 3)
        self.assertEqual(len(list((self.exp_dir / "corners" / rec["record_id"]).iterdir())), 45)

    def test_append_only_refusal(self):
        fixed = mock.patch.object(corner_run, "datetime", wraps=corner_run.datetime)
        with fixed as dt:
            dt.now.return_value = corner_run.datetime(2026, 1, 2, 3, 4, 5, tzinfo=corner_run.timezone.utc)
            self.run_main("--backend", "batch", *QUICK)
            n = len(self.klt_calls())
            # Fresh scratch (as in another clone): only the committed-evidence
            # check can refuse now. The same-scratch case is the reservation's.
            shutil.rmtree(self.tmp / "build" / ".reservations")
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("append-only", str(err))
        self.assertEqual(len(self.klt_calls()), n)

    def test_same_id_rerun_in_same_scratch_is_refused_by_reservation(self):
        with mock.patch.object(corner_run, "datetime", wraps=corner_run.datetime) as dt:
            dt.now.return_value = corner_run.datetime(2026, 1, 2, 3, 4, 5, tzinfo=corner_run.timezone.utc)
            self.run_main("--backend", "batch", *QUICK)
            n = len(self.klt_calls())
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
        self.assertIn("already reserved", str(err))
        self.assertEqual(len(self.klt_calls()), n)

    def test_no_write_creates_no_evidence(self):
        rc, out, _ = self.run_main("--backend", "batch", *QUICK, "--no-write")
        self.assertEqual(rc, 0)
        self.assertFalse((self.exp_dir / "records").exists())
        self.assertFalse((self.exp_dir / "klt-responses").exists())


class TestBatchGrading(BatchHarness):
    def run_quick(self, mutate=None, **fake_kw):
        self.fake = FakeKlt(self, self.pin, mutate=mutate, **fake_kw)
        return self.run_main("--backend", "batch", *QUICK, "--no-write")

    def first(self, resp):
        return resp["corners"][0]

    def test_min_max_equality_passes_and_each_bound_miss_fails(self):
        def setv(v, name="meas_vgs"):
            def m(resp, req):
                if req["corners"]["process"] != ["tt"]:
                    return  # alter one request only, so the spread check keeps its range
                for mm in self.first(resp)["measurements"]:
                    if mm["name"] == name:
                        mm["value"] = v
            return m
        # smoke vgs window is [0.3, 1.2], inclusive: the limits themselves pass
        self.assertEqual(self.run_quick(setv(0.3))[0], 0)
        self.assertEqual(self.run_quick(setv(1.2))[0], 0)
        for v, name in ((0.2999, "meas_vgs"), (1.2001, "meas_vgs"), (1e-9, "meas_isup"), (2e-3, "meas_isup")):
            rc, out, err = self.run_quick(setv(v, name))
            self.assertEqual(rc, 2, (v, name))
            self.assertIn("FAIL", out)

    def test_boundary_values_pass_grading(self):
        exp = corner_run.load_experiment(self.exp_dir)
        group = corner_run.group_batch_requests([corner_run.Corner("tt", 27.0, 1.8)], True)[0]
        for vgs in (0.3, 1.2):
            logp = self.tmp / "l.log"
            logp.write_text("ok\n")
            resp = {"corners": [{"process": "tt", "temperature_c": 27, "status": "pass",
                                 "artifacts": {"log": str(logp)},
                                 "measurements": [{"name": "meas_vgs", "value": vgs},
                                                  {"name": "meas_isup", "value": 1e-8}]}]}
            res, _ = corner_run.normalize_batch_response(exp, group, resp, self.tmp, 300)
            self.assertTrue(res[0]["pass"], vgs)
            self.assertEqual(res[0]["measurements"][1]["value"], 1e-8)  # isup == min is inclusive

    def test_klt_verdict_is_not_substituted(self):
        def m(resp, req):
            resp["status"] = "fail"
            for c in resp["corners"]:
                c["status"] = "fail"
        rc, out, _ = self.run_quick(m)
        # numerically fine => the harness verdict is its own, not klt's
        self.assertEqual(rc, 0)

    def test_spread_check_failure_is_recorded(self):
        def flat(resp, req):
            for c in resp["corners"]:
                c["measurements"][0]["value"] = 0.6
        rc, out, _ = self.run_quick(flat)
        self.assertEqual(rc, 2)
        # all per-point results pass; only the corner-sensitivity check fails
        self.assertIn("PASS  vgs=0.6", out)
        self.assertIn("overall  : FAIL", out)

    def test_each_solver_marker_fails_even_with_passing_values(self):
        for marker in corner_run.SOLVER_DIAGNOSTIC_MARKERS:
            def m(resp, req, marker=marker):
                Path(resp["corners"][0]["artifacts"]["log"]).write_text(f"warn\n{marker} here\n")
            rc, out, err = self.run_quick(m)
            self.assertEqual(rc, 2, marker)
            self.assertIn("solver diagnostic", err)

    def test_recovered_warning_in_klt_diagnostics_is_not_the_gate(self):
        def m(resp, req):
            self.first(resp)["diagnostics"] = [{"code": "recovered_warning", "message": "gmin stepping recovered"}]
        rc, out, err = self.run_quick(m)
        self.assertNotIn("solver diagnostic", err)

    def test_absent_or_unreadable_log_cannot_pass(self):
        for edit in (lambda c: c.pop("artifacts"),
                     lambda c: c["artifacts"].update(log=None),
                     lambda c: c["artifacts"].update(log="/nonexistent/x.log")):
            def m(resp, req, edit=edit):
                edit(self.first(resp))
            rc, out, err = self.run_quick(m)
            self.assertEqual(rc, 2)
            self.assertIn("engine log", err)

    def test_bad_values_and_statuses_are_recorded_fails(self):
        for edit in (lambda c: c["measurements"].pop(0),
                     lambda c: c["measurements"][0].update(value=None),
                     lambda c: c["measurements"][0].update(value=float("nan")),
                     lambda c: c["measurements"][0].update(value="0.6"),
                     lambda c: c.update(status="error"),
                     lambda c: c.update(status="inconclusive"),
                     lambda c: c.update(status="timeout")):
            def m(resp, req, edit=edit):
                edit(self.first(resp))
            rc, out, err = self.run_quick(m)
            self.assertEqual(rc, 2)
            self.assertIn("FAIL", out)

    def test_structural_response_problems_raise_and_never_fall_back(self):
        quick_bad = {
            "missing": lambda r, q: r["corners"].clear(),
            "duplicate": lambda r, q: r["corners"].append(dict(r["corners"][0])),
            "extra": lambda r, q: r["corners"].append({**r["corners"][0], "process": "ss"}),
            "wrong-temp": lambda r, q: r["corners"][0].update(temperature_c=28),
            "malformed": lambda r, q: r["corners"].__setitem__(0, "junk"),
            "pdk-missing": lambda r, q: r.pop("provenance"),
            "pdk-other": lambda r, q: r["provenance"]["pdk"].update(version="deadbeef"),
        }
        for name, mut in quick_bad.items():
            self.fake = FakeKlt(self, self.pin, mutate=mut)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, "--no-write", expect_exit=HarnessErr)
            self.assertTrue(str(err), name)
            self.assertTrue(all(c[0][0] == "/fake/klt" for c in self.fake.calls), name)
            self.assertEqual(len(self.klt_calls()), 1, name)  # stopped at first request, no retry

    def test_transport_failures_raise_without_evidence_or_fallback(self):
        cases = {
            "no stdout": dict(stdout="", rc=1),
            "non-json": dict(stdout="Traceback...", rc=1),
            "error envelope": dict(stdout=json.dumps({"error": "boom", "job_id": "klt-sim-abc123"}), rc=3),
            "not an object": dict(stdout="[1]", rc=0),
            "timeout": dict(raise_exc=subprocess.TimeoutExpired("klt", 1, output="submitted klt-sim-feed01")),
        }
        for name, kw in cases.items():
            self.fake = FakeKlt(self, self.pin, **kw)
            err, _, _ = self.run_main("--backend", "batch", *QUICK, expect_exit=HarnessErr)
            self.assertIn("no evidence record written", str(err), name)
            self.assertFalse((self.exp_dir / "records").exists(), name)
            self.assertEqual(len(self.klt_calls()), 1, name)
        self.assertIn("klt-sim-feed01", str(err))

    def test_nonzero_exit_with_valid_response_is_graded_not_trusted(self):
        rc, out, _ = self.run_quick(lambda r, q: None, rc=2)
        self.assertEqual(rc, 0)  # klt's exit status is not the verdict; the graded values are
        self.assertIn("overall  : PASS", out)

    def test_pdk_mismatch_allowed_is_visible_in_record(self):
        def m(resp, req):
            resp["provenance"]["pdk"]["version"] = "other"
        self.fake = FakeKlt(self, self.pin, mutate=m)
        rc, _, err = self.run_main("--backend", "batch", *QUICK, "--allow-pdk-mismatch")
        self.assertIn("WARNING", err)
        rec = json.loads(self.records()[0].read_text())
        self.assertFalse(rec["execution"]["requests"][0]["klt_pdk_names_pin"])
        self.assertIn("does NOT name", self.records()[0].with_suffix(".md").read_text())


class TestLocalPathUnchangedByBatchWork(BatchHarness):
    def test_default_and_explicit_local_use_the_same_ngspice_path(self):
        launched = []

        def fake_run(cmd, **kw):
            launched.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="meas_vgs = 0.6\nmeas_isup = 1e-5\n", stderr="")

        for extra in ([], ["--backend", "local"]):
            launched.clear()
            with mock.patch.object(corner_run.subprocess, "run", side_effect=fake_run):
                self.run_main(*QUICK, "--no-write", *extra)
            self.assertEqual([c[0] for c in launched], ["ngspice"] * 3)

    def test_local_record_has_no_batch_fields(self):
        def fake_run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, stdout="meas_vgs = 0.6\nmeas_isup = 1e-5\n", stderr="")
        with mock.patch.object(corner_run.subprocess, "run", side_effect=fake_run):
            self.run_main(*QUICK)
        rec = json.loads(self.records()[0].read_text())
        self.assertNotIn("backend", rec)
        self.assertNotIn("execution", rec)
        self.assertNotIn("klt_requests", rec["links"])
        self.assertNotIn("Execution backend", self.records()[0].with_suffix(".md").read_text())



if __name__ == "__main__":
    unittest.main()
