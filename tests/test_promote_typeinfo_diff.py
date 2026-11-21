import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import typeinfo_diff as T  # noqa: E402


def info(name, size=40, mdata=0, binders=None, type_="forall x, Eq x x"):
    return {
        "n": name.split("."),
        "size": size,
        "mdata": mdata,
        "binders": binders if binders is not None else [{"name": "x", "info": "default", "head": "Nat"}],
        "type": type_,
    }


class Diff(unittest.TestCase):
    def one(self, a, b):
        return T.diff_one(a, b)

    def test_equal_types_are_the_same(self):
        d = self.one(info("A.b"), info("A.b"))
        self.assertEqual(d["verdict"], "same")
        self.assertIsNone(d["first_binder_difference"])
        self.assertIsNone(d["type_difference"])

    def test_mdata_nodes_the_exporter_dropped_are_named_as_the_reason(self):
        d = self.one(info("A.b", size=33, mdata=2), info("A.b", size=31, mdata=0))
        self.assertEqual(d["verdict"], "differs: mdata nodes, node count")
        self.assertEqual((d["size"], d["mdata"]), ([33, 31], [2, 0]))

    def test_a_binder_name_or_annotation_is_found_by_position(self):
        a = info("A.b", binders=[{"name": "x", "info": "default", "head": "Nat"}, {"name": "h", "info": "implicit", "head": "Eq"}])
        b = info("A.b", binders=[{"name": "x", "info": "default", "head": "Nat"}, {"name": "h", "info": "default", "head": "Eq"}])
        d = self.one(a, b)
        self.assertIn("binders", d["verdict"])
        self.assertEqual(d["first_binder_difference"]["index"], 1)
        self.assertEqual(d["first_binder_difference"]["source"]["info"], "implicit")

    def test_one_binder_more_is_a_difference_at_the_end_of_the_shorter(self):
        d = self.one(info("A.b"), info("A.b", binders=[]))
        self.assertEqual(
            d["first_binder_difference"], {"index": 0, "source": {"name": "x", "info": "default", "head": "Nat"}, "replayed": None}
        )

    def test_the_type_text_says_where_it_parts(self):
        d = self.one(info("A.b", type_="fun a => Eq a 1"), info("A.b", type_="fun a => Eq a 2"))
        self.assertEqual(d["type_difference"]["at"], 14)
        self.assertEqual(d["verdict"], "differs: type text")

    def test_a_name_missing_on_one_side_is_missing_and_is_not_a_crash(self):
        self.assertEqual(self.one(info("A.b"), {"n": ["A", "b"], "missing": True})["verdict"], "missing")
        self.assertEqual(T.report({"A.b": info("A.b")}, {})["A.b"]["replayed_missing"], True)


class Files(unittest.TestCase):
    def test_the_command_line_prints_and_writes_the_report(self):
        with tempfile.TemporaryDirectory() as d:
            src, rep, out = Path(d) / "s.jsonl", Path(d) / "r.jsonl", Path(d) / "out.json"
            src.write_text(json.dumps(info("Usa.gcd", size=33, mdata=1)) + "\n" + json.dumps(info("B.c")) + "\n")
            rep.write_text(json.dumps(info("Usa.gcd", size=32, mdata=0)) + "\n" + json.dumps(info("B.c")) + "\n")
            self.assertEqual(T.main([str(src), str(rep), "--out", str(out)]), 0)
            report = json.loads(out.read_text())
            self.assertEqual(report["B.c"]["verdict"], "same")
            self.assertEqual(report["Usa.gcd"]["verdict"], "differs: mdata nodes, node count")
            text = T.render(report)
            self.assertIn("Usa.gcd: differs: mdata nodes, node count", text)
            self.assertIn("nodes 33 -> 32, mdata 1 -> 0", text)


if __name__ == "__main__":
    unittest.main()
