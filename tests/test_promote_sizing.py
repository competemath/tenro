import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
import sizing as S  # noqa: E402


def rec(name, closure, modules):
    return {"name": name, "closure": closure, "modules": modules}


CORE_MODS = {"Nat.add_comm": "Init.Data.Nat.Basic", "List.map": "Init.Data.List.Basic", "Std.HashMap": "Std.Data.HashMap.Basic"}


class Core(unittest.TestCase):
    def test_module_prefixes(self):
        self.assertTrue(S.in_core("Init", S.CORE))
        self.assertTrue(S.in_core("Init.Data.Nat", S.CORE))
        self.assertTrue(S.in_core("Lean.Elab", S.CORE))
        self.assertFalse(S.in_core("Initial.Foo", S.CORE))  # a prefix of the string is not a prefix of the module
        self.assertFalse(S.in_core("Tengoku.Algebra.Group", S.CORE))


class Outside(unittest.TestCase):
    def test_core_constants_cost_nothing_and_unknown_ones_are_not_core(self):
        r = rec("t", ["Nat.add_comm", "Group.mul_one", "Mystery.c"], {**CORE_MODS, "Group.mul_one": "Tengoku.Algebra.Group.Defs"})
        out, unplaced = S.outside_core(r, S.CORE)
        self.assertEqual(out, {"Group.mul_one", "Mystery.c"})
        self.assertEqual(unplaced, 1)


class Analyse(unittest.TestCase):
    def records(self):
        mods = {**CORE_MODS, "A.x": "Tengoku.A", "A.y": "Tengoku.A", "B.z": "Tengoku.B"}
        return [
            rec("t1", ["Nat.add_comm", "List.map"], mods),  # core closed
            rec("t2", ["A.x", "Nat.add_comm"], mods),
            rec("t3", ["A.x", "A.y"], mods),  # shares A.x with t2
            rec("t4", ["B.z"], mods),
        ]

    def test_counts_and_distribution(self):
        r = S.analyse(self.records(), steps=(1, 2, 4))
        self.assertEqual(r["theorems"], 4)
        self.assertEqual(r["core_closed"], 1)
        self.assertEqual(r["per_theorem"], {"min": 0, "median": 1, "p90": 2, "max": 2})
        self.assertEqual(r["unplaced"], 0)

    def test_the_curve_counts_distinct_constants_and_the_sharing(self):
        r = S.analyse(self.records(), steps=(1, 2, 3, 4))
        got = {c["theorems"]: (c["distinct"], c["sum_of_parts"]) for c in r["curve"]}
        self.assertEqual(got, {1: (0, 0), 2: (1, 1), 3: (2, 3), 4: (3, 4)})
        last = r["curve"][-1]
        self.assertEqual(last["share"], 0.75)  # 3 distinct constants for 4 constant-uses

    def test_a_step_beyond_the_file_is_dropped_and_the_whole_file_is_always_a_point(self):
        r = S.analyse(self.records(), steps=(1, 1000))
        self.assertEqual([c["theorems"] for c in r["curve"]], [1, 4])

    def test_empty_input(self):
        r = S.analyse([])
        self.assertEqual((r["theorems"], r["curve"], r["core_closed"]), (0, [], 0))

    def test_main_reads_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.jsonl"
            p.write_text("".join(json.dumps(x) + "\n" for x in self.records()))
            self.assertEqual(S.main([str(p), "--steps", "2"]), 0)


if __name__ == "__main__":
    unittest.main()
