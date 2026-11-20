import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import compare_ids as C  # noqa: E402

ISNAD_PY = """
VERSION = "1"
class Record:
    def __init__(self, line):
        p = line.rstrip("\\n").split("\\t")
        if len(p) != 10 or p[0] != "isnad1":
            raise ValueError(line)
        self.name, self.module, self.kind = p[1], p[2], p[3]
        self.hyps, self.vars, self.nodes, self.canonical = int(p[4]), int(p[5]), int(p[6]), p[7]
    @property
    def id(self):
        return f"{self.kind}.{self.hyps}h{self.vars}v.{self.canonical}"
"""


def line(name, canonical, hyps=1):
    # the real ten-column layout: isnad1 name module kind hyps vars nodes canonical shape vocab
    return "\t".join(["isnad1", name, "M", "eq", str(hyps), "1", "40", canonical, "shape", "vocab"])


class Compare(unittest.TestCase):
    def test_equal_different_and_missing(self):
        r = C.compare(["a", "b", "c", "d"], {"a": "x", "b": "y", "c": "z"}, {"a": "x", "b": "Y", "d": "w"})
        self.assertEqual(r["equal"], 1)
        self.assertEqual(r["different"], [{"name": "b", "source": "y", "replayed": "Y"}])
        self.assertEqual(r["missing_in_replayed"], ["c"])
        self.assertEqual(r["missing_in_source"], ["d"])
        self.assertFalse(r["ok"])

    def test_drift_is_the_same_statement_with_other_hyps_or_size(self):
        src = {"a": "dvd.1h3v.s6.397d2ae1b629", "b": "isiso.1h6v.s7.dd8b3fd48240", "c": "eq.1h1v.s5.aaaaaaaaaaaa"}
        rep = {"a": "dvd.1h3v.s5.397d2ae1b629", "b": "isiso.2h6v.s7.dd8b3fd48240", "c": "eq.1h1v.s5.bbbbbbbbbbbb"}
        r = C.compare(["a", "b", "c"], src, rep)
        self.assertEqual([d["name"] for d in r["drift"]], ["a", "b"])
        self.assertEqual([d["name"] for d in r["different"]], ["c"])  # another canonical hash: a changed statement
        self.assertFalse(r["ok"])
        r2 = C.compare(["a", "b"], src, rep)
        self.assertTrue(r2["ok"])
        self.assertEqual(len(r2["drift"]), 2)
        # another number of variables is not drift
        r3 = C.compare(["a"], {"a": "dvd.1h3v.s6.397d2ae1b629"}, {"a": "dvd.1h4v.s6.397d2ae1b629"})
        self.assertEqual(len(r3["different"]), 1)

    def test_all_equal_is_ok(self):
        r = C.compare(["a"], {"a": "x"}, {"a": "x"})
        self.assertTrue(r["ok"])

    def test_main_with_files(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "isnad.py").write_text(ISNAD_PY)
            (d / "names.txt").write_text("T.a\nT.b\n")
            (d / "src.tsv").write_text(
                "\n".join([line("T.a", "c1"), line("T.b", "c2", hyps=2), line("T.other", "c9"), "isnad1-deps\tT.a\tM\tX"]) + "\n"
            )
            (d / "rep.tsv").write_text("\n".join([line("T.a", "c1"), line("T.b", "c2", hyps=2)]) + "\n")
            args = [
                "--isnad-py",
                str(d / "isnad.py"),
                "--names",
                str(d / "names.txt"),
                "--source",
                str(d / "src.tsv"),
                "--replayed",
                str(d / "rep.tsv"),
                "--out",
                str(d / "r.json"),
            ]
            self.assertEqual(C.main(args), 0)
            self.assertEqual(json.loads((d / "r.json").read_text())["equal"], 2)
            # a restated theorem is caught
            (d / "rep.tsv").write_text("\n".join([line("T.a", "c1"), line("T.b", "c2-restated", hyps=2)]) + "\n")
            self.assertEqual(C.main(args), 1)


if __name__ == "__main__":
    unittest.main()
