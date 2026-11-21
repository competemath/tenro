import json
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

    def manifests(self, d: Path) -> Path:
        """a tiny data/intake: three libraries, one with a `_root_` name, one row without a tree module, one name that another library has too"""
        root = d / "intake"
        rows = {
            "alpha": [
                ("A.one", "Tengoku.Alpha.X"),
                ("A.two", "Tengoku.Alpha.X"),
                ("A.three", "Tengoku.Alpha.Y"),
                ("_root_.A.four", "Tengoku.Alpha.Y"),
            ],
            "beta": [("B.one", "Tengoku.Beta.Z"), ("A.one", "Tengoku.Beta.Z"), ("B.nomodule", "")],
            "gamma": [("G.one", "Tengoku.Gamma.W")],
        }
        for lib, rs in rows.items():
            (root / lib).mkdir(parents=True)
            (root / lib / "manifest.jsonl").write_text(
                "".join(json.dumps({"name": n, "module": m, "library": lib}) + "\n" for n, m in rs), encoding="utf-8"
            )
        return root

    def test_a_sample_over_the_manifests_spreads_over_the_libraries(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.manifests(Path(d))
            out = P.pick_manifests(root, ["all"], 100, "s")
            names = [r["name"] for r in out]
            self.assertEqual(
                sorted(names), ["A.one", "A.three", "A.two", "B.one", "G.one"]
            )  # no _root_ name, no row without a module, A.one once (alpha has it first)
            self.assertEqual({r["library"] for r in out if r["name"] == "A.one"}, {"alpha"})
            self.assertTrue(all(r["id"] is None for r in out))
            few = P.pick_manifests(root, ["all"], 3, "s")
            self.assertEqual(
                {r["library"] for r in few}, {"alpha", "beta", "gamma"}
            )  # the libraries in turn: each of them is in a sample of three
            self.assertEqual(P.pick_manifests(root, ["all"], 3, "s"), few)  # the same seed, the same sample
            (root / "delta").mkdir()
            (root / "delta" / "manifest.jsonl").write_text(
                "".join(json.dumps({"name": f"D.n{i}", "module": "Tengoku.Delta.M"}) + "\n" for i in range(30)), encoding="utf-8"
            )
            self.assertNotEqual(
                [r["name"] for r in P.pick_manifests(root, ["delta"], 10, "s")],
                [r["name"] for r in P.pick_manifests(root, ["delta"], 10, "t")],
            )
            self.assertEqual({r["library"] for r in P.pick_manifests(root, ["beta", "gamma"], 100, "s")}, {"beta", "gamma"})
            with self.assertRaises(SystemExit):
                P.pick_manifests(root, ["nosuch"], 3, "s")

    def test_main_with_manifests_writes_the_three_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            root = self.manifests(d)
            args = ["--manifests", str(root), "--libraries", "all", "--n", "4", "--seed", "s"]
            self.assertEqual(P.main([*args, "--names", str(d / "n"), "--modules", str(d / "m"), "--sample", str(d / "s.jsonl")]), 0)
            sample = [json.loads(ln) for ln in (d / "s.jsonl").read_text().splitlines()]
            self.assertEqual(len(sample), 4)
            self.assertEqual(sorted(sample[0]), ["id", "library", "module", "name"])
            self.assertEqual((d / "n").read_text().split(), [r["name"] for r in sample])
            self.assertEqual((d / "m").read_text().split(), sorted({r["module"] for r in sample}))

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
