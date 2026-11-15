"""Unit tests for layout/bin/_flow_common.sh, the shared run-*-flow.sh preamble
(issue #599).

Standard library only, and deliberately PDK-free / klt-free: every helper is
exercised against a stub `klt` and a scratch git tree, so this module runs in
the headless `checks` CI job alongside the rest of layout/tests.

Two of these tests are regression tests for the drifts the extraction closed,
and both fail against the five inlined copies that preceded it:

  * `test_no_driver_shells_out_to_raw_xschem` -- run-cap-rail-demo-flow.sh
    called `xschem -n -q -x -s` directly, so it alone had no timeout kill.
  * `test_record_id_tracks_repo_root_not_cwd` -- run-cap-rail-demo-flow.sh
    minted its record id with a bare `git rev-parse --short HEAD`, correct
    only because an earlier line happened to `cd` to the repo root first.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
LIB = BIN_DIR / "_flow_common.sh"
DRIVERS = sorted(BIN_DIR.glob("run-*-flow.sh"))

RECORD_ID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{7,}$")


def run_snippet(snippet: str, lib: Path = LIB, cwd: Path | None = None):
    """Source `lib` under `set -euo pipefail`, then run `snippet`."""
    script = f"set -euo pipefail\nsource {shlex.quote(str(lib))}\n{snippet}\n"
    return subprocess.run(
        ["bash", "-c", script],
        cwd=None if cwd is None else str(cwd),
        capture_output=True,
        text=True,
    )


def git(*args: str, cwd: Path) -> str:
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
    )
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True, env=env
    ).stdout.strip()


def make_repo(root: Path, message: str) -> str:
    """A scratch repo laid out like this one (`layout/bin/_flow_common.sh`)."""
    (root / "layout" / "bin").mkdir(parents=True)
    shutil.copy2(LIB, root / "layout" / "bin" / LIB.name)
    (root / "sim").mkdir()
    (root / "sim" / "xschemrc").write_text("* scratch rcfile\n")
    git("init", "--quiet", cwd=root)
    git("add", "-A", cwd=root)
    git("commit", "--quiet", "-m", message, cwd=root)
    return git("rev-parse", "--short", "HEAD", cwd=root)


class FlowPathsTest(unittest.TestCase):
    def test_paths_derive_from_the_library_not_the_caller_cwd(self):
        """LAYOUT_DIR/REPO_ROOT come from the library's own location."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_snippet('echo "$LAYOUT_DIR"; echo "$REPO_ROOT"', cwd=Path(tmp))
        self.assertEqual(result.returncode, 0, result.stderr)
        layout_dir, repo_root = result.stdout.split()
        self.assertEqual(Path(layout_dir), BIN_DIR.parent)
        self.assertEqual(Path(repo_root), BIN_DIR.parents[1])


class RequireKltTest(unittest.TestCase):
    def test_missing_klt_names_setup_venv_and_exits_1(self):
        result = run_snippet('flow_require_klt run-x-flow.sh /nope/klt')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "run-x-flow.sh: /nope/klt not found -- run layout/bin/setup-venv.sh first\n",
        )

    def test_a_hint_is_printed_as_an_indented_second_line(self):
        """run-ldo-erc-flow.sh's own --requirements file, byte for byte."""
        result = run_snippet(
            'flow_require_klt run-ldo-erc-flow.sh /nope/klt '
            '"layout/bin/setup-venv.sh --requirements layout/erc-requirements.txt"'
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            "run-ldo-erc-flow.sh: /nope/klt not found -- run\n"
            "  layout/bin/setup-venv.sh --requirements layout/erc-requirements.txt\n",
        )

    def test_an_executable_klt_passes_silently(self):
        result = run_snippet('flow_require_klt run-x-flow.sh "$(command -v bash)"; echo past')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "past\n")
        self.assertEqual(result.stderr, "")


class RequirePdkTest(unittest.TestCase):
    def _stub(self, tmp: Path, exit_code: int) -> Path:
        stub = tmp / "klt-stub"
        stub.write_text(
            '#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$STUB_LOG"\nexit '
            f"{exit_code}\n"
        )
        stub.chmod(0o755)
        return stub

    def test_an_unresolvable_pdk_exits_1_with_the_pin_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stub = self._stub(tmp, 1)
            result = run_snippet(
                f'export STUB_LOG={shlex.quote(str(tmp / "log"))}\n'
                f'flow_require_pdk run-x-flow.sh sky130A "see sim/pdk.json for the pin" '
                f'{shlex.quote(str(stub))}'
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(
                result.stderr,
                "run-x-flow.sh: no resolvable sky130A PDK -- see sim/pdk.json for the pin\n",
            )
            self.assertEqual(
                (tmp / "log").read_text(), "pdk find --pdk sky130A\n"
            )

    def test_a_multi_word_klt_command_is_passed_through(self):
        """run-cap-rail-demo-flow.sh's `uvx --from <pin> klt` shape."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            stub = self._stub(tmp, 0)
            result = run_snippet(
                f'export STUB_LOG={shlex.quote(str(tmp / "log"))}\n'
                f'flow_require_pdk run-x-flow.sh sky130A "see sim/pdk.json" '
                f'{shlex.quote(str(stub))} --from pin klt'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (tmp / "log").read_text(), "--from pin klt pdk find --pdk sky130A\n"
            )


class MintRecordTest(unittest.TestCase):
    def test_sets_record_id_out_dir_out_rel_and_announces_out_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sha = make_repo(root, "scratch")
            result = run_snippet(
                'flow_mint_record run-x-flow.sh "$REPO_ROOT/layout/block/reports"\n'
                'echo "$RECORD_ID"; echo "$OUT_DIR"; echo "$OUT_REL"; echo "$SHORT_SHA"',
                lib=root / "layout" / "bin" / LIB.name,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            announce, record_id, out_dir, out_rel, short_sha = result.stdout.splitlines()
            self.assertTrue(RECORD_ID_RE.match(record_id), record_id)
            self.assertTrue(record_id.endswith(f"-{sha}"), (record_id, sha))
            self.assertEqual(short_sha, sha)
            self.assertEqual(out_rel, f"layout/block/reports/{record_id}")
            self.assertEqual(out_dir, f"{root}/{out_rel}")
            self.assertEqual(announce, f"run-x-flow.sh: record {record_id} -> {out_dir}")
            # The record directory is created, not merely named.
            self.assertTrue(Path(out_dir).is_dir())

    def test_rel_announces_the_repo_relative_path(self):
        """run-cap-rail-demo-flow.sh has always printed OUT_REL, not OUT_DIR."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = run_snippet(
                'flow_mint_record run-cap-rail-demo-flow.sh '
                '"$REPO_ROOT/layout/cap-rail-demo/reports" --rel\n'
                'echo "$OUT_REL"',
                lib=root / "layout" / "bin" / LIB.name,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        announce, out_rel = result.stdout.splitlines()
        self.assertEqual(
            announce, f"run-cap-rail-demo-flow.sh: record {out_rel.rsplit('/', 1)[1]} -> {out_rel}"
        )
        self.assertFalse(out_rel.startswith("/"), out_rel)

    def test_suffix_is_appended_to_the_announcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = run_snippet(
                'flow_mint_record run-x-flow.sh "$REPO_ROOT/r" --suffix " (layout from abc)"',
                lib=root / "layout" / "bin" / LIB.name,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.rstrip("\n").endswith(" (layout from abc)"), result.stdout)

    def test_an_unknown_argument_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = run_snippet(
                'flow_mint_record run-x-flow.sh "$REPO_ROOT/r" --nope',
                lib=root / "layout" / "bin" / LIB.name,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("flow_mint_record: unknown argument '--nope'", result.stderr)

    def test_record_id_tracks_repo_root_not_cwd(self):
        """Drift 2: a record id is an evidence directory's identity.

        Minted from `git -C "$REPO_ROOT"`, so it names THIS checkout's HEAD
        even when the caller's cwd is some other repository. A bare
        `git rev-parse --short HEAD` would report the cwd repo's sha here.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            other = Path(tmp) / "other"
            sha = make_repo(root, "the record's repo")
            other_sha = make_repo(other, "an unrelated repo")
            self.assertNotEqual(sha, other_sha)
            result = run_snippet(
                'flow_mint_record run-x-flow.sh "$REPO_ROOT/r"\necho "$SHORT_SHA"',
                lib=root / "layout" / "bin" / LIB.name,
                cwd=other,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[-1], sha)


class NetlistSchematicTest(unittest.TestCase):
    def _run(self, root: Path, stub_body: str, extra_argv: str = ""):
        stub = root / "klt-stub"
        stub.write_text(f"#!/usr/bin/env bash\n{stub_body}\n")
        stub.chmod(0o755)
        return run_snippet(
            f'export STUB_LOG={shlex.quote(str(root / "log"))}\n'
            'flow_netlist_schematic run-x-flow.sh "$REPO_ROOT/design/x.sch" '
            f'"$REPO_ROOT/out/xschem_out" {shlex.quote(str(stub))}{extra_argv}\n'
            'echo "$SCHEM_NETLIST"',
            lib=root / "layout" / "bin" / LIB.name,
        )

    WRITES_NETLIST = (
        'printf "%s\\n" "$*" >> "$STUB_LOG"\n'
        'while [[ $# -gt 0 ]]; do\n'
        '  if [[ "$1" == -o ]]; then printf "* netlist\\n" > "$2"; fi\n'
        '  shift\n'
        'done\n'
    )

    def test_invokes_klt_netlist_with_the_repos_rcfile_and_sets_schem_netlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = self._run(root, self.WRITES_NETLIST)
            log = (root / "log").read_text().strip()
            self.assertEqual(result.returncode, 0, result.stderr)
            netlist = result.stdout.strip().splitlines()[-1]
            # The .spice name is derived from the schematic's basename,
            # which is what xschem names it.
            self.assertEqual(netlist, f"{root}/out/xschem_out/x.spice")
            self.assertEqual(
                log,
                f"netlist -o {root}/out/xschem_out/x.spice "
                f"--rcfile {root}/sim/xschemrc {root}/design/x.sch",
            )
            self.assertTrue(Path(netlist).is_file())

    def test_a_multi_word_klt_command_is_passed_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = self._run(root, self.WRITES_NETLIST, extra_argv=" --from pin klt")
            log = (root / "log").read_text().strip()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(log.startswith("--from pin klt netlist -o "), log)

    def test_a_netlist_that_was_never_written_is_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            make_repo(root, "scratch")
            result = self._run(root, 'exit 0')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            result.stderr,
            f"run-x-flow.sh: expected {root}/out/xschem_out/x.spice"
            " after xschem netlisting\n",
        )


class DriverExtractionTest(unittest.TestCase):
    """The drivers themselves: one definition of the preamble, not five."""

    def test_the_five_drivers_are_the_ones_under_test(self):
        self.assertEqual(
            [d.name for d in DRIVERS],
            [
                "run-cap-rail-demo-flow.sh",
                "run-ldo-erc-flow.sh",
                "run-ldo-layout-flow.sh",
                "run-ldo-lvs-flow.sh",
                "run-trivial-cell-flow.sh",
            ],
        )

    def test_every_driver_sources_the_shared_library(self):
        for driver in DRIVERS:
            with self.subTest(driver=driver.name):
                self.assertIn(
                    'source "$(dirname "${BASH_SOURCE[0]}")/_flow_common.sh"',
                    driver.read_text(),
                    f"{driver.name} does not source _flow_common.sh",
                )

    def test_no_driver_re_inlines_the_shared_preamble(self):
        """The copies are gone, so a future fix lands once rather than five times."""
        for driver in DRIVERS:
            text = driver.read_text()
            for copied in (
                'rev-parse --short HEAD',
                'LAYOUT_DIR="$(cd "$(dirname',
                'pdk find --pdk "$PDK_VARIANT" >/dev/null',
            ):
                with self.subTest(driver=driver.name, copied=copied):
                    self.assertNotIn(
                        copied,
                        text,
                        f"{driver.name} re-inlines {copied!r}; call the"
                        " _flow_common.sh helper instead",
                    )

    def test_no_driver_shells_out_to_raw_xschem(self):
        """Drift 1: `klt netlist` owns the headless xschem invocation.

        A bare `xschem` does not fail when the GUI initialises -- it writes a
        plausible-looking netlist and hangs in the Tk event loop -- so every
        netlisting driver must go through `klt netlist`, which forces the
        headless flags and kills a run that exceeds its timeout. Presence
        checks (`command -v xschem`) are not invocations and are allowed.
        """
        invocation = re.compile(r"(?<![-\w/])xschem(?=\s+-)")
        for driver in DRIVERS:
            for lineno, line in enumerate(driver.read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                with self.subTest(driver=driver.name, line=lineno):
                    self.assertIsNone(
                        invocation.search(code),
                        f"{driver.name}:{lineno} invokes xschem directly"
                        f" instead of `klt netlist`: {line.strip()}",
                    )


if __name__ == "__main__":
    unittest.main()
