import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "calibration"))
import groups  # noqa: E402


class FakeRecord:
    def __init__(self, line):
        self.name, self.module, self.id = line.split()[1:4]


class GroupsTest(unittest.TestCase):
    def test_lib_of(self):
        self.assertEqual(groups.lib_of("Tengoku.Apap.Basic.X"), "Apap")
        self.assertEqual(groups.lib_of("Init.Core"), "Init")

    def test_scan_keeps_only_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "Tengoku" / "A").mkdir(parents=True)
            (root / "Tengoku" / "A" / "X.lean").write_text(
                "/-- t\n@isnad1 id=eq.1h1v.s4.aaa from=seed src=0 shape=1 vocab=2 -/\ntheorem a : True := trivial\n"
            )
            (root / "Tengoku" / "B.lean").write_text(
                "/-- @isnad1 id=eq.1h1v.s4.aaa from=translated src=- shape=1 vocab=2 -/\ntheorem b : True := trivial\n"
                "/-- @isnad1 id=eq.0h0v.s1.bbb from=seed src=0 shape=1 vocab=2 -/\ntheorem c : True := trivial\n"
            )
            r = groups.scan(root)
        self.assertEqual(r["tags_read"], 3)
        self.assertEqual(r["distinct_ids"], 2)
        self.assertEqual(r["dup"], {"eq.1h1v.s4.aaa": ["Tengoku.A.X", "Tengoku.B"]})
        self.assertEqual(r["modules"], ["Tengoku.A.X", "Tengoku.B"])

    def test_meta_rows_filters_and_sorts(self):
        lines = ["isnad1 T.z Tengoku.B.M id1", "isnad1 T.a Tengoku.A.M id1", "isnad1 T.q Tengoku.A.M id2", "noise"]
        rows = groups.meta_rows(lines, {"id1"}, FakeRecord)
        self.assertEqual(rows, [("T.a", "id1", "A", "Tengoku.A.M"), ("T.z", "id1", "B", "Tengoku.B.M")])


if __name__ == "__main__":
    unittest.main()
