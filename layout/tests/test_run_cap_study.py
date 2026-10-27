"""Unit tests for the pure helpers of the #319 capacitor-study orchestrator
(layout/cap-study/run-cap-study.py): path scrubbing, klt response parsing,
request construction and the evidence-gap / verdict path. Stdlib only, tiny
inline fixtures -- no PDK, klt, ngspice or network. The module name is
hyphenated, so it is loaded with importlib."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from _layout_script_loader import load_script  # noqa: E402

CAP_DIR = Path(__file__).resolve().parents[1] / "cap-study"
sys.path.insert(0, str(CAP_DIR))

rcs = load_script("run_cap_study", CAP_DIR / "run-cap-study.py")
cs = rcs.cs

CAPS = [{"name": "C1", "nets": ["VOUT", "0"], "value_f": 1e-12},
        {"name": "C2", "nets": ["A", "B"], "value_f": 2e-12}]


def corner(process="tt", temp=27.0, status="pass", meas=None, diags=None):
    return {"process": process, "temperature_c": temp, "status": status,
            "measurements": [{"name": k, "value": v} for k, v in (meas or {}).items()],
            "diagnostics": [{"code": c} for c in (diags or [])]}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


class ScrubTests(unittest.TestCase):
    def test_repo_root_stripped(self):
        t = f"in {rcs.REPO_ROOT}/sim/x.cir done"
        self.assertEqual(rcs.scrub(t), "in sim/x.cir done")

    def test_bucket_name_replaced(self):
        out = rcs.scrub("s3://2am-batch-jobs-123456789012/k")
        self.assertNotIn("123456789012", out)
        self.assertIn("<batch-job-bucket>", out)

    def test_pdk_root_replaced(self):
        out = rcs.scrub("/opt/pdk/sky130A/libs.tech/x", Path("/opt/pdk"))
        self.assertEqual(out, "$PDK_ROOT/sky130A/libs.tech/x")

    def test_pdk_path_untouched_without_root(self):
        t = "/opt/pdk/sky130A/libs.tech/x"
        self.assertEqual(rcs.scrub(t), t)

    def test_negative_clean_text_and_prefix_lookalike(self):
        self.assertEqual(rcs.scrub("nothing here"), "nothing here")
        # bucket regex needs digits; a different bucket name is not rewritten
        self.assertEqual(rcs.scrub("2am-batch-jobs-abc"), "2am-batch-jobs-abc")

    def test_scrub_tree_rewrites_only_text_suffixes(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "out"
            (out / "sub").mkdir(parents=True)
            leak = f"{rcs.REPO_ROOT}/a 2am-batch-jobs-42"
            (out / "sub" / "r.json").write_text(leak)
            (out / "n.bin").write_text(leak)
            rcs.scrub_tree(out, Path("/opt/pdk"))
            self.assertEqual((out / "sub" / "r.json").read_text(), "a <batch-job-bucket>")
            self.assertEqual((out / "n.bin").read_text(), leak)


class JobFailedTests(unittest.TestCase):
    def test_no_response_is_failed(self):
        self.assertTrue(rcs.job_failed({"status": "no-response"}, Path(".")))

    def test_remote_failed_state(self):
        self.assertTrue(rcs.job_failed({"remote": {"remote": {"state": "failed"}}}, Path(".")))

    def test_ok_and_missing_remote_not_failed(self):
        self.assertFalse(rcs.job_failed({"status": "pass"}, Path(".")))
        self.assertFalse(rcs.job_failed({"remote": {"remote": {"state": "succeeded"}}}, Path(".")))
        self.assertFalse(rcs.job_failed({"remote": None}, Path(".")))
        self.assertFalse(rcs.job_failed({"remote": {"remote": None}}, Path(".")))


class RespPointsTests(unittest.TestCase):
    def test_parses_values_and_diagnostics(self):
        pts = rcs._resp_points({"corners": [corner(meas={"v_a": 1.5}, diags=["w"])]})
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["measurements"], {"v_a": 1.5})
        self.assertEqual(pts[0]["diagnostics"], ["w"])
        self.assertEqual(pts[0]["process"], "tt")

    def test_drops_nonfinite_nonnumeric_and_junk(self):
        resp = {"corners": ["junk", corner(meas={"a": float("nan"), "b": float("inf"), "c": "x",
                                                   "d": None, "e": 2})]}
        pts = rcs._resp_points(resp)
        self.assertEqual(len(pts), 1)
        self.assertEqual(pts[0]["measurements"], {"e": 2.0})

    def test_empty_and_missing_corners(self):
        self.assertEqual(rcs._resp_points({"corners": []}), [])
        self.assertEqual(rcs._resp_points({}), [])


def make_op_dir(rec: Path, name: str, resp, backend="batch", kind="batch"):
    d = rec / "op" / kind / name
    sub = {"backend": backend, "status": "pass" if resp else "no-response", "returncode": 0,
           "response": "response.json" if resp else None, "job_ids_seen": []}
    write_json(d / "submission.json", sub)
    write_json(d / "request.json", {"corners": {"process": ["tt"]}})
    if resp:
        write_json(d / "response.json", resp)


class ReadOpTests(unittest.TestCase):
    def rows(self, op, **kw):
        return [p for p in op["points"]
                if all(p[k] == v for k, v in kw.items())]

    def test_measured_point_and_grid_size(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            meas = {"v_vout": 1.8, "v_a": 3.0, "v_b": 1.0}
            make_op_dir(rec, "v3.30_50ma", {"corners": [corner(meas=meas)]})
            op = rcs.read_op(rec, CAPS, ["tt"])
            self.assertEqual(len(op["points"]), len(rcs.TEMPS_C) * len(rcs.SUPPLIES_V) * len(rcs.LOADS))
            (row,) = self.rows(op, temperature_c=27.0, supply_v=3.3, load="50ma")
            self.assertEqual(row["status"], "pass")
            self.assertEqual(row["caps"]["C1"]["v_plate_v"], 1.8)  # net "0" counts as 0 V
            self.assertEqual(row["caps"]["C2"]["v_plate_v"], 2.0)
            self.assertEqual(len(op["submissions"]), 1)

    def test_no_record_dirs_means_everything_unmeasured(self):
        with tempfile.TemporaryDirectory() as td:
            op = rcs.read_op(Path(td), CAPS, ["tt", "ss"])
            self.assertEqual(len(op["points"]), 2 * 3 * 3 * 2)
            self.assertEqual(op["submissions"], [])
            for p in op["points"]:
                self.assertEqual(p["status"], cs.UNMEASURED)
                self.assertTrue(all(cs.is_unmeasured(c) for c in p["caps"].values()))

    def test_missing_node_is_unmeasured_not_zero(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            make_op_dir(rec, "v3.30_0ma", {"corners": [corner(meas={"v_vout": 1.8})]})
            op = rcs.read_op(rec, CAPS, ["tt"])
            (row,) = self.rows(op, temperature_c=27.0, supply_v=3.3, load="0ma")
            self.assertFalse(cs.is_unmeasured(row["caps"]["C1"]))
            self.assertTrue(cs.is_unmeasured(row["caps"]["C2"]))  # v_a / v_b absent

    def test_failed_corner_and_batch_job_failed(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            meas = {"v_vout": 1.8, "v_a": 3.0, "v_b": 1.0}
            resp = {"corners": [corner(temp=27.0, status="fail", meas=meas),
                                corner(temp=125.0, meas=meas, diags=["batch_job_failed"])]}
            make_op_dir(rec, "v3.30_0ma", resp)
            op = rcs.read_op(rec, CAPS, ["tt"])
            for t in (27.0, 125.0):
                (row,) = self.rows(op, temperature_c=t, supply_v=3.3, load="0ma")
                self.assertTrue(all(cs.is_unmeasured(c) for c in row["caps"].values()))
            (row,) = self.rows(op, temperature_c=125.0, supply_v=3.3, load="0ma")
            self.assertIn("batch job failed", row["caps"]["C1"]["reason"])

    def test_no_response_submission_recorded_but_not_measured(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            make_op_dir(rec, "v3.30_0ma", None)
            op = rcs.read_op(rec, CAPS, ["tt"])
            self.assertEqual(len(op["submissions"]), 1)
            self.assertEqual(op["submissions"][0]["status"], "no-response")
            self.assertTrue(all(p["status"] == cs.UNMEASURED for p in op["points"]))

    def test_unparseable_dir_name_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            make_op_dir(rec, "weird", {"corners": [corner(meas={"v_vout": 1.8})]})
            op = rcs.read_op(rec, CAPS, ["tt"])
            self.assertTrue(all(p["status"] == cs.UNMEASURED for p in op["points"]))


CV_POINTS = [{"tag": "lvt_w5_l0p5_m0p10", "flavor": "lvt", "w_um": 5.0, "l_um": 0.5, "bias_v": -0.1},
             {"tag": "lvt_w5_l0p5_p0p10", "flavor": "lvt", "w_um": 5.0, "l_um": 0.5, "bias_v": 0.1}]


def make_cv_dir(rec: Path, name: str, resp, freqs=(1e3,)):
    write_json(rec / "cv" / "points.json", {"freqs_hz": list(freqs), "points": CV_POINTS})
    d = rec / "cv" / name
    write_json(d / "submission.json", {"backend": "local", "status": "pass" if resp else "no-response",
                                       "returncode": 0, "response": "response.json" if resp else None})
    if resp:
        write_json(d / "response.json", resp)


class ReadCvTests(unittest.TestCase):
    def test_no_points_file(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(rcs.read_cv(Path(td)), {"runs": [], "submissions": []})

    def test_curve_capacitance(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            vi = {f"vi_{CV_POINTS[0]['tag']}_f0": -1e9, f"vi_{CV_POINTS[1]['tag']}_f0": -2e9}
            make_cv_dir(rec, "run0", {"corners": [corner(meas=vi)]})
            cv = rcs.read_cv(rec)
            (run,) = cv["runs"]
            cur = run["curves"]["lvt_w5_l0.5"]
            self.assertEqual(cur["bias_v"], [-0.1, 0.1])
            c = cur["c_f"]["1000"]
            self.assertAlmostEqual(c[0], cs.c_from_vi(-1e9, 1e3), delta=abs(c[0]) * 1e-5)
            self.assertAlmostEqual(c[1], c[0] / 2, delta=abs(c[0]) * 1e-5)

    def test_missing_or_noncapacitive_measurement_is_none(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            vi = {f"vi_{CV_POINTS[1]['tag']}_f0": 5.0}  # positive Im(V): not capacitive
            make_cv_dir(rec, "run0", {"corners": [corner(meas=vi)]})
            (run,) = rcs.read_cv(rec)["runs"]
            self.assertEqual(run["curves"]["lvt_w5_l0.5"]["c_f"]["1000"], [None, None])

    def test_no_response_and_empty_corners_yield_no_runs(self):
        with tempfile.TemporaryDirectory() as td:
            rec = Path(td)
            make_cv_dir(rec, "run0", None)
            cv = rcs.read_cv(rec)
            self.assertEqual(cv["runs"], [])
            self.assertEqual(len(cv["submissions"]), 1)
        with tempfile.TemporaryDirectory() as td:
            make_cv_dir(Path(td), "run0", {"corners": []})
            self.assertEqual(rcs.read_cv(Path(td))["runs"], [])


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.pdk = SimpleNamespace(variant="sky130A", dir=Path("/p"), lib_file=Path("/p/libs.tech/s.lib"))
        patcher = mock.patch.object(rcs, "corner_run",
                                    return_value=SimpleNamespace(spiceinit_lines=lambda: ["set x"]))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_op_request_one_measurement_per_node(self):
        req = rcs.op_request(Path("n.cir"), self.pdk, ["tt"], [27.0], ["VOUT", "NET1"])
        names = [m["name"] for m in req["measurements"]]
        self.assertEqual(names, ["v_vout", "v_net1"])
        self.assertIn("v(vout)", req["measurements"][0]["spice"])
        self.assertIn("v(xldo.net1)", req["measurements"][1]["spice"])
        self.assertEqual(req["analysis"]["kind"], "tran")
        self.assertEqual(req["models"]["lib"], "libs.tech/s.lib")
        self.assertEqual(req["corners"], {"process": ["tt"], "temperature_c": [27.0]})

    def test_op_meas_nodes_dedup_and_skip_ground(self):
        self.assertEqual(rcs.op_meas_nodes(CAPS + [{"name": "C3", "nets": ["A", "0"]}]),
                         ["VOUT", "A", "B"])

    def test_cv_netlist_point_count_and_unique_tags(self):
        lines, pts = rcs.cv_netlist(flavors=["lvt", "hvt"], geoms=[(5.0, 0.5)], step=0.5, soa=1.0)
        self.assertEqual(len(pts), 2 * 1 * 5)  # biases -1.0 .. 1.0 in 0.5 steps
        self.assertEqual(len({p["tag"] for p in pts}), len(pts))
        self.assertEqual(sorted({p["bias_v"] for p in pts}), [-1.0, -0.5, 0.0, 0.5, 1.0])
        self.assertEqual(len(lines), 1 + 4 * len(pts))
        for p in pts:
            self.assertEqual(sum(1 for ln in lines if ln.startswith(f"X_{p['tag']} ")), 1)

    def test_cv_netlist_default_symmetric_bias(self):
        _, pts = rcs.cv_netlist()
        biases = [p["bias_v"] for p in pts if p["flavor"] == "lvt" and p["w_um"] == 5.0]
        self.assertEqual(biases, sorted(biases))
        self.assertEqual(biases[0], -biases[-1])

    def test_cv_request_measurements_and_sweep(self):
        _, pts = rcs.cv_netlist(flavors=["lvt"], geoms=[(5.0, 0.5)], step=1.0, soa=1.0)
        req = rcs.cv_request(Path("n.cir"), self.pdk, ["tt"], [27.0], pts, [1e3])
        self.assertEqual(len(req["measurements"]), len(pts))
        self.assertEqual(req["analysis"], {"kind": "ac", "args": "lin 3 1000 2000"})
        req2 = rcs.cv_request(Path("n.cir"), self.pdk, ["tt"], [27.0], pts, [1e3, 5e6])
        self.assertEqual(len(req2["measurements"]), 2 * len(pts))
        self.assertEqual(req2["analysis"]["args"], "lin 3 1000 5e+06")
        for p in pts:
            self.assertIn(f"vi_{p['tag']}_f1", [m["name"] for m in req2["measurements"]])

    def test_cv_request_rejects_bad_frequency_count(self):
        for freqs in ([], [1.0, 2.0, 3.0]):
            with self.assertRaises(ValueError):
                rcs.cv_request(Path("n.cir"), self.pdk, ["tt"], [27.0], [], freqs)


def op_ok(n=2):
    return {"points": [{"status": "pass", "caps": {"C1": {"v_plate_v": 1.0, "v_plus_v": 1.0, "v_minus_v": 0.0}}}
                       for _ in range(n)]}


def cv_full():
    return {"runs": [{"process": p, "temperature_c": t}
                     for p in ("tt", "ss", "ff", "sf", "fs", "ll", "hh") for t in rcs.TEMPS_C]}


class EvidenceGapsTests(unittest.TestCase):
    def test_complete_evidence_has_no_gaps(self):
        self.assertEqual(rcs.evidence_gaps(op_ok(), cv_full(), [{"id": "x", "verdict": "fits"}]), [])

    def test_unmeasured_point_status_is_a_gap(self):
        op = op_ok(3)
        op["points"][0]["status"] = cs.UNMEASURED
        gaps = rcs.evidence_gaps(op, cv_full(), [])
        self.assertEqual(len(gaps), 1)
        self.assertIn("1/3 points unmeasured", gaps[0])

    def test_unmeasured_cap_cell_is_a_gap(self):
        op = op_ok(2)
        op["points"][1]["caps"]["C1"] = cs.unmeasured("x")
        self.assertIn("1/2 points unmeasured", rcs.evidence_gaps(op, cv_full(), [])[0])

    def test_missing_cv_runs_counted(self):
        cv = cv_full()
        cv["runs"] = cv["runs"][:-2]
        (gap,) = rcs.evidence_gaps(op_ok(), cv, [])
        self.assertIn("2/21", gap)
        (gap,) = rcs.evidence_gaps(op_ok(), {"runs": []}, [])
        self.assertIn("21/21", gap)

    def test_not_established_option_is_a_gap(self):
        gaps = rcs.evidence_gaps(op_ok(), cv_full(),
                                 [{"id": "m", "verdict": "not-established", "verdict_reason": "why"},
                                  {"id": "k", "verdict": "does-not-fit"}])
        self.assertEqual(len(gaps), 1)
        self.assertIn("option m", gaps[0])
        self.assertIn("why", gaps[0])


class MosOptionTests(unittest.TestCase):
    SOA = {"lvt": {"vgs_min_v": -2.3, "vgs_max_v": 2.3}, "hvt": {"vgs_min_v": -2.3, "vgs_max_v": 2.3}}

    def test_no_cv_run_is_not_established(self):
        o = rcs.mos_option(CAPS[:1], 1e-12, 5e4, op_ok(), {"freqs_hz": [1e3], "runs": []}, self.SOA, None)
        self.assertEqual(o["verdict"], "not-established")
        self.assertTrue(all(cs.is_unmeasured(v) for v in o["cv_tt_27c"].values()))
        self.assertTrue(cs.is_unmeasured(o["area_162pf_um2"]["tt"]))
        self.assertTrue(o["plate_voltage_range"]["C1"]["complete"])

    def test_incomplete_op_matrix_never_yields_a_fit_verdict(self):
        op = op_ok(2)
        op["points"][1]["caps"]["C1"] = cs.unmeasured("x")
        tt = {"process": "tt", "temperature_c": 27.0, "source": "cv/r",
              "curves": {"lvt_w10_l10": {"flavor": "lvt", "w_um": 10.0, "l_um": 10.0,
                                         "bias_v": [-1.0, 0.0, 1.0],
                                         "c_f": {"1000": [1e-12, 2e-12, 3e-12]}}}}
        o = rcs.mos_option(CAPS[:1], 1e-12, 5e4, op, {"freqs_hz": [1e3], "runs": [tt]}, self.SOA, None)
        self.assertFalse(o["plate_voltage_range"]["C1"]["complete"])
        self.assertEqual(o["verdict"], "not-established")
        self.assertIn("incomplete", o["verdict_reason"])
        # the C(V) density itself is still reported
        self.assertEqual(o["cv_tt_27c"]["lvt_w10_l10"]["cmax_f"], 3e-12)


class BuildMatrixTests(unittest.TestCase):
    def test_missing_terminals_record_raises(self):
        # build_matrix needs the op/terminals.json budget before anything else
        # that is fixture-able; an empty record must fail loudly, not produce
        # a matrix.
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(rcs, "pdk_ctx", return_value=(None, {"process_corners": ["tt"]}, None)):
                with self.assertRaises(FileNotFoundError):
                    rcs.build_matrix(Path(td))


if __name__ == "__main__":
    unittest.main()
