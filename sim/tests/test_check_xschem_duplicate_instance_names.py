"""Fixture-based coverage for
.loom/scripts/check-xschem-duplicate-instance-names.sh (#38).

PDK-free by design (no ngspice/xschem/volare required, just `git` + `bash`)
so this runs on every `npm run check:ci` invocation, including in CI where
the sky130 PDK is not installed.

Each test builds a throwaway git repository under a temp dir with a
`design/*.sch` fixture, then invokes the real script against it (passing the
fixture repo root as the script's ROOT argument) and asserts on exit code +
stderr content -- mirroring how `npm run check:ci` actually runs it against
this repo's own `design/ldo_3v3in_1v8out.sch`.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / ".loom" / "scripts" / "check-xschem-duplicate-instance-names.sh"


def _make_fixture_repo(tmp_path: Path, sch_body: str) -> Path:
    """Create a throwaway git repo under tmp_path with design/fixture.sch
    containing sch_body, and return the repo root. The script scans tracked
    files (`git ls-files`), so the fixture must be committed.
    """
    repo = tmp_path / "repo"
    (repo / "design").mkdir(parents=True)
    (repo / "design" / "fixture.sch").write_text(sch_body)

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "fixture"], cwd=repo, check=True)
    return repo


def _run_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), str(root)],
        capture_output=True,
        text=True,
    )


class TestCheckXschemDuplicateInstanceNames(unittest.TestCase):
    def test_script_exists_and_is_executable(self):
        self.assertTrue(SCRIPT.is_file(), f"missing {SCRIPT}")

    def test_no_duplicates_passes(self):
        sch = (
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 -1300 0 0 {name=M_ENP2\n'
            "L=0.5\n"
            "W=10\n"
            "spiceprefix=X}\n"
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 600 -1600 0 0 {name=M_ENP\n'
            "L=0.5\n"
            "W=2\n"
            "spiceprefix=X}\n"
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 1700 -1600 0 0 {name=M_ENP3\n'
            "L=0.5\n"
            "W=2\n"
            "spiceprefix=X}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("OK", result.stdout)

    def test_duplicate_instance_name_fails_with_clear_message(self):
        # Reproduces the original #35/#36 incident: two M_ENP4 instances on
        # different nets in the same schematic.
        sch = (
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3000 -1300 0 0 {name=M_ENP4\n'
            "L=0.5\n"
            "W=2\n"
            "spiceprefix=X}\n"
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 3200 -2500 0 0 {name=M_ENP4\n'
            "L=0.5\n"
            "W=2\n"
            "spiceprefix=X}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("DUPLICATE INSTANCE NAME", result.stderr)
        self.assertIn("M_ENP4", result.stderr)
        self.assertIn("design/fixture.sch", result.stderr)

    def test_single_line_duplicate_also_fails(self):
        sch = (
            "C {devices/lab_pin.sym} 0 -70 0 0 {name=p_rbias1 lab=VIN}\n"
            "C {devices/lab_pin.sym} -20 -100 0 0 {name=p_rbias1 lab=0}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("p_rbias1", result.stderr)

    def test_name_only_single_line_instance_duplicate_is_caught(self):
        # Regression (PR #43 review): an instance whose ONLY attribute is
        # `name=`, closed with `}` on the same line and nothing after it.
        # The original regex required whitespace or end-of-line immediately
        # after the captured value, so `{name=M1}` never matched at all and
        # the instance was invisible to the duplicate check -- a silent
        # false negative that reported OK / exit 0 on this very fixture.
        sch = (
            "C {devices/lab_pin.sym} 0 0 0 0 {name=M1}\n"
            "C {devices/lab_pin.sym} 10 0 0 0 {name=M1}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("DUPLICATE INSTANCE NAME", result.stderr)
        self.assertIn("M1", result.stderr)

    def test_name_only_instance_duplicate_across_shapes_is_caught(self):
        # The same name reached via two *different* line shapes -- the
        # name-only single-line form (`{name=xldo}`, the exact shape every
        # testbench in this repo uses to instantiate the LDO core) and the
        # multi-attribute form -- must still collide.
        sch = (
            "C {design/ldo_3v3in_1v8out.sch} 0 0 0 0 {name=xldo}\n"
            "C {design/ldo_3v3in_1v8out.sch} 400 0 0 0 {name=xldo "
            "spiceprefix=X}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 1, msg=result.stdout)
        self.assertIn("xldo", result.stderr)

    def test_repeated_prefix_is_not_a_false_positive(self):
        # M_ENP, M_ENP2, M_ENP3 share a prefix but are distinct names -- must
        # not be flagged as duplicates of each other.
        #
        # These use the name-only, `}`-on-the-same-line shape, so a clean
        # exit 0 here is ambiguous on its own: it is equally consistent with
        # "recognized 3 distinct names" and "recognized 0 instances at all"
        # (which is exactly what the pre-fix regex did -- see PR #43's
        # review). The positive control below pins down which one it is by
        # duplicating one of the names in the *identical* shape and
        # requiring that to fail.
        sch = (
            "C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 0 0 0 {name=M_ENP}\n"
            "C {sky130_fd_pr/pfet_g5v0d10v5.sym} 100 0 0 0 {name=M_ENP2}\n"
            "C {sky130_fd_pr/pfet_g5v0d10v5.sym} 200 0 0 0 {name=M_ENP3}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

        # Positive control: same fixture, same line shape, one name repeated.
        dup_sch = sch + (
            "C {sky130_fd_pr/pfet_g5v0d10v5.sym} 300 0 0 0 {name=M_ENP2}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), dup_sch)
            dup_result = _run_check(repo)
        self.assertEqual(
            dup_result.returncode,
            1,
            msg="name-only single-line instances are not being recognized at "
            f"all: {dup_result.stdout}",
        )
        self.assertIn("M_ENP2", dup_result.stderr)

    def test_name_shaped_text_outside_component_instance_is_ignored(self):
        # A repeated name=-shaped token inside a T {...} comment/text block
        # is not a `C {...}` component instance and must not be scoped in.
        sch = (
            'C {sky130_fd_pr/pfet_g5v0d10v5.sym} 0 0 0 0 {name=M_ENP}\n'
            'T {see name=M_ENP in the comment above, and again name=M_ENP here} '
            "40 0 0 0 0.2 0.2 {}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            repo = _make_fixture_repo(Path(td), sch)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_no_tracked_sch_files_is_ok(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            result = _run_check(repo)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_current_repo_schematic_has_no_duplicates(self):
        # Regression check: the real design/ldo_3v3in_1v8out.sch on this
        # branch must pass cleanly (no false positive against the
        # known-good, duplicate-free file).
        result = _run_check(REPO_ROOT)
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
