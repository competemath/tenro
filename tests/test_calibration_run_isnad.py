import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "calibration"))
import run_isnad as r  # noqa: E402


def fake(bad: set[str]):
    calls: list[list[str]] = []

    def run(part: list[str]):
        calls.append(part)
        if any(m in bad for m in part):
            return 2, [], "uncaught exception: import failed"
        return 0, [f"isnad1\tT.{m}\t{m}" for m in part], ""

    return run, calls


class RunIsnad(unittest.TestCase):
    def test_names(self):
        self.assertTrue(r.valid("Tengoku.Apap.Basic"))
        self.assertTrue(r.valid("Tengoku.«weird-name».X"))
        self.assertFalse(r.valid("Tengoku..X"))
        self.assertFalse(r.valid(""))
        self.assertFalse(r.valid("Tengoku.X."))

    def test_a_bad_module_costs_only_itself(self):
        run, calls = fake({"B"})
        recs, failed = r.run_all(["A", "B", "C", "D", "E"], run, batch=3, jobs=1)
        self.assertEqual([x.split("\t")[2] for x in recs], ["A", "C", "D", "E"])
        self.assertEqual([m for m, _ in failed], ["B"])
        self.assertIn(["B"], calls)  # tried alone after its batch stopped

    def test_unnamed_module_is_not_passed_on(self):
        run, calls = fake(set())
        recs, failed = r.run_all(["A", "", "Tengoku..X"], run, batch=25, jobs=2)
        self.assertEqual(len(recs), 1)
        self.assertEqual({m for m, _ in failed}, {"", "Tengoku..X"})
        self.assertEqual(calls, [["A"]])

    def test_order_is_the_order_of_the_list_with_jobs(self):
        run, _ = fake(set())
        mods = [f"M{i}" for i in range(10)]
        recs, _ = r.run_all(mods, run, batch=2, jobs=4)
        self.assertEqual([x.split("\t")[2] for x in recs], mods)

    def test_exit_code_one_is_not_a_failure(self):
        recs, failed = r.batch_records(["A"], lambda part: (1, ["isnad1\tT.A\tA"], ""))
        self.assertEqual((len(recs), failed), (1, []))


if __name__ == "__main__":
    unittest.main()


class OnlyTheListedTheorems(unittest.TestCase):
    def test_names_by_module_and_the_arguments_of_a_batch(self):
        with tempfile.TemporaryDirectory() as d:
            meta = Path(d) / "meta.tsv"
            meta.write_text("T.b\tid1\tL\tM1\nT.a\tid2\tL\tM1\nT.c\tid3\tL2\tM2\nshort\n", encoding="utf-8")
            by = r.names_by_module(meta)
            self.assertEqual(by, {"M1": ["T.b", "T.a"], "M2": ["T.c"]})
            self.assertEqual(r.name_args(["M1"], by), ("--name", "T.a", "--name", "T.b"))
            self.assertEqual(r.name_args(["M2", "M1", "M9"], by), ("--name", "T.a", "--name", "T.b", "--name", "T.c"))
            self.assertEqual(r.name_args(["M9"], by), ())
            self.assertEqual(r.name_args(["M1"], None), (), "without a table the whole module is read")


class Timeout(unittest.TestCase):
    def test_a_process_over_the_limit_is_a_failure_and_the_batch_is_retried_module_by_module(self):
        with tempfile.TemporaryDirectory() as d:
            lake = Path(d) / "lake"
            lake.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
            lake.chmod(lake.stat().st_mode | stat.S_IXUSR)
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{d}:{old}"
            try:
                code, lines, err = r.run_exe(["A"], "x", timeout=0.3)
                self.assertEqual((code, lines), (124, []))
                self.assertIn("timeout", err)
                recs, failed = r.run_all(["A", "B"], lambda part: r.run_exe(part, "x", timeout=0.3), batch=2, jobs=1)
            finally:
                os.environ["PATH"] = old
        self.assertEqual(recs, [])
        self.assertEqual([m for m, _ in failed], ["A", "B"])
