#!/usr/bin/env python3
"""Tests for spec/check_spec_table.py (#607, #618).

    python3 -m unittest discover -s measurements/tests -t measurements/tests -v

Each case builds a throwaway Git repository holding a tiny README spec table,
a lock and a few decision records, then mutates it. Stdlib only; no PDK,
ngspice or network.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("cst", REPO / "spec" / "check_spec_table.py")
cst = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cst)

TABLE = """# Project

| Parameter | Target | Stretch |
|---|---|---|
| Output | 1.8 V | 1.2 V |
| Load | 0-50 mA | - |
| Area | < 0.1 mm2 | - |

Notes — these are part of the ratified spec, not commentary:

1. **First.** Verified across the
   full matrix.
2. **Second.** Reference error
   is excluded.
5a. **Fifth-a.** Inrush bound
    only to 1 uF.

Trailing paragraph, not a note.
"""

NOTES_EDIT = ("only to 1 uF.", "only to 4.7 uF.")


def dr_text(number: int, status: str, extra: str = "") -> str:
    return "# DR-%03d: t\n\n- **Status**: %s\n- **Date**: 2026-01-01\n%s" % (number, status, extra)


class Repo:
    def __init__(self, tmp: Path):
        self.root = tmp
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        # No detached background gc/maintenance racing temp-dir cleanup.
        self.git("config", "gc.auto", "0")
        self.git("config", "maintenance.auto", "false")
        (tmp / "spec" / "decision-records").mkdir(parents=True)
        self.write("README.md", TABLE)
        self.write_dr("DR-001-old.md", dr_text(1, "ratified"))
        self.write_dr("DR-002-prop.md", dr_text(2, "proposed"))
        self.write_dr("DR-003-superseded.md", dr_text(3, "superseded by DR-001"))

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.root), *a], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write(self, rel, text):
        (self.root / rel).write_text(text, encoding="utf-8")

    def write_dr(self, name, text):
        self.write("spec/decision-records/" + name, text)

    def commit(self, msg="c"):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cst.main([*args, "--root", str(self.root)])
        return rc, out.getvalue() + err.getvalue()

    def lock(self):
        return json.loads((self.root / cst.LOCK).read_text())

    def set_lock(self, obj):
        self.write(cst.LOCK, json.dumps(obj, indent=2, sort_keys=True) + "\n")

    def bootstrap(self):
        assert self.run("--write")[0] == 0
        self.commit("lock")


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.r = Repo(Path(td.name))
        self.r.commit("init")

    def ok(self, *args):
        rc, out = self.r.run(*args)
        self.assertEqual(rc, 0, out)
        return out

    def bad(self, *args, msg):
        rc, out = self.r.run(*args)
        self.assertEqual(rc, 1, out)
        self.assertIn(msg, out)

    def branch(self):
        self.r.git("checkout", "-q", "-b", "pr")


class ParserTests(unittest.TestCase):
    def test_whitespace_and_reorder_same_hashes(self):
        a = cst.table_hashes(cst.parse_table(TABLE))
        t2 = TABLE.replace("| Load | 0-50 mA | - |", "|  Load  |  0-50   mA |   - |")
        lines = t2.splitlines()
        i = lines.index("| Output | 1.8 V | 1.2 V |")
        lines[i], lines[i + 1] = lines[i + 1], lines[i]
        self.assertEqual(a, cst.table_hashes(cst.parse_table("\n".join(lines))))

    def test_value_change_changes_hash(self):
        a = cst.table_hashes(cst.parse_table(TABLE))
        b = cst.table_hashes(cst.parse_table(TABLE.replace("1.8 V", "1.9 V")))
        self.assertNotEqual(a["Output"], b["Output"])
        self.assertEqual(a["Load"], b["Load"])

    def test_duplicate_malformed_absent(self):
        with self.assertRaises(cst.CheckError):
            cst.parse_table(TABLE.replace("| Area |", "| Load |"))
        with self.assertRaises(cst.CheckError):
            cst.parse_table(TABLE.replace("| Area | < 0.1 mm2 | - |", "| Area | < 0.1 mm2 |"))
        with self.assertRaises(cst.CheckError):
            cst.parse_table(TABLE.replace("| Area | < 0.1 mm2 | - |", "| Area |  | - |"))
        with self.assertRaises(cst.CheckError):
            cst.parse_table("no table here\n")
        with self.assertRaises(cst.CheckError):
            cst.parse_table("| Parameter | Target | Stretch |\n|---|---|---|\n\nx\n")

    def test_real_readme_parses_and_matches_lock(self):
        text = (REPO / "README.md").read_text(encoding="utf-8")
        table = cst.parse_table(text)
        self.assertGreater(len(table), 5)
        notes = cst.parse_notes(text)
        # This repo's notes are plain 1.-7.; the 5a-style id is covered by the
        # fixture tests below (NOTE_ID_RE accepts it should one appear).
        self.assertEqual(list(notes), ["1", "2", "3", "4", "5", "6", "7"])
        lock = cst.parse_lock((REPO / cst.LOCK).read_text(encoding="utf-8"))
        self.assertEqual({k: v["hash"] for k, v in lock["rows"].items()},
                         cst.table_hashes(table))
        self.assertEqual({cst.NOTE_PREFIX + k: v["hash"] for k, v in lock["notes"].items()},
                         cst.notes_hashes(notes))

    def test_notes_parse_ids_and_normalization(self):
        n = cst.parse_notes(TABLE)
        self.assertEqual(list(n), ["1", "2", "5a"])
        self.assertEqual(n["1"], "**First.** Verified across the full matrix.")
        ws = TABLE.replace("   full matrix.", "      full   matrix.   ")
        self.assertEqual(n, cst.parse_notes(ws))
        self.assertNotEqual(n["5a"], cst.parse_notes(TABLE.replace(*NOTES_EDIT))["5a"])

    def test_notes_parse_failures(self):
        hdr = "Notes — these are part of the ratified spec, not commentary:"
        bad = {
            "missing section": TABLE.replace(hdr, "Other heading:"),
            "duplicate ids": TABLE.replace("2. **Second.**", "1. **Second.**"),
            "text before first id": TABLE.replace(hdr + "\n\n", hdr + "\n\nstray words\n\n"),
            "unindented continuation": TABLE.replace("   full matrix.", "full matrix."),
            "no notes": TABLE.split(hdr)[0] + hdr + "\n\nTrailing paragraph.\n",
            "empty note": TABLE.replace("2. **Second.** Reference error\n   is excluded.", "2.\n"),
            "two sections": TABLE + "\n" + hdr + "\n\n9. x\n",
        }
        for name, text in bad.items():
            with self.subTest(name):
                with self.assertRaises(cst.CheckError):
                    cst.parse_notes(text)

    def test_note_ledger_namespace_reserved(self):
        with self.assertRaises(cst.CheckError):
            cst.parse_table(TABLE.replace("| Area |", "| note:1 |"))

    def test_unicode_cells_round_trip(self):
        # The lock is byte-sensitive: a µ/°C/±/en-dash cell must survive
        # --write/--check unchanged, and a retyped hyphen is a real amendment.
        uni = TABLE.replace("| Load | 0-50 mA | - |", "| Load | 0–50 mA | ±2 µA @ 5 °C |")
        self.assertEqual(cst.parse_table(uni)["Load"], ("0–50 mA", "±2 µA @ 5 °C"))
        h1 = cst.row_hash("0–50 mA", "±2 µA @ 5 °C")
        h2 = cst.row_hash("0-50 mA", "±2 µA @ 5 °C")
        self.assertNotEqual(h1, h2)


class StatusHelperTests(unittest.TestCase):
    """The ported status helpers: this repo's 3-digit, 3-status vocabulary."""

    def test_status_block_first_line_and_continuations(self):
        text = "# DR-009: t\n\n- **Status**: proposed — detail\n  continued here\n- **Date**: x\n"
        self.assertEqual(cst.status_block(text), "proposed — detail continued here")

    def test_status_block_missing(self):
        self.assertIsNone(cst.status_block("# DR-009: t\n\n- **Date**: x\n"))

    def test_classify_vocabulary_and_emphasis(self):
        for block, want in (
            ("proposed — detail", "proposed"),
            ("**ratified** — ruled", "ratified"),
            ("superseded by DR-002", "superseded"),
        ):
            status, by = cst.classify(9, block)
            self.assertEqual(status, want)
        self.assertEqual(cst.classify(9, "superseded by `DR-002`"), ("superseded", "DR-002"))

    def test_classify_three_digit_superseded_pointer(self):
        # A 4-digit pointer must NOT read as absent: the probe is 3-digit.
        status, by = cst.classify(9, "superseded by DR-012")
        self.assertEqual(by, "DR-012")
        with self.assertRaises(cst.ClassifyError) as cm:
            cst.classify(9, "superseded")
        self.assertIn("superseded by DR-NNN", str(cm.exception))

    def test_classify_rejects_out_of_vocabulary(self):
        # No 'held' and no overrides: an out-of-vocabulary status fails, so the
        # guard can never quietly disagree with check-dr-numbering.sh.
        for bad in ("held", "withdrawn", ""):
            with self.subTest(status=bad):
                with self.assertRaises(cst.ClassifyError):
                    cst.classify(7, bad)
        with self.assertRaises(cst.ClassifyError):
            cst.classify(7, None)
        self.assertEqual(cst.STATUS_OVERRIDES, {})
        self.assertEqual(cst.STATUS_VOCABULARY, ("proposed", "ratified", "superseded"))

    def test_live_decision_records_all_classify(self):
        # The real 13 records must classify under the ported helpers, and the
        # vocabulary must stay in lockstep with check-dr-numbering.sh.
        for p in sorted((REPO / "spec" / "decision-records").glob("DR-[0-9][0-9][0-9]-*.md")):
            number = int(p.name[3:6])
            status, _ = cst.classify(number, cst.status_block(p.read_text(encoding="utf-8")))
            self.assertIn(status, cst.STATUS_VOCABULARY, p.name)


class CurrentTreeTests(Base):
    def test_bootstrap_and_deterministic_write(self):
        self.r.bootstrap()
        before = (self.r.root / cst.LOCK).read_bytes()
        self.assertIn("unchanged", self.ok("--write"))
        self.assertEqual(before, (self.r.root / cst.LOCK).read_bytes())
        self.ok("--check")

    def test_missing_lock_fails(self):
        self.bad("--check", msg="missing")

    def test_stale_lock_fails(self):
        self.r.bootstrap()
        self.r.write("README.md", TABLE.replace("1.8 V", "1.7 V"))
        self.bad("--check", msg="Output")

    def test_invalid_lock_schema_fails(self):
        self.r.bootstrap()
        lock = self.r.lock()
        lock["schema_version"] = 3
        self.r.set_lock(lock)
        self.bad("--check", msg="schema_version")
        for bogus in (1.0, True, "1"):
            with self.subTest(schema_version=bogus):
                lock["schema_version"] = bogus
                self.r.set_lock(lock)
                self.bad("--check", msg="unsupported schema_version")

    def test_lock_hash_tamper_fails(self):
        self.r.bootstrap()
        lock = self.r.lock()
        lock["rows"]["Output"]["target"] = "1.9 V"
        self.r.set_lock(lock)
        self.bad("--check", msg="hash")

    def test_whitespace_and_reorder_pass(self):
        self.r.bootstrap()
        self.r.write("README.md", TABLE.replace("| Load | 0-50 mA | - |", "| Load |   0-50 mA | -   |"))
        self.ok("--check")
        self.ok("--write")


class BaseTests(Base):
    def edit_target(self):
        self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V"))

    def test_unchanged_passes(self):
        self.r.bootstrap()
        self.branch()
        self.ok("--check", "--base", "main")

    def test_missing_ref_fails_closed(self):
        self.r.bootstrap()
        self.bad("--check", "--base", "nope", msg="git")

    def test_empty_base_fails_closed(self):
        # merge queue (#668): an event whose base sha arrives EMPTY must fail
        # explicitly here too, never fall into run_check's `base_ref is None`
        # current-tree branch (an empty string is not None). Mirrors
        # sky130-comparator#332's "merge_group without a base fails
        # explicitly"; the workflow guards the same thing in shell.
        self.r.bootstrap()
        self.bad("--check", "--base", "", msg="git merge-base")

    def test_table_and_lock_edit_with_old_dr_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.bad("--write", "--base", "main", "--dr", "DR-001", msg="existed at base as 'ratified'")
        # hand-edited lock citing an old ratified record
        self.edit_target()
        t = cst.parse_table((self.r.root / "README.md").read_text())
        bh = cst.table_hashes(cst.parse_table(TABLE))["Output"]
        am = [{"row": "Output", "before": bh, "after": cst.row_hash(*t["Output"]), "dr": "DR-001"}]
        self.r.write(cst.LOCK, cst.render_lock(t, cst.parse_notes(TABLE), am))
        self.bad("--check", "--base", "main", msg="DR-001")

    def test_new_dr_proposed_and_ratified_qualify(self):
        for status in ("proposed", "ratified 2026-10-01"):
            with self.subTest(status=status):
                self.setUp()
                self.r.bootstrap()
                self.branch()
                self.edit_target()
                self.r.write_dr("DR-010-new.md", dr_text(10, status))
                self.ok("--write", "--base", "main", "--dr", "DR-010")
                self.ok("--check", "--base", "main")
                self.assertEqual(len(self.r.lock()["amendments"]), 1)

    def test_new_dr_held_or_superseded_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write_dr("DR-010-new.md", dr_text(10, "superseded by DR-001"))
        self.bad("--write", "--base", "main", "--dr", "DR-010",
                 msg="DR-010 is new but its status is 'superseded'")
        # 'held' is not in this repo's vocabulary: the DR fails to classify and
        # the guard fails closed (no STATUS_OVERRIDES to force it through).
        self.r.write_dr("DR-010-new.md", dr_text(10, "held by the operator"))
        self.bad("--write", "--base", "main", "--dr", "DR-010",
                 msg="DR-010: cannot classify Status")

    def test_proposed_to_ratified_qualifies(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write_dr("DR-002-prop.md", dr_text(2, "ratified 2026-10-01"))
        self.ok("--write", "--base", "main", "--dr", "DR-002")
        self.ok("--check", "--base", "main")

    def test_unchanged_proposed_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.bad("--write", "--base", "main", "--dr", "DR-002",
                 msg="existed at base as 'proposed' and is 'proposed' now")

    def test_content_edit_without_status_change_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write_dr("DR-002-prop.md", dr_text(2, "proposed", "more\n"))
        self.bad("--write", "--base", "main", "--dr", "DR-002",
                 msg="existed at base as 'proposed' and is 'proposed' now")

    def test_renamed_dr_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.git("mv", "spec/decision-records/DR-002-prop.md", "spec/decision-records/DR-002-other.md")
        self.r.write_dr("DR-002-other.md", dr_text(2, "ratified"))
        self.bad("--write", "--base", "main", "--dr", "DR-002", msg="renamed")

    def test_already_ratified_or_superseded_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        for dr, st in (("DR-001", "ratified"), ("DR-003", "superseded")):
            self.bad("--write", "--base", "main", "--dr", dr, msg="existed at base as %r" % st)

    def test_out_of_vocabulary_base_status_fails_closed(self):
        # A DR that is 'held' (not a status here) at base fails closed whether
        # it stays held or flips to ratified: base_check cannot classify it.
        self.r.write_dr("DR-004-held.md", dr_text(4, "held by the operator"))
        self.r.commit("held dr")
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.bad("--write", "--base", "main", "--dr", "DR-004",
                 msg="cannot classify Status")
        self.r.write_dr("DR-004-held.md", dr_text(4, "ratified 2026-10-01"))
        self.bad("--write", "--base", "main", "--dr", "DR-004",
                 msg="cannot classify Status")

    def test_missing_and_ambiguous_dr_fail(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.bad("--write", "--base", "main", "--dr", "DR-099", msg="no DR-099-*.md exists")
        self.r.write_dr("DR-010-a.md", dr_text(10, "proposed"))
        self.r.write_dr("DR-010-b.md", dr_text(10, "proposed"))
        self.bad("--write", "--base", "main", "--dr", "DR-010", msg="ambiguous")

    def test_write_requires_dr(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.bad("--write", "--base", "main", msg="--dr")
        self.bad("--write", msg="--base")

    def test_added_removed_renamed_rows(self):
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.r.write("README.md", TABLE.replace("| Area | < 0.1 mm2 | - |", "| Area | < 0.1 mm2 | - |\n| Extra | 1 | - |"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.ok("--check", "--base", "main")
        am = self.r.lock()["amendments"]
        self.assertEqual((am[0]["row"], am[0]["before"]), ("Extra", None))
        # removal retains before hash
        self.setUp()
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.r.write("README.md", TABLE.replace("| Area | < 0.1 mm2 | - |\n", ""))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        am = self.r.lock()["amendments"]
        self.assertEqual((am[0]["row"], am[0]["after"]), ("Area", None))
        self.assertEqual(am[0]["before"], cst.table_hashes(cst.parse_table(TABLE))["Area"])
        self.ok("--check", "--base", "main")
        # rename = removal + addition (two transitions)
        self.setUp()
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.r.write("README.md", TABLE.replace("| Area |", "| Core area |"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.assertEqual(len(self.r.lock()["amendments"]), 2)
        self.ok("--check", "--base", "main")

    def _amended(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write("README.md", (self.r.root / "README.md").read_text().replace("0-50 mA", "0-40 mA"))
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        return self.r.lock()

    def test_multi_row_one_missing_authorization_fails(self):
        lock = self._amended()
        self.assertEqual(len(lock["amendments"]), 2)
        dropped = lock["amendments"].pop()
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main",
                 msg="no fresh amendment for changed/added/removed row(s): %r" % dropped["row"])

    def test_duplicate_or_unrelated_transition_fails(self):
        lock = self._amended()
        dup = dict(lock["amendments"][0])
        lock["amendments"].append(dup)
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="not contiguous")

    def test_unrelated_transition_fails(self):
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        lock = self.r.lock()
        lock["amendments"].append({"row": "Output", "before": "0" * 64, "after": "1" * 64, "dr": "DR-010"})
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="ends at a state that is not the locked row")

    def test_fabricated_amendment_without_table_change_fails(self):
        # Passes parse_lock/_check_chains (a single, contiguous entry ending at
        # the locked row) and cites an eligible new DR, but the table did not
        # change: base_check's transition match is the only rule that stops it.
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        lock = self.r.lock()
        cur = lock["rows"]["Output"]["hash"]
        lock["amendments"].append({"row": "Output", "before": "0" * 64, "after": cur, "dr": "DR-010"})
        self.r.set_lock(lock)
        cst.parse_lock(json.dumps(lock))  # structurally valid on its own
        self.bad("--check", "--base", "main",
                 msg="amendment for 'Output' (00000000 -> %s) is duplicate, unrelated or "
                     "contradicts the table change" % cur[:8])

    def test_amendment_contradicting_table_change_fails(self):
        # Table changes Output A -> B, but the ledger claims a different
        # starting state; chains are fine, the transition is not the real one.
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        t = cst.parse_table((self.r.root / "README.md").read_text())
        new = cst.row_hash(*t["Output"])
        self.r.write(cst.LOCK, cst.render_lock(
            t, cst.parse_notes(TABLE), [{"row": "Output", "before": "0" * 64, "after": new, "dr": "DR-010"}]))
        self.bad("--check", "--base", "main",
                 msg="is duplicate, unrelated or contradicts the table change")

    def test_history_rewrite_or_delete_fails(self):
        self._amended()
        self.r.commit("amend")
        self.r.git("checkout", "-q", "-b", "pr2")
        lock = self.r.lock()
        lock["amendments"][0]["dr"] = "DR-001"
        self.r.set_lock(lock)
        self.bad("--check", "--base", "pr", msg="history")
        lock["amendments"] = []
        self.r.set_lock(lock)
        self.bad("--check", "--base", "pr", msg="history was rewritten, reordered or removed")

    def test_lock_deletion_after_base_lock_fails(self):
        self.r.bootstrap()
        self.branch()
        (self.r.root / cst.LOCK).unlink()
        self.bad("--check", "--base", "main", msg="missing")

    def test_bootstrap_rules(self):
        # base has no lock: bootstrap with unchanged table passes
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.bad("--write", "--base", "main", "--dr", "DR-010",
                 msg="--dr given but base has no lock")
        self.assertFalse((self.r.root / cst.LOCK).exists())
        self.ok("--write")
        self.ok("--check", "--base", "main")
        # ... with a changed table fails
        self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V"))
        self.bad("--write", msg="--base")  # refuses to re-lock a changed table
        self.bad("--write", "--base", "main", msg="bootstrap cannot carry amendments")
        (self.r.root / cst.LOCK).unlink()
        self.ok("--write")  # fresh bootstrap of the changed table
        self.bad("--check", "--base", "main", msg="bootstrap requires an unchanged spec table")
        # ... or a non-empty ledger fails (lock regenerated for the unchanged
        # table so the current-tree check passes and the bootstrap rule is hit)
        self.r.write("README.md", TABLE)
        (self.r.root / cst.LOCK).unlink()
        self.ok("--write")
        lock = self.r.lock()
        lock["amendments"] = [{"row": "Output", "before": None, "after": lock["rows"]["Output"]["hash"], "dr": "DR-002"}]
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="bootstrap lock must have an empty amendments ledger")

    def test_diverged_branches_use_merge_base(self):
        self.r.bootstrap()
        self.branch()
        self.r.git("checkout", "-q", "main")
        # main moves on (changes the table with its own lock+DR) after the branch point
        self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V"))
        self.r.write_dr("DR-010-new.md", dr_text(10, "ratified"))
        self.ok("--write", "--base", "HEAD", "--dr", "DR-010")
        self.r.commit("main moves")
        self.r.git("checkout", "-q", "pr")
        # branch is unchanged vs its merge-base, so it passes despite main's change
        self.ok("--check", "--base", "main")

    def test_merge_checkout_shape(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.r.commit("pr work")
        base_sha = self.r.git("rev-parse", "main")
        self.r.git("checkout", "-q", "main")
        self.r.git("checkout", "-q", "--detach")
        self.r.git("merge", "-q", "--no-ff", "-m", "merge", "pr")
        self.ok("--check", "--base", base_sha)
        self.ok("--check")


class NoteTests(Base):
    """Ratified-note coverage."""

    def edit_note(self, text=None):
        self.r.write("README.md", (text or TABLE).replace(*NOTES_EDIT))

    def v1_lock(self):
        """Table-only legacy lock for the fixture, as written by the old checker."""
        lock = self.r.lock()
        lock.pop("notes", None)
        lock["schema_version"] = 1
        return lock

    # -- current tree ------------------------------------------------------
    def test_note_only_change_with_unchanged_lock_fails(self):
        self.r.bootstrap()
        self.edit_note()
        self.bad("--check", msg="ratified note '5a' changed")
        self.bad("--write", msg="ratified notes differ from lock")

    def test_whitespace_only_note_edit_passes(self):
        self.r.bootstrap()
        self.r.write("README.md", TABLE.replace("   full matrix.", "     full    matrix.  "))
        self.ok("--check")
        self.branch()
        self.ok("--check", "--base", "main")

    def test_lock_note_text_tamper_fails(self):
        self.r.bootstrap()
        lock = self.r.lock()
        lock["notes"]["1"]["text"] = "changed"
        self.r.set_lock(lock)
        self.bad("--check", msg="hash does not match its text")

    def test_candidate_missing_or_legacy_lock_notes_fails(self):
        self.r.bootstrap()
        lock = self.r.lock()
        del lock["notes"]
        self.r.set_lock(lock)
        self.bad("--check", msg="schema_version 2 must have exactly")
        self.r.set_lock(self.v1_lock())
        self.bad("--check", msg="legacy schema_version 1")

    def test_readme_note_section_missing_fails_check(self):
        self.r.bootstrap()
        self.r.write("README.md", TABLE.replace("Notes — these are part", "Other — these are part"))
        self.bad("--check", msg="notes section")

    # -- base-aware ----------------------------------------------------------
    def test_note_and_lock_edit_without_fresh_dr_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_note()
        self.bad("--write", "--base", "main", msg="--dr")
        self.bad("--write", "--base", "main", "--dr", "DR-001", msg="existed at base as 'ratified'")
        self.bad("--write", "--base", "main", "--dr", "DR-002", msg="existed at base as 'proposed'")
        # hand-edited lock with the right transition but an old ratified DR
        t, n = cst.parse_table(TABLE), cst.parse_notes(TABLE.replace(*NOTES_EDIT))
        before = cst.note_hash(cst.parse_notes(TABLE)["5a"])
        am = [{"row": "note:5a", "before": before, "after": cst.note_hash(n["5a"]), "dr": "DR-001"}]
        self.r.write(cst.LOCK, cst.render_lock(t, n, am))
        self.bad("--check", "--base", "main", msg="DR-001")
        # and with no amendment at all
        self.r.write(cst.LOCK, cst.render_lock(t, n, []))
        self.bad("--check", "--base", "main", msg="no fresh amendment for changed/added/removed row(s): note '5a'")

    def test_note_change_with_fresh_dr_passes(self):
        for status in ("proposed", "ratified 2026-10-01"):
            with self.subTest(status=status):
                self.setUp()
                self.r.bootstrap()
                self.branch()
                self.edit_note()
                self.r.write_dr("DR-010-new.md", dr_text(10, status))
                self.ok("--write", "--base", "main", "--dr", "DR-010")
                self.ok("--check", "--base", "main")
                am = self.r.lock()["amendments"]
                self.assertEqual([(a["row"], a["dr"]) for a in am], [("note:5a", "DR-010")])

    def test_proposed_to_ratified_dr_permits_note_change(self):
        self.r.bootstrap()
        self.branch()
        self.edit_note()
        self.r.write_dr("DR-002-prop.md", dr_text(2, "ratified 2026-10-01"))
        self.ok("--write", "--base", "main", "--dr", "DR-002")
        self.ok("--check", "--base", "main")

    def test_old_unchanged_dr_does_not_permit_note_change(self):
        self.r.bootstrap()
        self.branch()
        self.edit_note()
        self.r.write_dr("DR-001-old.md", dr_text(1, "ratified", "more\n"))
        self.bad("--write", "--base", "main", "--dr", "DR-001", msg="existed at base as 'ratified'")

    def test_note_addition_removal_and_id_change(self):
        extra = TABLE.replace("Trailing paragraph", "6. **Six.** New clause.\n\nTrailing paragraph")
        cases = {
            "add": (extra, [("note:6", None)]),
            "remove": (TABLE.replace("2. **Second.** Reference error\n   is excluded.\n", ""),
                       [("note:2", "before")]),
            "rename id": (TABLE.replace("2. **Second.**", "3. **Second.**"),
                          [("note:2", "before"), ("note:3", None)]),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                self.setUp()
                self.r.bootstrap()
                self.branch()
                self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
                self.r.write("README.md", text)
                self.bad("--check", "--base", "main", msg="note")
                self.ok("--write", "--base", "main", "--dr", "DR-010")
                self.ok("--check", "--base", "main")
                am = self.r.lock()["amendments"]
                self.assertEqual(sorted(a["row"] for a in am), sorted(w[0] for w in want))
                for a in am:
                    self.assertEqual(a["before"] is None, a["row"] == "note:6" or a["row"] == "note:3")
                    self.assertEqual(a["after"] is None, name == "remove" or a["row"] == "note:2")

    def test_table_and_note_change_need_both_transitions(self):
        self.r.bootstrap()
        self.branch()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V").replace(*NOTES_EDIT))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        lock = self.r.lock()
        self.assertEqual(sorted(a["row"] for a in lock["amendments"]), ["Output", "note:5a"])
        self.ok("--check", "--base", "main")
        lock["amendments"] = [a for a in lock["amendments"] if a["row"] != "note:5a"]
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="no fresh amendment for changed/added/removed row(s): note '5a'")

    def test_note_history_rewrite_fails(self):
        self.r.bootstrap()
        self.branch()
        self.edit_note()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.r.commit("amend")
        self.r.git("checkout", "-q", "-b", "pr2")
        lock = self.r.lock()
        lock["amendments"][0]["dr"] = "DR-001"
        self.r.set_lock(lock)
        self.bad("--check", "--base", "pr", msg="history")

    # -- schema migration ----------------------------------------------------
    def legacy_base(self):
        """Base commit holding a v1 (table-only) lock."""
        self.r.bootstrap()
        self.r.set_lock(self.v1_lock())
        cst.parse_lock((self.r.root / cst.LOCK).read_text())
        self.r.commit("legacy lock")
        self.branch()

    def test_unchanged_migration_passes_and_preserves_history(self):
        self.r.bootstrap()
        self.branch()
        self.edit_target = lambda: self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V"))
        self.edit_target()
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.r.commit("row amendment")
        history = self.r.lock()["amendments"]
        # downgrade that lock to v1 on main, then migrate on a branch
        self.r.git("checkout", "-q", "main")
        self.r.git("merge", "-q", "--ff-only", "pr")
        self.r.set_lock(self.v1_lock())
        self.r.commit("legacy")
        self.r.git("checkout", "-q", "-b", "mig")
        self.assertIn("legacy schema_version 1", self.r.run("--check")[1])
        self.ok("--write")
        self.assertEqual(self.r.lock()["schema_version"], cst.SCHEMA_VERSION)
        self.assertEqual(self.r.lock()["amendments"], history)
        self.ok("--check", "--base", "main")
        self.ok("--write", "--base", "main")
        self.ok("--check", "--base", "main")

    def test_migration_plus_note_relaxation_fails(self):
        self.legacy_base()
        self.edit_note()
        self.bad("--write", "--base", "main", "--dr", "DR-002",
                 msg="lock schema migration cannot carry ratified-note changes")
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.bad("--write", "--base", "main", "--dr", "DR-010",
                 msg="lock schema migration cannot carry ratified-note changes")
        # hand-built v2 lock claiming a fresh amendment still fails
        t, n = cst.parse_table(TABLE), cst.parse_notes(TABLE.replace(*NOTES_EDIT))
        before = cst.note_hash(cst.parse_notes(TABLE)["5a"])
        am = [{"row": "note:5a", "before": before, "after": cst.note_hash(n["5a"]), "dr": "DR-010"}]
        self.r.write(cst.LOCK, cst.render_lock(t, n, am))
        self.bad("--check", "--base", "main", msg="schema migration 1 -> 2 must not change ratified notes")
        # also with the lock migrated first (no amendment) -> inconsistent
        self.r.write(cst.LOCK, cst.render_lock(t, n, []))
        self.bad("--check", "--base", "main", msg="schema migration")

    def test_migration_of_table_change_with_dr_still_works(self):
        self.legacy_base()
        self.r.write("README.md", TABLE.replace("1.8 V", "1.9 V"))
        self.r.write_dr("DR-010-new.md", dr_text(10, "proposed"))
        self.ok("--write", "--base", "main", "--dr", "DR-010")
        self.ok("--check", "--base", "main")

    def test_notes_lock_deletion_and_downgrade_fail(self):
        self.r.bootstrap()
        self.branch()
        lock = self.r.lock()
        del lock["notes"]
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="notes")
        self.r.set_lock(self.v1_lock())
        self.bad("--check", "--base", "main", msg="legacy schema_version 1")
        # base_check itself rejects a downgraded candidate lock object
        base = cst.read_base(self.r.root, "main")
        t, n = cst.parse_table(TABLE), cst.parse_notes(TABLE)
        with self.assertRaises(cst.CheckError) as cm:
            cst.base_check(base, t, n, self.v1_lock(), {})
        self.assertIn("schema_version 2", str(cm.exception))
        # emptying the notes object is rejected too
        lock = json.loads(cst.render_lock(cst.parse_table(TABLE), cst.parse_notes(TABLE), []))
        lock["notes"] = {}
        self.r.set_lock(lock)
        self.bad("--check", "--base", "main", msg="notes must be a non-empty object")

    def test_base_without_notes_section_fails_closed(self):
        self.r.write("README.md", TABLE.replace("Notes — these are part", "Other — these are part"))
        self.r.commit("no notes at base")
        self.branch()
        self.r.write("README.md", TABLE)
        self.ok("--write")
        self.bad("--check", "--base", "main", msg="base README")

    def test_bootstrap_with_changed_notes_fails(self):
        self.branch()
        self.edit_note()
        self.ok("--write")
        self.bad("--check", "--base", "main", msg="bootstrap requires an unchanged spec table and notes")

    def test_duplicate_ids_and_missing_section_fail_cli(self):
        self.r.write("README.md", TABLE.replace("2. **Second.**", "1. **Second.**"))
        self.bad("--write", msg="duplicate ratified note id")
        self.r.write("README.md", TABLE.replace("Notes — these are part", "Other — these are part"))
        self.bad("--write", msg="notes section")


class CiWorkflowMergeGroupTests(unittest.TestCase):
    """The ci.yml wiring that runs this gate on merge-queue commits (#668).

    Stdlib-only, text-level assertions on .github/workflows/ci.yml (no YAML
    dependency): the merge_group trigger is declared, the single spec-table
    step selects the base per event through env values, and no `${{ }}`
    context is interpolated directly into the gate's command line (an empty
    interpolation would vanish before the gate could fail closed).
    """

    def setUp(self):
        self.text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    def _merge_group_block(self) -> str:
        """Text of the merge_group trigger entry: from its `key:` line
        through its indented continuations, up to the next key. Text-level,
        no YAML dependency; empty when the entry is absent."""
        lines = self.text.splitlines(keepends=True)
        try:
            start = lines.index("  merge_group:\n")
        except ValueError:
            return ""
        out = []
        for ln in lines[start + 1:]:
            if ln.strip() and not ln.startswith("    "):
                break  # next key (or comment) at or above trigger level
            out.append(ln)
        return "".join(out)

    def test_merge_group_trigger_declared(self):
        self.assertIn("  merge_group:", self.text)
        block = self._merge_group_block()
        self.assertTrue(block, "merge_group trigger entry not found in ci.yml")
        self.assertIn("types: [checks_requested]", block)
        # no path/branch filters narrow the trigger away from the queue —
        # scoped to the merge_group entry, not the whole file
        self.assertNotIn("paths:", block)
        self.assertNotIn("branches:", block)

    def test_spec_table_step_selects_base_from_env(self):
        self.assertIn("PR_BASE: ${{ github.event.pull_request.base.sha }}", self.text)
        self.assertIn("MG_BASE: ${{ github.event.merge_group.base_sha }}", self.text)

    def test_no_context_interpolated_into_gate_command(self):
        # the base reaches the gate through env, never `${{ }}` on the
        # command line — any spelling: bare, single- or double-quoted
        self.assertNotRegex(self.text, r"--base\s*['\"]?\$\{\{")

    def test_event_gated_spec_table_steps_gone(self):
        # the two old steps ran the weaker current-tree check on merge_group
        # (silent downgrade) and skipped the authorization diff (silent drop)
        self.assertNotIn("github.event_name != 'pull_request'", self.text)
        self.assertNotIn("if: github.event_name == 'pull_request'", self.text)

    def test_merge_group_empty_base_guard_present(self):
        self.assertIn("refusing to claim the spec table was verified", self.text)


if __name__ == "__main__":
    unittest.main()
