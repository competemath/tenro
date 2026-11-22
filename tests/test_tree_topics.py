"""tools/promote/tree_topics.py: the topics of a layered snapshot of a whole tree, from the theorems of each module."""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "promote"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "closure"))
import tree_topics as T  # noqa: E402


def line(module: str, *name) -> str:
    return json.dumps({"m": module, "n": list(name)})


LINES = [
    line("Tengoku.Seed.Algebra.Group.Basic", "Group", "mul_one"),
    line("Tengoku.Seed.Algebra.Ring.Defs", "Ring", "zero_mul"),
    line("Tengoku.Seed.Analysis.Normed.Basic", "norm_nonneg"),
    line("Tengoku.Seed", "root_thm"),
    line("Tengoku.AddCombi.AddCombi.Mathlib.Algebra", "Finset", "card_add_le"),
    line("Tengoku.AddCombi.AddCombi.Main", "AddCombi", "plunnecke"),
    line("Tengoku.Tauceti.TauCeti.Algebra", "Foo", "_private", 3, "bar"),
    "",
]


class Topics(unittest.TestCase):
    def test_a_seed_theorem_goes_to_its_area_and_any_other_to_its_library(self):
        t = T.build(LINES)
        self.assertEqual(
            t,
            {
                "Intake/AddCombi": ["AddCombi.plunnecke", "Finset.card_add_le"],
                "Intake/Tauceti": ["Foo._private.3.bar"],  # a numeric component is its digits, as the export's reader writes it
                "Seed/Algebra": ["Group.mul_one", "Ring.zero_mul"],
                "Seed/Analysis": ["norm_nonneg"],
                "Seed/Misc": ["root_thm"],  # a module of the seed with no area below it
            },
        )

    def test_the_depth_of_the_seed_areas_is_a_parameter(self):
        t = T.build(LINES, seed_depth=2)
        self.assertEqual(
            sorted(k for k in t if k.startswith("Seed/")), ["Seed/Algebra/Group", "Seed/Algebra/Ring", "Seed/Analysis/Normed", "Seed/Misc"]
        )
        self.assertEqual(T.build(LINES, seed_depth=3)["Seed/Algebra/Group/Basic"], ["Group.mul_one"])

    def test_the_names_of_a_topic_are_sorted_and_the_topics_too(self):
        t = T.build(LINES)
        self.assertEqual(list(t), sorted(t))
        self.assertTrue(all(v == sorted(v) for v in t.values()))

    def test_a_module_outside_the_root_is_refused(self):
        with self.assertRaises(SystemExit):
            T.build([line("Other.Mod", "x")])

    def test_the_topics_make_a_tree_for_the_planner(self):
        import layers as L  # the planner reads a topic name with slashes as a place in a tree

        paths = {t: L.topic_path(t) for t in T.build(LINES)}
        self.assertEqual(paths["Seed/Algebra"], ("Seed", "Algebra"))
        self.assertEqual(paths["Intake/Tauceti"], ("Intake", "Tauceti"))


class Command(unittest.TestCase):
    def test_main_writes_the_topics_and_the_sample_and_says_how_many(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "m.jsonl").write_text("\n".join(LINES), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(T.main([str(d / "m.jsonl"), "--out", str(d / "t.json"), "--sample-out", str(d / "s.jsonl")]), 0)
            topics = json.loads((d / "t.json").read_text(encoding="utf-8"))
            sample = [json.loads(ln) for ln in (d / "s.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sum(len(v) for v in topics.values()), len(sample))
        self.assertEqual({"name": "Group.mul_one", "library": "Seed/Algebra"} in sample, True)
        self.assertIn("5 topics (3 in the seed, 2 libraries), 7 theorems (4 in the seed)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
