"""tools/promote/faithful.py: a replayed snapshot against the environment it was exported from, by the records of `tengai-typeinfo --hashes`."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import faithful as F  # noqa: E402


def rec(name, kind, thash, tsize=5, vhash=None, lparams=()):
    r = {"n": name.split("."), "kind": kind, "thash": thash, "tsize": tsize, "lparams": list(lparams)}
    if vhash is not None:
        r["vhash"] = vhash
    return r


def table(*records):
    return {".".join(r["n"]): r for r in records}


SOURCE = table(
    rec("A.thm", "thm", 11, vhash=1001),  # stands as an axiom in the snapshot
    rec("A.kept", "thm", 12, vhash=1002),  # kept with its proof
    rec("A.def", "def", 13, vhash=1003),
    rec("A.ind", "induct", 14),
    rec("A.univ", "def", 15, vhash=1004, lparams=["u"]),
)
SNAPSHOT = table(
    rec("A.thm", "axiom", 11),
    rec("A.kept", "thm", 12, vhash=1002),
    rec("A.def", "def", 13, vhash=1003),
    rec("A.ind", "induct", 14),
    rec("A.univ", "def", 15, vhash=1004, lparams=["u"]),
)


class Compare(unittest.TestCase):
    def test_a_faithful_snapshot_passes_and_the_stubs_are_counted(self):
        r = F.compare(SOURCE, SNAPSHOT)
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual(
            (r["compared"], r["statement_stubs"], r["kept_with_value"], r["same_with_value"], r["same_without_value"]), (5, 1, 1, 2, 1)
        )
        self.assertEqual(r["refused_and_stubbed"], 0)
        self.assertEqual(r["by_kind"]["thm->axiom"], 1)

    def test_a_theorem_that_stands_as_an_axiom_of_another_type_is_a_problem(self):
        snap = dict(SNAPSHOT)
        snap["A.thm"] = rec("A.thm", "axiom", 99)
        r = F.compare(SOURCE, snap)
        self.assertFalse(r["passed"])
        self.assertEqual(r["problem_counts"], {"type_differs": 1})
        self.assertEqual(r["problems"]["type_differs"][0]["name"], "A.thm")

    def test_a_type_with_the_same_hash_and_another_size_is_a_problem(self):
        snap = dict(SNAPSHOT)
        snap["A.def"] = rec("A.def", "def", 13, tsize=6, vhash=1003)
        self.assertEqual(F.compare(SOURCE, snap)["problem_counts"], {"type_differs": 1})

    def test_a_kept_proof_or_a_definition_with_another_value_is_a_problem(self):
        snap = dict(SNAPSHOT)
        snap["A.kept"] = rec("A.kept", "thm", 12, vhash=7)
        snap["A.def"] = rec("A.def", "def", 13, vhash=8)
        r = F.compare(SOURCE, snap)
        self.assertEqual(r["problem_counts"], {"value_differs": 2})

    def test_the_value_of_a_stub_is_not_asked_for(self):
        snap = dict(SNAPSHOT)
        snap["A.thm"] = rec("A.thm", "axiom", 11)  # no vhash: the proof of the theorem is not in the snapshot
        self.assertTrue(F.compare(SOURCE, snap)["passed"])

    def test_a_declaration_the_kernel_refused_and_stubbed_is_counted_apart(self):
        snap = dict(SNAPSHOT)
        snap["A.def"] = rec("A.def", "axiom", 13)  # a definition the replay could not check
        r = F.compare(SOURCE, snap)
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual((r["refused_and_stubbed"], r["statement_stubs"]), (1, 1))

    def test_any_other_change_of_kind_is_a_problem(self):
        snap = dict(SNAPSHOT)
        snap["A.ind"] = rec("A.ind", "def", 14, vhash=5)
        snap["A.def"] = rec("A.def", "thm", 13, vhash=1003)
        r = F.compare(SOURCE, snap)
        self.assertEqual(r["problem_counts"], {"kind_changed": 2})
        self.assertEqual({x["name"] for x in r["problems"]["kind_changed"]}, {"A.ind", "A.def"})

    def test_universe_parameters_are_compared(self):
        snap = dict(SNAPSHOT)
        snap["A.univ"] = rec("A.univ", "def", 15, vhash=1004, lparams=["v"])
        self.assertEqual(F.compare(SOURCE, snap)["problem_counts"], {"universe_parameters_differ": 1})

    def test_a_name_the_snapshot_lacks_is_a_problem_and_a_name_missing_in_both_is_not(self):
        snap = dict(SNAPSHOT)
        del snap["A.ind"]
        r = F.compare(SOURCE, snap)
        self.assertEqual(r["problem_counts"], {"missing_in_snapshot": 1})
        both = {"n": ["No", "such"], "missing": True}
        src, snap2 = dict(SOURCE), dict(SNAPSHOT)
        src["No.such"] = snap2["No.such"] = both
        r = F.compare(src, snap2)
        self.assertTrue(r["passed"])
        self.assertEqual(r["absent_in_both"], 1)
        snap3 = dict(snap2)
        snap3["A.def"] = {"n": ["A", "def"], "missing": True}  # the source has it, the snapshot reports it missing
        self.assertEqual(F.compare(src, snap3)["problem_counts"], {"missing_in_snapshot": 1})

    def test_only_in_snapshot_asks_about_the_names_the_snapshot_lists(self):
        snap = {k: v for k, v in SNAPSHOT.items() if k in ("A.thm", "A.kept")}  # a run that replayed some of the layers
        self.assertFalse(F.compare(SOURCE, snap)["passed"])  # by default the others are missing
        r = F.compare(SOURCE, snap, only_in_snapshot=True)
        self.assertTrue(r["passed"], r["problems"])
        self.assertEqual((r["compared"], r["not_asked"], r["names"]), (2, 3, 2))
        extra = dict(snap)
        extra["A.new"] = rec("A.new", "def", 1, vhash=1)  # a name the snapshot lists and the source lacks is still a problem
        self.assertEqual(F.compare(SOURCE, extra, only_in_snapshot=True)["problem_counts"], {"snapshot_has_what_the_source_lacks": 1})

    def test_nothing_compared_is_not_a_pass(self):
        self.assertFalse(F.compare({}, {})["passed"])

    def test_the_examples_are_limited_but_the_counts_are_not(self):
        src = table(*[rec(f"B.t{i}", "thm", i, vhash=i) for i in range(30)])
        snap = table(*[rec(f"B.t{i}", "axiom", i + 1000) for i in range(30)])
        r = F.compare(src, snap, examples=5)
        self.assertEqual(r["problem_counts"], {"type_differs": 30})
        self.assertEqual(len(r["problems"]["type_differs"]), 5)


class Command(unittest.TestCase):
    def write(self, path: Path, tbl: dict) -> None:
        path.write_text("".join(json.dumps(r) + "\n" for r in tbl.values()), encoding="utf-8")

    def test_exit_zero_and_a_report_when_faithful_and_one_when_not(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.write(d / "s.jsonl", SOURCE)
            self.write(d / "t.jsonl", SNAPSHOT)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(F.main([str(d / "s.jsonl"), str(d / "t.jsonl"), "--out", str(d / "r.json")]), 0)
            self.assertIn("no problem: passed", out.getvalue())
            self.assertTrue(json.loads((d / "r.json").read_text())["passed"])
            bad = dict(SNAPSHOT)
            bad["A.thm"] = rec("A.thm", "axiom", 99)
            self.write(d / "u.jsonl", bad)
            with contextlib.redirect_stdout(io.StringIO()) as o2:
                self.assertEqual(F.main([str(d / "s.jsonl"), str(d / "u.jsonl")]), 1)
            self.assertIn("PROBLEMS", o2.getvalue())


if __name__ == "__main__":
    unittest.main()
