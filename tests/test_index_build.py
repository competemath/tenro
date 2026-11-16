import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "index"))
import build  # noqa: E402

RECORDS = [("A.t", "id1", "s1"), ("B.t", "id1", "s1"), ("C.u", "id2", "s1"), ("D.v", "id3", "s2")]
DEPS = [("A.t", ["C.u", "Ext.lemma"]), ("B.t", ["C.u"]), ("D.v", ["A.t", "B.t"]), ("Ghost.x", ["C.u"])]


class IndexTest(unittest.TestCase):
    def setUp(self):
        self.b = build.build(RECORDS, DEPS)

    def test_shape_index_prefilters_ids(self):
        self.assertEqual(self.b["shape"], [{"shape": "s1", "ids": ["id1", "id2"]}, {"shape": "s2", "ids": ["id3"]}])
        self.assertEqual(self.b["stats"]["shape_collisions"], 1)

    def test_graph_is_by_statement_id_and_unions_the_theorems_of_a_statement(self):
        g = {row["id"]: row["deps"] for row in self.b["graph"]}
        self.assertEqual(g, {"id1": ["id2"], "id2": [], "id3": ["id1"]})  # D.v depends on A.t and B.t, which state the same thing
        self.assertEqual(self.b["stats"]["dropped_dependencies"], 1)  # Ext.lemma has no id here

    def test_names_live_only_in_the_names_file(self):
        self.assertEqual(self.b["names"][0], {"id": "id1", "names": ["A.t", "B.t"]})
        with tempfile.TemporaryDirectory() as d:
            stats = build.write(Path(d), self.b)
            for f in ("shape.jsonl", "graph.jsonl"):
                text = (Path(d) / f).read_text()
                for n in ("A.t", "B.t", "C.u", "D.v"):
                    self.assertNotIn(n, text)
            self.assertIn("A.t", (Path(d) / "names.jsonl").read_text())
            self.assertEqual(set(stats["sha256"]), {"shape.jsonl", "graph.jsonl", "names.jsonl"})
            self.assertEqual(json.loads((Path(d) / "stats.json").read_text())["statements"], 3)

    def test_deterministic_whatever_the_input_order(self):
        again = build.build(list(reversed(RECORDS)), list(reversed(DEPS)))
        self.assertEqual(again, self.b)


STUB = """
DEPS_TAG = "isnad1-deps"
class Record:
    def __init__(self, line):
        p = line.split("\\t")
        self.name, self.id, self.shape = p[1], p[2], p[3]
def parse_deps_line(line):
    p = line.split("\\t")
    return p[1], p[2], p[3:]
"""


class LoaderTest(unittest.TestCase):
    def test_load_isnad_reads_records_and_deps_with_the_tengoku_module(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "common"))
        import tengoku_isnad

        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "isnad.py"
            stub.write_text(STUB)
            recs, deps = tengoku_isnad.load_isnad(stub, ["isnad1\tA.t\tid1\ts1", "noise"], ["isnad1-deps\tA.t\tM\tB.u\tC.v", "noise"])
        self.assertEqual(recs, [("A.t", "id1", "s1")])
        self.assertEqual(deps, [("A.t", ["B.u", "C.v"])])


if __name__ == "__main__":
    unittest.main()
