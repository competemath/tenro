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


class Select(unittest.TestCase):
    def rows(self):
        r = []
        for g in range(10):
            r += [
                (f"A{g}.t", f"id{g}", "libA", "M"),
                (f"B{g}.t", f"id{g}", "libB", "M"),
                (f"C{g}.t", f"id{g}", "libA", "M"),
                (f"D{g}.t", f"id{g}", "libC", "M"),
                (f"E{g}.t", f"id{g}", "libD", "M"),
            ]
        r += [("S1.t", "same", "libA", "M"), ("S2.t", "same", "libA", "M")]  # one library only: alias by rule 1, no closure needed
        return r

    def test_single_library_groups_are_not_selected_and_are_counted(self):
        chosen, stats = groups.select_groups(self.rows(), 100)
        self.assertEqual({r[1] for r in chosen} & {"same"}, set())
        self.assertEqual((stats["groups"], stats["single_library_groups"], stats["cross_library_groups"]), (11, 1, 10))

    def test_sample_is_deterministic_capped_and_members_cut_with_one_per_library_first(self):
        a, s = groups.select_groups(self.rows(), 3)
        self.assertEqual(a, groups.select_groups(list(reversed(self.rows())), 3)[0])
        self.assertEqual(s["selected_groups"], 3)
        self.assertEqual(len(a), 12)  # 4 members each
        for gid in {r[1] for r in a}:
            libs = {r[2] for r in a if r[1] == gid}
            self.assertEqual(libs, {"libA", "libB", "libC", "libD"})  # the four libraries, not two theorems of libA


class Shards(unittest.TestCase):
    ROWS = [(f"T.n{i}", f"id{i % 17}", f"L{i % 3}", f"M{i % 5}") for i in range(200)]

    def test_the_shards_partition_the_rows_and_keep_a_group_whole(self):
        parts = [groups.shard_rows(self.ROWS, 4, k) for k in range(4)]
        self.assertEqual(sorted(r for p in parts for r in p), sorted(self.ROWS))
        homes = {}
        for k, p in enumerate(parts):
            for r in p:
                homes.setdefault(r[1], set()).add(k)
        self.assertTrue(all(len(v) == 1 for v in homes.values()), "an id sits in two shards")

    def test_it_is_deterministic_and_a_bad_index_is_an_error(self):
        self.assertEqual(groups.shard_rows(self.ROWS, 3, 1), groups.shard_rows(list(self.ROWS), 3, 1))
        with self.assertRaises(ValueError):
            groups.shard_rows(self.ROWS, 3, 3)
        with self.assertRaises(ValueError):
            groups.shard_rows(self.ROWS, 3, -1)


if __name__ == "__main__":
    unittest.main()
