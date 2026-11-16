import sys
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
