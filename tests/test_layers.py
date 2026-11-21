"""tools/promote/layers.py: which layer of a promotion each constant belongs to, from the dependency closures of an export (synthetic exports in the format of lean4export 3.1)."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "promote"))
sys.path.insert(0, str(ROOT / "tests"))
import layers as L  # noqa: E402
from test_closure import Builder  # noqa: E402


def two_topics() -> Builder:
    """T and base are used by everything; `shared` by both topics; `only_a` by alpha alone"""
    b = Builder()
    b.decl("axiom", "T", b.sort())
    t = b.const("T")
    b.decl("axiom", "base", t)
    b.decl("thm", "shared", t, b.const("base"))
    b.decl("thm", "only_a", t, b.const("base"))
    b.decl("thm", "A1", t, b.app(b.const("shared"), b.const("only_a")))
    b.decl("thm", "B1", t, b.const("shared"))
    return b


def run(b: Builder, topics: dict, added: list | None = None, **kw) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "e.ndjson"
        b.write(p)
        ex = L.Full()
        ex.read(p)
        universe = None if added is None else {tuple(n.split(".")) for n in added}
        return L.plan(ex, topics, universe, **kw)


def names(p: dict, module: str) -> list[str]:
    return [".".join(str(c) for c in n) for n in p["names"][module]]


class Planning(unittest.TestCase):
    def test_a_constant_two_topics_need_is_in_the_foundation_and_one_topic_needs_is_in_its_layer(self):
        p = run(two_topics(), {"alpha": ["A1"], "beta": ["B1"]})
        self.assertEqual(names(p, "TengaiData.Foundation"), ["T", "base", "shared"])
        self.assertEqual(names(p, "TengaiData.Topic.Alpha"), ["A1", "only_a"])
        self.assertEqual(names(p, "TengaiData.Topic.Beta"), ["B1"])
        self.assertEqual(
            [x["module"] for x in p["layers"]], ["TengaiData.Foundation", "TengaiData.Topic.Alpha", "TengaiData.Topic.Beta"]
        )  # the order they must be replayed in
        self.assertEqual([x["imports"] for x in p["layers"]], [[], ["TengaiData.Foundation"], ["TengaiData.Foundation"]])

    def test_what_a_session_loads_is_the_foundation_and_its_own_layer(self):
        p = run(two_topics(), {"alpha": ["A1"], "beta": ["B1"]})
        self.assertEqual(
            p["topics"]["alpha"],
            {"module": "TengaiData.Topic.Alpha", "theorems": 1, "own_units": 2, "foundation_units_used": 3, "units_loaded": 5},
        )
        self.assertEqual(p["topics"]["beta"]["units_loaded"], 4)  # B1 and what it reaches: shared, base, T
        self.assertEqual(p["totals"], {"units": 6, "foundation_units": 3, "constants": 6})

    def test_one_topic_has_no_foundation(self):
        p = run(two_topics(), {"only": ["A1", "B1"]})
        self.assertEqual([x["module"] for x in p["layers"]], ["TengaiData.Topic.Only"])
        self.assertEqual(p["layers"][0]["imports"], [])
        self.assertEqual(p["totals"]["foundation_units"], 0)

    def test_a_theorem_another_topic_needs_is_in_the_foundation(self):
        p = run(two_topics(), {"alpha": ["A1", "shared"], "beta": ["B1"]})  # alpha names `shared` as its own theorem; beta needs it too
        self.assertIn("shared", names(p, "TengaiData.Foundation"))
        self.assertNotIn("shared", names(p, "TengaiData.Topic.Alpha"))

    def test_a_constant_the_core_holds_is_left_to_the_core(self):
        p = run(
            two_topics(), {"alpha": ["A1"], "beta": ["B1"]}, added=["base", "shared", "only_a", "A1", "B1"]
        )  # T is not in the list of what a replay added
        self.assertEqual(names(p, "TengaiData.Foundation"), ["base", "shared"])
        self.assertEqual(p["totals"]["units"], 5)

    def test_an_inductive_type_with_its_constructors_and_recursor_is_one_unit_with_the_union_of_their_users(self):
        b = two_topics()
        nat = b.name("Foo")
        mk, rec = b.name("Foo.mk"), b.name("Foo.rec")
        ty = b.const("T")
        b.lines.append(
            {
                "inductive": {
                    "types": [{"name": nat, "levelParams": [], "type": ty, "numParams": 0, "numIndices": 0, "all": [nat], "ctors": [mk]}],
                    "ctors": [{"name": mk, "levelParams": [], "type": ty, "induct": nat, "cidx": 0, "numParams": 0, "numFields": 0}],
                    "recs": [
                        {
                            "name": rec,
                            "levelParams": [],
                            "type": ty,
                            "all": [nat],
                            "numParams": 0,
                            "numIndices": 0,
                            "numMotives": 1,
                            "numMinors": 1,
                            "rules": [{"ctor": mk, "nfields": 0, "rhs": ty}],
                        }
                    ],
                }
            }
        )
        b.decl("thm", "uses_rec", ty, b.const("Foo.rec"))  # alpha reaches the recursor
        b.decl("thm", "uses_type", ty, b.const("Foo"))  # beta reaches only the type
        p = run(b, {"alpha": ["uses_rec"], "beta": ["uses_type"]})
        self.assertEqual(
            names(p, "TengaiData.Foundation"), ["Foo", "T"]
        )  # one unit, named by its first type; it holds Foo.mk and Foo.rec as well
        self.assertEqual(p["totals"]["constants"], 6)  # T, the three constants of Foo, the two theorems: counted by constant, not by unit
        self.assertEqual(p["totals"]["units"], 4)

    def test_a_theorem_that_is_not_in_the_export_is_refused(self):
        with self.assertRaises(SystemExit) as c:
            run(two_topics(), {"alpha": ["A1", "nothing_of_that_name"]})
        self.assertIn("not in the export", str(c.exception))

    def test_topics_that_make_the_same_module_name_are_refused(self):
        with self.assertRaises(SystemExit):
            run(two_topics(), {"a-b": ["A1"], "a_b": ["B1"]})
        with self.assertRaises(SystemExit):
            run(two_topics(), {"1abc": ["A1"]})

    def test_a_topic_called_foundation_is_a_topic_and_not_the_foundation(self):
        # Tengoku has a library called `foundation`: topic layers live under `Topic.`, so it cannot take the foundation's module name
        p = run(two_topics(), {"foundation": ["A1"], "b": ["B1"]})
        self.assertEqual([x["module"] for x in p["layers"]], ["TengaiData.Foundation", "TengaiData.Topic.Foundation", "TengaiData.Topic.B"])
        self.assertEqual(p["layers"][1]["imports"], ["TengaiData.Foundation"])

    def test_the_plan_is_deterministic(self):
        a = run(two_topics(), {"alpha": ["A1"], "beta": ["B1"]})
        b = run(two_topics(), {"alpha": ["A1"], "beta": ["B1"]})
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_three_topics_use_the_foundation_for_anything_two_of_them_share(self):
        b = two_topics()
        b.decl("thm", "C1", b.const("T"), b.const("only_a"))  # gamma reaches only_a too: alpha and gamma share it
        p = run(b, {"alpha": ["A1"], "beta": ["B1"], "gamma": ["C1"]})
        self.assertIn("only_a", names(p, "TengaiData.Foundation"))
        self.assertEqual(names(p, "TengaiData.Topic.Gamma"), ["C1"])

    def test_the_foundation_never_depends_on_a_topic_layer(self):
        p = run(two_topics(), {"alpha": ["A1"], "beta": ["B1"]})
        foundation = set(names(p, "TengaiData.Foundation"))
        self.assertEqual(foundation & set(names(p, "TengaiData.Topic.Alpha")), set())
        self.assertNotIn("only_a", foundation)  # only_a is alpha's, and nothing in the foundation reaches it


class Names(unittest.TestCase):
    def test_a_numeric_component_stays_a_number(self):
        lines = [
            {"meta": {"format": {"version": "3.1.0"}}},
            {"in": 1, "str": {"pre": 0, "str": "foo"}},
            {"in": 2, "num": {"pre": 1, "i": 7}},
            {"in": 3, "str": {"pre": 2, "str": "bar"}},
        ]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "e.ndjson"
            p.write_text("".join(json.dumps(o) + "\n" for o in lines))
            ex = L.Full()
            ex.read(p)
        self.assertEqual(ex.components(3), ["foo", 7, "bar"])

    def test_a_topic_becomes_one_module_component(self):
        self.assertEqual(
            [L.module_component(x) for x in ("equational-theories", "aintlib", "ben-27-formalization", "x_y")],
            ["EquationalTheories", "Aintlib", "Ben27Formalization", "XY"],
        )


class CommandLine(unittest.TestCase):
    def test_files_in_and_out(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d)
            two_topics().write(t / "e.ndjson")
            (t / "topics.json").write_text(json.dumps({"alpha": ["A1"], "beta": ["B1"]}))
            self.assertEqual(L.main([str(t / "e.ndjson"), "--topics", str(t / "topics.json"), "--out", str(t / "out")]), 0)
            plan = json.loads((t / "out" / "layers.json").read_text())
            self.assertEqual(
                [x["file"] for x in plan["layers"]],
                ["TengaiData.Foundation.names.jsonl", "TengaiData.Topic.Alpha.names.jsonl", "TengaiData.Topic.Beta.names.jsonl"],
            )
            self.assertEqual((t / "out" / "TengaiData.Topic.Beta.names.jsonl").read_text(), '["B1"]\n')
            self.assertEqual(
                (t / "out" / "TengaiData.Foundation.names.jsonl").read_text().splitlines(), ['["T"]', '["base"]', '["shared"]']
            )


if __name__ == "__main__":
    unittest.main()
