"""Issue #345: bounded caller-side retry of a fleet-cap refusal in run_klt_batch.

Headless: subprocess.run and time.sleep are mocked; nothing is submitted.
Only the `exceeds BATCH_MAX_CONCURRENT_INSTANCES` refusal with no job id is
retried; every other failure stays fatal and unretried.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_corner_run import corner_run

CAP = (
    "batch-fleet-provision.sh launch failed (exit 1): 8 instance(s) already "
    "running + 1 requested exceeds BATCH_MAX_CONCURRENT_INSTANCES=8"
)
OK = json.dumps({"status": "pass", "corners": []})


def done(rc, out="", err=""):
    return subprocess.CompletedProcess(["klt"], rc, stdout=out, stderr=err)


class CapacityRetry(unittest.TestCase):
    def run_with(self, results):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, True))
        req = tmp / "r.json"
        req.write_text("{}")
        run = mock.Mock(side_effect=results)
        sleep = mock.Mock()
        with mock.patch.object(corner_run, "klt_binary", return_value="/fake/klt"), \
                mock.patch.object(corner_run.subprocess, "run", run), \
                mock.patch.object(corner_run.time, "sleep", sleep):
            try:
                out = corner_run.run_klt_batch(req, tmp / "out", tmp)
                err = None
            except corner_run.HarnessError as exc:
                out, err = None, str(exc)
        return out, err, run, sleep

    def test_refusal_then_success_retries_once(self):
        out, err, run, sleep = self.run_with([done(1, "", CAP), done(0, OK)])
        self.assertIsNone(err)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args, run.call_args_list[1].args)
        sleep.assert_called_once_with(corner_run.CAPACITY_RETRY_BACKOFF_S)
        self.assertEqual(out[0]["status"], "pass")

    def test_refusal_beyond_budget_aborts(self):
        attempts = corner_run.CAPACITY_RETRY_BUDGET_S // corner_run.CAPACITY_RETRY_BACKOFF_S + 1
        out, err, run, sleep = self.run_with([done(1, CAP)] * (attempts + 5))
        self.assertIsNone(out)
        self.assertEqual(run.call_count, attempts)
        self.assertIn(f"all {attempts} attempt(s)", err)
        self.assertIn("NOT falling back to a local run", err)

    def test_cap_text_with_job_id_is_not_retried(self):
        out, err, run, sleep = self.run_with([done(1, "job klt-sim-0123abcd " + CAP)])
        self.assertIsNone(out)
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("klt-sim-0123abcd", err)

    def test_other_failure_is_not_retried(self):
        out, err, run, sleep = self.run_with([done(1, "", "batch_runner_version_mismatch")])
        self.assertIsNone(out)
        self.assertEqual(run.call_count, 1)
        sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
