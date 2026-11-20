import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import pick as P  # noqa: E402


def line(name, module, hyps, nodes):
    # the real layout (Tengoku scripts/isnad.py Record.FIELDS): isnad1 name module kind hyps vars nodes canonical shape vocab
    return "\t".join(["isnad1", name, module, "eq", str(hyps), "1", str(nodes), "canon", "shape", "vocab"])


LINES = [
    line("L.a", "M.A", 2, 100),
    line("L.b", "M.A", 0, 100),  # no hypothesis
    line("L.c", "M.B", 1, 10),  # too small
    line("L.d", "M.B", 3, 64),
    line("L.a", "M.C", 2, 100),  # a name twice
    "isnad1-deps\tL.x\tM.X\tL.a",
    "garbage",
]


class Pick(unittest.TestCase):
    def test_qualifying_rows(self):
        self.assertEqual(P.qualifying(LINES), [("L.a", "M.A"), ("L.d", "M.B")])

    def test_the_order_is_a_function_of_the_seed(self):
        rows = [(f"n{i}", "M") for i in range(50)]
        self.assertEqual(P.pick(rows, 10, "s"), P.pick(rows, 10, "s"))
        self.assertNotEqual(P.pick(rows, 10, "s"), P.pick(rows, 10, "t"))
        self.assertEqual(len(P.pick(rows, 10, "s")), 10)

    def test_main_writes_both_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "i.tsv").write_text("\n".join(LINES) + "\n")
            self.assertEqual(P.main([str(d / "i.tsv"), "--n", "5", "--seed", "s", "--names", str(d / "n"), "--modules", str(d / "m")]), 0)
            self.assertEqual(sorted((d / "n").read_text().split()), ["L.a", "L.d"])
            self.assertEqual((d / "m").read_text().split(), ["M.A", "M.B"])


if __name__ == "__main__":
    unittest.main()


class ImportTime(unittest.TestCase):
    def test_measure_reports_each_run_and_exit_codes(self):
        import import_time as T

        r = T.measure([sys.executable, "-c", "pass"], 3)
        self.assertEqual(len(r["runs"]), 3)
        self.assertEqual(r["exit_codes"], [0, 0, 0])
        self.assertLessEqual(r["min"], r["median"])
        bad = T.measure([sys.executable, "-c", "raise SystemExit(3)"], 2)
        self.assertEqual(bad["exit_codes"], [3, 3])
        self.assertEqual(T.main(["--runs", "1", "--", sys.executable, "-c", "raise SystemExit(1)"]), 1)
